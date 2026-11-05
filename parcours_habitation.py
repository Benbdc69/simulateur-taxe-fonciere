"""Parcours H1/H2 intégré au portail Axens, sans modifier le simulateur professionnel."""
from __future__ import annotations
import json
from pathlib import Path
import streamlit as st
from cadastre import adresses,parcelles_a_l_adresse
from historique_taux import resoudre_tout,COMPOSANTES,LIBELLES
from mise_a_jour_simple import synchroniser_taux
from moteur_habitation import surface_totale,simulations_tarifs,ENTRETIEN,SITUATION,CATEGORIES
from facteurs_habitation import facteur_departement_annee
from tarifs_habitation import rechercher_tarifs,SOURCE
from export_habitation_pdf import generer_pdf_habitation

ROOT=Path(__file__).resolve().parent
REF=ROOT/'data'/'referentiel_local.json'
REF_INITIAL=ROOT/'data'/'referentiel_initial.json'

def load_ref():
    p=REF if REF.exists() else REF_INITIAL
    return json.loads(p.read_text(encoding='utf-8'))

def fmt(v):return f'{float(v):,.2f}'.replace(',',' ').replace('.',',')+' €'

def normaliser_code(adr,ps):
    """Pour Lyon, conserver code arrondissement 6938x et non la ville globale 69123."""
    candidate=str((ps[0].get('insee') if ps else '') or adr.get('insee') or '').strip()
    cp=str(adr.get('code_postal') or '')
    if candidate in ('','69123') and cp in [f'6900{i}' for i in range(1,10)]:
        return '6938'+cp[-1]
    return candidate or str(adr.get('insee') or '')

st.markdown('''<style>
.block-container{max-width:1050px;padding-top:1.4rem;padding-bottom:3rem}
.hab-banner{background:#F4F8FB;border:1px solid #DDE8EF;border-left:5px solid #246A9D;border-radius:12px;padding:16px;margin-bottom:20px;color:#153957}
</style>''',unsafe_allow_html=True)
st.title('Taxe foncière — Habitation')
st.markdown('<div class="hab-banner">Déclarations H1 (maison) et H2 (appartement) · Tarifs cadastraux DGFiP 2024 · Valeur locative revalorisée automatiquement jusqu’en 2026</div>',unsafe_allow_html=True)
st.caption('Estimation fiscale non opposable · Ne comprend pas les avantages personnels, exonérations, frais de gestion et éventuelles dépendances évaluées séparément.')

with st.form('hab_saisie_v3'):
    adresse=st.text_input('Adresse du bien',placeholder='18 cours Gambetta, 69007 Lyon')
    a,b,c=st.columns(3)
    with a:nature_texte=st.selectbox('Nature du logement',['Appartement (H2)','Maison (H1)'])
    with b:
        ordre=sorted(CATEGORIES,key=lambda x:(int(x[0]),0 if len(x)==1 else 1))
        categorie=st.selectbox('Catégorie cadastrale',ordre,index=ordre.index('5'))
    with c:annee=st.selectbox("Année d'imposition",[2026,2025,2024],index=0)
    st.markdown('**Surfaces (déclaration H1/H2)**')
    a,b,c=st.columns(3)
    with a:surface=st.number_input('Surface principale et annexes intérieures (m²)',min_value=1.,max_value=20000.,value=45.,step=1.)
    with b:terrasse=st.number_input('Terrasse accessible (m²)',min_value=0.,max_value=10000.,value=0.,step=1.)
    with c:autres=st.number_input('Garage, cave, grenier, autres dépendances (m²)',min_value=0.,max_value=10000.,value=0.,step=1.)
    with st.expander('Situation, étage et équipements (renseignements H1/H2)',expanded=True):
        a,b,c=st.columns(3)
        with a:
            entretien=st.selectbox("État d’entretien cadastral",list(ENTRETIEN),index=2)
            sit_gen=st.selectbox('Situation générale',list(SITUATION),index=2)
        with b:
            sit_part=st.selectbox('Situation particulière',list(SITUATION),index=2)
            coef_terrasse=st.selectbox('Coefficient de pondération terrasse', [.2,.3,.4,.5,.6],index=2,
              help='Pondération réglementaire 0,2 à 0,6. Le coefficient précis dépend du service rendu et du dossier cadastral.')
        with c:
            etage=st.number_input('Étage (0 = rez-de-chaussée)',min_value=0,max_value=80,value=0,step=1)
            ascenseur=st.checkbox('Ascenseur dans l’immeuble',value=False)
            coef_annexe=st.selectbox('Coefficient autres dépendances', [.2,.3,.4,.5,.6],index=2)
        st.markdown('**Confort (équivalences superficielles)**')
        a,b,c,d=st.columns(4)
        with a:
            wc=st.number_input('WC',min_value=0,value=1,step=1)
            lavabo=st.number_input('Lavabos',min_value=0,value=1,step=1)
        with b:
            douches=st.number_input('Douches',min_value=0,value=1,step=1)
            bains=st.number_input('Baignoires',min_value=0,value=0,step=1)
        with c:
            pieces_ch=st.number_input('Pièces chauffées (si chauffage fixe assimilé central)',min_value=0,value=0,step=1,
                 help='2 m² par pièce chauffée admissible ; ne pas inclure WC/couloirs. Radiateurs mobiles seuls : 0.')
            gaz=st.checkbox('Gaz fixe',value=False)
        with d:
            eau=st.checkbox('Eau courante',value=True)
            elec=st.checkbox('Électricité',value=True)
            egout=st.checkbox('Tout-à-l’égout',value=True)
            vide=st.checkbox('Vide-ordures',value=False)
    submitted=st.form_submit_button('Calculer mon estimation',type='primary',use_container_width=True)

if submitted:
    st.session_state.pop('hab_resultat_v3',None)
    if len(adresse.strip())<6:
        st.error('Renseignez une adresse complète.')
    else:
        with st.spinner('Recherche du cadastre, des tarifs et des taux fiscaux…'):
            try:
                adr_opts=adresses(adresse)
                if not adr_opts:raise ValueError('Adresse introuvable dans le géocodage.')
                adr=adr_opts[0]
                try:ps=parcelles_a_l_adresse(adr)
                except Exception:ps=[]
                code=normaliser_code(adr,ps)
                nature='A' if nature_texte.startswith('Appartement') else 'M'
                sp=surface_totale(surface,nature,categorie,annexes=autres,terrasse=terrasse,
                   coeff_annexes=coef_annexe,coeff_terrasse=coef_terrasse,
                   entretien=entretien,situation_generale=sit_gen,situation_particuliere=sit_part,
                   etage=etage,ascenseur=ascenseur,eau=eau,gaz=gaz,electricite=elec,
                   baignoires=bains,douches=douches,lavabos=lavabo,wc=wc,egout=egout,
                   vide_ordures=vide,pieces_chauffees=pieces_ch)
                facteur=facteur_departement_annee(code,annee,adr.get('commune',''))
                tarifs=rechercher_tarifs(code,nature,categorie)
                if not tarifs:raise ValueError(f'Aucun tarif public 2024 pour {code}, nature {nature}, catégorie {categorie}.')
                rates=resoudre_tout(load_ref(),code,annee)
                if any(v is None for v in rates.values()):
                    try:
                        synchroniser_taux(annee,code)
                        rates=resoudre_tout(load_ref(),code,annee)
                    except Exception:pass
                taux={k:r['taux'] for k,r in rates.items() if r is not None and r.get('taux') is not None}
                complet=all(c in taux for c in COMPOSANTES)
                scenarios=simulations_tarifs(sp['surface_ponderee'],tarifs,facteur['coefficient_cumule'],taux if complet else None)
                st.session_state['hab_resultat_v3']={
                   'adresse':adr['libelle'],'code_insee':code,'parcelle':ps[0] if ps else None,
                   'nature':nature_texte,'categorie':categorie,'annee':int(annee),
                   'surface_reelle':surface,'terrasse_reelle':terrasse,'autres_dependances':autres,
                   'surfaces':sp,'tarifs':scenarios,'facteur':facteur,'taux':rates,
                   'taux_complets':complet,'source_tarifs':SOURCE}
            except Exception as e:st.error('Estimation indisponible : '+str(e))

r=st.session_state.get('hab_resultat_v3')
if r:
    st.divider();st.subheader('Résultat de la simulation')
    st.caption(f"{r['adresse']} · {r['nature']} · catégorie {r['categorie']} · {r['annee']}")
    a,b,c=st.columns(3)
    a.metric('Surface pondérée principale',f"{r['surfaces']['surface_ponderee']} m²")
    b.metric('Actualisation 1980',f"× {r['facteur']['actualisation_1980']:.2f}")
    c.metric('Revalorisation 1981–N',f"× {r['facteur']['revalorisation_nationale']:.4f}")
    if r['surfaces']['dependances_a_evaluer_separement']:
        st.warning('**Attention : estimation partielle.** La terrasse et/ou les dépendances de cet appartement peuvent être évaluées distinctement. Les montants présentés ci-dessous portent uniquement sur la partie principale et ne sont PAS le montant total du bien.')
    if len(r['tarifs'])>1:
        st.info(f"{len(r['tarifs'])} séries tarifaires DGFiP disponibles pour cette catégorie. La bonne série doit être vérifiée sur la fiche d’évaluation cadastrale ; l’adresse seule ne permet pas toujours de la déterminer.")
        totals=[x['total'] for x in r['tarifs'] if 'total' in x]
        if totals:st.markdown(f"**Fourchette selon la série : {fmt(min(totals))} à {fmt(max(totals))}**, hors dépendances distinctes, exonérations et frais.")
    if not r['taux_complets']:
        missing=[LIBELLES.get(c,c) for c in COMPOSANTES if r['taux'].get(c) is None]
        st.warning('Composantes fiscales non documentées : '+', '.join(missing)+'. Une valeur absente n’est pas supposée égale à zéro ; aucun total final n’est affiché.')
    anciens=[f"{LIBELLES.get(k,k)} ({v['annee_source']})" for k,v in r['taux'].items() if v and int(v.get('annee_source',r['annee']))<r['annee']]
    if anciens:st.caption('Taux repris d’un millésime antérieur : '+', '.join(anciens)+'.')
    options=[f"Série {x['serie']} · origine {x['origine'] or 'non précisée'} · tarif 1970 {fmt(x['tarif_1970'])}/m²" for x in r['tarifs']]
    choice=st.selectbox('Scénario tarifaire / série cadastrale',range(len(options)),format_func=lambda i:options[i])
    x=r['tarifs'][choice]
    a,b,c=st.columns(3)
    a.metric('Valeur locative 1970',fmt(x['vl_1970']))
    b.metric(f"Valeur locative brute {r['annee']}",fmt(x['vl_annee']))
    c.metric('Base TFPB (50 %)',fmt(x['base_tf']))
    if 'montants' in x:
        st.subheader('Cotisations calculées (hors frais et exonérations)')
        c=st.columns(3)
        for i,(k,v) in enumerate(x['montants'].items()):
            c[i%3].metric(LIBELLES.get(k,k),fmt(v))
        st.metric('Sous-total estimé — partie principale',fmt(x['total']))
    st.caption('VL 1970 = surface pondérée × tarif cadastral DGFiP ; VL '+str(r['annee'])+' = VL 1970 × actualisation 1980 × revalorisations nationales. Résultat indicatif non opposable.')
    r_pdf={**r,'serie_selectionnee':choice}
    st.download_button('Télécharger le rapport PDF',data=generer_pdf_habitation(r_pdf),file_name=f"estimation_habitation_{r['annee']}_{r['code_insee']}.pdf",mime='application/pdf',use_container_width=True)
