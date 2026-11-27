"""Choix du parcours et téléchargement du support commercial."""
from pathlib import Path

import streamlit as st

from import_cerfa import TAILLE_MAX_CERFA, lire_cerfa
from session_calcul import cle_calcul, effacer_calcul

SUPPORT_COMMERCIAL = Path(__file__).resolve().parent / 'data' / 'documents' / 'offre-axens-pre-audit-taxe-fonciere.pdf'

st.title('Simulateur de taxe foncière')
st.write('Choisissez votre simulation.')
a, b, c, d = st.columns(4)
with a:
    with st.container(border=True):
        st.markdown('### 🏢 Local professionnel')
        st.write('Bureaux, commerces et autres locaux professionnels. Surfaces et paramètres de la déclaration 6660-REV.')
        if st.button('Local professionnel', type='primary', use_container_width=True):
            st.switch_page('parcours_express.py')
with b:
    with st.container(border=True):
        st.markdown('### 🏠 Local d’habitation')
        st.write('Appartement ou maison. Consistance, confort et classement cadastral selon les déclarations H2 ou H1.')
        if st.button('Local d’habitation', type='primary', use_container_width=True):
            st.switch_page('parcours_habitation.py')
with c:
    with st.container(border=True):
        st.markdown('### 🧾 CFE – Base minimum')
        st.write('Estimez la cotisation minimum de votre entreprise selon la commune, l’année et le chiffre d’affaires N−2.')
        if st.button('CFE – Base minimum', type='primary', use_container_width=True):
            st.switch_page('parcours_cfe.py')
with d:
    with st.container(border=True):
        st.markdown('### 📄 Pré-audit Axens')
        st.write('Offre de pré-audit de taxe foncière pour les locaux professionnels et liste des pièces à fournir.')
        st.download_button(
            'Télécharger le PDF',
            data=SUPPORT_COMMERCIAL.read_bytes(),
            file_name=SUPPORT_COMMERCIAL.name,
            mime='application/pdf',
            on_click='ignore',
            type='primary',
            use_container_width=True,
        )

with st.expander('Importer une déclaration déjà remplie'):
    st.caption('Ouvrez une nouvelle simulation à partir d’un H1, H2 ou 6660-REV rempli dans le PDF interactif. Vérifiez ensuite les données reprises.')
    fichier = st.file_uploader('Déclaration H1, H2 ou 6660-REV', type='pdf', key=cle_calcul('import_cerfa'))
    if fichier is not None and st.button('Préremplir une simulation', type='primary'):
        try:
            if fichier.size > TAILLE_MAX_CERFA:
                raise ValueError('Choisissez un PDF de 10 Mo maximum.')
            modele, saisie, a_verifier = lire_cerfa(fichier.getvalue())
        except ValueError as exc:
            st.error(str(exc))
        else:
            effacer_calcul()
            st.session_state['_cerfa_importe'] = {'modele': modele, 'a_verifier': a_verifier}
            if modele == '6660-rev':
                st.session_state['_saisie_cerfa_pro'] = saisie
                st.switch_page('parcours_express.py')
            st.session_state['hab_saisie'] = saisie
            st.switch_page('parcours_habitation.py')
st.caption('Les parcours de taxe foncière permettent une recherche par adresse ou par parcelle cadastrale.')
