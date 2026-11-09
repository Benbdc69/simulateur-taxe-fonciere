"""Remise à zéro des calculs sans interrompre l'authentification."""
import streamlit as st


def cle_calcul(nom):
    return f"{nom}_{st.session_state.get('_generation_calcul', 0)}"


def effacer_calcul():
    generation = st.session_state.get('_generation_calcul', 0) + 1
    for cle in list(st.session_state):
        if cle not in ('_acces_valide', '_erreurs_acces'):
            del st.session_state[cle]
    st.session_state['_generation_calcul'] = generation


def bouton_nouveau_calcul():
    st.button('Nouveau calcul', icon='🔄', key='nouveau_calcul', on_click=effacer_calcul,
              help='Efface toutes les saisies, recherches et résultats de cette session, sans vous déconnecter.')
