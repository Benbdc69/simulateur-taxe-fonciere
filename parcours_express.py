"""Parcours grand public : adresse, catégorie, 5 surfaces 6660-REV, année.
Moteur RVLLP hérité de V13.1. Les montants incomplets ne sont jamais présentés
comme une cotisation définitive. Les données publiques sont synchronisées à la demande.
"""
from __future__ import annotations
from contextlib import nullcontext
import json
import os
from datetime import datetime
import streamlit as st
from saisie_adresse import saisir_adresse
from session_calcul import bouton_nouveau_calcul, cle_calcul
from cadastre import adresses, parcelles_a_l_adresse
from recherche_bien import saisir_reference, identifier_par_reference, libelle_parcelle, saisir_commune
from moteur import (COEFF_SURFACES, TAXES, TAXES_AVANT_2021, insee_cadastral_adresse,
                    nom_commune_cadastrale, secteur_automatique,
                    localisation_automatique, neutralisation_avec_teom_reference,
                    neutralisation_automatique, tarif_automatique, estimation)
from historique_taux import resoudre, resoudre_tout
from actualiser import BASE
from mise_a_jour_simple import (ouvrir_referentiel as lire_ref, synchroniser_dgfip, synchroniser_taux,
                               synchroniser_taux_historiques)
from export_pdf import creer_pdf_estimation
from saisie_declaration import afficher_declaration
from frais_gestion import afficher_frais
from montants import euro_arrondi
from mesure_cadastrale import afficher_mesures
from exoneration_neuf import exon_neuf_non_habitation
from planchonnement_saisie import montant_facultatif, preparer_planchonnement, valider_corrections
from reforme_2017 import reconstituer_reforme
from guide_categories import afficher_guide_categories, libelle_categorie
from vue_rue import afficher_lien_street_view, afficher_street_view_adresse, url_street_view
from saisie_preaudit import actions_preaudit

def euro(val):
    return f'{float(val):,.2f}'.replace(',', ' ').replace('.', ',') + ' €'



def pct(val):
    return f'{float(val):,.2f}'.replace(',', ' ').replace('.', ',') + ' %'


def normaliser_identite(parcelle, adresse, ref):
    code = str(parcelle.get('insee') or adresse.get('insee') or '')
    code = insee_cadastral_adresse(code, adresse.get('code_postal', ''))
    dep = str(parcelle.get('departement') or code[:2])
    commune = nom_commune_cadastrale(ref, dep, code, adresse.get('commune', ''))
    return {'code_insee': code, 'departement': dep, 'commune': commune,
            'prefixe': str(parcelle.get('prefixe') or ''),
            'section': str(parcelle.get('section') or ''),
            'numero': str(parcelle.get('numero') or '')}


def calculer_dossier(ref, ref_initial, bien, categorie, surfaces, annee, construction_nouvelle=False,
                    annee_achevement=None, historique="inconnu", corrections_planchonnement=None,
                    *, base_2016=None, localisation_2017=None, avec_replis=True, total_sans_ventilation=False):
    """Calcule l’estimation et le planchonnement à partir de la base 2016."""
    exo = exon_neuf_non_habitation(annee, annee_achevement, construction_nouvelle)
    reconstitution = historique == 'ancien' and base_2016 is not None and 2017 <= annee <= 2026
    taxes = TAXES_AVANT_2021 if reconstitution and annee < 2021 else TAXES
    dep, com, code = bien['departement'], bien['commune'], bien['code_insee']
    sect, sec_message = secteur_automatique(ref, dep, com, bien['prefixe'], bien['section'], code)
    loc, loc_message, loc_year = localisation_automatique(
        ref, dep, annee, com, bien['prefixe'], bien['section'], bien['numero'], code)
    tarif = tarif_automatique(ref, dep, annee, categorie, sect)
    neutral, neutral_message, neutral_warnings = neutralisation_avec_teom_reference(
        ref, ref_initial, dep, com, annee, code, bien['prefixe'])
    rates = resoudre_tout(ref, code, annee)
    if reconstitution and annee < 2021:
        rates = {cle: resoudre(ref, code, annee, cle, repli=False) for cle in taxes}
        neutral, neutral_message = neutralisation_automatique(
            ref, dep, com, annee, code, bien['prefixe'], taxes=taxes)
        # Une part dont le taux est explicitement nul ne requiert pas de base taxable.
        taxes = {cle: label for cle, label in taxes.items()
                 if not rates[cle] or rates[cle]['taux'] != 0 or (neutral or {}).get(cle)}
    missing = []
    if sect is None: missing.append('secteur d’évaluation')
    if tarif is None: missing.append('tarif de la catégorie / secteur / année')
    coeffs = {}
    taux = {}
    for key, label in taxes.items():
        coeffs[key] = neutral.get(key) if neutral else None
        taux[key] = rates.get(key, {}).get('taux') if rates.get(key) else None
        if coeffs[key] is None: missing.append('neutralisation : ' + label)
        if taux[key] is None: missing.append('taux : ' + label)
    weighted = sum(float(surfaces.get(k,0)) * w for k,w in COEFF_SURFACES.items())
    result = None
    reforme = None
    corrections = corrections_planchonnement or {}
    if reconstitution:
        reforme = reconstituer_reforme(
            ref, bien, categorie, weighted, annee, base_2016, taux, corrections,
            localisation_2017=localisation_2017, coefficients_actuels=coeffs, avec_replis=avec_replis)
        planch = preparer_planchonnement(annee, historique, reforme['corrections'], taxes=taxes)
        planch['complet'] = not reforme['planchonnement_manquant']
        reserves = list(reforme['hypotheses'])
        if reforme['planchonnement_manquant']:
            reserves.append('Planchonnement non calculé pour ' + ', '.join(reforme['planchonnement_manquant']) + '.')
        if reforme['parametres_manquants']:
            reserves.append('Données historiques manquantes · ' + ', '.join(reforme['parametres_manquants']) + '.')
        planch['reserve'] = ' '.join(reserves) or None
        if annee == 2017:
            loc, loc_message = reforme['localisation_2017'], reforme['message_localisation']
    else:
        planch = preparer_planchonnement(annee, historique, corrections)
    if loc is None: missing.append('coefficient de localisation')
    partial = {'surface_ponderee': weighted, 'secteur': sect, 'tarif': tarif, 'localisation': loc,
               'valeur_locative_brute': weighted * tarif * loc if tarif is not None and loc is not None else None}
    if total_sans_ventilation:
        partial['valeur_locative_brute'] = None
        missing.append('ventilation des surfaces bâties en P1/P2')
    elif weighted <= 0:
        missing.append('surface du local')
    if not missing:
        result = estimation(surfaces, tarif, loc, coeffs, taux, abattements=exo['taux'],
                            planchonnements=planch['corrections'], taxes=taxes)
    return {'result':result,'partial':partial,'missing':missing,'taux':rates,'exoneration_neuf':exo,'planchonnement':planch,
            'neutralisations':neutral,'neutral_warnings':neutral_warnings, 'reforme_2017':reforme,
            'messages':{'secteur':sec_message,'localisation':loc_message,
                        'neutralisation':neutral_message,'localisation_annee':loc_year}}


def actualiser_si_necessaire(annee, bien, *, valeurs=True, taux=True, taux_historiques=False):
    """Synchronisation discrète une fois par session et territoire / année.
    Ne met jamais à zéro une donnée existante si la source n'est pas joignable.
    """
    cle=(int(annee),bien['departement'],bien['code_insee'],valeurs,taux,taux_historiques)
    st.session_state.setdefault('_synch_effectuees',{})
    done=st.session_state['_synch_effectuees']
    if cle in done:
        return done[cle]
    erreurs=[]
    if valeurs:
        try:
            b=synchroniser_dgfip(annee,bien['departement'])
            erreurs.extend(b.get('echecs',[]))
        except Exception as exc:
            erreurs.append('Sources de valeurs locatives indisponibles : '+str(exc))
    if taux:
        try:
            synchroniser = synchroniser_taux_historiques if taux_historiques else synchroniser_taux
            b=synchroniser(annee,bien['code_insee'])
            erreurs.extend(b.get('incidents',[]))
        except Exception as exc:
            erreurs.append('Sources de taux indisponibles : '+str(exc))
    if not erreurs:
        done[cle] = []
    return erreurs




def finaliser(candidat, categorie, surfaces, annee, construction_nouvelle=False, annee_achevement=None,
              historique="inconnu", corrections_planchonnement=None, *, base_2016=None,
              localisation_2017=None, mesures=None):
    adresse_result, parcelle = candidat
    ref = lire_ref()
    bien = normaliser_identite(parcelle, adresse_result, ref)
    initial = json.loads(BASE.read_text(encoding='utf-8'))
    total_sans_ventilation = bool((mesures or {}).get('surface_batie')) and not (surfaces.get('P1') or surfaces.get('P2'))
    with st.spinner('Calcul à partir des barèmes et taux disponibles…'):
        def calculer(ref_actif, *, avec_replis=False):
            return calculer_dossier(ref_actif, initial, bien, categorie, surfaces, annee,
                                   construction_nouvelle, annee_achevement, historique,
                                   corrections_planchonnement, base_2016=base_2016,
                                   localisation_2017=localisation_2017, avec_replis=avec_replis,
                                   total_sans_ventilation=total_sans_ventilation)

        res = calculer(ref)
        issues, actualise = [], False
        if not res['result'] or any(t and t['annee_source'] < annee for t in res['taux'].values()):
            issues = actualiser_si_necessaire(annee, bien, taux_historiques=bool(res['reforme_2017']) and annee < 2021)
            ref, actualise = lire_ref(), True
            res = calculer(ref)
        reforme = res['reforme_2017']
        if reforme and (reforme['parametres_manquants'] or reforme['planchonnement_manquant']):
            if annee != 2017 or not actualise:
                issues.extend(actualiser_si_necessaire(2017, bien, taux=False))
                ref = lire_ref()
            res = calculer(ref, avec_replis=True)
    st.session_state['_calcul_express']={
        'bien':bien,'adresse':adresse_result['libelle'], 'adresse_declaree':adresse_result,
        'street_view': url_street_view(adresse_result, parcelle),
        'categorie':categorie,'annee':annee, 'construction_nouvelle':construction_nouvelle, 'annee_achevement':annee_achevement,
        'historique':historique,
        'surfaces':surfaces,'mesures':mesures or {},'analyse':res,'sync_incidents':issues}
    st.session_state.pop('_brouillon_preaudit', None)
    st.session_state.pop('_parcelles_attente',None)


st.markdown('''<style>
.block-container{max-width:980px;padding-top:2rem;padding-bottom:4rem}
section[data-testid="stSidebar"]{display:none}
/* Les boutons sont pilotés par primaryColor ; ce style sert de filet de sécurité
   si le thème n'a pas encore été rechargé sur le serveur. */
div.stButton > button[kind="primary"],div.stFormSubmitButton > button[kind="primary"]{background:#246A9D!important;border-color:#246A9D!important;color:#FFFFFF!important}
div.stButton > button[kind="primary"]:hover,div.stFormSubmitButton > button[kind="primary"]:hover{background:#164C79!important;border-color:#164C79!important}
</style>''',unsafe_allow_html=True)
bouton_nouveau_calcul()
def afficher_saisie():
    st.title('Estimez votre taxe foncière')
    st.caption('Locaux professionnels · Déclaration 6660-REV · Informations fiscales récupérées automatiquement')

    ref = lire_ref()
    cat_map={c['code']:c for c in ref.get('categories',[])}
    if not cat_map:
        st.error('Le référentiel des catégories fiscales est indisponible.')
        st.stop()
    cat_codes=list(cat_map)

    importation = st.session_state.get('_cerfa_importe', {})
    importe = importation.get('modele') == '6660-rev'
    initial = st.session_state.get('_saisie_cerfa_pro', {}) if importe else {}
    a_verifier = importation.get('a_verifier', []) if importe else []
    if importe:
        st.success('Déclaration 6660-REV importée. Confirmez les données reprises et choisissez l’année d’imposition.')
        if a_verifier:
            st.warning('À vérifier ou compléter · ' + ', '.join(a_verifier))
    else:
        st.info('Préparez votre déclaration 6660-REV ou votre fiche d’évaluation cadastrale. Les surfaces se saisissent en m² réels : la pondération est automatique.')
    with st.container(border=True):
        st.markdown('#### 1 · Identifier votre local')
        mode_recherche = st.radio('Rechercher le bien par', ['Adresse', 'Parcelle cadastrale'], horizontal=True, key=cle_calcul('express_mode'))
        reference = {}
        adresse = ''
        adresse_selectionnee = None
        if mode_recherche == 'Adresse':
            adresse, adresse_selectionnee = saisir_adresse('Adresse complète du bien', cle_calcul('express_adresse'),
                                                            initial.get('recherche', ''), manuelle=importe)
            if initial.get('parcelle_declaree'):
                st.caption('Parcelle déclarée · ' + initial['parcelle_declaree'])
            afficher_street_view_adresse(adresse, adresse_selectionnee)
        else:
            reference_importee = initial.get('reference')
            automatique, selection_commune = saisir_commune(cle_calcul('express_ref'), reference_importee)
            reference = saisir_reference(cle_calcul('express_ref'), reference_importee, automatique=automatique, selection=selection_commune)
        categorie_declaree = initial.get('categorie')
        categorie=st.selectbox('Catégorie du local', cat_codes,key=cle_calcul('express_categorie'),
            index=cat_codes.index(categorie_declaree) if categorie_declaree in cat_map else None,
            placeholder='Sélectionnez la catégorie figurant sur votre document',
            format_func=lambda code: f'{code} — {libelle_categorie(code, cat_map)}',
            help='Reprenez le code fiscal de la déclaration 6660-REV ou de la fiche cadastrale (ex. BUR2).')
        if st.button('Consulter le guide des catégories', type='tertiary', key=cle_calcul('express_ouvrir_guide')):
            afficher_guide_categories(cat_map, categorie)
        st.markdown('#### 2 · Répartir les surfaces')
        section_surfaces = st.expander(
            'Vérifier les surfaces importées', expanded=any(champ.startswith('surface') for champ in a_verifier)
        ) if importe else nullcontext()
        with section_surfaces:
            mesures = afficher_mesures(mode_recherche, reference, adresse, adresse_selectionnee) or {}
            st.caption('Chaque surface doit apparaître une seule fois. Ne saisissez pas une surface déjà pondérée. Laissez 0 pour les rubriques qui ne concernent pas votre bien.')
            aides_surfaces={
                'P1':'Surface des parties principales utilisées pour l’activité. Reprenez la rubrique P1 de la déclaration, sans y ajouter les surfaces P2, P3 ou les parkings.',
                'P2':'Parties secondaires couvertes, de moindre utilité pour l’activité, selon votre déclaration (par exemple certaines réserves). Ne les comptez pas aussi en P1.',
                'P3':'Parties secondaires non couvertes rattachées au local, selon votre déclaration. Les stationnements sont à renseigner en PK1 ou PK2.',
                'PK1':'Surface des emplacements de stationnement couverts. Indiquez des m², et non le nombre de places.',
                'PK2':'Surface des emplacements de stationnement non couverts. Indiquez des m², et non le nombre de places.',
            }
            surfaces={}
            labels={'P1':'P1 · Principale','P2':'P2 · Secondaire couverte',
                    'P3':'P3 · Secondaire non couverte','PK1':'PK1 · Stationnement couvert',
                    'PK2':'PK2 · Stationnement non couvert'}
            cols=st.columns(3)
            for i,(k,v) in enumerate(labels.items()):
                with cols[i%3]:
                    surfaces[k]=st.number_input(v,min_value=0.0,max_value=1_000_000.0,step=1.0,value=float(initial.get('surfaces', {}).get(k, 0)),key=cle_calcul('express_'+k),help=aides_surfaces[k])
            with st.expander('Comment les surfaces sont-elles prises en compte ?'):
                st.write('Exemple : si votre déclaration indique 100 m² en P1 et 20 m² en P2, saisissez 100 et 20, sans réduire vous-même la surface secondaire.')
                st.write('Pondérations appliquées : '+', '.join(f'{k} × {v:g}' for k,v in COEFF_SURFACES.items())+'. Le classement de chaque surface reste celui de votre déclaration.')
                st.caption(f"Surface pondérée issue de votre saisie : {sum(surfaces[k]*v for k,v in COEFF_SURFACES.items()):,.2f} m²".replace(',', ' '))
        st.markdown('#### 3 · Préciser l’année et l’historique')
        st.caption('L’année est celle de l’avis que vous souhaitez estimer. Les informations historiques permettent de préciser les correctifs applicables.')
        annee=int(st.number_input('Année d’imposition',key=cle_calcul('express_annee'), min_value=2017, max_value=2026, value=2026, step=1, format='%d', help='Choisissez l’année d’imposition de l’avis, pas l’année de déclaration ou d’achat. Le moteur couvre 2017 à 2026 ; les règles à partir de 2027 ne sont pas encore intégrées.'))
        construction_nouvelle=st.checkbox('Construction nouvelle, reconstruction ou addition de construction (hors habitation)', value=initial.get('construction_nouvelle', False),key=cle_calcul('express_neuf'),
            help='Cochez uniquement pour une construction nouvelle, une reconstruction ou une addition de construction, pas pour un simple achat ou changement de locataire. Exonération temporaire de 40 % de la part communale et des taxes additionnelles éligibles (GEMAPI, TSE et syndicats sans fiscalité propre), sous conditions.')
        annee_achevement=None
        if construction_nouvelle:
            achevement_importe = initial.get('annee_achevement')
            achevement_initial = (achevement_importe if achevement_importe and achevement_importe <= annee else None) if importe else annee - 1
            annee_achevement=st.number_input('Année d’achèvement des travaux',key=cle_calcul('express_achevement'),min_value=1900,max_value=annee, value=achevement_initial,step=1,help='Année où les travaux permettent l’utilisation effective du bien. Ce n’est pas nécessairement l’année du permis, de l’achat ou de la déclaration fiscale.')
            st.caption('Sous réserve de déclaration dans les 90 jours : 40 % pour la commune, les syndicats sans fiscalité propre, la TSE et la GEMAPI ; pas pour l’EPCI à fiscalité propre ni la TEOM.')
        historique = st.selectbox(
            'Le local existait-il comme local professionnel au 1er janvier 2017 ?',key=cle_calcul('express_historique'),
            options=['inconnu', 'ancien', 'recent'],
            format_func=lambda v: {
                'inconnu': 'Je ne sais pas',
                'ancien': 'Oui, il existait avant 2017',
                'recent': 'Non, il a été créé depuis 2017',
            }[v],
            help='Répondez pour le local lui-même, indépendamment de sa date d’achat ou de création de votre société. En cas de doute, conservez « Je ne sais pas ». Nécessaire uniquement pour l’éventuel planchonnement de 2017 à 2026. Un changement de consistance ou d’affectation peut modifier le régime.',
        )
        corrections_brutes = {}
        base_brute = localisation_brute = ''
        if historique == 'ancien' and 2017 <= annee <= 2026:
            base_brute = st.text_input(
                'Base TFPB du local figurant sur l’avis 2016 (€)',
                key=cle_calcul('express_base_2016'), placeholder='Montant de la base en euros',
                help='Reprenez la base du local dans la colonne « Commune », déjà réduite de 50 %. '
                     'Si l’avis regroupe des biens ou si le local était exonéré, utilisez la base nette '
                     'propre au local figurant sur sa fiche cadastrale. Le calcul suppose que les '
                     'surfaces et le classement saisis correspondent à la situation de 2017.')
            st.caption('Ce montant suffit pour lancer le calcul automatique du planchonnement.')
            with st.expander('Corriger le calcul avec votre fiche cadastrale (facultatif)'):
                st.caption('Les montants justifiés saisis ici remplacent les corrections calculées.')
                if base_brute.strip():
                    localisation_brute = st.text_input(
                        'Coefficient de localisation de 2017', key=cle_calcul('express_loc_2017'),
                        placeholder='Si connu', help='Valeur relevée sur la fiche cadastrale pour 2017.')
                cols_plan = st.columns(2)
                plan_taxes = TAXES_AVANT_2021 if annee < 2021 and base_brute.strip() else TAXES
                for i,(cle,libelle) in enumerate(plan_taxes.items()):
                    with cols_plan[i % 2]:
                        corrections_brutes[cle] = st.text_input(libelle+' · correction de base (€)', value='', key=cle_calcul(f'plan_{cle}_{annee}'), placeholder='ex. -125,50', help='Montant signé de correction de base imposable pour cette taxe et cette année, justifié par votre fiche fiscale. Vide = inconnu ; 0 = correction nulle confirmée. Ce champ ne reçoit ni le montant de taxe payé ni un taux.')
        signature=json.dumps([mode_recherche,reference,adresse,adresse_selectionnee,categorie,surfaces,mesures,annee,construction_nouvelle,annee_achevement,historique,corrections_brutes,base_brute,localisation_brute],sort_keys=True)
        if st.session_state.get('_express_saisie') != signature:
            st.session_state.pop('_calcul_express',None)
            st.session_state.pop('_parcelles_attente',None)
            st.session_state['_express_saisie']=signature
        run=st.button('Calculer mon estimation',type='primary',use_container_width=True)
        st.caption('Le résultat détaillera les paramètres disponibles et les données manquantes. Une donnée absente ne sera pas remplacée par zéro.')

    if run:
        st.session_state.pop('_parcelles_attente',None)
        st.session_state.pop('_calcul_express',None)
        if mode_recherche == 'Adresse' and len(adresse.strip())<6:
            st.error('Indiquez une adresse complète pour localiser le bien.')
        elif categorie is None:
            st.error('Sélectionnez la catégorie fiscale figurant sur votre déclaration 6660-REV ou votre fiche cadastrale.')
        elif construction_nouvelle and annee_achevement is None:
            st.error('Renseignez l’année d’achèvement des travaux pour une construction nouvelle.')
        elif not any(surfaces.values()) and not mesures.get('surface_batie'):
            st.error('Renseignez au moins une surface.')
        else:
            try:
                corrections_validees = valider_corrections(corrections_brutes)
                base_2016 = montant_facultatif(base_brute, 'Base TFPB 2016')
                if base_2016 is not None and base_2016 < 0:
                    raise ValueError('La base TFPB 2016 doit être positive ou nulle.')
                localisation_2017 = montant_facultatif(localisation_brute, 'Coefficient de localisation 2017')
                if localisation_2017 is not None and not 0.5 <= localisation_2017 <= 1.5:
                    raise ValueError('Le coefficient de localisation 2017 doit être compris entre 0,5 et 1,5.')
                donnees_historiques = {
                    'base_2016': base_2016, 'localisation_2017': localisation_2017,
                }
            except ValueError as exc:
                st.error(str(exc))
                st.stop()
            with st.spinner('Recherche de la parcelle et des données fiscales…'):
                try:
                    if mode_recherche == 'Parcelle cadastrale':
                        trouves = identifier_par_reference(reference)
                        if not trouves:
                            st.error('Aucune parcelle trouvée. Vérifiez le code INSEE cadastral, le préfixe, la section et le numéro.')
                        else:
                            st.session_state['_parcelles_attente'] = {
                                'candidats': [(opt,opt['parcelle']) for opt in trouves],
                                'categorie':categorie,'surfaces':surfaces,'annee':annee,
                                'construction_nouvelle':construction_nouvelle,'annee_achevement':annee_achevement,
                                'historique':historique,'corrections_planchonnement':corrections_validees,
                                'donnees_historiques':donnees_historiques, 'mesures':mesures}
                    else:
                        options=[adresse_selectionnee] if adresse_selectionnee is not None else adresses(adresse)
                        if not options:
                            st.error('Adresse non trouvée : précisez le numéro, la voie et le code postal.')
                        else:
                            cand=[]
                            for opt in options[:3]:
                                try:
                                    parcels=parcelles_a_l_adresse(opt)
                                except Exception:
                                    parcels=[]
                                if parcels:
                                    cand=[(opt,p) for p in parcels[:12]]
                                    break
                            if not cand:
                                st.error('Aucune parcelle identifiable à cette adresse. Essayez une adresse plus précise.')
                            elif len(cand)==1 and cand[0][1].get('recherche')=='Point dans la parcelle' and not importe:
                                finaliser(cand[0], categorie, surfaces, annee, construction_nouvelle,
                                          annee_achevement, historique, corrections_validees,
                                          mesures=mesures, **donnees_historiques)
                                st.rerun()
                            else:
                                st.session_state['_parcelles_attente']={
                                    'candidats':cand,'categorie':categorie,'surfaces':surfaces,'annee':annee,'construction_nouvelle':construction_nouvelle,'annee_achevement':annee_achevement,'historique':historique,'corrections_planchonnement':corrections_validees,
                                    'donnees_historiques':donnees_historiques, 'mesures':mesures}
                except Exception as exc:
                    st.error('Recherche cadastrale momentanément indisponible : '+str(exc))

    pending=st.session_state.get('_parcelles_attente')
    if pending:
        candidats=pending['candidats']
        with st.container(border=True):
            if len(candidats)>1:
                st.markdown('**Confirmez la parcelle correspondant au local**')
                selection=st.selectbox('Parcelle cadastrale',range(len(candidats)), index=None, placeholder='Sélectionnez la parcelle exacte',
                    format_func=lambda i: libelle_parcelle(candidats[i][1]),
                    help='Comparez la section et le numéro avec votre avis ou votre titre de propriété. La proximité du point d’adresse ne suffit pas à identifier juridiquement votre parcelle.')
            else:
                selection=0
                p=candidats[0][1]
                st.caption('Parcelle identifiée : '+libelle_parcelle(p))
            st.caption('Confirmez la référence cadastrale. La parcelle ne détermine pas à elle seule le local, sa catégorie ou ses surfaces.')
            if selection is not None and adresse_selectionnee is None:
                afficher_lien_street_view(url_street_view(*candidats[selection]))
            if st.button('Obtenir le résultat',type='primary',use_container_width=True,disabled=selection is None):
                try:
                    finaliser(candidats[selection],pending['categorie'],pending['surfaces'],pending['annee'],pending.get('construction_nouvelle',False),pending.get('annee_achevement'),pending.get('historique','inconnu'),pending.get('corrections_planchonnement',{}),
                              base_2016=pending.get('donnees_historiques', {}).get('base_2016'),
                              localisation_2017=pending.get('donnees_historiques', {}).get('localisation_2017'),
                              mesures=pending.get('mesures'))
                    st.rerun()
                except Exception as exc:
                    st.error('Le calcul n’a pas pu être finalisé : '+str(exc))


calcule = st.session_state.get('_calcul_express')
if not calcule:
    afficher_saisie()
else:
    # Les widgets de saisie sont masqués pendant la synthèse. Conserver leurs valeurs entre les deux écrans.
    for cle in st.session_state:
        if cle.startswith(('express_', 'plan_')) and not cle.endswith('_chercher_commune'):
            st.session_state[cle] = st.session_state[cle]
    st.title('Votre estimation')
    analyse=calcule['analyse']; result=analyse['result']; partial=analyse['partial']
    reforme = analyse.get('reforme_2017')
    st.caption(f"Local professionnel · {calcule['adresse']} · {calcule['annee']} · {calcule['categorie']}")
    bien = calcule['bien']
    st.caption(f"Parcelle {bien['section']} {bien['numero']} · {bien['commune']}")
    afficher_lien_street_view(calcule.get('street_view') or url_street_view(calcule.get('adresse_declaree')))
    st.button('Modifier mes informations', on_click=st.session_state.pop, args=('_calcul_express', None))
    synthese = st.container()
    rapport, declaration = st.columns(2)
    frais = None
    if result:
        frais = afficher_frais({ligne['cle']: ligne['montant'] for ligne in result['lignes']},
                               calcule['annee'], TAXES, euro, cle_calcul('frais_teom_express'))
    with synthese:
        if result:
            total = frais.get('total') if frais else None
            if total is not None:
                st.metric('Taxe foncière estimée, frais inclus', euro_arrondi(total))
                st.caption(f"Cotisations hors frais {euro(result['total_hors_frais'])} · Frais {euro(frais['frais'])}")
                if 'taxes_speciales' in frais['lignes']:
                    st.caption(f"Frais sur les taxes spéciales estimés à {frais['lignes']['taxes_speciales']['taux']} %.")
            else:
                st.metric('Taxe foncière estimée hors frais', euro_arrondi(result['total_hors_frais']))
        else:
            if partial['valeur_locative_brute'] is not None:
                st.metric('Valeur locative brute estimée', euro_arrondi(partial['valeur_locative_brute']))
            st.warning('Cotisations indisponibles. Données manquantes : '+', '.join(analyse['missing']))
        planch = analyse.get('planchonnement', {})
        if result and planch.get('applique'):
            st.caption('Planchonnement intégré à l’estimation.')
        if planch.get('reserve'):
            st.warning(planch['reserve'])
    actions_preaudit({**calcule, 'frais': frais})
    rapport.download_button(
        'Télécharger mon estimation en PDF',
        data=creer_pdf_estimation({**calcule, 'frais': frais}),
        file_name=f"estimation_taxe_fonciere_{calcule['annee']}_{bien['code_insee']}.pdf",
        mime='application/pdf',
        use_container_width=True,
        key='export_pdf_express',
    )
    with declaration:
        afficher_declaration('6660-rev', calcule)
    with st.expander('Détail des cotisations, du calcul et des sources'):
        if result:
            st.table([{'Taxe': ligne['taxe'], 'Base': euro(ligne['base_taxable']),
                       'Taux': pct(ligne['taux_pct']), 'Cotisation': euro(ligne['montant'])}
                      for ligne in result['lignes']])
        if reforme:
            st.markdown('**Calcul du planchonnement**')
            st.write(f"Base TFPB 2016 de {euro(reforme['base_2016'])} × 1,004 = ancienne base 2017 de "
                     f"{euro(reforme['base_ancienne_2017'])}.")
            if reforme['vl_revisee_2017'] is not None:
                st.write(f"Valeur locative révisée 2017 de {euro(reforme['vl_revisee_2017'])} "
                         f"pour un tarif de {euro(reforme['tarif_2017'])}/m² et un coefficient de "
                         f"localisation de {reforme['localisation_2017']:g}.")
            if planch['corrections']:
                st.caption('Correction de base = (ancienne base 2017 − base révisée neutralisée de 2017) ÷ 2.')
                bases = reforme.get('bases_neutralisees', {})
                st.table([
                    {'Taxe': TAXES_AVANT_2021[cle],
                     'Base révisée neutralisée 2017': euro(bases[cle]) if cle in bases else '—',
                     'Correction de base': euro(montant)}
                    for cle, montant in planch['corrections'].items()
                ])
            st.caption('Le calcul suppose que les surfaces et le classement saisis correspondent à 2017.')
            st.markdown('[Barèmes départementaux de la DGFiP](https://www.impots.gouv.fr/revision-des-valeurs-locatives)')
        exo = analyse.get('exoneration_neuf', {})
        if exo.get('active'):
            st.caption('Construction nouvelle : exonération de 40 % appliquée aux composantes éligibles.')
        elif exo.get('a_verifier'):
            st.caption('Construction nouvelle : régime antérieur à 2021 à vérifier selon l’année simulée.')
        stale = [f"{v['annee_source']} · {TAXES[k]}" for k, v in analyse['taux'].items()
                 if v and v.get('decalage', 0) > 0]
        if stale:
            st.caption('Taux antérieurs : '+', '.join(stale)+'.')
        if analyse['neutral_warnings']:
            st.caption('Certaines neutralisations historiques ont été reprises à titre provisoire.')
        st.caption(f"Surface pondérée : {partial['surface_ponderee']:g} m²")

        st.write({'Commune':calcule['bien']['commune'],'Code cadastral':calcule['bien']['code_insee'],
                  'Parcelle':calcule['bien']['section']+' '+calcule['bien']['numero'],
                  'Secteur':partial['secteur'],'Coefficient de localisation':partial['localisation'],
                  'Tarif €/m²':partial['tarif'],'Taux et années':analyse['taux'],
                  'Neutralisations':analyse['neutralisations']})
        if calcule['sync_incidents']:
            st.caption('Certaines sources n’ont pas répondu. Le référentiel précédent a été conservé.')
