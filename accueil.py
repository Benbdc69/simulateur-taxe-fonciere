"""Choix du parcours avant toute saisie."""
import streamlit as st

st.title('Simulateur de taxe foncière')
st.write('Quel type de local souhaitez-vous évaluer ?')
a, b = st.columns(2)
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
st.caption('Une recherche par adresse ou par parcelle cadastrale est disponible dans les deux parcours.')
