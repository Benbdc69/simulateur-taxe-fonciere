"""Dépendances H2 : rattachement explicite, surfaces et bases fiscales distinctes."""
from math import floor, isfinite
from decimal import Decimal, ROUND_FLOOR
from referentiel_formulaires import SURFACES_DEP_H1

TYPES = {'piece': 'Pièce indépendante / chambre de service', 'garage': 'Garage, box ou parking privé',
         'cave': 'Grenier, cave ou autre rangement', 'agrement': 'Élément de pur agrément', 'batiment_h1':'Dépendance H1 détaillée'}
MODES = {'incorporee': 'Rattachée au logement — même tarif', 'distincte': 'Évaluation distincte'}


def nombre(value, label, entier=False):
    try:
        n = float(value)
    except (ValueError, TypeError):
        raise ValueError(f'{label} : nombre invalide.') from None
    if isinstance(value, bool) or not isfinite(n) or n < 0 or (entier and not n.is_integer()):
        raise ValueError(f'{label} : valeur positive ou nulle attendue' + (' et entière.' if entier else '.'))
    return int(n) if entier else n


SOURCE_PONDERATION = 'https://www.impots.gouv.fr/www2/fichiers/documentation/brochure/idl/idl_2025.pdf'


def ponderer_surface(surface, coefficient):
    """Articles 324 M/N : surface réelle puis pondérée arrondies au m² inférieur."""
    reelle = floor(nombre(surface, 'Surface'))
    coeff = nombre(coefficient, 'Coefficient de pondération')
    if not .2 <= coeff <= .6:
        raise ValueError('Coefficient de pondération attendu entre 0,2 et 0,6.')
    produit = Decimal(reelle) * Decimal(str(coeff))
    return int(produit.to_integral_value(rounding=ROUND_FLOOR))


def valider_dependances(lignes):
    resultat = []
    for i, ligne in enumerate(lignes or [], 1):
        if not isinstance(ligne, dict):
            raise ValueError('Format de dépendance invalide.')
        r = dict(ligne)
        if r.get('type') not in TYPES:
            raise ValueError(f'Dépendance {i} : choisissez un type.')
        if r.get('mode') not in MODES:
            raise ValueError(f'Dépendance {i} : choisissez un rattachement ou une évaluation distincte.')
        r['designation'] = str(r.get('designation') or TYPES[r['type']]).strip()
        r['situation'] = str(r.get('situation') or '').strip()
        r['lot'] = str(r.get('lot') or '').strip()
        if r['type']=='batiment_h1':
            composition=r.get('composition', {})
            if not isinstance(composition,dict) or set(composition)-set(SURFACES_DEP_H1) or any(not isinstance(v,dict) for v in composition.values()):
                raise ValueError('Rubriques de surfaces H1 invalides.')
            r['composition']={k:{'surface':nombre(v.get('surface',0),k), 'coefficient':nombre(v.get('coefficient',.4),k)} for k,v in composition.items()}
            r['surface']=sum(v['surface'] for v in r['composition'].values())
            if r['mode']=='incorporee' and r['composition'].get('agrement',{}).get('surface',0):
                raise ValueError('Les éléments de pur agrément doivent être évalués distinctement.')
        r['surface'] = nombre(r.get('surface', 0), f'Dépendance {i}, surface')
        if r['surface'] <= 0:
            raise ValueError(f'Dépendance {i} : renseignez une surface supérieure à zéro.')
        r['coefficient'] = nombre(r.get('coefficient', .4), f'Dépendance {i}, pondération')
        if r['mode'] == 'incorporee' and not .2 <= r['coefficient'] <= .6:
            raise ValueError(f'Dépendance {i} : pondération attendue entre 0,2 et 0,6.')
        for cle in ('wc', 'baignoires', 'douches', 'lavabos', 'pieces_chauffees'):
            r[cle] = nombre(r.get(cle, 0), f'Dépendance {i}, {cle}', entier=True) if r['type'] == 'piece' else 0
        r['eau'] = bool(r.get('eau', False))
        r['electricite'] = bool(r.get('electricite', False))
        r['base_tf'] = None if r.get('base_tf') is None else nombre(r['base_tf'], f'Dépendance {i}, base fiscale')
        r['taux_logement_confirmes'] = bool(r.get('taux_logement_confirmes', False))
        r['surface_ponderee'] = ponderer_surface(r['surface'], r['coefficient']) if r['mode'] == 'incorporee' else 0
        if r['type']=='batiment_h1' and r['mode']=='incorporee':
            r['surface_ponderee']=sum(ponderer_surface(v['surface'],v['coefficient']) for v in r['composition'].values() if v['surface'])
        r['equivalence_confort'] = ((4 if r['eau'] else 0) + (2 if r['electricite'] else 0)
            + 3*r['wc'] + 5*r['baignoires'] + 4*r['douches'] + 3*r['lavabos'] + 2*r['pieces_chauffees']) if r['mode'] == 'incorporee' else 0
        resultat.append(r)
    return resultat


def evaluer_distinctes(lignes, taux, taux_complets):
    resultats = []
    for ligne in lignes:
        if ligne['mode'] != 'distincte':
            continue
        r = dict(ligne)
        if r['base_tf'] is not None and r['taux_logement_confirmes'] and taux_complets:
            r['montants'] = {k: round(r['base_tf'] * float(v) / 100, 2) for k, v in taux.items()}
            r['total'] = round(sum(r['montants'].values()), 2)
        resultats.append(r)
    return resultats
