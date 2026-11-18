"""Lecture des seuls coefficients explicitement rattachés à la CFE."""
from math import isfinite

import requests

from imports_dgfip import _as_number, _get, _labels, _match_col, feuilles, telecharger, url_fichier
from moteur import norm
from taux_composantes import _code_raw, code_commune_fiscale, siren_epci


def lire_neutralisation_cfe(contenu, source, code_insee, siren=None):
    code = code_commune_fiscale(code_insee)
    valeurs = {'commune': set(), 'epci': set()}
    for feuille, lignes in feuilles(contenu, source):
        titre = norm(feuille)
        feuille_cfe = ('CFE' in titre or 'COTISATIONFONCIEREDESENTREPRISES' in titre) and 'TFPB' not in titre
        for debut in range(min(40, len(lignes))):
            for span in (1, 2, 3):
                labels = _labels(lignes, debut, span)
                col_code = _match_col(labels, 'code_commune')
                col_siren = next((i for i, libelle in enumerate(labels)
                                  if libelle in ('SIREN', 'SIRENEPCI', 'NUMEROSIREN', 'CODEEPCI')), None)
                if col_code is None and col_siren is None:
                    continue
                for i, libelle in enumerate(labels):
                    if i in (col_code, col_siren) or any(
                        mot in libelle for mot in ('TFPB', 'TAXEFONCIERE', 'TEOM', 'TAUX', 'BASE', 'CODESIREN')
                    ):
                        continue
                    cfe = 'CFE' in libelle or 'COTISATIONFONCIEREDESENTREPRISES' in libelle
                    if not (cfe or feuille_cfe) or 'NEUTRALISATION' not in libelle:
                        continue
                    if any(mot in libelle for mot in ('EPCI', 'INTERCO', 'GROUPEMENT')):
                        part = 'epci'
                    elif any(mot in libelle for mot in ('COMMUNE', 'COMMUNAL')):
                        part = 'commune'
                    elif col_code is None and col_siren is not None:
                        part = 'epci'
                    else:
                        continue
                    for ligne in lignes[debut + span:]:
                        idu = _code_raw(_get(ligne, col_code))
                        code_court = idu.isdecimal() and len(idu) <= 3 and idu.zfill(3) == code[-3:]
                        correspond = idu == code or code_court
                        if not correspond and not (part == 'epci' and siren and _code_raw(_get(ligne, col_siren)) == siren):
                            continue
                        coefficient = _as_number(_get(ligne, i))
                        if coefficient is not None and isfinite(coefficient) and coefficient > 0:
                            valeurs[part].add(coefficient)
    return {part: next(iter(coefficients)) for part, coefficients in valeurs.items() if len(coefficients) == 1}


def rechercher_neutralisation_cfe(code_insee, annee):
    code = code_commune_fiscale(code_insee)
    departement = code[:3] if code.startswith(('97', '98')) else code[:2]
    source = url_fichier(departement, 'neutralisations', annee)
    try:
        contenu = telecharger(source)
    except requests.RequestException as exc:
        raise ValueError('La publication DGFiP est inaccessible.') from exc
    coefficients = lire_neutralisation_cfe(contenu, source, code)
    if 'epci' not in coefficients:
        try:
            siren = siren_epci(code)
        except ValueError:
            pass
        else:
            coefficients = lire_neutralisation_cfe(contenu, source, code, siren)
    if not coefficients:
        raise ValueError('Aucun coefficient CFE identifié pour cette commune dans la publication.')
    return coefficients, source
