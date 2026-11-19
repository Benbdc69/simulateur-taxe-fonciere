"""Recherche à la demande de fichiers annuels CFE dans le catalogue data.gouv.fr."""
import csv
from html.parser import HTMLParser
import io
import re
from tempfile import TemporaryFile
from urllib.parse import unquote, urljoin, urlsplit
from zipfile import BadZipFile, ZipFile
from openpyxl import load_workbook
from openpyxl.utils.exceptions import InvalidFileException
import requests
from .rei_dgfip import ANNEES, lire_dictionnaire, lire_tableau, metadonnees_dgfip, recuperer_dgfip
from .rei_ofgl import _champ, _normaliser, _nombre, _parser, lire_libelles_ofgl

API = "https://www.data.gouv.fr/api/1/datasets/"
PORTAIL_REI = (
    "https://data.economie.gouv.fr/explore/assets/"
    "impots-locaux-fichier-de-recensement-des-elements-dimposition-a-la-fiscalite-dir/"
)
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "simulateur-cfe-minimum/1.0"})


def _row(row, year, code):
    cols = {k.lower().replace("-", "_").strip(): v for k, v in row.items() if k}
    found_code = (cols.get("code_insee") or cols.get("insee") or cols.get("code_commune") or "").strip().upper()
    if found_code != code.upper():
        return None
    value_year = cols.get("millesime") or cols.get("annee") or cols.get("annee_rei") or cols.get("exercice")
    if not value_year or str(value_year).strip() != str(year):
        return None
    rate = _nombre(cols.get("taux_global_hors_zone_activite_pct"))
    if rate is None:
        return None
    bars = []
    for i in range(1, 7):
        base = _nombre(cols.get(f"base_minimum_{i}") or cols.get(f"base_minimum_tranche_{i}"))
        if base is None:
            return None
        bars.append({"tranche": i, "base": base, "chiffre_affaires": str(i)})
    return {
        "commune": cols.get("commune") or cols.get("nom_commune") or code,
        "code_insee": code.upper(),
        "millesime": year,
        "taux_global_hors_zone_activite_pct": rate,
        "base_minimum_eur": bars,
    }


def _separateur(fichier):
    extrait = fichier.read(8192)
    fichier.seek(0)
    premier = next((ligne for ligne in extrait.splitlines() if ligne.strip()), "")
    return max((";", ",", "\t"), key=premier.count)


def _lire_csv(fichier, annee, code, archive_annuelle, libelles):
    lecteur = csv.DictReader(fichier, delimiter=_separateur(fichier))
    champs = {nom.strip().lower(): nom for nom in lecteur.fieldnames or []}
    champ_code = _champ(champs, "idcom", "insee_com")
    champ_valeur = _champ(champs, "valeur", "montant")
    format_long = champ_code and champ_valeur and "varlib" in champs
    if not format_long and "taux_global_hors_zone_activite_pct" not in champs:
        return lire_tableau(lecteur, lecteur.fieldnames or [], libelles, annee, code, archive_annuelle)

    champ_annee = _champ(champs, *ANNEES)

    variables = []
    for brute in lecteur:
        ligne = {cle: brute[nom] for cle, nom in champs.items()}
        if archive_annuelle and not champ_annee:
            ligne["millesime"] = str(annee)
        if not format_long:
            resultat = _row(ligne, annee, code)
            if resultat:
                return resultat
            continue
        millesime = ligne.get(champ_annee or "millesime")
        if str(millesime).strip() == str(annee) and (ligne[champ_code] or "").strip().upper() == code.upper():
            variables.append({
                "libelle": ligne["varlib"],
                "montant": _nombre(ligne[champ_valeur]),
                "code": ligne.get("var"),
                "commune": ligne.get("libcom") or code,
            })
    return _parser(variables, annee, code) if format_long else None


def _lire_texte(ouvrir, lire):
    for encodage in ("utf-8-sig", "cp1252"):
        try:
            with ouvrir() as brut, io.TextIOWrapper(brut, encoding=encodage, newline="") as fichier:
                return lire(fichier)
        except UnicodeDecodeError:
            continue
    return None


def _est_dictionnaire(nom):
    libelle = _normaliser(nom)
    return any(mot in libelle for mot in ("DICTIONNAIRE", "DESCRIPTIF", "VARIABLES", "STRUCTURE"))


def _dictionnaire(ouvrir, extension):
    if extension == "xlsx":
        with ouvrir() as brut:
            classeur = load_workbook(brut, read_only=True, data_only=True)
            try:
                for feuille in classeur.worksheets:
                    resultat = lire_dictionnaire(feuille.values)
                    if resultat:
                        return resultat
            finally:
                classeur.close()
    if extension in {"tsv", "csv", "txt"}:
        return _lire_texte(ouvrir, lambda fichier: lire_dictionnaire(
            csv.reader(fichier, delimiter=_separateur(fichier))
        ))
    return {}


def _lire_zip(reponse, annee, code, libelles):
    with TemporaryFile() as copie:
        for bloc in reponse.iter_content(chunk_size=1024 * 1024):
            copie.write(bloc)
        with ZipFile(copie) as archive:
            membres = [
                membre for membre in archive.infolist()
                if not membre.is_dir() and not (
                    set(re.findall(r"(?<!\d)20\d{2}(?!\d)", membre.filename)) - {str(annee)}
                )
            ]
            libelles = dict(libelles)
            for membre in membres:
                if _est_dictionnaire(membre.filename):
                    extension = membre.filename.rsplit(".", 1)[-1].lower()
                    try:
                        libelles.update(_dictionnaire(lambda: archive.open(membre), extension) or {})
                    except (BadZipFile, InvalidFileException, ValueError, csv.Error):
                        # Un descriptif annexe illisible ne bloque pas les CSV lisibles.
                        continue
            tableaux = [membre for membre in membres
                        if membre.filename.lower().endswith((".csv", ".tsv", ".txt"))]
            resultat = _lire_tableaux_zip(archive, tableaux, libelles, annee, code)
            if resultat or not tableaux:
                return resultat

            # Certaines éditions diffusent le CSV sans dictionnaire dans le ZIP.
            # Les libellés OFGL servent uniquement de nomenclature. Les montants viennent du ZIP.
            try:
                reference = lire_libelles_ofgl()
            except (requests.RequestException, ValueError):
                return None
            if reference.keys() - libelles.keys():
                return _lire_tableaux_zip(archive, tableaux, reference | libelles, annee, code)
    return None


def _lire_tableaux_zip(archive, tableaux, libelles, annee, code):
    for membre in tableaux:
        resultat = _lire_texte(
            lambda: archive.open(membre),
            lambda fichier: _lire_csv(fichier, annee, code, True, libelles),
        )
        if resultat:
            return resultat
    return None


class _LiensArchives(HTMLParser):
    def __init__(self, page):
        super().__init__()
        self.page = page
        self.ressources = []

    def handle_starttag(self, tag, attrs):
        href = dict(attrs).get("href") if tag == "a" else None
        if href:
            url = urljoin(self.page, href)
            chemin = unquote(urlsplit(url).path)
            extension = chemin.rsplit(".", 1)[-1].lower()
            titre = dict(attrs).get("title") or ""
            if extension == "zip" or (
                extension in {"xlsx", "csv", "tsv", "txt"} and _est_dictionnaire(chemin + titre)
            ):
                self.ressources.append({"url": url, "format": extension, "title": titre})


def _catalogues(annee, erreurs):
    try:
        response = SESSION.get(PORTAIL_REI, timeout=12)
        response.raise_for_status()
        liens = _LiensArchives(response.url)
        liens.feed(response.text)
        yield {"title": "REI DGFiP", "resources": liens.ressources}
    except requests.RequestException:
        erreurs.add("portail DGFiP inaccessible")

    # Le catalogue peut regrouper les archives de plusieurs années sous un titre sans année.
    requetes = ("fichier de recensement des éléments d'imposition",
                f"CFE base minimum {annee}")
    for requete in requetes:
        try:
            response = SESSION.get(API, params={"q": requete, "page_size": 20}, timeout=12)
            response.raise_for_status()
            yield from response.json().get("data", [])
        except (requests.RequestException, ValueError):
            erreurs.add("catalogue data.gouv.fr inaccessible")


def rechercher_rei_annuel(code_insee: str, annee: int):
    """Découvre les archives du millésime et lit leurs CSV à la demande."""
    erreurs = set()
    libelles = {}
    try:
        champs, libelles = metadonnees_dgfip(SESSION)
        resultat = recuperer_dgfip(SESSION, champs, libelles, annee, code_insee)
        if resultat:
            return resultat
    except (requests.RequestException, ValueError, RuntimeError):
        erreurs.add("lecture du jeu DGFiP en ligne impossible")

    urls_vues = set()
    annee_exacte = re.compile(rf"(?<!\d){annee}(?!\d)")
    autre_annee = re.compile(rf"(?<!\d)(?!{annee}(?!\d))20\d{{2}}(?!\d)")
    for dataset in _catalogues(annee, erreurs):
        titre = dataset.get("title") or ""
        identite = _normaliser(titre)
        est_rei = "RECENSEMENTDESELEMENTSDIMPOSITION" in identite or re.search(r"\bREI\b", titre, re.I)
        if not est_rei and ("CFE" not in identite or not annee_exacte.search(titre)):
            continue
        ressources = dataset.get("resources", [])
        libelles_dataset = dict(libelles)
        if est_rei:
            for annexe in ressources:
                adresse = annexe.get("url") or ""
                chemin = unquote(urlsplit(adresse).path)
                nom = (annexe.get("title") or "") + " " + chemin.rsplit("/", 1)[-1]
                extension = chemin.rsplit(".", 1)[-1].lower()
                if (
                    not adresse.startswith("https://") or not _est_dictionnaire(nom)
                    or extension not in {"xlsx", "csv", "tsv", "txt"}
                    or autre_annee.search(nom)
                    or not (annee_exacte.search(nom) or annee_exacte.search(titre) and not autre_annee.search(titre))
                ):
                    continue
                try:
                    reponse = SESSION.get(adresse, timeout=12)
                    reponse.raise_for_status()
                    if len(reponse.content) <= 10_000_000:
                        dictionnaire = _dictionnaire(lambda: io.BytesIO(reponse.content), extension)
                        libelles_dataset.update(dictionnaire or {})
                except (requests.RequestException, ValueError, BadZipFile, InvalidFileException, csv.Error):
                    continue
        for resource in ressources:
            url = resource.get("url") or ""
            chemin = unquote(urlsplit(url).path)
            format_fichier = (resource.get("format") or chemin.rsplit(".", 1)[-1]).strip().lower()
            titre_ressource = resource.get("title") or ""
            if url in urls_vues or not url.startswith("https://"):
                continue
            if format_fichier == "zip":
                millesime = titre_ressource + " " + chemin.rsplit("/", 1)[-1]
                if not est_rei or autre_annee.search(millesime):
                    continue
                if not annee_exacte.search(millesime):
                    if not annee_exacte.search(titre) or autre_annee.search(titre):
                        continue
            elif format_fichier != "csv" or (resource.get("filesize") or 0) > 15000000:
                continue

            urls_vues.add(url)
            try:
                with SESSION.get(url, timeout=30, stream=format_fichier == "zip") as response:
                    response.raise_for_status()
                    if format_fichier == "zip":
                        parsed = _lire_zip(response, annee, code_insee, libelles_dataset)
                    else:
                        response.encoding = "utf-8-sig"
                        parsed = _lire_csv(io.StringIO(response.text), annee, code_insee, False, libelles_dataset)
                if parsed:
                    parsed["citation"] = f"{titre} · REI {annee}"
                    parsed["url_page"] = url
                    return parsed
                if format_fichier == "zip":
                    erreurs.add("archive trouvée, barème ou taux non lus pour cette commune")
            except requests.RequestException:
                erreurs.add("téléchargement d’une ressource impossible")
            except (ValueError, csv.Error, BadZipFile, OSError, RuntimeError):
                erreurs.add("ressource téléchargée, format de données non exploitable")
    if erreurs:
        raise RuntimeError(", ".join(sorted(erreurs)))
    return None
