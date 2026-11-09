"""Référentiel officiel des revalorisations métropolitaines H1/H2 (1970 -> 2026)."""
from __future__ import annotations
import json
import unicodedata
from pathlib import Path
ROOT=Path(__file__).resolve().parent
FICHIER=ROOT/'data'/'habitation_facteurs.json'

def _norm(x):
    return ''.join(c for c in unicodedata.normalize('NFKD',str(x).lower()) if not unicodedata.combining(c)).replace('-',' ').replace("'",' ')

def departement_insee(code):
    code=str(code or '').strip().upper()
    if code.startswith(('97','98')):return None # 1970 non applicable aux DOM et Mayotte
    if code.startswith(('2A','2B')):return code[:2]
    if len(code)!=5 or not code.isdigit():raise ValueError('Code INSEE invalide')
    return code[:2]

def facteur_departement_annee(code_insee,annee,commune=''):
    y=str(int(annee)); dep=departement_insee(code_insee)
    if dep is None:raise ValueError('Le référentiel 1970 métropolitain ne couvre pas les DROM/Mayotte.')
    data=json.loads(FICHIER.read_text(encoding='utf-8'))
    national=data.get('coefficients_amalgames', {}).get(y)
    if national is None:
        national=data.get('coefficients_amalgames_1981_2026', {}).get(y)
    if national is None:raise ValueError(f'Coefficient officiel de revalorisation {y} non disponible dans le référentiel. Le millésime doit être actualisé avant de chiffrer cette année ; aucun coefficient antérieur n’est extrapolé.')
    actual=data['coefficient_1980'].get(dep)
    if actual is None:raise ValueError('Coefficient départemental 1980 non renseigné.')
    if dep in ('21','54'):
        if not commune:raise ValueError(f'La commune est nécessaire pour le coefficient spécial du département {dep}.')
        v=_norm(commune)
        if dep=='21':
            spec=data['exceptions_1980'][dep]
            if any(_norm(x) in v for x in spec['communes']):actual=spec['coefficient']
            else:actual=spec['autres']
        else:
            spec=data['exceptions_1980'][dep]
            actual=spec['coefficient'] if _norm(spec['commune']) in v else spec['autres']
    source = data.get('sources_revalorisation', {}).get(y)
    if source is None:
        if int(annee) > 2026:
            raise ValueError(f'Source du coefficient officiel {y} non renseignée.')
        source = data['source_2026'] if int(annee)>=2026 else data['source_2025'] if int(annee)>=2025 else data['source_1980']
    return {'departement':dep,'annee':int(annee),'actualisation_1980':float(actual),
            'revalorisation_nationale':float(national),'coefficient_cumule':round(float(actual)*float(national),9),
            'source_departement':data['source_1980'],
            'source_revalorisation':source,
            'precision':data['precision']}
