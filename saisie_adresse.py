"""Suggestions IGN pendant la frappe et repli vers la saisie manuelle."""
import streamlit as st
from streamlit_searchbox import st_searchbox
from cadastre import adresses


def suggestions_adresses(recherche):
    texte = str(recherche or '').strip()
    if len(texte) < 5:
        return []
    return [(r['libelle'], r) for r in adresses(texte)]


def saisir_adresse(label, cle, valeur=''):
    mode = st.radio('Saisie de l’adresse', ['Suggestions pendant la saisie', 'Saisie manuelle'], horizontal=True, key=cle+'_mode')
    if mode == 'Saisie manuelle':
        return st.text_input(label, value=valeur, key=cle+'_manuelle', placeholder='Numéro, voie, code postal et commune'), None
    erreur = cle+'_erreur'

    def chercher(texte):
        st.session_state.pop(erreur, None)
        try:
            return suggestions_adresses(texte)
        except (ValueError, ConnectionError):
            st.session_state[erreur] = 'Suggestions indisponibles. Réessayez ou choisissez la saisie manuelle.'
            return []

    selection = st_searchbox(chercher, key=cle+'_suggestions', label=label,
        placeholder='Commencez à saisir le numéro, la voie et la commune…',
        debounce=450, edit_after_submit='option', default_use_searchterm=True,
        help='À partir de 5 caractères, choisissez une adresse proposée par l’IGN. Précisez la commune ou le code postal pour affiner.')
    st.caption('Suggestions à partir de 5 caractères. Sélectionnez l’adresse exacte dans la liste.')
    if st.session_state.get(erreur):
        st.warning(st.session_state[erreur])
    if isinstance(selection, dict) and selection.get('libelle') and 'lon' in selection and 'lat' in selection:
        return selection['libelle'], selection
    return '', None
