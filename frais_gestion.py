"""Estimation des frais de gestion de la fiscalité foncière (CGI, art. 1641)."""
from decimal import Decimal, ROUND_HALF_UP

SOURCE = ('https://github.com/lexlib/code-general-des-impots/blob/bcc58eee8d4a12156aa7f567ffedb48f5293baa8/'
          '01.%20Livre%20premier%20%3A%20Assiette%20et%20liquidation%20de%20l%27imp%C3%B4t/'
          'Article%201641%20-%206311906.md')
TAUX_FRAIS = {'commune': 3, 'epci': 3, 'gemapi': 3, 'syndicat': 8, 'teom': 8}
MOTIF_INCOMPLET = 'Le taux de frais de certaines cotisations est indéterminé.'


def estimer_frais(montants, annee, teom_incitative_debut=False, taux_taxes_speciales=9):
    """Applique le barème aux cotisations estimées. Arrondi indicatif au centime."""
    if not 2023 <= int(annee) <= 2026:
        return None
    if taux_taxes_speciales not in (8, 9):
        raise ValueError('Taux de frais des taxes spéciales attendu : 8 ou 9 %.')
    taux = {**TAUX_FRAIS, 'teom': 3 if teom_incitative_debut else 8,
            'taxes_speciales': taux_taxes_speciales}
    assiettes = {cle: Decimal(str(montant)) for cle, montant in montants.items()}
    frais = {cle: (assiettes[cle] * taux[cle] / 100).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
             for cle in taux if assiettes.get(cle)}
    incomplet = any(assiette for cle, assiette in assiettes.items() if cle not in taux)
    sous_total = sum(frais.values(), Decimal(0))
    notes = [MOTIF_INCOMPLET] if incomplet else []
    if assiettes.get('taxes_speciales'):
        notes.append(f'Taxes spéciales : frais estimés à {taux_taxes_speciales} %, selon le bénéficiaire retenu. '
                     'Vérifiez ce taux sur votre avis fiscal.')
    return {
        'lignes': {cle: {'taux': taux[cle], 'montant': float(montant)} for cle, montant in frais.items()},
        'frais': float(sous_total),
        'total': None if incomplet else float((sum(assiettes.values()) + sous_total).quantize(
            Decimal('0.01'), rounding=ROUND_HALF_UP)),
        'note': ' '.join(notes),
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
        taux_taxes_speciales = 9
        if montants.get('taxes_speciales'):
            taux_taxes_speciales = st.selectbox(
                'Taux de frais sur les taxes spéciales', [9, 8],
                format_func=lambda taux: f'{taux} % — ' + ('autre organisme' if taux == 9 else 'collectivité ou groupement'),
                key=cle + '_taxes_speciales',
                help='Les taxes spéciales sont regroupées dans le référentiel. Le taux de droit commun de 9 % '
                     'est proposé à titre indicatif. Choisissez 8 % si elles reviennent à une collectivité locale '
                     'ou à un groupement et que ce taux s’applique.',
            )
        frais = estimer_frais(montants, annee, incitative, taux_taxes_speciales)
        if frais['lignes']:
            st.table([{'Cotisation': libelles[k], 'Taux de frais': f"{ligne['taux']} %",
                       'Frais estimés': formater(ligne['montant'])} for k, ligne in frais['lignes'].items()])
        st.write(f"**{'Frais calculables' if frais['total'] is None else 'Frais de gestion'} : {formater(frais['frais'])}**")
        if frais['note']:
            st.info(frais['note'])
        st.caption(f'Calcul indicatif avant les arrondis de l’avis fiscal. [CGI, article 1641]({SOURCE})')
        return frais
