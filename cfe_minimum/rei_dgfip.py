"""Lecture des données REI en colonnes, à partir des libellés officiels."""
from itertools import islice

from .rei_ofgl import _champ, _normaliser, _nombre, _parser


JEU_DGFIP = "https://data.economie.gouv.fr/api/explore/v2.1/catalog/datasets/fiscalite-locale-des-entreprises"
ANNEES = ("exercice", "annee", "millesime", "annee_rei")
CODES = ("idcom", "insee_com", "code_insee", "code_commune", "insee")


def _libelle_cfe(valeur):
    libelle = _normaliser(valeur)
    return "CFE" in libelle or "COTISATIONFONCIEREDESENTREPRISES" in libelle


def lire_dictionnaire(lignes):
    """Associe les codes et libellés d'un dictionnaire tabulaire."""
    for entete in islice(lignes, 20):
        code = _champ(entete, "var", "code variable", "code", "variable",
                      "code de la variable", "nom variable", "nom du champ", "nom de la variable")
        libelle = _champ(entete, "varlib", "libellé variable", "libellé",
                         "libellé de la variable", "description", "signification", "intitulé")
        if code and libelle and code != libelle:
            i, j = entete.index(code), entete.index(libelle)
            resultat = {}
            for ligne in lignes:
                if len(ligne) <= max(i, j) or not ligne[i] or not _libelle_cfe(ligne[j]):
                    continue
                identifiant = _normaliser(ligne[i])
                description = str(ligne[j])
                if identifiant in resultat and resultat[identifiant] != description:
                    raise ValueError(f"Libellés CFE contradictoires pour {ligne[i]}.")
                resultat[identifiant] = description
            return resultat
    return {}


def _code_commune(code, departement, commune):
    if code:
        return str(code).strip().upper().zfill(5)
    if not departement or not commune:
        return ""
    departement = str(departement).strip().upper()
    commune = str(commune).strip()
    if not commune.isdecimal():
        return ""
    if len(commune) == 5:
        return commune
    if departement.startswith(("97", "98")) and len(departement) == 3:
        return departement + str(int(commune)).zfill(2)
    return departement.removeprefix("0").zfill(2) + commune.zfill(3)


def lire_tableau(lignes, champs, libelles, annee, code, archive_annuelle=False):
    """Transforme les colonnes documentées en variables pour le lecteur REI commun."""
    code_insee = _champ(champs, *CODES)
    code_dep = _champ(champs, "dep", "code département")
    code_com = _champ(champs, "com", "commune")
    if not code_insee and not (code_dep and code_com):
        return None

    descriptions = {champ: libelles.get(_normaliser(champ), champ) for champ in champs}
    variables = {champ: desc for champ, desc in descriptions.items() if _libelle_cfe(desc)}
    if not variables:
        return None

    champ_annee = _champ(champs, *ANNEES)
    champ_commune = _champ(champs, "libcom", "nom commune", "nom")
    champ_regime = _champ(champs, "optepci", "dispositif fiscal")
    if not champ_annee and not archive_annuelle:
        return None

    resultat = None
    for ligne in lignes:
        if _code_commune(ligne.get(code_insee), ligne.get(code_dep), ligne.get(code_com)) != code.upper():
            continue
        if champ_annee and str(ligne.get(champ_annee) or "").strip() != str(annee):
            continue
        regime = _normaliser(ligne.get(champ_regime))
        donnees = _parser([
            {"code": champ, "libelle": description, "montant": _nombre(ligne.get(champ)),
             "commune": str(ligne.get(champ_commune) or code), "regime": regime}
            for champ, description in variables.items()
        ], annee, code.upper())
        if donnees is None:
            continue
        if resultat is not None and resultat != donnees:
            raise ValueError("Plusieurs barèmes ou taux CFE incompatibles pour cette commune.")
        resultat = donnees
    return resultat


def metadonnees_dgfip(session):
    reponse = session.get(JEU_DGFIP, timeout=12)
    reponse.raise_for_status()
    champs = reponse.json().get("fields", [])
    libelles = {}
    for champ in champs:
        nom = champ.get("name")
        description = next(
            (texte for texte in (champ.get("description"), champ.get("label")) if _libelle_cfe(texte)),
            None,
        )
        if nom and description:
            libelles[_normaliser(nom)] = description
    return champs, libelles


def recuperer_dgfip(session, champs, libelles, annee, code):
    """Interroge le jeu de la DGFiP si son schéma documente les variables CFE."""
    noms = {champ["name"]: champ.get("type") for champ in champs if champ.get("name")}
    date = _champ(noms, *ANNEES)
    commune = _champ(noms, *CODES)
    if not date or not commune or not libelles:
        return None
    valeur_annee = f'"{annee}"' if noms[date] == "text" else str(annee)
    filtre = f'{date}={valeur_annee} AND {commune}="{code}"'
    reponse = session.get(f"{JEU_DGFIP}/records", params={"where": filtre, "limit": 100}, timeout=15)
    reponse.raise_for_status()
    resultat = lire_tableau(reponse.json().get("results", []), noms, libelles, annee, code)
    if resultat:
        resultat["citation"] = f"DGFiP · Fiscalité locale des entreprises · REI {annee}"
        resultat["url_page"] = "https://data.economie.gouv.fr/explore/dataset/fiscalite-locale-des-entreprises/"
    return resultat
