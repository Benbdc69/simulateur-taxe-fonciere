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
from cadastre import adresses, parcelles_a_l_adresse
from moteur import (COEFF_SURFACES, TAXES, insee_cadastral_adresse,
                    nom_commune_cadastrale, secteur_automatique,
                    localisation_automatique, neutralisation_avec_teom_reference,
                    tarif_automatique, estimation)
from historique_taux import resoudre_tout
from mise_a_jour_simple import synchroniser_dgfip, synchroniser_taux
from export_pdf import creer_pdf_estimation
from exoneration_neuf import exon_neuf_non_habitation

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


def _html(s: str) -> str:
    return str(s).replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;')


def render_tax_cards(lignes):
    st.markdown('**Répartition par taxe**')
    cols = st.columns(2)
    for i, r in enumerate(lignes):
        with cols[i % 2]:
            st.markdown(
                f'''<div class="tf-tax-card">
                <div class="tf-tax-head">{_html(r['taxe'])}</div>
                <div class="tf-tax-amount">{euro(r['montant'])}</div>
                <div class="tf-tax-meta">Base : {_html(euro(r['base_taxable']))} · Taux : {_html(pct(r['taux_pct']))}</div>
                <div class="tf-tax-meta">Exonération : {_html(pct(r['abattement_pct']))}</div>
                </div>''',
                unsafe_allow_html=True,
            )



def normaliser_identite(parcelle, adresse, ref):
    code = str(parcelle.get('insee') or adresse.get('insee') or '')
    code = insee_cadastral_adresse(code, adresse.get('code_postal', ''))
    dep = str(parcelle.get('departement') or code[:2])
    commune = nom_commune_cadastrale(ref, dep, code, adresse.get('commune', ''))
    return {'code_insee': code, 'departement': dep, 'commune': commune,
            'prefixe': str(parcelle.get('prefixe') or ''),
            'section': str(parcelle.get('section') or ''),
            'numero': str(parcelle.get('numero') or '')}


def calculer_dossier(ref, ref_initial, bien, categorie, surfaces, annee, construction_nouvelle=False, annee_achevement=None):
    """L'unique point d'entrée métier du parcours simple (aucune duplication de calcul).

    Un 6660-REV ne contient pas l'ancienne VL 2017 ou les éventuelles
    exonérations. On produit donc une estimation de base *conditionnelle*.
    """
    exo = exon_neuf_non_habitation(annee, annee_achevement, construction_nouvelle)
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
        result = estimation(surfaces,tarif,loc,coeffs,taux,abattements=exo['taux'],planchonnements={},frais_pct=0)
    return {'result':result,'partial':partial,'missing':missing,'taux':rates,'exoneration_neuf':exo,
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




def finaliser(candidat, categorie, surfaces, annee, construction_nouvelle=False, annee_achevement=None):
    adresse_result, parcelle = candidat
    bien=normaliser_identite(parcelle,adresse_result,lire_ref())
    with st.spinner('Calcul à partir des barèmes et taux disponibles…'):
        issues=actualiser_si_necessaire(annee,bien)
        res=calculer_dossier(lire_ref(),json.loads(BASE.read_text(encoding='utf-8')),
             bien,categorie,surfaces,annee,construction_nouvelle,annee_achevement)
    st.session_state['_calcul_express']={
        'bien':bien,'adresse':adresse_result['libelle'],
        'categorie':categorie,'annee':annee, 'construction_nouvelle':construction_nouvelle, 'annee_achevement':annee_achevement,
        'surfaces':surfaces,'analyse':res,'sync_incidents':issues}
    st.session_state.pop('_parcelles_attente',None)



st.markdown('''<style>
.block-container {
    max-width: 980px;
    padding-top: 2rem;
    padding-bottom: 4rem;
}

section[data-testid="stSidebar"] {
    display: none;
}

/* Cartes de résultats */
.tf-summary-card,
.tf-tax-card {
    border: 1px solid #DFE8F2;
    background: #FFFFFF;
    color: #153957;
    border-radius: 18px;
    padding: 1.15rem 1.2rem;
    margin: .25rem 0 .8rem 0;
    box-shadow: 0 5px 22px rgba(22,67,109,.055);
}

.tf-tax-card {
    border-left: 4px solid #246A9D;
    min-height: 176px;
}

.tf-summary-card {
    border-top: 3px solid #246A9D;
    min-height: 152px;
}

/* Libellés */
.tf-summary-label,
.tf-tax-head {
    font-size: .88rem;
    font-weight: 600;
    color: #547088;
    margin-bottom: .45rem;
}

/* Montants */
.tf-summary-value,
.tf-tax-amount {
    font-size: 1.55rem;
    font-weight: 750;
    line-height: 1.15;
    margin-bottom: .4rem;
    color: #164C79;
}

/* Textes secondaires */
.tf-summary-sub,
.tf-tax-meta {
    font-size: .87rem;
    color: #526B80;
    line-height: 1.45;
}

/* Boutons principaux */
div.stButton > button[kind="primary"],
div.stFormSubmitButton > button[kind="primary"] {
    background: #246A9D !important;
    border-color: #246A9D !important;
    color: #FFFFFF !important;
}

div.stButton > button[kind="primary"]:hover,
div.stFormSubmitButton > button[kind="primary"]:hover {
    background: #164C79 !important;
    border-color: #164C79 !important;
}

/* Affichage mobile */
@media (max-width: 640px) {
    .tf-tax-card {
        min-height: 0;
    }
}
</style>''', unsafe_allow_html=True)

st.title('Estimez votre taxe foncière')
st.caption('Locaux professionnels · Déclaration 6660-REV · Informations fiscales récupérées automatiquement')

ref = lire_ref()
cat_map={c['code']:c for c in ref.get('categories',[])}
if not cat_map:
    st.error('Le référentiel des catégories fiscales est indisponible.')
    st.stop()
cat_codes=list(cat_map)

with st.form('saisie_unique',border=True):
    st.markdown('#### Votre local')
    adresse=st.text_input('Adresse complète du bien',placeholder='Ex. 18 cours Gambetta, 69007 Lyon')
    categorie=st.selectbox('Catégorie du local', cat_codes,
        format_func=lambda code:f"{code} — {cat_map[code]['description']}")
    st.markdown('**Surfaces figurant sur votre déclaration 6660-REV**')
    st.caption('Saisissez les mètres carrés par type d’usage. L’application calcule les pondérations.')
    surfaces={}
    labels={'P1':'P1 · Principale','P2':'P2 · Secondaire couverte',
            'P3':'P3 · Secondaire non couverte','PK1':'PK1 · Stationnement couvert',
            'PK2':'PK2 · Stationnement non couvert'}
    cols=st.columns(3)
    for i,(k,v) in enumerate(labels.items()):
        with cols[i%3]:
            surfaces[k]=st.number_input(v,min_value=0.0,max_value=1_000_000.0,step=1.0,key='express_'+k)
    annee=int(st.number_input('Année d’imposition', min_value=2017, value=2026, step=1, format='%d', help='Vous pouvez choisir une année future. Une estimation n’est calculée que si les données fiscales correspondantes sont disponibles.'))
    construction_nouvelle=st.checkbox('Construction nouvelle, reconstruction ou addition de construction (hors habitation)', value=False,
        help='Exonération temporaire de 40 % de la part communale et des taxes additionnelles éligibles (GEMAPI, TSE et syndicats sans fiscalité propre), sous conditions.')
    annee_achevement=None
    if construction_nouvelle:
        annee_achevement=st.number_input('Année d’achèvement des travaux',min_value=1900,max_value=annee, value=max(1900,annee-1),step=1)
        st.caption('Sous réserve de déclaration dans les 90 jours : 40 % pour la commune, les syndicats sans fiscalité propre, la TSE et la GEMAPI ; pas pour l’EPCI à fiscalité propre ni la TEOM.')
    run=st.form_submit_button('Calculer mon estimation',type='primary',use_container_width=True)

if run:
    st.session_state.pop('_parcelles_attente',None)
    st.session_state.pop('_calcul_express',None)
    if len(adresse.strip())<6:
        st.error('Indiquez une adresse complète pour localiser le bien.')
    elif not any(surfaces.values()):
        st.error('Renseignez au moins une surface.')
    else:
        with st.spinner('Recherche de la parcelle et des données fiscales…'):
            try:
                options=adresses(adresse)
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
                        finaliser(cand[0],categorie,surfaces,annee,construction_nouvelle,annee_achevement)
                    else:
                        st.session_state['_parcelles_attente']={
                            'candidats':cand,'categorie':categorie,'surfaces':surfaces,'annee':annee,'construction_nouvelle':construction_nouvelle,'annee_achevement':annee_achevement}
            except Exception as exc:
                st.error('Recherche cadastrale momentanément indisponible : '+str(exc))

pending=st.session_state.get('_parcelles_attente')
if pending:
    candidats=pending['candidats']
    with st.container(border=True):
        if len(candidats)>1:
            st.markdown('**Confirmez la parcelle correspondant au local**')
            selection=st.selectbox('Parcelle cadastrale',range(len(candidats)),
                format_func=lambda i: f"{candidats[i][1]['section']} {candidats[i][1]['numero']} · {candidats[i][1]['insee']} · {candidats[i][1].get('distance_m','?')} m du point d’adresse")
        else:
            selection=0
            p=candidats[0][1]
            st.caption(f"Parcelle identifiée : {p['section']} {p['numero']}")
        if st.button('Obtenir le résultat',type='primary',use_container_width=True):
            try:
                finaliser(candidats[selection],pending['categorie'],pending['surfaces'],pending['annee'],pending.get('construction_nouvelle',False),pending.get('annee_achevement'))
                st.rerun()
            except Exception as exc:
                st.error('Le calcul n’a pas pu être finalisé : '+str(exc))

calcule=st.session_state.get('_calcul_express')
if calcule:
    analyse=calcule['analyse']; result=analyse['result']; partial=analyse['partial']
    st.divider()
    st.subheader('Votre estimation')
    st.caption(f"{calcule['adresse']} · {calcule['annee']} · {calcule['categorie']}")
    if result:
        st.metric('Montant estimé des taxes, hors frais de gestion',euro(result['total_estime']))
        exo = analyse.get('exoneration_neuf', {})
        if exo.get('active'):
            st.caption(f"Construction achevée en {exo['annee_achevement']} : exonération de 40 % appliquée à la part communale et aux taxes additionnelles éligibles (hors EPCI à fiscalité propre et TEOM), sous réserve des conditions déclaratives.")
        else:
            st.caption('Estimation de base sans autres exonérations particulières ni corrections historiques non fournies ; frais de gestion non inclus.')
        if exo.get('a_verifier') and not exo.get('active'):
            st.caption('Construction nouvelle : régime antérieur à 2021 à vérifier selon l’année simulée.')
        render_tax_cards(result['lignes'])
    else:
        st.info('La valeur locative peut être estimée, mais une cotisation complète ne peut pas être établie sans inventer certains paramètres officiels.')
        if partial['valeur_locative_brute'] is not None:
            st.metric('Valeur locative brute estimée',euro(partial['valeur_locative_brute']))
        st.caption('Données indisponibles : '+', '.join(analyse['missing']))
    c1,c2,c3 = st.columns(3)
    with c1:
        st.markdown(
            f'''<div class="tf-summary-card">
                <div class="tf-summary-label">Surface pondérée</div>
                <div class="tf-summary-value">{f"{partial['surface_ponderee']:,.2f}".replace(',', ' ')} m²</div>
                <div class="tf-summary-sub">Calculée automatiquement à partir des surfaces 6660-REV</div>
            </div>''',
            unsafe_allow_html=True,
        )
    with c2:
        vl_text = euro(partial['valeur_locative_brute']) if partial['valeur_locative_brute'] is not None else 'Indisponible'
        st.markdown(
            f'''<div class="tf-summary-card">
                <div class="tf-summary-label">Valeur locative brute</div>
                <div class="tf-summary-value">{vl_text}</div>
                <div class="tf-summary-sub">Avant frais de gestion et sous réserve des paramètres publics</div>
            </div>''',
            unsafe_allow_html=True,
        )
    with c3:
        parcelle = f"{calcule['bien']['section']} {calcule['bien']['numero']}"
        st.markdown(
            f'''<div class="tf-summary-card">
                <div class="tf-summary-label">Parcelle cadastrale</div>
                <div class="tf-summary-value">{parcelle}</div>
                <div class="tf-summary-sub">{calcule['bien']['commune']} · Code {calcule['bien']['code_insee']}</div>
            </div>''',
            unsafe_allow_html=True,
        )
    st.warning('Pour un local existant avant 2017, les corrections historiques de planchonnement (et, jusqu’en 2025, de lissage) peuvent modifier sensiblement le montant. L’adresse et la déclaration 6660-REV seules ne permettent pas de les reconstituer. Vérifiez également les exonérations, les frais et le zonage TEOM.')
    stale=[f"{r['annee_source']} : {key}" for key,r in analyse['taux'].items() if r and r.get('decalage',0)>0]
    if stale: st.caption('Taux repris d’un millésime antérieur : '+', '.join(stale)+'.')
    if analyse['neutral_warnings']:st.caption('Certaines neutralisations historiques ont été reprises à titre provisoire.')
    st.download_button(
        'Télécharger mon estimation en PDF',
        data=creer_pdf_estimation(calcule),
        file_name=f"estimation_taxe_fonciere_{calcule['annee']}_{calcule['bien']['code_insee']}.pdf",
        mime='application/pdf',
        use_container_width=True,
        key='export_pdf_express',
    )
    with st.expander('Voir les paramètres utilisés et les sources'):
        st.write({'Commune':calcule['bien']['commune'],'Code cadastral':calcule['bien']['code_insee'],
                  'Parcelle':calcule['bien']['section']+' '+calcule['bien']['numero'],
                  'Secteur':partial['secteur'],'Coefficient de localisation':partial['localisation'],
                  'Tarif €/m²':partial['tarif'],'Taux et années':analyse['taux'],
                  'Neutralisations':analyse['neutralisations']})
        if calcule['sync_incidents']:
            st.caption('Certaines sources n’ont pas répondu. Le référentiel précédent a été conservé.')
