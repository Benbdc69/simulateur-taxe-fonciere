"""Choix du parcours avant toute saisie."""
import streamlit as st
from acces_dossiers import configuration_dossiers

st.title('Simulateur de taxe foncière')
st.write('Choisissez votre simulation.')
a, b, c = st.columns(3)
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
st.caption('Les parcours de taxe foncière permettent une recherche par adresse ou par parcelle cadastrale.')
if configuration_dossiers():
    if st.button('Dossiers clients'):
        st.switch_page('dossiers_clients.py')
