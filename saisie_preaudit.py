"""Préparation du rapport Word à partir de la simulation professionnelle."""

import streamlit as st

from preaudit_word import MIME_WORD, VENTILATIONS, creer_word_preaudit
from session_calcul import cle_calcul


@st.dialog('Pré-audit professionnel', width='large')
def completer_preaudit(evaluation):
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
    st.download_button(
        'Télécharger le pré-audit Word',
        data=creer_word_preaudit(evaluation, audit),
        file_name=f"pre-audit_taxe_fonciere_{evaluation['annee']}.docx",
        mime=MIME_WORD,
        key=cle + '_telecharger_word',
    )


def actions_preaudit(evaluation):
    if st.button('Préparer le pré-audit Word', key=cle_calcul('ouvrir_preaudit')):
        completer_preaudit(evaluation)
