"""Préparation des scénarios habitation, indépendante de l'interface et du réseau."""
from moteur_habitation import CATEGORIES, surface_totale, simulations_tarifs
from facteurs_habitation import facteur_departement_annee
from historique_taux import COMPOSANTES, resoudre_tout
from tarifs_habitation import rechercher_tarifs


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
    if categorie is not None and categorie not in CATEGORIES:
        raise ValueError('Catégorie cadastrale inconnue.')
    categories = [categorie] if categorie else sorted(CATEGORIES, key=lambda x: (int(x[0]), len(x)))
    scenarios = []
    for cat in categories:
        rows = rechercher_tarifs(code, saisie['nature'], cat, rows=tarifs)
        if not rows:
            continue
        sp = surface_totale(saisie['surface'], saisie['nature'], cat, **saisie['parametres'])
        for scenario in simulations_tarifs(sp['surface_ponderee'], rows, facteur['coefficient_cumule'], taux if complet else None):
            scenarios.append({**scenario, 'categorie': cat, 'surfaces': sp})
    if not scenarios:
        raise ValueError('Aucun tarif public pour cette commune et ce type de logement'
                         + (f' en catégorie {categorie}.' if categorie else '.'))
    return {'adresse': adresse['libelle'], 'code_insee': code, 'annee': annee,
            'nature': 'Maison (H1)' if saisie['nature'] == 'M' else 'Appartement (H2)',
            'categorie_inconnue': categorie is None, 'facteur': facteur,
            'surface_reelle': saisie['surface'],
            'terrasse_reelle': saisie['parametres'].get('terrasse', 0),
            'autres_dependances': saisie['parametres'].get('annexes', 0),
            'tarifs': scenarios, 'taux': rates, 'taux_complets': complet}
