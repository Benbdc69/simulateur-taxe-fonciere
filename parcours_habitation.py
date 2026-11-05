"""Parcours habitation autonome, sans modification du calcul professionnel.
Tarif de référence DGFiP en valeur 1970 ; facteur de mise à jour certifié
nécessaire pour afficher une cotisation chiffrée, jamais inventé.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import streamlit as st
from cadastre import adresses, parcelles_a_l_adresse
from historique_taux import resoudre_tout
from mise_a_jour_simple import synchroniser_taux
from moteur_habitation import surface_totale, simulations_tarifs, ENTRETIEN, SITUATION
from tarifs_habitation import rechercher_tarifs
from export_habitation_pdf import generer_pdf_habitation

ROOT=Path(__file__).resolve().parent
REF=ROOT/'data'/'referentiel_local.json'
REF_INITIAL=ROOT/'data'/'referentiel_initial.json'
FACTORS=ROOT/'data'/'habitation_facteurs.json'


def load_ref():
    return json.loads((REF if REF.exists() else REF_INITIAL).read_text(encoding='utf-8'))


def facteur_documente(departement,annee):
    """Seuls les facteurs métadonnées et validés sont utilisés ; pas de défaut 1."""
    try:
        params=json.loads(FACTORS.read_text(encoding='utf-8'))
        entry=params['coefficients_cumules'][str(departement)][str(annee)]
        return float(entry['valeur']),str(entry['source'])
    except (OSError,KeyError,ValueError,TypeError):return None,None


def fmt(v):return f'{float(v):,.2f}'.replace(',',' ').replace('.',',')+' €'

st.markdown('''<style>
.block-container{max-width:980px;margin:auto;padding-top:2rem;padding-bottom:3rem}
.hab-card{border:1px solid #DFE8F2;border-left:4px solid #246A9D;border-radius:15px;padding:18px;margin:10px 0;background:rgba(127,127,127,.04)}
.hab-value{font-size:1.8rem;font-weight:750;color:#246A9D}
</style>''',unsafe_allow_html=True)
st.title('Estimer la taxe foncière d’un logement')
st.caption('Maisons H1 et appartements H2 · Tarifs cadastraux officiels · Estimation non opposable')
with st.form('hab_saisie'):
    adresse=st.text_input('Adresse complète du bien',placeholder='Ex. 18 cours Gambetta, 69007 Lyon')
    a,b,c=st.columns(3)
    with a:
        nature_texte=st.selectbox('Nature du logement',['Maison (H1)','Appartement (H2)'])
    with b:
        categorie=st.selectbox('Catégorie cadastrale',list(range(1,9)),index=4,
                   format_func=lambda n:f'Catégorie {n}')
    with c:
        annee=st.number_input('Année d’imposition',min_value=2020,max_value=2100,value=2026,step=1)
    st.markdown('**Surfaces du logement**')
    a,b=st.columns(2)
    with a:surface=st.number_input('Pièces et annexes intégrées au logement (m²)',min_value=0.,value=80.,step=1.)
    with b:annexes=st.number_input('Garage, cave, grenier, dépendances (m²)',min_value=0.,value=0.,step=1.,help='Pour les appartements, certaines dépendances sont évaluées séparément.')
    with st.expander('Préciser la situation et les équipements (H1 / H2)',expanded=True):
        a,b,c=st.columns(3)
        with a:
            entretien=st.selectbox('État d’entretien',list(ENTRETIEN),index=2)
            sit_gen=st.selectbox('Situation générale',list(SITUATION),index=2)
        with b:
            sit_part=st.selectbox('Situation particulière',list(SITUATION),index=2)
            coef_annexe=st.selectbox('Pondération des annexes de maison',[.2,.3,.4,.5,.6],index=2,
                                       help='Estimation : choix d’un coefficient de 0,2 à 0,6, selon le service rendu.')
        with c:
            ch=st.number_input('Pièces/annexes avec chauffage central',min_value=0,value=0,step=1)
            wc=st.number_input('WC',min_value=0,value=1,step=1)
        a,b,c=st.columns(3)
        with a:
            bain=st.number_input('Baignoires',min_value=0,value=0,step=1)
            douches=st.number_input('Douches',min_value=0,value=1,step=1)
        with b:
            lavabos=st.number_input('Lavabos (hors éviers)',min_value=0,value=1,step=1)
            eau=st.checkbox('Eau courante',value=True)
        with c:
            elec=st.checkbox('Électricité',value=True)
            gaz=st.checkbox('Gaz (installation fixe)',value=False)
            egout=st.checkbox('Raccordement à l’égout',value=True)
            vide=st.checkbox('Vide-ordures',value=False)
    submitted=st.form_submit_button('Estimer mon logement',type='primary',use_container_width=True)

if submitted:
    st.session_state.pop('hab_resultat',None)
    if len(adresse.strip())<6 or surface<=0:
        st.error('Indiquez une adresse complète et une surface principale positive.')
    else:
        with st.spinner('Recherche des références cadastrales et des tarifs officiels…'):
            try:
                adr_opts=adresses(adresse)
                if not adr_opts:raise ValueError('Adresse non reconnue par le service géographique.')
                adr=adr_opts[0]
                ps=parcelles_a_l_adresse(adr)
                code=str((ps[0].get('insee') if ps else None) or adr['insee'])
                nature='M' if nature_texte.startswith('Maison') else 'A'
                sp=surface_totale(surface,nature,categorie,annexes=annexes,coeff_annexes=coef_annexe,
                  entretien=entretien,situation_generale=sit_gen,situation_particuliere=sit_part,
                  eau=eau,gaz=gaz,electricite=elec,baignoires=bain,douches=douches,lavabos=lavabos,
                  wc=wc,egout=egout,vide_ordures=vide,pieces_chauffees=ch)
                tarifs=rechercher_tarifs(code,nature,categorie)
                if not tarifs:raise ValueError('Aucun tarif de référence publié pour la commune, la nature et la catégorie choisies.')
                facteur,source_facteur=facteur_documente(code[:2],annee)
                rates=resoudre_tout(load_ref(),code,int(annee)) if int(annee)<=2026 else {}
                if int(annee)<=2026 and not all(v is not None for v in rates.values()):
                    try:
                        synchroniser_taux(int(annee),code)
                        rates=resoudre_tout(load_ref(),code,int(annee))
                    except Exception:
                        pass  # les sources absentes ne deviennent jamais des taux zéro

                taux={k:r['taux'] for k,r in rates.items() if r and r.get('taux') is not None}
                taux_complets=len(taux)==6
                scen=simulations_tarifs(sp['surface_ponderee'],tarifs,facteur,taux if taux_complets else None)
                st.session_state['hab_resultat']={'adresse':adr['libelle'],'parcelle':ps[0] if ps else None,
                    'nature':nature_texte,'categorie':categorie,'annee':int(annee),'surfaces':sp,
                    'tarifs':scen,'facteur':facteur,'source_facteur':source_facteur,'taux':rates,'taux_complets':taux_complets}
            except Exception as exc:
                st.error('Estimation non finalisée : '+str(exc))

r=st.session_state.get('hab_resultat')
if r:
    st.divider()
    st.subheader('Résultat de l’étude')
    st.caption(f"{r['adresse']} · {r['nature']} · Catégorie {r['categorie']} · {r['annee']}")
    st.metric('Surface cadastrale pondérée calculée',f"{r['surfaces']['surface_ponderee']:,.0f} m²".replace(',',' '))
    if r['surfaces']['dependances_a_evaluer_separement']:
        st.info('Les dépendances de cet appartement peuvent devoir être évaluées séparément : elles ne sont pas intégrées aux montants ci-dessous.')
    if len(r['tarifs'])>1:
        st.info(f"{len(r['tarifs'])} séries tarifaires sont publiées pour cette catégorie. Sans la série applicable, un montant unique ne serait pas justifié.")
    if r['facteur'] is None:
        st.warning('Le tarif public est exprimé en valeur de référence 1970. Le coefficient cumulé d’actualisation départementale et de revalorisation jusqu’à l’année choisie n’est pas encore validé dans le référentiel. Aucun montant de taxe n’est inventé.')
    elif not r.get('taux_complets'):
        st.warning('Certains taux d’imposition manquent : aucun total incomplet n’est présenté comme une taxe complète.')
    for x in r['tarifs'][:12]:
        with st.container(border=True):
            st.markdown(f"**Série {x['serie']}** · Tarif 1970 : {fmt(x['tarif_1970'])}/m²")
            a,b=st.columns(2)
            a.metric('Valeur locative de référence 1970',fmt(x['vl_1970']))
            if 'total' in x:
                b.metric('Taxes estimées, hors frais et exonérations',fmt(x['total']))
            elif 'vl_annee' in x:
                b.metric('Valeur locative brute actualisée',fmt(x['vl_annee']))
            if 'montants' in x:
                st.markdown('**Répartition indicative**')
                for k,v in x['montants'].items():st.write(f'{k.replace("_"," ").capitalize()} : {fmt(v)}')
    st.caption('La valeur de référence publiée n’identifie pas à elle seule la série d’évaluation d’un logement donné. Les coefficients et les taux manquants ne sont jamais assimilés à zéro.')
    st.download_button('Télécharger le rapport PDF',data=generer_pdf_habitation(r),
                       file_name=f"estimation_habitation_{r['annee']}.pdf",mime='application/pdf',use_container_width=True)
