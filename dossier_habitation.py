"""Préparation des scénarios habitation, indépendante de l'interface et du réseau."""
from moteur_habitation import CATEGORIES, surface_totale, simulations_tarifs
from facteurs_habitation import facteur_departement_annee
from historique_taux import COMPOSANTES, resoudre_tout
from tarifs_habitation import rechercher_tarifs
from formulaire_h1 import valider_description_h1
from dependances_habitation import valider_dependances, evaluer_distinctes, nombre

from referentiel_formulaires import PIECES_HABITATION as H2_PIECES


def compter_pieces_chauffees(description, modele):
    pieces = description.get('pieces', {})
    if set(pieces) - set(H2_PIECES):
        raise ValueError(f'Rubrique de consistance {modele} inconnue.')
    quantites = {cle: nombre(valeur, f'Nombre de pièces {modele}', entier=True)
                 for cle, valeur in pieces.items()}
    if not sum(quantites.values()):
        raise ValueError(f'Renseignez au moins une pièce dans le cadre 41 du {modele}.')
    if not description.get('chauffage'):
        return 0
    return sum(qte for cle, qte in quantites.items() if cle != 'autres_annexes')


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
    if saisie['nature']=='M' and saisie.get('h1') is not None:
        valider_description_h1(saisie['h1'])
    h2 = saisie.get('h2') if saisie['nature'] == 'A' else None
    description = saisie.get('h1') if saisie['nature'] == 'M' else h2
    params = dict(saisie['parametres'])
    if description is not None:
        modele = 'H1' if saisie['nature'] == 'M' else 'H2'
        params['pieces_chauffees'] = compter_pieces_chauffees(description, modele)
    chauffage = {'pieces_chauffage_scenario': params['pieces_chauffees']} if description and description.get('chauffage') else {}
    reserves = []
    if h2 is not None:
        if h2.get('partie_professionnelle'):
            reserves.append('Local mixte : seule la surface affectée à l’habitation est simulée. La partie professionnelle et sa déclaration 6660-REV doivent être traitées séparément.')
        if h2.get('escalier_service'):
            reserves.append('Escalier de service déclaré : information conservée, sans correctif supplémentaire automatique.')
    dependances = valider_dependances(saisie.get('dependances', []))
    for d in dependances:
        if d['mode'] == 'distincte' and d['base_tf'] is not None and d.get('annee_base') != annee:
            raise ValueError('La base de la dépendance doit être documentée pour l’année simulée.')
    distinctes = evaluer_distinctes(dependances, taux, complet)
    dependances_completes = all('total' in d for d in distinctes)
    if saisie['nature']=='M' and saisie.get('h1',{}).get('partie_professionnelle'):
        reserves.append('Maison comportant une partie professionnelle : seule la surface affectée à l’habitation est simulée. La partie professionnelle et sa déclaration 6660-REV sont à traiter séparément.')
    rows = rechercher_tarifs(code, saisie['nature'], categorie, rows=tarifs)
    if not rows:
        raise ValueError(f'Aucun tarif public pour cette commune et ce type de logement en catégorie {categorie}.')
    sp = surface_totale(saisie['surface'], saisie['nature'], categorie, dependances=dependances, **params)
    scenarios = simulations_tarifs(sp['surface_ponderee'], rows, facteur['coefficient_cumule'], taux if complet else None)
    for scenario in scenarios:
        if dependances_completes and 'total' in scenario:
            scenario['total_bien'] = round(scenario['total'] + sum(d['total'] for d in distinctes), 2)
        scenario.update(categorie=categorie, surfaces=sp, **chauffage)
    return {'adresse': adresse['libelle'], 'parcelle': adresse.get('parcelle'), 'code_insee': code, 'annee': annee,
            'nature': 'Maison (H1)' if saisie['nature'] == 'M' else 'Appartement (H2)',
            'categorie': categorie, 'categorie_inconnue': False,
            'categorie_confirmee': bool(saisie.get('categorie_confirmee')), 'facteur': facteur,
            'surface_reelle': saisie['surface'],
            'terrasse_reelle': saisie['parametres'].get('terrasse', 0),
            'autres_dependances': saisie['parametres'].get('annexes', 0) + sum(e['surface'] for e in saisie['parametres'].get('elements_incorpores', {}).values()) + sum(d['surface'] for d in dependances),
            'dependances': dependances, 'dependances_distinctes': distinctes,
            'dependances_completes': dependances_completes,
            'tarifs': scenarios, 'taux': rates, 'taux_complets': complet,
            'h1':saisie.get('h1') if saisie['nature']=='M' else None, 'h2': h2, 'reserves_h2': reserves}
