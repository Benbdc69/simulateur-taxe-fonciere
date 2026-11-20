"""Référentiel fiscal versionné, sans déductions silencieuses de données manquantes.

La DGFiP publie notamment les coefficients de neutralisation TF des périodes
2017-2020 et 2021+, sans nécessairement faire une nouvelle publication annuelle.
"""

from __future__ import annotations
from copy import deepcopy

DEPARTEMENTS = tuple([f'{i:02d}' for i in range(1, 96) if i != 20]
                    + ['2A', '2B', '971', '972', '973', '974', '976'])
NEUTRALISATIONS = ('2017-2020', '2021+')


def normaliser_departement(dep):
    dep = str(dep).strip().upper()
    if dep.isdecimal() and len(dep) <= 2:
        dep = dep.zfill(2)
    if dep not in DEPARTEMENTS:
        raise ValueError(f'Département « {dep} » non prévu dans le catalogue DGFiP. Vérifiez le code.')
    return dep


def activer_departement(ref, departement):
    dep = normaliser_departement(departement)
    ref.setdefault('tarifs', {}).setdefault(dep, {})
    ref.setdefault('localisations', {}).setdefault(dep, {})
    ref.setdefault('secteurs', {}).setdefault(dep, [])
    ref.setdefault('neutralisations', {}).setdefault(dep, [])  # Données historiques V1/V2/V3
    ref.setdefault('neutralisations_versions', {}).setdefault(dep, {})
    ref.setdefault('sources', {})
    return dep


def periode_neutralisation(annee):
    return '2017-2020' if int(annee) < 2021 else '2021+'


def lignes_neutralisation(ref, dep, annee):
    """Ne retourne jamais des données 2021+ pour une imposition 2020.

    Compatibilité descendante V3 : le champ neutralisations[dep] ne contient que
    les coefficients du classeur V3 étiquetés 2021+.
    """
    period = periode_neutralisation(annee)
    versions = ref.get('neutralisations_versions', {}).get(dep, {})
    if period in versions:
        return versions[period], period, 'DGFiP / référentiel millésimé'
    if period == '2021+':
        return ref.get('neutralisations', {}).get(dep, []), period, 'Référentiel historique importé (2021+)'
    return [], period, 'Coefficient 2017–2020 non chargé'


def integrer_jeu(ref, departement, nature, millesime, donnees, source):
    """Conserve chaque période de neutralisation, archive les sources séparément."""
    dep = activer_departement(ref, departement)
    millesime = int(millesime)
    if nature == 'tarifs':
        ref['tarifs'][dep][str(millesime)] = deepcopy(donnees)
        cle = f'{dep}/tarifs/{millesime}'
    elif nature == 'localisations':
        ref['localisations'][dep][str(millesime)] = deepcopy(donnees)
        cle = f'{dep}/localisations/{millesime}'
    elif nature == 'secteurs':
        ref['secteurs'][dep] = deepcopy(donnees)
        cle = f'{dep}/secteurs/2017'
    elif nature == 'neutralisations':
        periode = periode_neutralisation(millesime)
        ref['neutralisations_versions'][dep][periode] = deepcopy(donnees)
        if periode == '2021+':
            ref['neutralisations'][dep] = deepcopy(donnees)  # Conservation V3
        cle = f'{dep}/neutralisations/{2017 if periode == "2017-2020" else 2021}'
    else:
        raise ValueError('Nature de publication inconnue.')
    ref['sources'][cle] = deepcopy(source)
    return cle


def publication_attendue(annee, inclure_historique=False):
    """Liste des publications existantes: ne suppose pas une localisation annuelle.

    Pour l'année 2026, secteurs de 2017, localisations de 2026,
    neutralisation de 2021 en vigueur, tarifs de 2026.
    """
    annee = int(annee)
    if not 2017 <= annee <= 2026:
        raise ValueError('La simulation ne modélise pas les règles 2027 et suivantes.')
    dispo_loc = [2017, 2018, 2019, 2020, 2024, 2026]
    loc = max(y for y in dispo_loc if y <= annee)
    spec = [('tarifs', annee), ('secteurs', 2017),
            ('neutralisations', 2021 if annee >= 2021 else 2020)]
    spec.insert(1, ('localisations', loc))
    if inclure_historique and annee >= 2021:
        spec.append(('neutralisations', 2020))
    return spec
