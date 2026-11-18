"""Estimation des frais de gestion de la fiscalité foncière (CGI, art. 1641)."""
from decimal import Decimal, ROUND_HALF_UP

SOURCE = ('https://github.com/lexlib/code-general-des-impots/blob/bcc58eee8d4a12156aa7f567ffedb48f5293baa8/'
          '01.%20Livre%20premier%20%3A%20Assiette%20et%20liquidation%20de%20l%27imp%C3%B4t/'
          'Article%201641%20-%206311906.md')
TAUX_FRAIS = {'commune': 3, 'epci': 3, 'gemapi': 3, 'syndicat': 8, 'teom': 8}
MOTIF_TAXES_SPECIALES = ('Le taux de frais des taxes spéciales dépend du bénéficiaire. '
                         'Le référentiel les regroupe sans préciser le bénéficiaire.')


def estimer_frais(montants, annee, teom_incitative_debut=False):
    """Applique le barème aux cotisations estimées. Arrondi indicatif au centime."""
    if not 2023 <= int(annee) <= 2026:
        return None
    taux = {**TAUX_FRAIS, 'teom': 3 if teom_incitative_debut else 8}
    assiettes = {cle: Decimal(str(montant)) for cle, montant in montants.items()}
    frais = {cle: (assiettes[cle] * taux[cle] / 100).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
             for cle in taux if assiettes.get(cle)}
    incomplet = any(assiette for cle, assiette in assiettes.items() if cle not in taux)
    sous_total = sum(frais.values(), Decimal(0))
    return {
        'lignes': {cle: {'taux': taux[cle], 'montant': float(montant)} for cle, montant in frais.items()},
        'frais': float(sous_total),
        'total': None if incomplet else float((sum(assiettes.values()) + sous_total).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP)),
        'note': MOTIF_TAXES_SPECIALES if incomplet else '',
        'teom': taux['teom'] if assiettes.get('teom') else None,
    }


def afficher_frais(montants, annee, libelles, formater, cle, perimetre=''):
    import streamlit as st

    with st.expander('Frais de gestion estimés' + (f' · {perimetre}' if perimetre else '')):
        if not 2023 <= int(annee) <= 2026:
            st.caption('Le barème vérifié couvre les années d’imposition 2023 à 2026.')
            return None
        incitative = bool(montants.get('teom')) and st.checkbox(
            'La TEOM en est à l’une des cinq premières années avec part incitative',
            help='Cochez uniquement si la collectivité confirme l’année de mise en œuvre de la part incitative. '
                 'Le taux de frais est alors de 3 % au lieu de 8 %.',
            key=cle,
        )
        frais = estimer_frais(montants, annee, incitative)
        if frais['lignes']:
            st.table([{'Cotisation': libelles[k], 'Taux de frais': f"{ligne['taux']} %",
                       'Frais estimés': formater(ligne['montant'])} for k, ligne in frais['lignes'].items()])
        st.write(f"**{'Frais calculables' if frais['note'] else 'Frais de gestion'} : {formater(frais['frais'])}**")
        if frais['note']:
            st.info(frais['note'])
        st.caption(f'Calcul indicatif avant les arrondis de l’avis fiscal. [CGI, article 1641]({SOURCE})')
        return frais
