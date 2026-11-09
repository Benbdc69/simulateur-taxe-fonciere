"""Portail Axens : professionnel V15 et habitation H1/H2 V3. Accès sécurisé."""
from __future__ import annotations
import os
import streamlit as st
from securite import verification_mot_de_passe

st.set_page_config(page_title="Simulateur TF | Axens", page_icon="🏢",layout="wide",initial_sidebar_state="collapsed")
st.markdown("""<style>
.block-container{max-width:1120px;padding-top:1.6rem}
h1,h2,h3{letter-spacing:-.02em}
[data-testid="stMetric"]{border-radius:14px;padding:14px;border:1px solid #d7e2ec}
</style>""",unsafe_allow_html=True)

if os.environ.get('TF_LOCAL_MODE') != '1':
    def get_secret(key):
        try:return str(st.secrets.get(key,'')).strip()
        except Exception:return ''
    stored=get_secret('TF_SHARED_PASSWORD_HASH') or os.environ.get('TF_SHARED_PASSWORD_HASH','')
    if not stored:
        st.error("Accès fermé : le mot de passe de l'application n'a pas été configuré dans les secrets d'hébergement.")
        st.stop()
    if not st.session_state.get('_acces_valide',False):
        st.title('Accès au simulateur')
        st.write('Application réservée aux personnes qui disposent du code d’accès communiqué par son administrateur.')
        with st.form('connexion',clear_on_submit=True):
            password=st.text_input('Mot de passe',type='password',max_chars=200)
            submitted=st.form_submit_button('Se connecter',type='primary',use_container_width=True)
        if submitted:
            errors=st.session_state.get('_erreurs_acces',0)
            if errors>=6:
                st.error('Nombre maximal de tentatives atteint pour cette session. Fermez l’onglet et contactez votre administrateur.')
            elif verification_mot_de_passe(password,stored):
                st.session_state['_acces_valide']=True
                st.session_state['_erreurs_acces']=0
                st.rerun()
            else:
                st.session_state['_erreurs_acces']=errors+1
                st.error('Mot de passe incorrect.')
        st.caption('Le code partagé ne permet pas de distinguer les utilisateurs. Ne déposez pas d’informations clients sensibles sur un hébergement gratuit sans validation préalable.')
        st.stop()
    if st.sidebar.button('Se déconnecter'):
        st.session_state.clear()
        st.rerun()

pages=[
    st.Page('accueil.py', title='Accueil', icon='🏠', default=True),
    st.Page('parcours_express.py',title='Local professionnel',icon='🏢'),
    st.Page('parcours_habitation.py',title='Habitation H1 / H2',icon='🏠'),
]
pg=st.navigation(pages,position='hidden')
if pg.title != 'Accueil':
    if st.button('Retour à l’accueil', icon='🏠', key='retour_accueil'):
        st.switch_page('accueil.py')
pg.run()
