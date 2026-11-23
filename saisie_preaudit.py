"""Préparation du rapport Word et enregistrement dans un dossier client."""

import sqlite3

from psycopg import Error as ErreurPostgreSQL
import streamlit as st

from acces_dossiers import configuration_dossiers, demander_acces_dossiers, stockage_configure
from preaudit_word import MIME_WORD, VENTILATIONS, creer_word_preaudit
from session_calcul import cle_calcul


ERREURS_STOCKAGE = (sqlite3.Error, ErreurPostgreSQL, OSError)


def telecharger_word(evaluation, audit, *, societe='', local=''):
    st.download_button(
        'Télécharger le pré-audit Word',
        data=creer_word_preaudit(evaluation, audit, societe=societe, local=local),
        file_name=f"pre-audit_taxe_fonciere_{evaluation['annee']}.docx",
        mime=MIME_WORD,
        key=cle_calcul('preaudit_telecharger_word'),
    )


@st.dialog('Pré-audit professionnel', width='large')
def completer_preaudit(evaluation, *, enregistrer=False):
    cle = cle_calcul('preaudit')
    brouillon = st.session_state.get('_brouillon_preaudit', {})
    for champ, defaut in (
        ('montant_avis', None), ('ventilation', 'inconnue'), ('observation', ''),
        ('surface_batie', (evaluation.get('mesures') or {}).get('surface_batie')),
    ):
        st.session_state.setdefault(f'{cle}_{champ}', brouillon.get(champ, defaut))
    montant_avis = st.number_input(
        'Montant de l’avis pour ce local (€)', min_value=0.0, max_value=1e9, step=1.0,
        value=None, key=cle + '_montant_avis',
        help='Facultatif. Indiquez le total du même local et du même millésime, avec la TEOM et les frais '
             'sur le même périmètre que l’estimation.',
    )
    ventilation = st.selectbox(
        'Origine de la ventilation P1/P2', list(VENTILATIONS),
        format_func=VENTILATIONS.__getitem__, key=cle + '_ventilation',
    )
    surface_batie = brouillon.get('surface_batie', (evaluation.get('mesures') or {}).get('surface_batie'))
    if ventilation == 'inconnue':
        surface_batie = st.number_input(
            'Surface bâtie totale mesurée (m²)', min_value=0.0, max_value=1e6, step=1.0, value=None,
            key=cle + '_surface_batie', help='Facultatif. Le rapport peut restituer cette mesure avec la ventilation à confirmer.',
        )
    observation = st.text_area('Observation pour le rapport', key=cle + '_observation', max_chars=450,
                              placeholder='Facultatif')
    audit = {
        'montant_avis': montant_avis, 'ventilation': ventilation,
        'surface_batie': surface_batie, 'observation': observation.strip(),
    }
    st.session_state['_brouillon_preaudit'] = audit

    if not enregistrer:
        telecharger_word(evaluation, audit)
        return
    identite = demander_acces_dossiers()
    if not identite:
        return
    nom, role = identite
    if role != 'edition':
        st.info('Votre compte dispose d’un accès en lecture aux dossiers.')
        return
    try:
        base = stockage_configure(**configuration_dossiers())
        societes = {cle: libelle for cle, libelle, _ in base.societes()}
    except ERREURS_STOCKAGE:
        st.error('Le stockage des dossiers est momentanément indisponible.')
        return
    st.subheader('Dossier client')
    societe = st.selectbox('Société', [None, *societes], key=cle + '_societe',
                           format_func=lambda choix: societes.get(choix, 'Nouvelle société'))
    nom_societe = societes[societe] if societe else st.text_input('Nom de la société', max_chars=160,
                                                                 key=cle + '_nom_societe')
    local = st.text_input('Référence du local (facultative)', max_chars=120, key=cle + '_local',
                          help='Permet de distinguer des locaux situés à la même adresse.')
    lien = st.text_input('Lien documentaire (facultatif)', max_chars=1500, key=cle + '_lien',
                         placeholder='https://…')
    if st.button('Enregistrer l’évaluation', type='primary', key=cle + '_enregistrer'):
        try:
            base.enregistrer(nom_societe, evaluation, audit, nom, local=local, lien=lien)
        except ValueError as exc:
            st.error(str(exc))
        except ERREURS_STOCKAGE:
            st.error('L’enregistrement a échoué. Réessayez dans un instant.')
        else:
            st.success('Évaluation enregistrée dans ' + ' '.join(nom_societe.split()) + '.')
    telecharger_word(evaluation, audit, societe=' '.join(nom_societe.split()), local=local.strip())


def actions_preaudit(evaluation):
    if st.button('Préparer le pré-audit Word', key=cle_calcul('ouvrir_preaudit')):
        completer_preaudit(evaluation)
    if configuration_dossiers() and st.button('Enregistrer dans un dossier', key=cle_calcul('ouvrir_enregistrement')):
        completer_preaudit(evaluation, enregistrer=True)
