"""Estimation de la cotisation principale minimum de CFE dans le portail."""
from datetime import date
import re

import streamlit as st

from cfe_minimum.calcul_cfe import calculer_cfe_minimum
from cfe_minimum.cfe_rei import CODE_INSEE
from cfe_minimum.millesimes import recuperer_pour_annee
from recherche_bien import rechercher_communes_locales
from session_calcul import cle_calcul


@st.cache_data(ttl=86400, show_spinner=False)
def charger_bareme(code_insee, annee):
    return recuperer_pour_annee(code_insee, annee)


def choisir_commune():
    texte = st.text_input(
        'Commune ou code INSEE',
        key=cle_calcul('cfe_commune'),
        help='Saisissez le nom de la commune ou son code INSEE à cinq caractères.',
    ).strip()
    if CODE_INSEE.fullmatch(texte.upper()):
        return texte.upper()
    if len(texte) < 2:
        return None

    communes = {
        item['insee']: f"{item['commune']} · {item['departement']} · INSEE {item['insee']}"
        for item in rechercher_communes_locales(texte, '')
    }
    if not communes:
        st.warning('Aucune commune trouvée. Vérifiez le nom ou saisissez le code INSEE.')
        return None
    return st.selectbox(
        'Commune à retenir',
        options=list(communes),
        index=None,
        format_func=communes.__getitem__,
        key=cle_calcul(f'cfe_choix_{texte.casefold()}'),
    )


def afficher_resultat(selection, resultat):
    st.subheader(f"{resultat['commune']} ({resultat['code_insee']})")
    annee = selection['annee_utilisee']
    if selection['estimation_n_moins_1']:
        st.warning(f"Estimation de la CFE {selection['annee_demandee']} avec la base et le taux REI {annee} (N−1).")
    else:
        st.caption(f'Millésime des données REI {annee}')
    cotisation, base, taux = st.columns(3)
    cotisation.metric('Cotisation minimum estimée', f"{resultat['cotisation_principale_minimum']:.2f} €".replace('.', ','))
    base.metric('Base minimum retenue', f"{resultat['base_minimum']:.2f} €".replace('.', ','))
    taux.metric('Taux de CFE hors zone', f"{resultat['taux_cfe_pct']:g} %".replace('.', ','))
    if resultat['exonere_cotisation_minimum']:
        st.info('Jusqu’à 5 000 € de chiffre d’affaires, vous êtes exonéré de cotisation minimum.')
    with st.expander('Barème local publié'):
        st.dataframe(selection['donnees']['base_minimum_eur'], hide_index=True)
    if resultat['url_page']:
        st.link_button('Consulter la source', resultat['url_page'])
    if resultat['citation']:
        st.caption(resultat['citation'])


st.title('CFE – Base minimum')
st.caption('Estimation de la cotisation principale sur base minimum, hors taxes additionnelles et frais de gestion.')
code = choisir_commune()
annee = st.number_input(
    'Année de CFE',
    min_value=2010,
    max_value=date.today().year + 1,
    value=None,
    step=1,
    key=cle_calcul('cfe_annee'),
)
libelle_ca = f'Chiffre d’affaires HT {annee - 2} (€)' if annee else 'Chiffre d’affaires HT N−2 (€)'
texte_ca = st.text_input(
    libelle_ca,
    key=cle_calcul('cfe_ca'),
    help='Saisissez le chiffre d’affaires fiscal de référence, annualisé si nécessaire.',
)
if code and annee and texte_ca.strip():
    ca = re.sub(r'\s', '', texte_ca)
    if not re.fullmatch(r'[0-9]+(?:[,.][0-9]{1,2})?', ca):
        st.error('Saisissez un chiffre d’affaires HT positif ou nul, en euros.')
    else:
        try:
            with st.spinner(f'Recherche du REI {annee}…'):
                selection = charger_bareme(code, annee)
                resultat = calculer_cfe_minimum(selection['donnees'], ca)
        except (ValueError, RuntimeError) as exc:
            st.error(str(exc))
        else:
            afficher_resultat(selection, resultat)
