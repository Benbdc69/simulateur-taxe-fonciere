"""Taux TFPB et TEOM des REI antérieurs au transfert de la part départementale."""
from __future__ import annotations

import csv
import re
from tempfile import TemporaryFile
from urllib.parse import unquote, urlsplit
from zipfile import BadZipFile, ZipFile

import requests

from cfe_minimum.rei_a_la_demande import SESSION, _catalogues, _lire_texte, _separateur
from cfe_minimum.rei_dgfip import _code_commune
from cfe_minimum.rei_ofgl import lire_variables
from historique_taux import code_reference
from moteur import TAXES_AVANT_2021, norm
from taux_dgfip import _number


PAGE_OFGL = 'https://data.ofgl.fr/explore/dataset/rei/'
COLONNES_REI = {
    'commune': 'E12',
    'syndicat': 'E22',
    'epci': 'E32',
    'departement': 'E42',
    'gemapi': 'E52GGEMAPI',
    'teom': 'TAUXPLEINTEOM',
}
COLONNES_TSE = ('E52', 'E52A', 'E52TASA')


def _taux_rei(valeurs):
    taux = {}
    for cle, colonne in COLONNES_REI.items():
        valeur = _number(valeurs.get(colonne))
        if valeur is not None:
            taux[cle] = valeur
    sous_taux = [_number(valeurs.get(colonne)) for colonne in COLONNES_TSE]
    if all(t is not None for t in sous_taux) and sum(sous_taux) <= 100:
        taux['taxes_speciales'] = sum(sous_taux)
    return taux


def _taux_ofgl(code, annee):
    variables = {}
    for ligne in lire_variables(code, annee):
        identifiant = norm(ligne['code'])
        libelle = norm(ligne['libelle'])
        if 'TAUXPLEIN' in libelle and 'TEOM' in libelle and 'ZONE' not in libelle:
            identifiant = COLONNES_REI['teom']
        if not identifiant or 'TAUX' not in libelle or 'TAUXMOYEN' in libelle:
            continue
        variables.setdefault(identifiant, set()).add(ligne['montant'])
    return _taux_rei({k: next(iter(v)) for k, v in variables.items() if len(v) == 1})


def _lire_csv(fichier, code, annee):
    lecteur = csv.DictReader(fichier, delimiter=_separateur(fichier))
    colonnes = {norm(c): c for c in (lecteur.fieldnames or [])}
    code_insee = next((colonnes[c] for c in ('IDCOM', 'INSEECOM', 'CODEINSEE') if c in colonnes), None)
    dep = colonnes.get('DEP')
    com = colonnes.get('COM')
    if not code_insee and not (dep and com):
        return {}
    champ_annee = next((colonnes[c] for c in ('ANNEE', 'EXERCICE', 'MILLESIME') if c in colonnes), None)
    taux = None
    for ligne in lecteur:
        if _code_commune(ligne.get(code_insee), ligne.get(dep), ligne.get(com)) != code:
            continue
        if champ_annee and str(ligne[champ_annee]).strip() not in (str(annee), f'{annee}.0'):
            continue
        courant = _taux_rei({cle: ligne.get(colonne) for cle, colonne in colonnes.items()})
        if not courant:
            continue
        if taux is not None and taux != courant:
            return {}
        taux = courant
    return taux or {}


def _lire_archive(url, code, annee):
    with SESSION.get(url, timeout=(6, 20), stream=True) as reponse, TemporaryFile() as fichier:
        reponse.raise_for_status()
        for bloc in reponse.iter_content(chunk_size=1024 * 1024):
            fichier.write(bloc)
            if fichier.tell() > 200_000_000:
                raise ValueError('Archive REI trop volumineuse.')
        with ZipFile(fichier) as archive:
            for membre in archive.infolist():
                annees = set(re.findall(r'(?<!\d)20\d{2}(?!\d)', membre.filename))
                if annees - {str(annee)} or not membre.filename.lower().endswith(('.csv', '.txt', '.tsv')):
                    continue
                taux = _lire_texte(lambda: archive.open(membre), lambda f: _lire_csv(f, code, annee))
                if taux:
                    return taux
    return {}


def rechercher_taux_historiques(code_insee, annee):
    """Vérifie le millésime de l’archive et conserve les zéros explicitement publiés."""
    code = code_reference(code_insee)
    choix = {}
    try:
        choix.update({k: (v, PAGE_OFGL) for k, v in _taux_ofgl(code, annee).items()})
    except (requests.RequestException, RuntimeError, ValueError):
        pass
    if set(TAXES_AVANT_2021) <= choix.keys():
        return choix

    urls_vues = set()
    for jeu in _catalogues(annee, set(), requete_complementaire=f'REI {annee}'):
        titre = str(jeu.get('title') or '')
        if 'RECENSEMENTDESELEMENTSDIMPOSITION' not in norm(titre) and not re.search(r'\bREI\b', titre, re.I):
            continue
        for ressource in jeu.get('resources', []):
            url = ressource.get('url') or ''
            nom = unquote(urlsplit(url).path).rsplit('/', 1)[-1]
            format_fichier = str(ressource.get('format') or '').strip().lower()
            if url in urls_vues or not url.startswith('https://') or not (nom.lower().endswith('.zip') or format_fichier == 'zip'):
                continue
            etiquette = f"{ressource.get('title') or ''} {nom}"
            annees = set(re.findall(r'(?<!\d)20\d{2}(?!\d)', etiquette))
            if not annees:
                annees = set(re.findall(r'(?<!\d)20\d{2}(?!\d)', titre))
            if annees != {str(annee)}:
                continue
            urls_vues.add(url)
            try:
                archive = _lire_archive(url, code, annee)
            except (requests.RequestException, OSError, ValueError, BadZipFile, csv.Error):
                continue
            # Le fichier fiscal confirme notamment les taux à zéro absents de l’API OFGL.
            choix.update({k: (v, url) for k, v in archive.items()})
            if set(TAXES_AVANT_2021) <= choix.keys():
                return choix
    return choix
