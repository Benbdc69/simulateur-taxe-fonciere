"""Estimation facultative de la cotisation principale de CFE."""
from decimal import Decimal, ROUND_HALF_UP

import streamlit as st

from montants import euro_arrondi
from neutralisation_cfe import rechercher_neutralisation_cfe
from session_calcul import cle_calcul
from taux_composantes import DGCL_PAGE, rechercher_dgcl

PARTS = {'commune': 'commune', 'epci': 'intercommunalité'}


def taux_cfe_public(code_insee, annee):
    taux = rechercher_dgcl(code_insee, annee, taxe='CFE')['taux']
    utiles = {k: taux[k] for k in PARTS if k in taux and 0 <= taux[k] <= 100}
    if not utiles:
        raise ValueError('Aucune part du taux voté n’est documentée.')
    return utiles


def afficher_cfe(code_insee, annee, valeur_locative=None):
    prefixe = cle_calcul(f'cfe_{code_insee}_{annee}')
    cle_public = prefixe + '_public'
    valeur = st.empty()
    with st.expander('Compléter l’estimation CFE'):
        st.caption(f'Les biens retenus pour la CFE {annee} sont en principe ceux utilisés en {annee - 2}.')
        methode = st.radio('Données de base CFE', ['Calculer depuis la valeur locative', 'Reprendre les bases de l’avis'],
                           key=prefixe + '_methode')
        if methode == 'Calculer depuis la valeur locative':
            utiliser_tf = valeur_locative is not None and st.checkbox(
                'Utiliser la valeur locative brute de la simulation de taxe foncière',
                help='Confirmez que le périmètre et la valeur locative de ce local sont applicables à la CFE simulée.',
                key=prefixe + '_utiliser_tf',
            )
            if utiliser_tf:
                vl = valeur_locative
                st.caption(f'Valeur locative brute retenue : {vl:,.2f} €'.replace(',', ' '))
            else:
                vl = st.number_input('Valeur locative brute applicable à la CFE (€)', min_value=0.0,
                                     value=None, step=1.0, key=prefixe + '_vl',
                                     help='Valeur avant abattement de taxe foncière et avant neutralisation.')
            cle_neutralisation = prefixe + '_publication_neutralisation'
            if st.button('Rechercher les coefficients CFE (DGFiP)', key=prefixe + '_chercher_neutralisation'):
                try:
                    with st.spinner('Recherche de la neutralisation CFE…'):
                        publies, source = rechercher_neutralisation_cfe(code_insee, annee)
                    st.session_state[cle_neutralisation] = publies, source
                    for part, coefficient in publies.items():
                        st.session_state[f'{prefixe}_neutralisation_{part}'] = coefficient
                except ValueError:
                    st.info('Aucun coefficient CFE n’a pu être récupéré. Vérifiez la publication DGFiP ou renseignez les coefficients documentés.')
            coefficients = {
                cle: st.number_input(f'Coefficient de neutralisation CFE · {libelle}', min_value=0.0,
                                     value=None, step=0.01, format='%.6f', key=f'{prefixe}_neutralisation_{cle}',
                                     help='Reprenez le coefficient propre à la CFE pour cette part. '
                                          'Saisissez 1 si vous avez confirmé qu’aucune neutralisation ne s’applique.')
                for cle, libelle in PARTS.items()
            }
            publication = st.session_state.get(cle_neutralisation)
            if publication:
                publies, source = publication
                parts = [PARTS[k] for k, coefficient in publies.items() if coefficients[k] == coefficient]
                if parts:
                    st.caption('Coefficient publié utilisé pour '+', '.join(parts)+f'. [Source DGFiP]({source})')
            bases = {
                cle: (Decimal(str(vl)) * Decimal(str(coefficient))).quantize(Decimal('1'), rounding=ROUND_HALF_UP)
                if vl is not None and coefficient is not None and coefficient > 0 else None
                for cle, coefficient in coefficients.items()
            }
            st.caption('Calcul de la base à partir de la valeur locative intégrale. '
                       'Si une base minimum, un planchonnement ou une réduction intervient, utilisez les bases nettes de l’avis.')
        else:
            distinctes = st.checkbox('Les bases CFE diffèrent entre les deux parts', key=prefixe + '_distinctes')
            base = st.number_input('Base nette de CFE · commune (€)' if distinctes else 'Base nette commune aux deux parts (€)',
                                   min_value=0.0, value=None, step=1.0, key=prefixe + '_base')
            base_epci = base
            if distinctes:
                base_epci = st.number_input('Base nette de CFE · intercommunalité (€)', min_value=0.0,
                                            value=None, step=1.0, key=prefixe + '_base_epci')
            bases = {'commune': base, 'epci': base_epci}
        if st.button('Rechercher les taux votés (DGCL)', key=prefixe + '_recherche'):
            try:
                with st.spinner('Recherche des taux de CFE…'):
                    public = taux_cfe_public(code_insee, annee)
                st.session_state[cle_public] = public
                for cle, taux in public.items():
                    st.session_state[f'{prefixe}_taux_{cle}'] = taux
            except ValueError:
                st.info('Aucun taux voté récupéré pour ce millésime. Reprenez les taux de votre avis de CFE.')
        taux = {cle: st.number_input(f'Taux CFE · {libelle} (%)', min_value=0.0, max_value=100.0,
                                     value=None, step=0.01, format='%.4f', key=f'{prefixe}_taux_{cle}')
                for cle, libelle in PARTS.items()}
        publies = st.session_state.get(cle_public, {})
        parts = [PARTS[k] for k, valeur in publies.items() if taux[k] == valeur]
        if parts:
            st.caption(f'Taux voté récupéré pour {", ".join(parts)} en {annee}. Vérifiez les parts sur l’avis. [Source DGCL]({DGCL_PAGE})')
        else:
            st.caption(f'[Consulter les taux votés publiés par la DGCL]({DGCL_PAGE})')
        st.caption('Saisissez 0 si l’avis confirme une part à taux nul. La cotisation estimée couvre les parts '
                   'communale et intercommunale, hors frais de gestion et taxes additionnelles.')

    if any(taux[cle] is None or (taux[cle] > 0 and bases[cle] is None) for cle in PARTS):
        valeur.metric('CFE pour ce local', 'À compléter')
    else:
        montant = sum(Decimal(str(bases[cle])) * Decimal(str(taux[cle])) / 100
                      for cle in PARTS if taux[cle])
        if methode == 'Calculer depuis la valeur locative':
            for cle, libelle in PARTS.items():
                if taux[cle]:
                    st.caption(f'Base CFE estimée · {libelle} : {euro_arrondi(bases[cle])}')
        valeur.metric('CFE estimée pour ce local', euro_arrondi(montant),
                      help='Parts communale et intercommunale hors frais et taxes additionnelles.')
