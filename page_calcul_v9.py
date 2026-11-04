"""Version locale sans connexion de calcul de taxe foncière sur locaux professionnels.
Lancer avec : streamlit run app.py --server.address 127.0.0.1
"""
from __future__ import annotations
import copy
import csv
import html
import io
import json
import hashlib
import os
from pathlib import Path
from datetime import datetime

import streamlit as st
from moteur import (COEFF_SURFACES, TAXES, norm, secteur_automatique,
                    localisation_automatique, neutralisation_avec_teom_reference,
                    tarif_automatique, estimation, regime_reforme,
                    nom_commune_cadastrale, insee_cadastral_adresse,
                    planchonnement_2017, lissage_2017_2025)
from imports_dgfip import (url_fichier, telecharger, importer, construire_source, PAGE,
                            apercu_fichier, _labels, _match_col)
from cadastre import adresses, parcelles_a_l_adresse, rechercher_parcelle
from referentiel import (DEPARTEMENTS, integrer_jeu, normaliser_departement,
                         publication_attendue, periode_neutralisation)
from actualiser import preparer_proposition
from taux_dgfip import rechercher_taux, SOURCE as SOURCE_TAUX
from historique_taux import (COMPOSANTES, LIBELLES, code_reference, enregistrer as sauver_taux,
                              supprimer as supprimer_taux, resoudre_tout, lignes_historique)
from collecte_taux import preparer as proposer_taux
from mise_a_jour_simple import synchroniser_dgfip, synchroniser_taux

HERE=Path(__file__).resolve().parent
BASE=HERE/'data'/'referentiel_initial.json'
LOCAL=HERE/'data'/'referentiel_local.json'
BACKUPS=HERE/'data'/'historique'
PENDING=HERE/'data'/'en_attente'/'proposition.json'

# Configuration centralisée par le routeur app.py
st.markdown('''<style>
.block-container{max-width:1290px;padding-top:1.4rem;padding-bottom:3rem}
header[data-testid="stHeader"]{background:transparent}
.hero{background:linear-gradient(115deg,#11263e,#244e68);color:white;padding:26px 30px;border-radius:18px;margin-bottom:18px}
.hero h1{color:white;font-size:2rem;letter-spacing:-0.04rem;margin:4px 0 9px}
.hero p{color:#d8e8f4;margin:0;font-size:.96rem}
.hero .eyebrow{color:#9dddcb;text-transform:uppercase;letter-spacing:.15em;font-size:.75rem;font-weight:700}
.smallnote{font-size:.8rem;color:#687485}
div[data-testid="stMetric"]{border:1px solid #dce3ec;border-radius:12px;padding:11px 15px}
</style>''',unsafe_allow_html=True)
st.markdown('''<div class="hero"><div class="eyebrow">Estimation • Interface simplifiée, calcul V9</div>
<h1>Estimation de taxe foncière</h1><p>Locaux professionnels · Valeur locative révisée · Référentiel fiscal versionné · Parcelles cadastrales</p></div>''',unsafe_allow_html=True)


def base_ref():
    file=LOCAL if LOCAL.exists() else BASE
    with open(file,encoding='utf-8') as f:return json.load(f)


def sauver_ref(ref):
    BACKUPS.mkdir(exist_ok=True)
    if LOCAL.exists():
        stamp=datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        (BACKUPS/f'referentiel-{stamp}.json').write_bytes(LOCAL.read_bytes())
    tmp=LOCAL.with_suffix('.tmp')
    tmp.write_text(json.dumps(ref,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    os.replace(tmp,LOCAL)


# Toujours relire le référentiel actif, même si celui-ci a été actualisé depuis
# une autre session ou copié depuis un ancien dossier. Évite le cache obsolète.
st.session_state.ref=base_ref()
REF=st.session_state.ref

EXEMPLE={
 'adresse':'Exemple fictif sans adresse cadastrale', 'departement':'42',
 'commune_saisie':'', 'code_insee':'', 'prefixe':'', 'section':'', 'numero':'', 'annee':2025,
 'categorie':'BUR2', 'p1':100.0, 'p2':20.0, 'p3':0.0, 'pk1':10.0, 'pk2':0.0,
 'achevement':'2017 ou après', 'annee_achevement':2020,
 'taux_ok':False, 'frais_pct':0.0, 'forcer_secteur':False, 'forcer_loc':False,
}
EXEMPLE_TAUX={'commune':0.0,'syndicat':0.0,'epci':0.0,'taxes_speciales':0.0,'teom':0.0,'gemapi':0.0}
EXEMPLE_ABATTEMENTS={'commune':0.0,'syndicat':0.0,'epci':0.0,'taxes_speciales':0.0,'teom':0.0,'gemapi':0.0}


def exemple():
    for k,v in EXEMPLE.items():st.session_state[k]=v
    st.session_state[f'taux_ok_{EXEMPLE["departement"]}_{norm(EXEMPLE["commune_saisie"])}_{EXEMPLE["annee"]}']=False
    for k in TAXES:
        st.session_state[f'taux_{EXEMPLE["departement"]}_{norm(EXEMPLE["commune_saisie"])}_{EXEMPLE["annee"]}_{k}']=EXEMPLE_TAUX[k]
        st.session_state[f'abattement_{EXEMPLE["departement"]}_{norm(EXEMPLE["commune_saisie"])}_{EXEMPLE["annee"]}_{k}']=EXEMPLE_ABATTEMENTS[k]
        st.session_state['planchonnement_'+k]=0.0
    signature='|'.join([EXEMPLE['departement'],EXEMPLE['code_insee'],EXEMPLE['prefixe'],
                        EXEMPLE['section'],EXEMPLE['numero'],EXEMPLE['categorie']])
    id_bien=hashlib.sha256(signature.encode('utf8')).hexdigest()[:12]
    st.session_state['annee_achevement_'+id_bien]=EXEMPLE['annee_achevement']
    st.session_state['achevement_'+id_bien]=EXEMPLE['achevement']
    st.session_state['manual_secteur']=4
    st.session_state['manual_loc']=1.0


def reinitialiser():
    for k in list(EXEMPLE)+['manual_secteur','manual_loc','type_changement','planch_mode','planch_valide','planch_source','lissage_mode','lissage_valide','lissage_source','lissage_pas','lissage_avis','lissage_avant','lissage_apres','annee_effet_changement','variation_surface']:
        st.session_state.pop(k,None)
    for k in TAXES:
        for pre in ('taux_','abattement_','planchonnement_','vl_ancienne_2017_','vl_revisee_2017_'):
            st.session_state.pop(pre+k,None)
    for k in list(st.session_state):
        if any(k.startswith(prefix) for prefix in (
             'achevement_', 'annee_achevement_', 'type_changement_', 'planch_mode_',
             'planch_valide_', 'planch_source_', 'lissage_mode_', 'lissage_valide_',
             'lissage_source_', 'lissage_pas_', 'lissage_avis_', 'lissage_avant_',
             'lissage_apres_', 'planchonnement_', 'vl_ancienne_2017_',
             'vl_revisee_2017_', 'annee_effet_changement_', 'variation_surface_',
             'taux_ok_', 'taux_', '_auto_last_taux_', 'abattement_', 'neut_')):
            st.session_state.pop(k,None)
    for k in ['resultat','adresse_results','parcelle_results','recherche_adresse','recherche_parcelle_directe','selected_address','taux_dgfip_info','taux_propositions','gestion_proposition_taux']:
        st.session_state.pop(k,None)


def euro(v,digits=2):
    return f'{float(v):,.{digits}f}'.replace(',',' ').replace('.',',')+' €'


def sq(v):
    return f'{float(v):,.2f}'.replace(',',' ').replace('.',',')+' m²'


def confirmer_territoire(p):
    adr=st.session_state.get('selected_address') or {}
    code_postal=str(adr.get('code_postal') or '')
    c=insee_cadastral_adresse(p.get('insee',''),code_postal)
    dept=str(p.get('departement') or c[:2])
    if dept in DEPARTEMENTS:
        st.session_state['departement']=dept
    commune = nom_commune_cadastrale(REF,dept,c,p.get('commune',''))
    # Les grilles DGFiP utilisent LYON 7EME (INSEE 69387),
    # tandis que le géocodeur d'adresses peut simplement répondre LYON (69123).
    code = str(c)[-3:]
    rows = [r for r in REF.get('secteurs',{}).get(dept,[])
            if str(r.get('code_commune') or '').zfill(3) == code]
    names = {r.get('commune') for r in rows if r.get('commune')}
    if len(names) == 1:
        commune = next(iter(names))
    if commune:
        st.session_state['commune_saisie']=commune
    if c:
        st.session_state['code_insee']=c
    st.session_state['section']=p.get('section','')
    st.session_state['numero']=p.get('numero','')
    st.session_state['prefixe']=p.get('prefixe','')


st.caption('Une adresse, une parcelle, les surfaces : les taux et les neutralisations proviennent du référentiel actif.')

main, importer_tab, taux_tab, doc_tab=st.tabs(['Estimation','Mise à jour DGFiP','Historique des taux','Référentiels'])

with main:
    a,b=st.columns([1,1])
    with a:
        st.button('Charger un exemple fictif',on_click=exemple,use_container_width=True)
    with b:
        st.button('Nouvelle simulation vierge',on_click=reinitialiser,use_container_width=True)
    st.caption('Référentiel initial : données historiques reprises du fichier fourni ; exemple de saisie fictif. Les nouveaux départements et millésimes doivent être synchronisés depuis la DGFiP.')
    st.subheader('1. Identifier le local')
    c1,c2=st.columns([3,1])
    with c1:
        adresse=st.text_input('Adresse complète',key='adresse',placeholder='Ex. 18 cours Gambetta, 69007 Lyon')
    with c2:
        annee=st.selectbox('Année d’imposition',tuple(range(2026,2016,-1)),key='annee',index=0)
    if st.button('Rechercher la parcelle cadastrale',type='primary',use_container_width=True,key='adresse_cadastre_auto'):
        st.session_state.pop('parcelle_results',None)
        st.session_state.pop('adresse_results',None)
        st.session_state.pop('selected_address',None)
        try:
            suggestions=adresses(adresse)
            st.session_state['adresse_results']=suggestions
            if suggestions:
                st.session_state['selected_address']=suggestions[0]
                st.session_state['parcelle_results']=parcelles_a_l_adresse(suggestions[0],rayon_m=50)
            else:
                st.warning('Adresse non reconnue. Précisez le numéro de voie et le code postal.')
        except Exception as ex:
            st.error('La recherche cadastrale a échoué : '+str(ex))
    parcelles=st.session_state.get('parcelle_results') or []
    if parcelles:
        p_idx=st.selectbox('Parcelle trouvée — sélectionnez la bonne référence',range(len(parcelles)),
            format_func=lambda i:(f"{parcelles[i]['insee']} · section {parcelles[i]['section']} · parcelle {parcelles[i]['numero']}"
                    +f" · préfixe {parcelles[i].get('prefixe') or '000'}"),key='parcelle_idx')
        if st.button('Utiliser cette parcelle',on_click=confirmer_territoire,args=(parcelles[p_idx],),key='utiliser_parcelle_auto'):
            st.success('Parcelle utilisée dans le calcul.')
    elif 'parcelle_results' in st.session_state:
        st.warning('Aucune parcelle trouvée. Vous pouvez saisir la référence dans les informations cadastrales ci-dessous.')
    # Ces champs sont facultatifs. Leur absence ne doit jamais empêcher
    # l'affichage du calcul ou la génération des rapports JSON/HTML.
    bat = ent = niv = porte = ''
    with st.expander('Informations cadastrales — vérifier ou saisir manuellement',expanded=False):
        c1,c2,c3=st.columns([2,1,1])
        with c1:commune=st.text_input('Commune (nom cadastral)',key='commune_saisie')
        with c2:departement=st.selectbox('Département',DEPARTEMENTS,key='departement')
        with c3:code_insee=st.text_input('Code INSEE cadastral',key='code_insee')
        c1,c2,c3=st.columns(3)
        with c1:prefixe=st.text_input('Préfixe',key='prefixe')
        with c2:section=st.text_input('Section',key='section')
        with c3:numero=st.text_input('N° de parcelle',key='numero')
        if st.checkbox('Vérifier cette référence cadastrale auprès de l’IGN',value=False,key='vérifier_référence_manuelle'):
            if st.button('Lancer la vérification cadastrale',key='recherche_cadastrale_directe'):
                try:
                    r=rechercher_parcelle(code_insee,section,numero,prefixe)
                    if r:
                        st.success('Référence confirmée : les champs cadastraux sont déjà pris en compte.')
                    else:
                        st.warning('Référence non confirmée par le cadastre public.')
                except Exception as e:st.warning('Cadastre indisponible : '+str(e))
        if st.checkbox('Préciser bâtiment, entrée, niveau et porte',value=False,key='details_batiment'):
            i1,i2,i3,i4=st.columns(4)
            with i1:bat=st.text_input('Bâtiment',key='batiment')
            with i2:ent=st.text_input('Entrée',key='entree')
            with i3:niv=st.text_input('Niveau',key='niveau')
            with i4:porte=st.text_input('Porte',key='porte')
    # Récupération des valeurs actuelles après validation de la parcelle.
    commune=st.session_state.get('commune_saisie','')
    departement=st.session_state.get('departement','69')
    code_insee=st.session_state.get('code_insee','')
    prefixe=st.session_state.get('prefixe','')
    section=st.session_state.get('section','')
    numero=st.session_state.get('numero','')
    if section and numero and commune:
        st.caption(f"Parcelle retenue : {commune} · {section} {numero} · code cadastral {code_insee}")
    if st.button(f'Actualiser les données fiscales {annee} du département {departement}',
                 use_container_width=True,key='maj_annuelle_un_clic'):
        with st.spinner('Mise à jour des publications DGFiP et des taux publics…'):
            messages=[]
            try:
                bilan=synchroniser_dgfip(annee,departement)
                messages.append(f"Barèmes : {bilan.get('changements',0)} source(s) actualisée(s).")
                if bilan.get('echecs'):
                    messages.append('Certaines sources DGFiP sont indisponibles ; valeurs déjà enregistrées conservées.')
            except Exception as e:
                messages.append('Actualisation des barèmes non aboutie : '+str(e))
            if code_insee:
                try:
                    compte=synchroniser_taux(annee,code_insee)
                    messages.append(f"Taux : {len(compte['ajoutes'])} nouvelle(s) valeur(s), "
                                    f"{len(compte['deja_presents'])} déjà enregistrée(s).")
                    if compte['incidents']:
                        messages.append('Certaines sources de taux n’ont pas répondu. Les derniers taux connus sont conservés.')
                except Exception as e:
                    messages.append('Actualisation des taux non aboutie : '+str(e))
            else:
                messages.append('Sélectionnez une parcelle pour récupérer les taux communaux.')
            st.session_state.ref=base_ref()
            for k in list(st.session_state):
                if k.startswith(('taux_','_auto_last_taux_','neut_','resultat')):
                    st.session_state.pop(k,None)
            st.session_state['maj_bilan_simple']=messages
            st.rerun()
    if st.session_state.get('maj_bilan_simple'):
        for msg in st.session_state.pop('maj_bilan_simple'):st.caption(msg)

    st.subheader('2. Évaluer le local')
    categorie_labels={x['code']:x['description'] for x in REF.get('categories',[])}
    codes=sorted(categorie_labels)
    if not codes:st.stop()
    if st.session_state.get('categorie') not in codes:
        st.session_state['categorie']=codes[0]
    categorie=st.selectbox('Catégorie fiscale du local',codes,
                           format_func=lambda x:f'{x} — {categorie_labels[x]}',key='categorie')
    ca,cb=st.columns(2)
    secteur_auto, secteur_msg=secteur_automatique(REF,departement,commune,prefixe,section,code_insee)
    loc_auto, loc_msg, loc_year=localisation_automatique(REF,departement,annee,commune,prefixe,section,numero,code_insee)
    with ca:
        st.write('**Secteur d’évaluation**')
        st.caption(f'Automatique : {secteur_auto if secteur_auto is not None else "indisponible"}. {secteur_msg}')
        st.checkbox('Renseigner le secteur manuellement',key='forcer_secteur')
        if st.session_state.get('forcer_secteur',False) or secteur_auto is None:
            secteur=st.number_input('Secteur manuel',min_value=1,max_value=15,value=4,step=1,key='manual_secteur')
            manuel_secteur=True
        else:secteur=secteur_auto;manuel_secteur=False
    with cb:
        st.write('**Coefficient de localisation**')
        st.caption(f'Automatique : {loc_auto if loc_auto is not None else "indisponible"}. {loc_msg}')
        st.checkbox('Renseigner le coefficient manuellement',key='forcer_loc')
        if st.session_state.get('forcer_loc',False) or loc_auto is None:
            loc=st.number_input('Coefficient manuel',min_value=0.1,max_value=2.0,step=0.05,format='%.3f',value=1.0,key='manual_loc')
            manuel_loc=True
        else:loc=loc_auto;manuel_loc=False
    tarif=tarif_automatique(REF,departement,annee,categorie,secteur)
    source_tarif=REF.get('sources',{}).get(f'{departement}/tarifs/{annee}',{})
    if tarif is None:
        st.error(f'Tarif {annee} introuvable pour {departement} / {categorie} / secteur {secteur}. Importer le fichier DGFiP officiel dans l’onglet 02.')
        tarif_manu=st.number_input('Saisie manuelle provisoire du tarif officiel (€/m²)',0.0,10000.0,0.0,step=0.10)
        tarif=tarif_manu if tarif_manu>0 else None
        tarif_manuel=tarif is not None
    else:
        st.info(f'Tarif retenu : **{euro(tarif)}/m²** · Source : {source_tarif.get("origine","référentiel")} · Millésime {annee}.')
        tarif_manuel=False
    st.markdown('**Surfaces et pondérations**')
    col_p=st.columns(5)
    surfaces={}
    for k, col in zip(COEFF_SURFACES,col_p):
        with col:
            val=st.number_input(f'{k} · {COEFF_SURFACES[k]:.1f}'.replace('.',','),min_value=0.0,
                                max_value=1000000.0,step=1.0,key=k.lower())
            surfaces[k]=val
    surface_ponderee=sum(surfaces[k]*v for k,v in COEFF_SURFACES.items())
    st.caption('Surface pondérée : **'+sq(surface_ponderee)+'** · Pondérations identiques à celles du classeur (P1 1 ; P2 0,5 ; P3 0,2 ; PK1 0,5 ; PK2 0,2).')

    st.subheader('3. Calculer les impositions')
    # Les corrections historiques et leur validation ne doivent jamais fuiter
    # d'un bien à un autre ; le lissage d'avis est aussi propre au millésime.
    identite_fiscale='|'.join([departement,code_insee or norm(commune),prefixe,section,numero,categorie])
    bien_id=hashlib.sha256(identite_fiscale.encode('utf8')).hexdigest()[:12]
    bien_annee_id=f'{bien_id}_{annee}'
    annee_achevement=st.number_input('Année d’achèvement déclarée (à contrôler)',min_value=1800,max_value=2035,value=2020,step=1,key='annee_achevement_'+bien_id)
    statut_achevement=st.radio('Situation du local au 1er janvier 2017',
                               ('2017 ou après','Avant 2017 (local professionnel évalué en 2017)'),
                               horizontal=True,key='achevement_'+bien_id)
    ancien_local=statut_achevement.startswith('Avant')
    type_changement='aucun'; annee_effet=None; variation_surface=None
    if ancien_local:
        st.caption('Un local achevé avant 2017 ne conserve pas forcément les mécanismes : vérifier les changements intervenus depuis la réforme.')
        choix_changement=st.selectbox('Événements après le 1er janvier 2017',
           ('Situation inconnue','Aucun changement au sens de l’article 1406','Changement de consistance (surface)',
            'Changement d’affectation ou d’utilisation'),key='type_changement_'+bien_id)
        type_changement={
          'Aucun changement au sens de l’article 1406':'aucun',
          'Changement de consistance (surface)':'consistance',
          'Changement d’affectation ou d’utilisation':'affectation_utilisation',
          'Situation inconnue':'inconnu'}[choix_changement]
        if type_changement in ('consistance','affectation_utilisation'):
            annee_effet=st.number_input('Première année de prise en compte de ce changement dans les bases',
                                        min_value=2018,max_value=2026,value=2019,step=1,key='annee_effet_changement_'+bien_id)
            if type_changement=='consistance':
                variation_surface=st.number_input('Variation de la surface du local (%)',
                    min_value=0.0,max_value=1000.0,step=0.5,key='variation_surface_'+bien_id)
    try:
        regime=regime_reforme(annee,ancien_local,type_changement,annee_effet,variation_surface)
        erreur_regime=None
    except ValueError as ex:
        regime=None
        erreur_regime=str(ex)
        st.error('Situation à vérifier : '+erreur_regime)
    if regime is not None:
        st.info(('Planchonnement : **applicable sous réserve des données historiques**' if regime['planchonnement']
            else 'Planchonnement : **non applicable**')+' · '+
            ('Lissage 2017 : **applicable**' if regime['lissage'] else 'Lissage 2017 : **non applicable**')+
            '. '+regime['raison'])
    if annee==2026:
        st.caption('En 2026, le planchonnement de 2017 reste applicable aux locaux éligibles ; le lissage de cotisation initial est terminé.')
    coefficients,coeff_info,alertes_neutralisation=neutralisation_avec_teom_reference(
        REF,json.loads(BASE.read_text(encoding='utf-8')),
        departement,commune,annee,code_insee,prefixe)
    if alertes_neutralisation:
        st.caption('Certaines neutralisations historiques ont été reprises du référentiel initial et restent à confirmer.')
    if coefficients is None:
        st.warning(f'{coeff_info} Les coefficients de chaque taxe devront être saisis explicitement.')
    st.caption('La neutralisation, le planchonnement et l’éventuel lissage sont distincts. Les taux et exonérations restent à confirmer pour chaque année. Les fichiers DGFiP de neutralisation TF ne renseignent pas nécessairement la TEOM : si ce coefficient est absent, il doit être documenté séparément.')
    st.markdown('**Taux d’imposition : année N ou dernier millésime connu**')
    st.caption('Préremplissage individualisé par taxe : N si disponible, sinon N-1 ou le dernier taux plus ancien enregistré. Les taux antérieurs restent identifiés comme tels ; ils ne deviennent pas des taux de N. La TEOM peut être zonée.')
    taux_pub=None  # Une éventuelle consultation d'un taux global n'est jamais affectée à la part communale.
    taux_archive={}
    try:
        taux_archive=resoudre_tout(REF,code_insee,annee)
    except ValueError:
        st.info('Renseignez un code INSEE de commune valide pour utiliser le référentiel de taux.')
    historique_lignes=[]
    for key,label in TAXES.items():
        rec=taux_archive.get(key)
        cle=f'taux_{departement}_{norm(commune)}_{annee}_{key}'
        auto_tag='_auto_last_'+cle
        new_value=float(rec['taux']) if rec else 0.0
        if cle not in st.session_state:
            st.session_state[cle]=new_value
        elif auto_tag in st.session_state:
            old_auto=float(st.session_state[auto_tag])
            # Rafraîchit une valeur préremplie, sans effacer une retouche du collaborateur.
            if abs(float(st.session_state[cle])-old_auto)<1e-8:
                st.session_state[cle]=new_value
        st.session_state[auto_tag]=new_value
        historique_lignes.append({'Composante':label,'Taux connu (%)':None if rec is None else rec['taux'],
                                  'Millésime': 'Non connu' if rec is None else rec['annee_source'],
                                  'Situation':'À jour' if rec and rec['decalage']==0 else ('⚠ À actualiser' if rec else 'Non renseigné'),
                                  'Source':rec['source'] if rec else '—'})
    st.dataframe(historique_lignes,use_container_width=True,hide_index=True)
    anciennes=[LIBELLES[k]+f' : {v["annee_source"]} pour {annee}' for k,v in taux_archive.items()
              if v and v['decalage']>0]
    if anciennes:
        st.warning('**Taux repris d’années antérieures :** '+' ; '.join(anciennes)+'. Une vérification est recommandée avant utilisation sur un dossier client.')
    if any(v is None for v in taux_archive.values()):
        st.info('Certaines composantes restent sans taux enregistré. Un taux zéro ne sera jamais supposé automatiquement : vous pouvez le confirmer manuellement dans « 03 · Taux annuels ».')
    if any(k=='teom' and v and not v.get('zonage_confirme') for k,v in taux_archive.items()):
        st.warning('Le taux TEOM doit être vérifié au niveau du bien : plusieurs zones de TEOM peuvent exister dans une même commune.')
    s1,s2=st.columns(2)
    with s1:
        if st.button('Rechercher les taux publics (N puis N-1)',key='rechercher_taux_annuels',use_container_width=True):
            try:
                st.session_state['taux_propositions']=proposer_taux(code_insee,annee)
            except Exception as exc:
                st.error('Recherche impossible : '+str(exc))
    with s2:
        if st.button('Réappliquer les taux enregistrés à la simulation',key='recharger_taux_annuels',use_container_width=True):
            for key,val in taux_archive.items():
                t_key=f'taux_{departement}_{norm(commune)}_{annee}_{key}'
                st.session_state[t_key]=float(val['taux']) if val else 0.0
                st.session_state['_auto_last_'+t_key]=st.session_state[t_key]
            st.session_state[f'taux_ok_{departement}_{norm(commune)}_{annee}']=False
            st.rerun()
    proposition_taux=st.session_state.get('taux_propositions')
    try:
        proposition_valide=bool(proposition_taux and proposition_taux.get('code_insee')==code_reference(code_insee)
                                and proposition_taux.get('annee_imposition')==annee)
    except ValueError:
        proposition_valide=False
    if not proposition_valide:proposition_taux=None
    if proposition_taux:
        found=proposition_taux['propositions']
        if found:
            st.markdown('**Taux récupérés — à enregistrer après contrôle**')
            st.caption('Pour Lyon 7e, les taux de commune sont recherchés sous le code fiscal 69123, et non le code cadastral 69387. Les autres parts 2025 sont proposées avec une alerte pour 2026.')
            st.dataframe([{'Composante':LIBELLES[k], 'Taux (%)':v['taux'],
                           'Année réelle':v['annee'],'Source':v['source'],
                           'Statut':'⚠ Repli antérieur' if v['repli'] else 'Année N'}
                          for k,v in found.items()],hide_index=True,use_container_width=True)
            remplacer_pub=st.checkbox('Autoriser le remplacement de taux annuels déjà enregistrés après comparaison des sources',key='remplacer_taux_annuels')
            if st.button('Enregistrer ces taux dans leur année réelle',key='confirmer_taux_annuels',use_container_width=True):
                copied=copy.deepcopy(REF);modifies=[];erreurs=[]
                for k,v in found.items():
                    try:
                        saved=sauver_taux(copied,code_insee,v['annee'],k,v['taux'],v['source'],
                           url=v['url'],detail=v.get('detail',''),remplacer=remplacer_pub)
                        if saved:modifies.append(k+' '+str(v['annee']))
                    except ValueError as ex:erreurs.append(k+' : '+str(ex))
                if modifies:
                    sauver_ref(copied);st.session_state.ref=copied
                    # Recharger seulement les composantes trouvées pour ne pas écraser les saisies étrangères.
                    newval=resoudre_tout(copied,code_insee,annee)
                    for key,record in newval.items():
                        if record:
                            t_key=f'taux_{departement}_{norm(commune)}_{annee}_{key}'
                            st.session_state[t_key]=float(record['taux'])
                            st.session_state['_auto_last_'+t_key]=float(record['taux'])
                    st.session_state[f'taux_ok_{departement}_{norm(commune)}_{annee}']=False
                if erreurs:st.warning('Non enregistrés : '+' ; '.join(erreurs))
                if modifies:st.success('Enregistrés : '+', '.join(modifies));st.rerun()
        else:
            st.warning('Aucun taux détaillé exploitable n’a été trouvé. Vous pouvez renseigner le millésime dans « 03 · Taux annuels ».')
        if proposition_taux['incidents']:
            with st.expander('Sources indisponibles ou points à contrôler'):
                st.write(proposition_taux['incidents'])
        if found and 'commune' not in found:
            st.error('Taux communal absent des réponses : ouvrez les « Sources indisponibles ou points à contrôler ». Si la DGCL ne répond pas, saisissez temporairement le taux confirmé via « 03 · Taux annuels ».')
    st.caption('Sources : [DGCL — taux votés communes / EPCI](https://www.collectivites-locales.gouv.fr/etudes-et-statistiques/acces-aux-statistiques-par-thematique/fiscalite/taux-de-fiscalite-directe-locale-votes-par-les-collectivites) et [DGFiP — détail TFPB 2025](https://data.economie.gouv.fr/explore/dataset/fiscalite-locale-des-particuliers-geo/). Une valeur globale TFPB n’est jamais affectée à une part isolée.')
    st.markdown('**Paramètres par taxe**')
    heads=st.columns([2.4,1.05,1.05,1.05])
    for col,label in zip(heads,['Imposition','Neutralisation','Abattement (%)','Taux (%)']):
        col.markdown(f'**{label}**')
    neut_values={}; taux_values={}; abat_values={}; plan_values={k:0.0 for k in TAXES}
    neut_source_key=(f'{departement}/neutralisations/' + ('2017' if annee<=2020 else '2021'))
    neut_source_sha=REF.get('sources',{}).get(neut_source_key,{}).get('sha256','historique')[:12]
    for key,label in TAXES.items():
        cols=st.columns([2.4,1.05,1.05,1.05])
        with cols[0]:st.write(label)
        value_neut=(coefficients or {}).get(key)
        with cols[1]:
            neu=st.number_input(f'Neutralisation {label}',min_value=0.0,max_value=2.0,
                                value=float(value_neut or 0),step=0.0001,format='%.6f',
                                key=f'neut_{departement}_{norm(commune)}_{annee}_{neut_source_sha}_{key}',label_visibility='collapsed')
            neut_values[key]=neu if neu>0 else None
        with cols[2]:abat_values[key]=st.number_input(f'Abattement {label}',min_value=0.0,max_value=100.0,
                                                      step=1.0,key=f'abattement_{departement}_{norm(commune)}_{annee}_{key}',label_visibility='collapsed')
        with cols[3]:taux_values[key]=st.number_input(f'Taux {label}',min_value=0.0,max_value=100.0,
                                                      step=0.01,key=f'taux_{departement}_{norm(commune)}_{annee}_{key}',label_visibility='collapsed')

    if taux_pub and 'tfb_global' in taux_pub.get('taux',{}):
        total_tfb=sum(taux_values[k] for k in ('commune','syndicat','epci','taxes_speciales','gemapi'))
        t_global=taux_pub['taux']['tfb_global']
        if abs(total_tfb-t_global)>0.05:
            st.warning(f'Écart de contrôle : somme des taux de composantes = {total_tfb:.3f} %, taux global publié = {t_global:.3f} %. Vérifier notamment les taux, la territorialité et les taxes annexes avant simulation.')
        else:
            st.success(f'Contrôle de cohérence des taux TFPB : somme des composantes proche du taux global DGFiP ({t_global:.3f} %). Cela ne valide pas les autres paramètres.')

    st.markdown('**A. Planchonnement — correction de valeur locative historique de 2017**')
    plan_mode='Non applicable'; plan_documente=True; plan_source=''
    if regime is not None and regime['planchonnement']:
        plan_mode=st.radio('Source des correctifs historiques',
          ('À documenter (montant non calculable)',
           'Corrections de base connues (avis ou fiche historique)',
           'Calcul à partir des valeurs locatives historiques 2017'),
          key='planch_mode_'+bien_id)
        if plan_mode != 'À documenter (montant non calculable)':
            with st.expander('Saisir les valeurs par composante fiscale',expanded=True):
                if plan_mode.startswith('Corrections'):
                    st.caption('Saisir des corrections **déjà converties en base TF** (après la déduction de 50 % et avant abattement), avec leur signe. Ne pas ressaisir une correction exprimée en valeur locative.')
                    for key,label in TAXES.items():
                        plan_values[key]=st.number_input(label+' — correction historique de base (€)',
                            min_value=-1e8,max_value=1e8,step=10.0,format='%.2f',key='planchonnement_'+key+'_'+bien_id)
                else:
                    st.caption('Utiliser les deux valeurs **de 2017**, avant et après réforme/neutralisation, propres à chaque taxe. Correction de base = (VL ancienne 2017 − VL révisée neutralisée 2017) ÷ 4.')
                    for key,label in TAXES.items():
                        cols_h=st.columns([1.8,1.1,1.1,1.0])
                        cols_h[0].write(label)
                        old=cols_h[1].number_input('VL ancienne 2017 · '+label,min_value=0.0,
                             max_value=1e9,step=100.0,key='vl_ancienne_2017_'+key+'_'+bien_id)
                        new=cols_h[2].number_input('VL révisée neutralisée 2017 · '+label,min_value=0.0,
                             max_value=1e9,step=100.0,key='vl_revisee_2017_'+key+'_'+bien_id)
                        plan_values[key]=planchonnement_2017(old,new)['correction_base_tf']
                        cols_h[3].caption('Base : '+euro(plan_values[key]))
                plan_source=st.text_input('Référence du document historique (avis, calcul DGFiP, pièce du dossier)',key='planch_source_'+bien_id)
                plan_documente=st.checkbox('Je confirme avoir contrôlé les corrections et leur signe, y compris si le montant est nul.',key='planch_valide_'+bien_id)
        else:
            plan_documente=False
            st.warning('Le montant global ne sera pas calculé tant que les correctifs de planchonnement ne sont pas documentés.')
    else:
        st.caption('Pas de planchonnement historique pour ce local / cette année selon les indications saisies.')

    st.markdown('**B. Lissage de cotisation — régime 2017 à 2025 uniquement**')
    lissage_data=None; lissage_documente=True; lissage_source=''
    if regime is not None and regime['lissage']:
        lissage_mode=st.radio('Comment établir la correction signée de l’année ?',
            ('À documenter (cotisation non calculable)',
             'Comparer les deux cotisations de référence 2017',
             'Saisir le pas annuel de lissage (signé)',
             'Saisir le montant du lissage sur l’avis de cette année (signé)'),
            key='lissage_mode_'+bien_annee_id)
        try:
            if lissage_mode.startswith('Comparer'):
                c_old,c_new=st.columns(2)
                cot_old=c_old.number_input('Cotisation 2017 sans réforme (€), taxes annexes comprises',
                    min_value=0.0,max_value=1e9,step=100.0,key='lissage_avant_'+bien_annee_id)
                cot_new=c_new.number_input('Cotisation 2017 avec réforme (€), taxes annexes comprises',
                    min_value=0.0,max_value=1e9,step=100.0,key='lissage_apres_'+bien_annee_id)
                lissage_data=lissage_2017_2025(annee,cotisation_avant_reforme_2017=cot_old,
                                                 cotisation_apres_reforme_2017=cot_new)
            elif lissage_mode.startswith('Saisir le pas'):
                pas=st.number_input('Pas annuel 2017 (= [cotisation avec réforme − sans réforme] / 10), signé (€)',
                    min_value=-1e8,max_value=1e8,step=10.0,key='lissage_pas_'+bien_annee_id)
                lissage_data=lissage_2017_2025(annee,pas_annuel=pas)
            elif lissage_mode.startswith('Saisir le montant'):
                montant=st.number_input('Montant de lissage indiqué pour cette année, signé (€)',
                    min_value=-1e8,max_value=1e8,step=10.0,key='lissage_avis_'+bien_annee_id)
                lissage_data=lissage_2017_2025(annee,montant_avis=montant)
            else:
                lissage_documente=False
        except ValueError as ex:
            st.error('Lissage non calculable : '+str(ex));lissage_documente=False
        if lissage_data is not None:
            st.info('Correction de cotisation '+str(annee)+' : **'+euro(lissage_data['montant'])+'** · '+
                str(lissage_data['annees_restantes'])+' dixième(s) restant(s) jusqu’en 2025.')
            lissage_source=st.text_input('Source des données de lissage 2017 / avis fiscal',key='lissage_source_'+bien_annee_id)
            lissage_documente=st.checkbox('Je confirme les valeurs historiques et le signe du lissage.',key='lissage_valide_'+bien_annee_id)
    else:
        lissage_data=lissage_2017_2025(annee,eligible=False)
        st.caption('Aucun lissage initial n’est appliqué. En 2026, cette correction est obligatoirement nulle.')

    fra=st.columns([1,2])
    with fra[0]:frais_pct=st.number_input('Frais de gestion indicatifs (%)',min_value=0.0,max_value=20.0,step=0.1,key='frais_pct')
    taux_confirmation_key=f'taux_ok_{departement}_{norm(commune)}_{annee}'
    with fra[1]:st.checkbox('J’ai vérifié les taux, les exonérations et la situation fiscale de ce bien pour le millésime retenu.',key=taux_confirmation_key)
    warnings=[]
    if tarif_manuel:warnings.append('Tarif saisi manuellement, sans référence importée.')
    if manuel_secteur:warnings.append('Secteur saisi manuellement.')
    if manuel_loc:warnings.append('Localisation saisie manuellement.')
    if (source_tarif.get('origine')!='DGFiP') and not tarif_manuel:
        warnings.append('Tarifs provenant du classeur historique ; validation externe souhaitable.')
    if ancien_local and regime is not None and regime['planchonnement']:
        warnings.append('Planchonnement documenté à partir des valeurs historiques propres au local : vérifier la correspondance avec les avis fiscaux.')
    # Les taux N-1 sont utilisables à la demande, mais jamais sans alerte explicite.
    taux_provenances={}
    for k in TAXES:
        record=taux_archive.get(k)
        current=taux_values.get(k)
        if record is not None and abs(float(current)-float(record['taux']))<=1e-8:
            taux_provenances[k]=record
            if record['decalage']>0:
                warnings.append(f'Taux {LIBELLES[k]} {annee} : valeur {record["annee_source"]} réutilisée ({record["taux"]} %), actualisation nécessaire.')
            if k=='teom' and not record.get('zonage_confirme'):
                warnings.append('TEOM : zonage applicable à la parcelle non confirmé.')
        else:
            taux_provenances[k]={'taux':current,'annee_source':None,'source':'Saisie en cours / valeur non enregistrée',
                                 'statut':'À confirmer', 'composante':k}
            warnings.append(f'Taux {LIBELLES[k]} : valeur de simulation non rapprochée d’un millésime enregistré.')
    if not st.session_state.get(taux_confirmation_key,False):warnings.append('Taux et exonérations non confirmés.')
    if (annee_achevement<2017) != ancien_local:
        warnings.append('Incohérence entre année d’achèvement et situation déclarée vis-à-vis de la réforme 2017.')
    if any(v is None for v in neut_values.values()):warnings.append('Au moins un coefficient de neutralisation manque.')
    if not section or not numero:warnings.append('Référence cadastrale incomplète : vérifier manuellement le secteur et le coefficient de localisation.')
    if ancien_local and annee in (2023,2024):
        warnings.append('Imposition historique 2023–2024 : tenir compte des contentieux et de la décision QPC du 28 novembre 2025 sur le planchonnement.')
    if regime is not None and regime['lissage']:
        warnings.append('Lissage appliqué globalement à la cotisation TF et annexes, sans reconstitution de la ventilation administrative par collectivité.')
    if not plan_source and regime is not None and regime['planchonnement']:
        warnings.append('Source documentaire du planchonnement non renseignée.')
    if regime is not None and regime['lissage'] and not lissage_source:
        warnings.append('Source documentaire du lissage non renseignée.')

    st.divider()
    st.subheader('4. Résultat de l’estimation')
    try:
        if regime is None:
            raise ValueError(erreur_regime or 'Situation du local non qualifiée.')
        if not plan_documente:
            raise ValueError('Planchonnement historique non documenté : compléter et confirmer les correctifs avant de produire un total.')
        if not lissage_documente or lissage_data is None:
            raise ValueError('Lissage historique non documenté : renseigner les références 2017 ou le montant signé figurant sur l’avis.')
        if surface_ponderee <= 0:
            raise ValueError('La surface pondérée doit être strictement positive.')
        if not commune.strip():
            raise ValueError('La commune doit être renseignée.')
        if all(v == 0 for v in taux_values.values()):
            raise ValueError('Aucun taux d’imposition renseigné : impossible de produire une estimation chiffrée fiable.')
        result=estimation(surfaces,tarif,loc,neut_values,taux_values,abat_values,plan_values,frais_pct,correction_lissage=lissage_data['montant'])
    except (ValueError,TypeError) as ex:
        result=None
        st.warning('Calcul non disponible : '+str(ex))
    if result is not None:
        cols=st.columns(4)
        cols[0].metric('Surface pondérée',sq(result['surface_ponderee_totale']))
        cols[1].metric('Valeur locative brute',euro(result['valeur_locative_brute']))
        cols[2].metric('Assiette TF initiale (50 %)',euro(result['assiette_tf_avant_neutralisation']))
        cols[3].metric('**Total estimé**',euro(result['total_estime']))
        if warnings:
            st.warning('**Simulation indicative — contrôles à réaliser :** '+' • '.join(warnings))
        else:
            st.success('Toutes les données requises sont renseignées. Montant indicatif : contrôler avec un avis réel avant utilisation.')
        st.markdown('**Détail par composante**')
        st.dataframe([{'Taxe':v['taxe'],'Neutralisation':f"{v['coefficient_neutralisation']:.6f}",
                       'Base neutralisée':euro(v['base_neutralisee']),
                       'Planchonnement':euro(v['correction_planchonnement']),
                       'Abattement':f"{v['abattement_pct']:g} %",'Base taxable':euro(v['base_taxable']),
                       'Taux':f"{v['taux_pct']:g} %",'Montant':euro(v['montant'])} for v in result['lignes']],
                     use_container_width=True,hide_index=True)
        st.caption('Cotisations avant lissage : '+euro(result['total_avant_lissage'])+' · Correction de lissage : '+euro(result['correction_lissage'])+' · Total estimé : '+euro(result['total_estime']))
        report={'date_calcul':datetime.now().isoformat(),'type':'Estimation TFPB locaux professionnels',
                'adresse':adresse,'commune':commune,'insee':code_insee,'departement':departement,
                'prefixe':prefixe,'section':section,'parcelle':numero,'batiment':bat,'entree':ent,'niveau':niv,'porte':porte,'annee':annee,'annee_achevement':annee_achevement,
                'categorie':categorie,'secteur':secteur,'secteur_automatique':secteur_auto,
                'coefficient_localisation':loc,'annee_coefficient_localisation':loc_year,
                'surface':surfaces,'tarif':tarif,
                'dispositifs_reforme':{'eligibilite':regime,
                  'planchonnement':{'mode':plan_mode,'source':plan_source,'corrections_base':plan_values},
                  'lissage':{'source':lissage_source,'calcul':lissage_data}},
                'sources':{
                    'tarif':source_tarif,'localisation':REF.get('sources',{}).get(f'{departement}/localisations/{loc_year}',{}),
                    'secteur':REF.get('sources',{}).get(f'{departement}/secteurs/2017',{}),
                    'neutralisation':REF.get('sources',{}).get(neut_source_key,{}),
                    'taux_dgfip':taux_pub or {},'taux_effectifs':taux_provenances},
                'resultat':result,'avertissements':warnings}
        c1,c2=st.columns(2)
        with c1:
            st.download_button('Télécharger le rapport (JSON)',data=json.dumps(report,ensure_ascii=False,indent=2),
                               file_name='estimation_taxe_fonciere.json',mime='application/json',use_container_width=True)
        with c2:
            # Le rapport HTML se convertit en PDF par impression navigateur (contrôle humain).
            lines=''.join('<tr>'+''.join(f'<td>{html.escape(str(item))}</td>' for item in [x['taxe'],euro(x['base_taxable']),f"{x['taux_pct']:g} %",euro(x['montant'])])+'</tr>' for x in result['lignes'])
            warning_html=''.join(f'<li>{html.escape(w)}</li>' for w in warnings)
            trace_html=''.join('<tr><td>'+html.escape(LIBELLES[key])+'</td><td>'+html.escape(str(v.get('taux')))+'</td><td>'+html.escape(str(v.get('annee_source') or 'Non documentée'))+'</td><td>'+html.escape(str(v.get('source','—')))+'</td></tr>' for key,v in taux_provenances.items())
            doc=f'''<!doctype html><html lang="fr"><meta charset="utf-8"><title>Estimation taxe foncière</title>
<style>body{{font:15px Arial,sans-serif;max-width:860px;margin:50px auto;color:#152c44}}h1{{border-bottom:3px solid #267a8d;padding-bottom:15px}}table{{width:100%;border-collapse:collapse}}td,th{{padding:9px;border-bottom:1px solid #ddd;text-align:left}}th{{background:#edf4f6}}.total{{font-size:27px;font-weight:700}}.muted{{color:#667}}@media print{{body{{margin:12px}}}}</style>
<h1>Estimation de taxe foncière — locaux professionnels</h1><p><b>Bien :</b> {html.escape(adresse)} — {html.escape(commune)} ({html.escape(departement)})</p>
<p><b>Année :</b> {annee} · <b>Parcelle :</b> {html.escape(section)} {html.escape(numero)} · <b>Catégorie :</b> {html.escape(categorie)} · <b>Secteur :</b> {secteur}</p>
<p><b>Surface pondérée :</b> {sq(result['surface_ponderee_totale'])} · <b>Tarif :</b> {euro(tarif)}/m² · <b>Coefficient localisation :</b> {loc}</p>
<p><b>Valeur locative brute :</b> {euro(result['valeur_locative_brute'])} · <b>Base avant neutralisation :</b> {euro(result['assiette_tf_avant_neutralisation'])}</p>
<table><thead><tr><th>Taxe</th><th>Base taxable</th><th>Taux</th><th>Estimation</th></tr></thead><tbody>{lines}</tbody></table>
<p><b>Cotisations hors frais :</b> {euro(result['total_hors_frais'])} · <b>Frais indicatifs :</b> {euro(result['frais_gestion_estimes'])}</p>
<p><b>Planchonnement :</b> {html.escape(plan_mode)} · <b>Lissage signé :</b> {euro(result['correction_lissage'])}</p><p class="total">Total estimé : {euro(result['total_estime'])}</p>
<h3>Traçabilité des taux utilisés</h3><table><tr><th>Composante</th><th>Taux (%)</th><th>Année source</th><th>Source</th></tr>{trace_html}</table>
<h3>Points à contrôler</h3><ul>{warning_html or '<li>Aucun avertissement supplémentaire.</li>'}</ul>
<p class="muted">Document de simulation interne, non opposable à l'administration. Contrôler les sources, les taux, les abattements et les données historiques.</p></html>'''
            st.download_button('Télécharger le rapport imprimable (HTML / PDF)',data=doc,
                               file_name='rapport_estimation_tf.html',mime='text/html',use_container_width=True)

with importer_tab:
    st.subheader('Importer les publications officielles de la DGFiP')
    if PENDING.exists():
        try:
            proposition=json.loads(PENDING.read_text(encoding='utf8'))
            st.warning(f"Proposition de mise à jour détectée ({len(proposition.get('modifications',[]))} jeu(x) de données). Aucun barème n'a été écrasé automatiquement.")
            st.dataframe([{'Département':x['departement'],'Donnée':x['type'],
                           'Année':x['millesime'],'Lignes':x['nombre_lignes']}
                          for x in proposition['modifications']],hide_index=True,use_container_width=True)
            with st.expander('Incidents de téléchargement détectés'):
                st.write(proposition.get('echecs') or 'Aucun incident.')
            accepter=st.checkbox('J’ai effectué le contrôle de la publication et j’autorise l’activation de ces données.',key='accepter_proposition')
            valider,rejet=st.columns(2)
            if valider.button('Activer la mise à jour proposée',disabled=not accepter,use_container_width=True):
                active_file=LOCAL if LOCAL.exists() else BASE
                active_sha=hashlib.sha256(active_file.read_bytes()).hexdigest()
                if active_sha!=proposition['base_sha256']:
                    st.error('La base active a changé depuis la création de la proposition : relancer la vérification plutôt que d’écraser des données nouvelles.')
                else:
                    sauver_ref(proposition['referentiel']);st.session_state.ref=proposition['referentiel']
                    PENDING.unlink();st.success('Barèmes mis à jour et ancienne version archivée.')
                    st.rerun()
            if rejet.button('Rejeter la proposition',use_container_width=True):
                PENDING.unlink();st.info('Proposition écartée : le référentiel existant reste inchangé.')
                st.rerun()
        except Exception as ex:
            st.error('Proposition de mise à jour illisible : '+str(ex))
    st.markdown('Les fichiers sont publiés département par département. Cette application sait **télécharger les fichiers officiels par leur URL** et les **convertir en tableaux structurés**, mais elle ne valide pas seule leur applicabilité juridique. Les téléchargements sont tentés au moment où vous les déclenchez.')
    st.link_button('Voir les publications sur impots.gouv.fr',PAGE)
    d1,d2=st.columns([2,1])
    with d1:
        deps_import=st.multiselect('Départements à importer ou vérifier (un ou plusieurs)',
            DEPARTEMENTS,default=['42','43','69'],key='deps_import')
    with d2:
        year_import=st.number_input('Année d’imposition à préparer',min_value=2017,
            max_value=2026,value=2026,step=1,key='year_import')
    st.caption('Publications vérifiées : '+', '.join(f'{typ} {millesime}'
        for typ,millesime in publication_attendue(year_import,inclure_historique=True))+'. Les coefficients de neutralisation ne sont pas remplacés annuellement : on vérifie si la publication de référence a changé.')
    if st.button('Vérifier les publications DGFiP et préparer une mise à jour',
                 type='primary',use_container_width=True,disabled=not deps_import or PENDING.exists()):
        with st.spinner('Vérification des fichiers officiels sélectionnés…'):
            try:
                bilan=preparer_proposition(year_import,deps_import)
                if bilan['changements']:
                    st.success(f"{bilan['changements']} fichier(s) nouveau(x) dans une proposition de mise à jour. Rechargez l’onglet pour approuver.")
                else:
                    st.info('Aucune nouvelle donnée exploitable. '+str(bilan['identiques'])+' fichier(s) déjà identique(s).')
                if bilan['echecs']:
                    st.warning(str(len(bilan['echecs']))+' fichier(s) n’ont pas été vérifiés ou importés : aucune valeur n’a été remplacée pour ces fichiers.')
                    st.code('\n'.join(bilan['echecs'][:25]))
            except Exception as e:st.error('Synchronisation non terminée : '+str(e))
    st.caption('Le téléchargement dépend de l’accès réseau de votre Mac et des formats publiés par la DGFiP. Le référentiel n’est activé qu’après confirmation dans le panneau ci-dessus.')
    st.divider()
    st.markdown('**Import manuel d’un fichier téléchargé depuis la DGFiP**')
    m0,m1,m2=st.columns(3)
    with m0:dept_import=st.selectbox('Département du fichier',DEPARTEMENTS,key='dept_import')
    with m1:typ_man=st.selectbox('Nature du fichier',['tarifs','localisations','secteurs','neutralisations'],key='typ_man')
    with m2:year_man=st.selectbox('Publication / période (2017-2026)',tuple(range(2026,2016,-1)),key='year_man')
    uploaded=st.file_uploader('Sélectionner le XLSX (tarifs) ou ODS (autres données)',type=['xlsx','ods'])
    if uploaded:
        extension=uploaded.name.lower().split('.')[-1]
        expected_ext=('ods' if year_man<=2020 else 'xlsx') if typ_man=='tarifs' else 'ods'
        if extension!=expected_ext:
            st.error(f'Pour « {typ_man} », utiliser un fichier .{expected_ext}. La nature du fichier est-elle correctement sélectionnée ?')
        import re as _re
        m_dept=_re.search(r'-(\d{2}|2[ab]|97[1-6])\.(?:xlsx|ods)$', uploaded.name.lower())
        if m_dept and m_dept.group(1)!=dept_import.lower():
            st.error(f'Ce fichier semble concerner le département {m_dept.group(1)}, alors que vous avez sélectionné {dept_import}.')
        def _enregistrer(data,sha,nom):
            staged=copy.deepcopy(st.session_state.ref)
            version=(2017 if typ_man=='secteurs' else
                     (2021 if year_man>=2021 else 2020) if typ_man=='neutralisations' else
                     int(year_man))
            integrer_jeu(staged,dept_import,typ_man,version,data,
                         construire_source('import manuel : '+nom,sha,typ_man,version,len(data)))
            sauver_ref(staged);st.session_state.ref=staged
            st.success(f'{len(data)} entrées importées pour le département {dept_import}, millésime {version}. Ancienne base sauvegardée.')
            st.info('Comparer les coefficients et les calculs avec la publication officielle et un avis réel avant utilisation en cabinet.')

        wrong_format=extension!=expected_ext or bool(m_dept and m_dept.group(1)!=dept_import.lower())
        confirm=st.checkbox(f'Je confirme que ce fichier correspond à « {typ_man} », au département {dept_import} et au millésime indiqué.',key='confirmation_import_dgfip')
        if st.button('Importer et enregistrer ce fichier (détection automatique)',disabled=wrong_format or not confirm):
            try:
                data,sha=importer(uploaded.getvalue(),uploaded.name,typ_man)
                _enregistrer(data,sha,uploaded.name)
            except Exception as ex:
                st.error('Import automatique refusé : '+str(ex))
                st.info('Ouvrez « Import assisté » ci-dessous pour voir les colonnes réellement présentes et les associer aux données attendues.')

        with st.expander('Import assisté — voir les feuilles et associer les colonnes',expanded=False):
            st.caption('Utile si le fichier officiel répartit ses en-têtes sur plusieurs lignes ou utilise des intitulés différents. Il n’y a aucune modification tant que vous ne validez pas l’import.')
            try:
                previews=apercu_fichier(uploaded.getvalue(),uploaded.name,max_lignes=60)
                sheet=st.selectbox('Feuille à importer',[x['nom'] for x in previews],key='assist_feuille')
                preview=next(x for x in previews if x['nom']==sheet)
                rows=preview['lignes']
                hrow=st.number_input('Ligne contenant les intitulés des colonnes (aperçu ci-dessous)',min_value=1,
                    max_value=max(1,len(rows)),value=1,step=1,key='assist_entete')
                begin=st.number_input('Première ligne de données à importer',min_value=1,
                    max_value=max(1,preview['nombre_lignes']),value=min(hrow+1,max(1,preview['nombre_lignes'])),step=1,key='assist_debut')
                labels=_labels(rows,hrow-1,1)
                max_cols=min(22,max((len(r) for r in rows),default=0))
                example_rows=[]
                for i,r in enumerate(rows[:min(15,len(rows))]):
                    obj={'Ligne':i+1}
                    for j in range(max_cols):obj[chr(65+j)]=str(r[j])[:70] if j<len(r) else ''
                    example_rows.append(obj)
                st.dataframe(example_rows,hide_index=True,use_container_width=True)
                options=['— Ne pas utiliser —']
                for j in range(max_cols):
                    raw=str(rows[hrow-1][j]) if hrow-1<len(rows) and j<len(rows[hrow-1]) else ''
                    options.append(chr(65+j)+' : '+raw[:60])
                required={'tarifs':['categorie','1','2','3','4','5','6'],
                          'secteurs':['nom_commune','secteur'],
                          'localisations':['nom_commune','coefficient','section'],
                          'neutralisations':['nom_commune','commune']}
                optional={'tarifs':['7','8','9','10'],
                          'secteurs':['code_commune','prefixe','section'],
                          'localisations':['code_commune','prefixe','parcelle'],
                          'neutralisations':['syndicat','epci','taxes_speciales','teom','gemapi','code_commune']}
                translated={'categorie':'Code catégorie (BUR2, MAG1…)',
                            'nom_commune':'Nom de la commune','code_commune':'Code INSEE de commune',
                            'secteur':'Numéro du secteur','section':'Section cadastrale',
                            'prefixe':'Préfixe cadastral','parcelle':'Numéro de parcelle',
                            'coefficient':'Coefficient de localisation',
                            'commune':'Coefficient communal','syndicat':'Coefficient syndical',
                            'epci':'Coefficient EPCI','taxes_speciales':'Coefficient taxes spéciales',
                            'teom':'Coefficient TEOM','gemapi':'Coefficient GEMAPI'}
                cols={};selected=set()
                st.markdown('**Associez les colonnes (lettres A, B, C, etc.) aux champs fiscaux :**')
                for field in required[typ_man]+optional[typ_man]:
                    guessed=_match_col(labels,field) if field not in ('categorie','1','2','3','4','5','6','7','8','9','10') else None
                    if field=='categorie':
                        for j in range(min(6,max_cols)):
                            if sum(bool(_re.fullmatch(r'[A-Z]{3}[1-9]',str(row[j]).strip().upper())) for row in rows[:60] if j<len(row))>10:
                                guessed=j;break
                    if field.isdigit():
                        catcol=cols.get('categorie',-1)
                        guesscol=(catcol+int(field)) if catcol>=0 else -1
                        if guesscol < max_cols:guessed=guesscol
                    default=guessed+1 if guessed is not None and 0<=guessed<max_cols else 0
                    choose=st.selectbox(translated.get(field,'Secteur '+field),options,index=default,
                                        key='assist_col_'+field)
                    if choose!=options[0]:
                        col_idx=ord(choose[0])-65
                        cols[field]=col_idx
                        if col_idx in selected:st.warning(f'La colonne {choose[0]} est utilisée plusieurs fois : vérifiez le choix.')
                        selected.add(col_idx)
                if st.button('Valider cet import assisté',disabled=wrong_format or not confirm):
                    try:
                        missing=[k for k in required[typ_man] if k not in cols]
                        if missing:raise ValueError('Champs obligatoires non associés : '+', '.join(missing))
                        if len(set(cols.values()))<len(cols):
                            raise ValueError('Une même colonne est associée à plusieurs champs.')
                        data,sha=importer(uploaded.getvalue(),uploaded.name,typ_man,
                                           feuille=sheet,colonnes=cols,ligne_debut=begin-1)
                        _enregistrer(data,sha,uploaded.name+' [import assisté]')
                    except Exception as ex:
                        st.error('Import assisté non validé : '+str(ex))
            except Exception as ex:
                st.error('Aperçu du fichier impossible : '+str(ex))
    st.divider()
    st.download_button('Sauvegarder tout le référentiel (JSON)',
                       data=json.dumps(st.session_state.ref,ensure_ascii=False,indent=2),
                       file_name='referentiel_tf_local.json',mime='application/json')

with taux_tab:
    st.subheader('Gestion des taux par commune et par millésime')
    st.caption('Conservez une fiche par année. En 2026, les parts votées DGCL 2026 priment ; les parts détaillées DGFiP/REI 2025 sont proposées en repli avec alerte. Une valeur 0 % est autorisée si elle est explicitement publiée.')
    c_ed,c_year=st.columns([2,1])
    with c_ed:
        edit_code=st.text_input('Code INSEE de la commune (arrondissement admis)',
             value=st.session_state.get('code_insee',''),key='gestion_code_taux')
    with c_year:
        edit_year=st.selectbox('Année à gérer',list(range(2026,2016,-1)),
             index=0,key='gestion_annee_taux')
    try:
        edit_key=code_reference(edit_code)
    except ValueError:
        edit_key=None
        st.info('Indiquez le code INSEE à cinq caractères pour gérer les taux de cette commune.')
    if edit_key:
        st.caption(f'Identifiant fiscal de commune utilisé pour les taux : {edit_key} (les arrondissements de Lyon, Paris et Marseille sont rapprochés de la commune correspondante).')
        if st.button('Rechercher et préparer les taux publics pour '+str(edit_year),
                     key='chercher_gestion_'+edit_key+str(edit_year)):
            try:
                st.session_state['gestion_proposition_taux']=proposer_taux(edit_key,edit_year)
            except Exception as ex:
                st.error('Recherche des taux impossible : '+str(ex))
        gest=st.session_state.get('gestion_proposition_taux')
        if gest and gest.get('code_insee')==edit_key and gest.get('annee_imposition')==edit_year:
            if gest['propositions']:
                st.dataframe([{'Composante':LIBELLES[k],'Taux (%)':v['taux'],
                               'Année de la donnée':v['annee'], 'Source':v['source'],
                               'Alerte':'⚠ Repli antérieur' if v['repli'] else 'Millésime demandé'}
                              for k,v in gest['propositions'].items()],hide_index=True,use_container_width=True)
                replace_gest=st.checkbox('Autoriser le remplacement d’anciens taux enregistrés',
                                         key='rempl_gestion_'+edit_key+str(edit_year))
                if st.button('Valider et enregistrer cette proposition',
                             key='save_gestion_'+edit_key+str(edit_year)):
                    staged=copy.deepcopy(REF);added=[];conflicts=[]
                    for k,v in gest['propositions'].items():
                        try:
                            ok=sauver_taux(staged,edit_key,v['annee'],k,v['taux'],v['source'],
                                 url=v['url'],detail=v.get('detail',''),remplacer=replace_gest)
                            if ok:added.append(LIBELLES[k]+' '+str(v['annee']))
                        except ValueError as ex:conflicts.append(LIBELLES[k]+' : '+str(ex))
                    if added:
                        sauver_ref(staged);st.session_state.ref=staged
                        st.success('Enregistrés : '+', '.join(added))
                    if conflicts:st.warning('Conflits non écrasés : '+' ; '.join(conflicts))
                    if added:st.rerun()
            else:
                st.warning('Aucune composante reconnue dans les sources publiques consultées.')
            if gest.get('incidents'):
                with st.expander('Sources qui nécessitent un contrôle'):
                    st.write(gest['incidents'])
        current_year=REF.get('taux_annuels',{}).get(edit_key,{}).get(str(edit_year),{})
        with st.form('form_taux_'+edit_key+'_'+str(edit_year)):
            st.markdown('**Saisir ou mettre à jour les taux de '+str(edit_year)+'**')
            rows_form={}
            for key,label in TAXES.items():
                col_val,col_src=st.columns([1.05,2.2])
                existing=current_year.get(key)
                rate_default='' if existing is None else str(existing['taux']).replace('.',',')
                rate_string=col_val.text_input(f'{label} (%)',value=rate_default,
                                 placeholder='Vide = ne pas modifier',key='edval_'+edit_key+str(edit_year)+key)
                ref_default=existing.get('source','Saisie vérifiée sur avis fiscal') if existing else 'Saisie vérifiée sur avis fiscal'
                source=col_src.text_input('Source de '+label,value=ref_default,
                                key='edsrc_'+edit_key+str(edit_year)+key)
                rows_form[key]=(rate_string,source)
            doc_url=st.text_input('Référence ou lien vers la source (facultatif)',
                placeholder='Avis de taxe foncière, délibération ou URL officielle',key='edurl_'+edit_key+str(edit_year))
            zone=st.checkbox('Pour la TEOM, le zonage de la parcelle a été vérifié',
                 value=bool(current_year.get('teom',{}).get('zonage_confirme',False)),
                 key='edzone_'+edit_key+str(edit_year))
            submitted=st.form_submit_button('Enregistrer les taux de cette année',type='primary')
        if submitted:
            try:
                staged=copy.deepcopy(REF);changed=[]
                for key,(txt,src) in rows_form.items():
                    if txt.strip()=='':continue
                    existing=current_year.get(key)
                    normalized_taux=float(txt.replace(',','.').replace('%','').strip())
                    zone_changed=(key=='teom' and existing and bool(zone)!=bool(existing.get('zonage_confirme')))
                    rate_changed=(existing is None or abs(float(existing['taux'])-normalized_taux)>1e-8)
                    source_changed=(existing is None or src.strip()!=existing.get('source',''))
                    if not (rate_changed or source_changed or zone_changed or (doc_url.strip() and doc_url.strip()!=existing.get('url','') if existing else False)):
                        continue
                    # Une modification manuelle d'un taux officiel doit porter sa propre provenance.
                    if existing and rate_changed and not source_changed:
                        src='Saisie manuelle / correction de '+existing.get('source','la source précédente')
                    enregistrer_ok=sauver_taux(staged,edit_key,edit_year,key,txt,src,
                         url=doc_url or (existing.get('url','') if existing else ''),
                         detail='Correction ou saisie contrôlée manuellement',remplacer=True,
                         zonage_confirme=zone if key=='teom' else True)
                    if enregistrer_ok:changed.append(LIBELLES[key])
                if not changed:st.info('Aucune valeur nouvelle renseignée.')
                else:
                    sauver_ref(staged);st.session_state.ref=staged
                    st.success('Taux enregistrés pour '+str(edit_year)+' : '+', '.join(changed)+'. Les calculs de '+str(edit_year)+' et des années suivantes en bénéficieront selon leur disponibilité.')
                    st.rerun()
            except Exception as exc:
                st.error('Enregistrement refusé : '+str(exc))
        if current_year:
            del_key=st.selectbox('Supprimer une composante enregistrée dans '+str(edit_year),
                 ['— Sélectionner —']+[k for k in COMPOSANTES if k in current_year],
                 format_func=lambda k:LIBELLES.get(k,k),key='effacer_taux_'+edit_key+str(edit_year))
            if del_key!='— Sélectionner —' and st.button('Supprimer ce taux après contrôle',
                  key='valider_effacement_taux_'+edit_key+str(edit_year)):
                staged=copy.deepcopy(REF)
                supprimer_taux(staged,edit_key,edit_year,del_key)
                sauver_ref(staged);st.session_state.ref=staged
                st.success('Taux supprimé. La simulation pourra réutiliser le millésime antérieur en l’indiquant.')
                st.rerun()
        st.markdown('**Historique de cette commune**')
        historiques=lignes_historique(REF,edit_key)
        if historiques:
            st.dataframe(historiques,use_container_width=True,hide_index=True)
            import csv as _csv
            from io import StringIO as _StringIO
            buf=_StringIO();writer=_csv.DictWriter(buf,fieldnames=list(historiques[0]),delimiter=';')
            writer.writeheader();writer.writerows(historiques)
            st.download_button('Exporter l’historique des taux en CSV',buf.getvalue().encode('utf-8-sig'),
                               file_name=f'taux_{edit_key}.csv',mime='text/csv')
        else:
            st.info('Aucun taux annuel encore enregistré pour cette commune.')
        data_n=resoudre_tout(REF,edit_key,edit_year)
        st.markdown('**Taux retenus si vous simulez '+str(edit_year)+'**')
        st.dataframe([{'Composante':LIBELLES[k],
                       'Taux (%)':rec['taux'] if rec else None,
                       'Année réellement utilisée':rec['annee_source'] if rec else 'À renseigner',
                       'Alerte':'⚠ Taux non actualisé' if rec and rec['decalage']>0 else ('OK' if rec else 'Manquant')}
                      for k,rec in data_n.items()],hide_index=True,use_container_width=True)
    st.caption('Les taux archivés restent dans le fichier local data/referentiel_local.json, sauvegardé avant chaque modification. Un taux non publié ne doit jamais être inventé. Le taux TEOM peut varier à l’intérieur d’une commune.')

with doc_tab:
    st.subheader('Référentiel actuellement utilisé')
    st.caption('Un fichier local est créé lors de la première synchronisation. Chaque mise à jour conserve une copie précédente dans data/historique.')
    items=[]
    deps_present=sorted(set(REF.get('tarifs',{})) | set(REF.get('neutralisations_versions',{})) |
                        set(REF.get('secteurs',{})),key=lambda d:(len(d),d))
    for dep in deps_present:
        for year,tableau in sorted(REF.get('tarifs',{}).get(dep,{}).items()):
            source=REF.get('sources',{}).get(f'{dep}/tarifs/{year}',{})
            items.append({'Département':dep,'Donnée':'Tarifs','Millésime / validité':year,
                          'Lignes':len(tableau),'Origine':source.get('origine','Historique Excel')})
        for year,tableau in sorted(REF.get('localisations',{}).get(dep,{}).items()):
            source=REF.get('sources',{}).get(f'{dep}/localisations/{year}',{})
            items.append({'Département':dep,'Donnée':'Localisation','Millésime / validité':year,
                          'Lignes':len(tableau),'Origine':source.get('origine','Historique Excel')})
        sectors=REF.get('secteurs',{}).get(dep,[])
        if sectors:
            source=REF.get('sources',{}).get(f'{dep}/secteurs/2017',{})
            items.append({'Département':dep,'Donnée':'Sectorisation','Millésime / validité':'2017',
                          'Lignes':len(sectors),'Origine':source.get('origine','Historique Excel')})
        versions=REF.get('neutralisations_versions',{}).get(dep,{})
        for period,rows in sorted(versions.items()):
            source_key='2017' if period=='2017-2020' else '2021'
            source=REF.get('sources',{}).get(f'{dep}/neutralisations/{source_key}',{})
            items.append({'Département':dep,'Donnée':'Neutralisation','Millésime / validité':period,
                          'Lignes':len(rows),'Origine':source.get('origine','Historique Excel')})
        if '2021+' not in versions and REF.get('neutralisations',{}).get(dep):
            rows=REF['neutralisations'][dep]
            items.append({'Département':dep,'Donnée':'Neutralisation','Millésime / validité':'2021+ (classeur)',
                          'Lignes':len(rows),'Origine':'Historique Excel'})
    st.dataframe(items,use_container_width=True,hide_index=True)
    st.markdown('''**Règles et limites importantes**

- La valeur locative brute est calculée par : surface pondérée × tarif/m² × coefficient de localisation.
- La taxe foncière repose sur une base réduite de 50 %, puis des coefficients de neutralisation différenciés selon les composantes. Les corrections de planchonnement sont saisies séparément.
- **Planchonnement 2017–2026 inclus**, si le local est éligible : calcul à partir des VL historiques 2017 ou correction de base documentée, par composante fiscale. Le 2026 est la dernière année de ce mécanisme d’après le CGI en vigueur.
- **Lissage 2017–2025 inclus** : correction signée sur cotisation, obligatoire à justifier si éligible pour une simulation historique. **2026 : première année sans lissage de cotisation**.
- **2027–2031** : nouveau régime de transition (article 1518 A quinquies A), non modélisé par cette V7 ; ne jamais prolonger automatiquement les mécanismes 2017.
- Une parcelle cadastrale ne donne pas accès aux parties d’évaluation, aux surfaces fiscales ou à la catégorie de locaux. Les taux et exonérations doivent être confirmés par le professionnel ; le taux global TFPB DGFiP ne doit jamais être utilisé comme taux de la part communale.
- Les barèmes récupérés automatiquement doivent être contrôlés, notamment en cas de modification de format ou de publication rectificative.
- Le classeur d’origine couvre les départements 42, 43 et 69 ; les autres départements ne sont utilisables qu’après import de leurs jeux de données DGFiP et vérification des calculs.
- Usage **interne et local**, sans authentification ni base clients. Ne pas l’exposer sur internet en l’état.
''')
    st.markdown('**Reprendre le référentiel d’une version précédente**')
    st.caption('Sur votre Mac, récupérez « data/referentiel_local.json » dans l’ancien dossier du simulateur, ou le JSON téléchargé depuis l’onglet de mise à jour. Ce transfert ne remplace pas automatiquement les données fiscales sans confirmation.')
    previous_file=st.file_uploader('Référentiel JSON à restaurer (V2/V3/V4/V5)',type=['json'],key='fichier_migration')
    if previous_file is not None:
        try:
            if previous_file.size>20_000_000:
                raise ValueError('Référentiel supérieur à 20 Mo : contrôle manuel nécessaire.')
            previous=json.loads(previous_file.getvalue().decode('utf8'))
            expected_keys={'tarifs','localisations','secteurs','neutralisations','categories','sources'}
            if not isinstance(previous,dict) or not expected_keys.issubset(previous):
                raise ValueError('Structure de référentiel incompatible ; aucun changement.')
            if not all(isinstance(previous.get(key),dict) for key in ('tarifs','localisations','secteurs','neutralisations','sources')):
                raise ValueError('Contenu des tableaux du référentiel incorrect.')
            restore=st.checkbox('Je confirme vouloir remplacer le référentiel actif par ce fichier. Une sauvegarde sera conservée.',key='restaurer_confirmation')
            if st.button('Restaurer le référentiel',disabled=not restore):
                sauver_ref(previous)
                st.session_state.ref=previous
                st.success('Référentiel restauré. Vérifiez les années, les départements et les sources.')
                st.rerun()
        except (ValueError,UnicodeDecodeError) as ex:
            st.error('Fichier non restaurable : '+str(ex))

    st.markdown('**Sources officielles**')
    st.link_button('DGFiP — Révision des valeurs locatives',PAGE)
    st.link_button('DGFiP — Taux globaux TF et TEOM',SOURCE_TAUX)
    st.link_button('IGN — Documentation API Carto','https://apicarto.ign.fr/api/doc/cadastre')
    st.link_button('Service Public — Calcul de la VLLP','https://entreprendre.service-public.gouv.fr/vosdroits/F31046')
    st.link_button('DGFiP — Lissage terminé en 2026','https://www.impots.gouv.fr/professionnel/questions/quoi-sert-le-lissage')
    st.link_button('CGI, art. 1518 A quinquies (planchonnement 2026)','https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000053589332/2026-01-01')
    st.link_button('CGI, art. 1518 A quinquies A (2027–2031)','https://www.legifrance.gouv.fr/codes/article_lc/LEGIARTI000053534927/')
