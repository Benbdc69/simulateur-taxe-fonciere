"""Parcours grand public : adresse, catégorie, 5 surfaces 6660-REV, année.
Moteur RVLLP hérité de V13.1. Les montants incomplets ne sont jamais présentés
comme une cotisation définitive. Les données publiques sont synchronisées à la demande.
"""
from __future__ import annotations
import json
import os
from datetime import datetime
from pathlib import Path
import streamlit as st
from saisie_adresse import saisir_adresse
from session_calcul import bouton_nouveau_calcul, cle_calcul
from cadastre import adresses, parcelles_a_l_adresse
from recherche_bien import saisir_reference, identifier_par_reference, libelle_parcelle, saisir_commune
from moteur import (COEFF_SURFACES, TAXES, insee_cadastral_adresse,
                    nom_commune_cadastrale, secteur_automatique,
                    localisation_automatique, neutralisation_avec_teom_reference,
                    tarif_automatique, estimation)
from historique_taux import resoudre_tout
from mise_a_jour_simple import synchroniser_dgfip, synchroniser_taux
from export_pdf import creer_pdf_estimation
from saisie_declaration import afficher_declaration
from frais_gestion import afficher_frais
from montants import euro_arrondi
from mesure_cadastrale import afficher_mesures
from exoneration_neuf import exon_neuf_non_habitation
from planchonnement_saisie import preparer_planchonnement, valider_corrections

ROOT = Path(__file__).resolve().parent
BASE = ROOT / 'data' / 'referentiel_initial.json'
LOCAL = ROOT / 'data' / 'referentiel_local.json'


def lire_ref():
    source = LOCAL if LOCAL.exists() else BASE
    return json.loads(source.read_text(encoding='utf-8'))


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


def calculer_dossier(ref, ref_initial, bien, categorie, surfaces, annee, construction_nouvelle=False, annee_achevement=None, historique="inconnu", corrections_planchonnement=None):
    """L'unique point d'entrée métier du parcours simple (aucune duplication de calcul).

    Un 6660-REV ne contient pas l'ancienne VL 2017 ou les éventuelles
    exonérations. On produit donc une estimation de base *conditionnelle*.
    """
    exo = exon_neuf_non_habitation(annee, annee_achevement, construction_nouvelle)
    planch = preparer_planchonnement(annee, historique, corrections_planchonnement or {})
    dep, com, code = bien['departement'], bien['commune'], bien['code_insee']
    sect, sec_message = secteur_automatique(ref, dep, com, bien['prefixe'], bien['section'], code)
    loc, loc_message, loc_year = localisation_automatique(
        ref, dep, annee, com, bien['prefixe'], bien['section'], bien['numero'], code)
    tarif = tarif_automatique(ref, dep, annee, categorie, sect)
    neutral, neutral_message, neutral_warnings = neutralisation_avec_teom_reference(
        ref, ref_initial, dep, com, annee, code, bien['prefixe'])
    rates = resoudre_tout(ref, code, annee)
    missing = []
    if sect is None: missing.append('secteur d’évaluation')
    if loc is None: missing.append('coefficient de localisation')
    if tarif is None: missing.append('tarif de la catégorie / secteur / année')
    coeffs = {}
    taux = {}
    for key, label in TAXES.items():
        coeffs[key] = neutral.get(key) if neutral else None
        taux[key] = rates.get(key, {}).get('taux') if rates.get(key) else None
        if coeffs[key] is None: missing.append('neutralisation : ' + label)
        if taux[key] is None: missing.append('taux : ' + label)
    weighted = sum(float(surfaces.get(k,0)) * w for k,w in COEFF_SURFACES.items())
    partial = {'surface_ponderee': weighted, 'secteur': sect, 'tarif': tarif, 'localisation': loc,
               'valeur_locative_brute':weighted * float(tarif) * float(loc) if tarif is not None and loc is not None else None}
    result = None
    if weighted <= 0: missing.append('surface du local')
    if not missing:
        result = estimation(surfaces,tarif,loc,coeffs,taux,abattements=exo['taux'],planchonnements=planch['corrections'],frais_pct=0)
    return {'result':result,'partial':partial,'missing':missing,'taux':rates,'exoneration_neuf':exo,'planchonnement':planch,
            'neutralisations':neutral,'neutral_warnings':neutral_warnings,
            'messages':{'secteur':sec_message,'localisation':loc_message,
                        'neutralisation':neutral_message,'localisation_annee':loc_year}}


def actualiser_si_necessaire(annee, bien):
    """Synchronisation discrète une fois par session et territoire / année.
    Ne met jamais à zéro une donnée existante si la source n'est pas joignable.
    """
    cle=(int(annee),bien['departement'],bien['code_insee'])
    st.session_state.setdefault('_synch_effectuees',{})
    done=st.session_state['_synch_effectuees']
    if cle in done:
        return done[cle]
    erreurs=[]
    try:
        b=synchroniser_dgfip(annee,bien['departement'])
        erreurs.extend(b.get('echecs',[]))
    except Exception as exc:
        erreurs.append('Sources de valeurs locatives indisponibles : '+str(exc))
    try:
        b=synchroniser_taux(annee,bien['code_insee'])
        erreurs.extend(b.get('incidents',[]))
    except Exception as exc:
        erreurs.append('Sources de taux indisponibles : '+str(exc))
    done[cle]=erreurs
    return erreurs




def finaliser(candidat, categorie, surfaces, annee, construction_nouvelle=False, annee_achevement=None, historique="inconnu", corrections_planchonnement=None):
    adresse_result, parcelle = candidat
    bien=normaliser_identite(parcelle,adresse_result,lire_ref())
    with st.spinner('Calcul à partir des barèmes et taux disponibles…'):
        issues=actualiser_si_necessaire(annee,bien)
        res=calculer_dossier(lire_ref(),json.loads(BASE.read_text(encoding='utf-8')),
             bien,categorie,surfaces,annee,construction_nouvelle,annee_achevement,historique,corrections_planchonnement)
    st.session_state['_calcul_express']={
        'bien':bien,'adresse':adresse_result['libelle'], 'adresse_declaree':adresse_result,
        'categorie':categorie,'annee':annee, 'construction_nouvelle':construction_nouvelle, 'annee_achevement':annee_achevement,
        'historique':historique,
        'surfaces':surfaces,'analyse':res,'sync_incidents':issues}
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
st.title('Estimez votre taxe foncière')
st.caption('Locaux professionnels · Déclaration 6660-REV · Informations fiscales récupérées automatiquement')

ref = lire_ref()
cat_map={c['code']:c for c in ref.get('categories',[])}
if not cat_map:
    st.error('Le référentiel des catégories fiscales est indisponible.')
    st.stop()
cat_codes=list(cat_map)

st.info('Préparez votre déclaration 6660-REV ou votre fiche d’évaluation cadastrale. Les surfaces se saisissent en m² réels : la pondération est automatique.')
with st.container(border=True):
    st.markdown('#### 1 · Identifier votre local')
    mode_recherche = st.radio('Rechercher le bien par', ['Adresse', 'Parcelle cadastrale'], horizontal=True, key=cle_calcul('express_mode'))
    reference = {}
    adresse = ''
    adresse_selectionnee = None
    if mode_recherche == 'Adresse':
        adresse, adresse_selectionnee = saisir_adresse('Adresse complète du bien', cle_calcul('express_adresse'))
    else:
        automatique, selection_commune = saisir_commune(cle_calcul('express_ref'))
        reference = saisir_reference(cle_calcul('express_ref'), automatique=automatique, selection=selection_commune)
    categorie=st.selectbox('Catégorie du local', cat_codes,key=cle_calcul('express_categorie'),
        index=None, placeholder='Sélectionnez la catégorie figurant sur votre document',
        format_func=lambda code:f"{code} — {cat_map[code]['description']}",
        help='Reprenez le code fiscal de la déclaration 6660-REV ou de la fiche cadastrale (ex. BUR2). Il décrit la nature et l’utilisation du local ; ce n’est pas un code d’activité NAF.')
    st.caption('Catégorie inconnue ? Demandez la fiche d’évaluation au service des impôts fonciers. Choisir une catégorie au hasard peut modifier fortement le tarif.')
    st.markdown('#### 2 · Répartir les surfaces')
    afficher_mesures(mode_recherche, reference, adresse, adresse_selectionnee)
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
            surfaces[k]=st.number_input(v,min_value=0.0,max_value=1_000_000.0,step=1.0,key=cle_calcul('express_'+k),help=aides_surfaces[k])
    with st.expander('Comment les surfaces sont-elles prises en compte ?'):
        st.write('Exemple : si votre déclaration indique 100 m² en P1 et 20 m² en P2, saisissez 100 et 20, sans réduire vous-même la surface secondaire.')
        st.write('Pondérations appliquées : '+', '.join(f'{k} × {v:g}' for k,v in COEFF_SURFACES.items())+'. Le classement de chaque surface reste celui de votre déclaration.')
        st.caption(f"Surface pondérée issue de votre saisie : {sum(surfaces[k]*v for k,v in COEFF_SURFACES.items()):,.2f} m²".replace(',', ' '))
    st.markdown('#### 3 · Préciser l’année et l’historique')
    st.caption('L’année est celle de l’avis que vous souhaitez estimer. Les informations historiques permettent de préciser les correctifs applicables.')
    annee=int(st.number_input('Année d’imposition',key=cle_calcul('express_annee'), min_value=2017, max_value=2026, value=2026, step=1, format='%d', help='Choisissez l’année d’imposition de l’avis, pas l’année de déclaration ou d’achat. Le moteur couvre 2017 à 2026 ; les règles à partir de 2027 ne sont pas encore intégrées.'))
    construction_nouvelle=st.checkbox('Construction nouvelle, reconstruction ou addition de construction (hors habitation)', value=False,key=cle_calcul('express_neuf'),
        help='Cochez uniquement pour une construction nouvelle, une reconstruction ou une addition de construction, pas pour un simple achat ou changement de locataire. Exonération temporaire de 40 % de la part communale et des taxes additionnelles éligibles (GEMAPI, TSE et syndicats sans fiscalité propre), sous conditions.')
    annee_achevement=None
    if construction_nouvelle:
        annee_achevement=st.number_input('Année d’achèvement des travaux',key=cle_calcul('express_achevement'),min_value=1900,max_value=annee, value=max(1900,annee-1),step=1,help='Année où les travaux permettent l’utilisation effective du bien. Ce n’est pas nécessairement l’année du permis, de l’achat ou de la déclaration fiscale.')
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
    if historique == 'ancien' and 2017 <= annee <= 2026:
        with st.expander('Planchonnement : renseigner les corrections historiques si vous les connaissez'):
            st.caption('Facultatif. Saisissez les corrections SIGNÉES de base imposable (en euros, après déduction de 50 %), pour cette année et chaque taxe, à partir de références fiscales documentées. Une valeur négative diminue la base. Ne saisissez pas ici des coefficients de neutralisation ni des valeurs locatives brutes.')
            st.caption('Laisser vide signifie « inconnue » ; saisir 0 signifie « correction nulle confirmée ». Si des corrections manquent, le montant restera indicatif.')
            cols_plan = st.columns(2)
            for i,(cle,libelle) in enumerate(TAXES.items()):
                with cols_plan[i % 2]:
                    corrections_brutes[cle] = st.text_input(libelle+' · correction de base (€)', value='', key=cle_calcul('plan_'+cle), placeholder='ex. -125,50', help='Montant signé de correction de base imposable pour cette taxe et cette année, justifié par votre fiche fiscale. Vide = inconnu ; 0 = correction nulle confirmée. Ce champ ne reçoit ni le montant de taxe payé ni un taux.')
    signature=json.dumps([mode_recherche,reference,adresse,adresse_selectionnee,categorie,surfaces,annee,construction_nouvelle,annee_achevement,historique,corrections_brutes],sort_keys=True)
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
    elif not any(surfaces.values()):
        st.error('Renseignez au moins une surface.')
    else:
        try:
            corrections_validees = valider_corrections(corrections_brutes)
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
                            'historique':historique,'corrections_planchonnement':corrections_validees}
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
                        elif len(cand)==1 and cand[0][1].get('recherche')=='Point dans la parcelle':
                            finaliser(cand[0],categorie,surfaces,annee,construction_nouvelle,annee_achevement,historique,corrections_validees)
                        else:
                            st.session_state['_parcelles_attente']={
                                'candidats':cand,'categorie':categorie,'surfaces':surfaces,'annee':annee,'construction_nouvelle':construction_nouvelle,'annee_achevement':annee_achevement,'historique':historique,'corrections_planchonnement':corrections_validees}
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
        if st.button('Obtenir le résultat',type='primary',use_container_width=True,disabled=selection is None):
            try:
                finaliser(candidats[selection],pending['categorie'],pending['surfaces'],pending['annee'],pending.get('construction_nouvelle',False),pending.get('annee_achevement'),pending.get('historique','inconnu'),pending.get('corrections_planchonnement',{}))
                st.rerun()
            except Exception as exc:
                st.error('Le calcul n’a pas pu être finalisé : '+str(exc))

calcule=st.session_state.get('_calcul_express')
if calcule:
    analyse=calcule['analyse']; result=analyse['result']; partial=analyse['partial']
    st.divider()
    st.subheader('Votre estimation')
    st.caption(f"{calcule['adresse']} · {calcule['annee']} · {calcule['categorie']}")
    bien = calcule['bien']
    st.caption(f"Parcelle {bien['section']} {bien['numero']} · {bien['commune']}")
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
            else:
                st.metric('Taxe foncière estimée hors frais', euro_arrondi(result['total_estime']))
        else:
            if partial['valeur_locative_brute'] is not None:
                st.metric('Valeur locative brute estimée', euro_arrondi(partial['valeur_locative_brute']))
            st.warning('Cotisations indisponibles. Données manquantes : '+', '.join(analyse['missing']))
        planch = analyse.get('planchonnement', {})
        if planch.get('reserve'):
            st.warning(planch['reserve'])
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
        st.caption('Estimation sous réserve des régimes particuliers et du lissage éventuel jusqu’en 2025.')
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
