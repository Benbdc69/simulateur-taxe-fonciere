"""Dépendances H2 : rattachement explicite, surfaces et bases fiscales distinctes."""
from math import floor, isfinite

TYPES = {'piece': 'Pièce indépendante / chambre de service', 'garage': 'Garage, box ou parking privé',
         'cave': 'Grenier, cave ou autre rangement', 'agrement': 'Élément de pur agrément'}
MODES = {'incorporee': 'Rattachée au logement — même tarif', 'distincte': 'Évaluation distincte'}


def nombre(value, label, entier=False):
    try:
        n = float(value)
    except (ValueError, TypeError):
        raise ValueError(f'{label} : nombre invalide.') from None
    if isinstance(value, bool) or not isfinite(n) or n < 0 or (entier and not n.is_integer()):
        raise ValueError(f'{label} : valeur positive ou nulle attendue' + (' et entière.' if entier else '.'))
    return int(n) if entier else n


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
        r['surface_ponderee'] = floor(r['surface'] * r['coefficient']) if r['mode'] == 'incorporee' else 0
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
