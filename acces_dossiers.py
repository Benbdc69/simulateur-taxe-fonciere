"""Configuration et contrôle des accès de l’équipe aux dossiers clients."""

from collections.abc import Mapping
import os

import streamlit as st

from securite import verification_mot_de_passe
from stockage_dossiers import StockageDossiers


def secret_dossiers(cle, defaut):
    try:
        return st.secrets.get(cle, defaut)
    except FileNotFoundError:
        return defaut


def configuration_dossiers():
    postgres = (os.environ.get('TF_DOSSIERS_DATABASE_URL')
                or secret_dossiers('TF_DOSSIERS_DATABASE_URL', ''))
    if postgres:
        return {'postgres': postgres}
    if os.environ.get('TF_LOCAL_MODE') == '1' and os.environ.get('TF_DOSSIERS_SQLITE_PATH'):
        return {'sqlite': os.environ['TF_DOSSIERS_SQLITE_PATH']}
    return {}


@st.cache_resource(show_spinner=False)
def stockage_configure(**configuration):
    stockage = StockageDossiers(**configuration)
    stockage.initialiser()
    return stockage


def _comptes():
    return secret_dossiers('dossiers_utilisateurs', {})


def identite_dossiers():
    nom = st.session_state.get('_dossiers_identite')
    compte = _comptes().get(nom) if nom else None
    if isinstance(compte, Mapping) and compte.get('role') in ('lecture', 'edition'):
        return nom, compte['role']
    return None


def demander_acces_dossiers():
    identite = identite_dossiers()
    if identite:
        return identite
    comptes = _comptes()
    if not comptes:
        st.info('Un compte individuel doit être configuré pour accéder aux dossiers clients.')
        return None
    echecs = st.session_state.get('_dossiers_echecs', 0)
    if echecs >= 6:
        st.error('Nombre maximal de tentatives atteint pour cette session.')
        return None
    with st.form('connexion_dossiers', clear_on_submit=True):
        nom = st.text_input('Identifiant professionnel', max_chars=120)
        mdp = st.text_input('Mot de passe personnel', type='password', max_chars=200)
        soumettre = st.form_submit_button('Accéder aux dossiers')
    if soumettre:
        nom = nom.strip()
        compte = comptes.get(nom)
        if (isinstance(compte, Mapping) and compte.get('role') in ('lecture', 'edition')
                and verification_mot_de_passe(mdp, compte.get('mot_de_passe_hash') or '')):
            st.session_state['_dossiers_identite'] = nom
            st.session_state.pop('_dossiers_echecs', None)
            return nom, compte['role']
        st.session_state['_dossiers_echecs'] = echecs + 1
        st.error('Identifiant ou mot de passe incorrect.')
    return None
