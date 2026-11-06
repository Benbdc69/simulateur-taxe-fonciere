"""Préparation des scénarios habitation, indépendante de l'interface et du réseau."""
from moteur_habitation import CATEGORIES, surface_totale, simulations_tarifs
from facteurs_habitation import facteur_departement_annee
from historique_taux import COMPOSANTES, resoudre_tout
from tarifs_habitation import rechercher_tarifs
from math import isfinite

H2_PIECES = {
    'reception': 'Salles à manger et pièces de réception',
    'chambres': 'Chambres et autres pièces habitables',
    'cuisines_moins_9': 'Cuisines de moins de 9 m²',
    'cuisines_9_plus': 'Cuisines de 9 m² et plus',
    'salles_eau': 'Salles d’eau',
    'autres_annexes': 'Autres annexes intérieures',
}


def hypotheses_chauffage_h2(h2):
    """Le H2 décrit la consistance et la présence, pas la desserte du chauffage.

    Les bornes sont des hypothèses de sensibilité du moteur existant (2 m²
    par pièce desservie), pas un classement ni une règle d'affectation automatique.
    """
    pieces = h2.get('pieces', {})
    if set(pieces) - set(H2_PIECES):
        raise ValueError('Rubrique de consistance H2 inconnue.')
    total = 0
    for value in pieces.values():
        n = float(value)
        if isinstance(value, bool) or not isfinite(n) or n < 0 or not n.is_integer():
            raise ValueError('Les nombres de pièces H2 doivent être des entiers positifs ou nuls.')
        total += int(n)
    if not total:
        raise ValueError('Renseignez au moins une pièce dans le cadre 41 du H2.')
    return [0, total] if h2.get('chauffage') else [0]


def code_adresse(adresse):
    """Utilise l'adresse confirmée, jamais la première parcelle voisine."""
    code = str(adresse.get('insee') or '').strip().upper()
    postal = str(adresse.get('code_postal') or '')
    if code in ('', '69123') and postal in {f'6900{i}' for i in range(1, 10)}:
        code = '6938' + postal[-1]
    return code


def calculer_scenarios(saisie, adresse, referentiel, tarifs):
    code = code_adresse(adresse)
    annee = int(saisie['annee'])
    facteur = facteur_departement_annee(code, annee, adresse.get('commune', ''))
    rates = resoudre_tout(referentiel, code, annee)
    taux = {k: r['taux'] for k, r in rates.items() if r and r.get('taux') is not None}
    complet = all(k in taux for k in COMPOSANTES)
    categorie = saisie.get('categorie')
    if categorie not in CATEGORIES:
        raise ValueError('Choisissez une catégorie cadastrale avant de calculer.')
    categories = [categorie]
    h2 = saisie.get('h2') if saisie['nature'] == 'A' else None
    hypotheses = hypotheses_chauffage_h2(h2) if h2 is not None else [None]
    reserves = []
    if h2 is not None:
        if h2.get('chauffage'):
            reserves.append('Chauffage déclaré au H2 : la desserte des pièces n’est pas précisée. Les scénarios sans équivalence chauffage et avec toutes les pièces déclarées desservies sont des hypothèses de sensibilité, à confirmer sur la fiche cadastrale.')
        if h2.get('partie_professionnelle'):
            reserves.append('Local mixte : seule la surface affectée à l’habitation est simulée. La partie professionnelle et sa déclaration 6660-REV doivent être traitées séparément.')
        if h2.get('escalier_service'):
            reserves.append('Escalier de service déclaré : information conservée, sans correctif supplémentaire automatique.')
    scenarios = []
    for cat in categories:
        rows = rechercher_tarifs(code, saisie['nature'], cat, rows=tarifs)
        if not rows:
            continue
        for nombre in hypotheses:
            params = dict(saisie['parametres'])
            if nombre is not None:
                # Une ancienne saisie manuelle ne doit pas survivre au passage au H2.
                params['pieces_chauffees'] = nombre
            sp = surface_totale(saisie['surface'], saisie['nature'], cat, **params)
            for scenario in simulations_tarifs(sp['surface_ponderee'], rows, facteur['coefficient_cumule'], taux if complet else None):
                scenarios.append({**scenario, 'categorie': cat, 'surfaces': sp,
                                  **({'pieces_chauffage_scenario': nombre} if h2 and h2.get('chauffage') else {})})
    if not scenarios:
        raise ValueError('Aucun tarif public pour cette commune et ce type de logement'
                         + (f' en catégorie {categorie}.' if categorie else '.'))
    return {'adresse': adresse['libelle'], 'code_insee': code, 'annee': annee,
            'nature': 'Maison (H1)' if saisie['nature'] == 'M' else 'Appartement (H2)',
            'categorie': categorie, 'categorie_inconnue': False,
            'categorie_confirmee': bool(saisie.get('categorie_confirmee')), 'facteur': facteur,
            'surface_reelle': saisie['surface'],
            'terrasse_reelle': saisie['parametres'].get('terrasse', 0),
            'autres_dependances': saisie['parametres'].get('annexes', 0),
            'tarifs': scenarios, 'taux': rates, 'taux_complets': complet,
            'h2': h2, 'reserves_h2': reserves}
