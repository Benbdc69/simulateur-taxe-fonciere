"""Consultation des évaluations enregistrées par l'équipe."""

from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from acces_dossiers import configuration_dossiers, demander_acces_dossiers, stockage_configure
from montants import euro_arrondi
from preaudit_word import VENTILATIONS, bilan_preaudit
from saisie_preaudit import ERREURS_STOCKAGE, telecharger_word


st.title('Dossiers clients')
configuration = configuration_dossiers()
if not configuration:
    st.info('Configurez le stockage pour accéder aux dossiers clients.')
    st.stop()
identite = demander_acces_dossiers()
if not identite:
    st.stop()
nom, role = identite
st.caption(f'Compte · {nom}')
if st.button('Se déconnecter des dossiers', type='tertiary'):
    st.session_state.pop('_dossiers_identite', None)
    st.rerun()

try:
    base = stockage_configure(**configuration)
    societes = {cle: (libelle, lien) for cle, libelle, lien in base.societes()}
except ERREURS_STOCKAGE:
    st.error('Le stockage des dossiers est momentanément indisponible.')
    st.stop()

if not societes:
    st.info('Enregistrez une première évaluation depuis le parcours professionnel.')
    st.stop()
societe = st.selectbox('Société', list(societes), format_func=lambda cle: societes[cle][0])
nom_societe, lien = societes[societe]
if lien:
    st.link_button('Ouvrir le dossier documentaire', lien)
if role == 'edition':
    with st.expander('Modifier le lien documentaire'):
        with st.form('lien_documentaire_' + societe):
            nouveau_lien = st.text_input('Lien HTTPS du dossier', value=lien, max_chars=1500)
            actualiser = st.form_submit_button('Enregistrer le lien')
        if actualiser:
            try:
                base.modifier_lien(societe, nouveau_lien)
            except ValueError as exc:
                st.error(str(exc))
            except ERREURS_STOCKAGE:
                st.error('La mise à jour du lien a échoué.')
            else:
                st.rerun()

try:
    evaluations = base.evaluations(societe)
except ERREURS_STOCKAGE:
    st.error('Les évaluations de cette société sont momentanément indisponibles.')
    st.stop()
if not evaluations:
    st.info('Aucune évaluation enregistrée pour cette société.')
    st.stop()
locaux = list(dict.fromkeys((local, adresse) for _, local, adresse, *_ in evaluations))
local, adresse = st.selectbox('Local', locaux,
                              format_func=lambda l: l[0] if l[0] == l[1] else ' · '.join(l),
                              key='dossiers_local_' + societe)
versions = {}
for identifiant, libelle, adresse_version, annee, date, auteur in evaluations:
    if (libelle, adresse_version) == (local, adresse):
        date_locale = datetime.fromisoformat(date).astimezone(ZoneInfo('Europe/Paris'))
        versions[identifiant] = f"{annee} · {date_locale:%d/%m/%Y à %H:%M:%S} · {auteur}"
version = st.selectbox('Évaluation enregistrée', list(versions), format_func=versions.__getitem__)
try:
    fiche = base.lire(societe, version)
except ERREURS_STOCKAGE:
    st.error('Cette évaluation est momentanément indisponible.')
    st.stop()
if not fiche:
    st.error('Cette évaluation est indisponible.')
    st.stop()
evaluation, audit = fiche['evaluation'], fiche['audit']
bilan = bilan_preaudit(evaluation, audit)
colonnes = st.columns(3)
for colonne, cle, titre in zip(colonnes, ('avis', 'estimation', 'ecart'),
                               ('Montant de l’avis', 'Estimation', 'Écart indicatif')):
    montant = bilan[cle]
    colonne.metric(titre, euro_arrondi(montant) if montant is not None else '—')
st.caption(VENTILATIONS[audit.get('ventilation', 'inconnue')])
if audit.get('observation'):
    st.text(audit['observation'])
st.write(bilan['suite'])
telecharger_word(evaluation, audit, societe=nom_societe, local=local)
with st.expander('Détail de l’évaluation enregistrée'):
    st.caption(f"{evaluation['adresse']} · {evaluation['annee']} · {evaluation['categorie']}")
    st.table([{'Surface': cle, 'm² saisis': valeur} for cle, valeur in evaluation['surfaces'].items()])
    mesures = evaluation.get('mesures') or {}
    if mesures.get('surface_batie') is not None:
        st.caption(f"Surface bâtie mesurée · {mesures['surface_batie']:g} m²")
    if mesures.get('pk2') is not None:
        st.caption(f"Stationnement non couvert mesuré · {mesures['pk2']:g} m²")
    analyse = evaluation['analyse']
    lignes = (analyse.get('result') or {}).get('lignes', [])
    if lignes:
        st.table([{'Taxe': ligne['taxe'], 'Base (€)': ligne['base_taxable'],
                   'Taux (%)': ligne['taux_pct'], 'Cotisation (€)': ligne['montant']}
                  for ligne in lignes])
    if analyse.get('missing'):
        st.caption('Données manquantes · ' + ', '.join(analyse['missing']))
