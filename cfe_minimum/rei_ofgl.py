"""Lecture à la demande du REI OFGL (2024-2025) via Explore API 2.1.

Ne fabrique jamais les valeurs non publiées et ne mélange pas les millésimes.
"""
from functools import lru_cache
from math import isfinite
import re
import unicodedata
import requests

BASE = "https://data.ofgl.fr/api/explore/v2.1/catalog/datasets/rei"
SESSION = requests.Session()
SESSION.headers.update({"User-Agent": "Simulateur-CFE-REI/1.1"})


def _normaliser(texte):
    texte = unicodedata.normalize("NFKD", str(texte or ""))
    texte = "".join(c for c in texte if not unicodedata.combining(c))
    return re.sub(r"[^A-Z0-9]", "", texte.upper())


def _nombre(value):
    if value is None or str(value).strip() == "":
        return None
    try:
        nombre = float(str(value).replace("\u202f", "").replace("\xa0", "").replace(" ", "").replace(",", "."))
    except (TypeError, ValueError):
        return None
    return nombre if isfinite(nombre) and nombre >= 0 else None


def _champ(disponibles, *options):
    index = {_normaliser(v): v for v in disponibles}
    for option in options:
        candidat = index.get(_normaliser(option))
        if candidat:
            return candidat
    return None


def _requete(url, params=None):
    reponse = SESSION.get(url, params=params, timeout=20)
    reponse.raise_for_status()
    return reponse.json()


@lru_cache(maxsize=1)
def lire_libelles_ofgl():
    """Récupère la nomenclature DGFiP publiée par l’OFGL, sans valeurs fiscales."""
    libelles = {}
    conflits = set()
    for offset in range(0, 1000, 100):
        page = _requete(f"{BASE}/records", {
            "select": "var,varlib",
            "group_by": "var,varlib",
            "where": 'search(varlib, "CFE")',
            "order_by": "var,varlib",
            "limit": 100,
            "offset": offset,
        })
        lignes = page.get("results") or []
        for ligne in lignes:
            code = _normaliser(ligne.get("var"))
            libelle = ligne.get("varlib") or ""
            if not code or not _normaliser(libelle).startswith("CFE"):
                continue
            if code in libelles and _normaliser(libelles[code]) != _normaliser(libelle):
                conflits.add(code)
            libelles[code] = libelle
        if len(lignes) < 100:
            break
    return {code: libelle for code, libelle in libelles.items() if code not in conflits}


def lire_variables(code, annee):
    meta = _requete(BASE)
    champs = {item["name"]: item.get("type") for item in meta.get("fields", []) if item.get("name")}
    champ_annee = _champ(champs, "annee", "exercice", "millesime")
    champ_insee = _champ(champs, "idcom", "insee_com", "insee", "code_insee", "code_commune", "com")
    champ_variable = _champ(champs, "varlib", "libelle_variable", "libelle", "variable")
    champ_code_var = _champ(champs, "var", "code_variable", "code_var")
    champ_montant = _champ(champs, "montant", "valeur")
    champ_commune = _champ(champs, "libcom", "nom_commune", "commune")
    if not all((champ_annee, champ_insee, champ_variable, champ_montant)):
        raise RuntimeError(f"Structure OFGL inattendue : champs {champs}")

    code = code.upper().replace("'", "''")
    valeur_annee = str(int(annee))
    if champs[champ_annee] == "text":
        valeur_annee = f'"{valeur_annee}"'
    filtre = f'{champ_annee}={valeur_annee} AND {champ_insee}="{code}"'
    resultats = []
    for offset in range(0, 1500, 100):
        page = _requete(f"{BASE}/records", {
            "where": filtre, "limit": 100, "offset": offset,
        })
        lignes = page.get("results") or []
        resultats.extend(lignes)
        if len(lignes) < 100:
            break

    variables = []
    for ligne in resultats:
        if str(ligne.get(champ_annee)) not in (str(annee), f"{annee}.0") or str(ligne.get(champ_insee, "")).upper() != code:
            continue
        variables.append({
            "libelle": str(ligne.get(champ_variable) or ""),
            "code": str(ligne.get(champ_code_var) or "") if champ_code_var else "",
            "montant": _nombre(ligne.get(champ_montant)),
            "commune": str(ligne.get(champ_commune) or code) if champ_commune else code,
        })
    return variables


def _parser(variables, annee, code):
    bases = {}
    taux_par_type = {}
    commune = code
    for item in variables:
        label = _normaliser(item["libelle"])
        valeur = item["montant"]
        code_var = _normaliser(item["code"])
        if valeur is None or not (
            label.startswith("CFE") or "COTISATIONFONCIEREDESENTREPRISES" in label
            or ("CFE" in label and code_var.startswith("P"))
        ):
            continue
        commune = item["commune"] or commune
        # Uniquement la base MINIMUM TEMPS COMPLET (pas temps partiel).
        match = re.search(r"BASEMINIM(?:UM|ALE).*?TRANCHE(?:N(?:O)?)?([1-6])(?![0-9])", label)
        if "TEMPSPARTIEL" in label or "NOMBRE" in label:
            continue
        if match:
            tranche = int(match.group(1))
            if tranche in bases and bases[tranche] != valeur:
                raise RuntimeError("Plusieurs bases minimum contradictoires dans le REI OFGL.")
            bases[tranche] = valeur
            continue

        # REI : taux net CFE par bénéficiaire, hors ZAE / zone éolienne.
        # Il faut distinguer la part unique (FPU) de la part additionnelle.
        if "TAUXNET" not in label:
            continue
        regime = item.get("regime")
        if (regime == "FPU" and code_var == "P321"
                or regime in {"FPA", "FPZ"} and code_var == "P322U"):
            # En FPZ, le taux P32_2U vise la zone, pas la cotisation hors zone.
            continue
        nature = None
        if code_var.startswith("P12") or ("COMMUNE" in label and "INTERCOMMUN" not in label):
            nature = "commune"
        elif code_var.startswith("P22") or "SYNDICAT" in label:
            nature = "syndicat"
        elif code_var.startswith("P321") or "FISCALITEADDITIONNELLE" in label:
            nature = "epci_additionnel"
        elif code_var.startswith("P322U") or "FPUNIQUE" in label:
            nature = "epci_unique"
        # P32_2U identifie la part unique même si son libellé mentionne la ZAE.
        taux_de_zone = ("ZAE" in label or "EOLIEN" in label) and "HORSZONE" not in label
        if nature == "epci_unique" and taux_de_zone and not code_var.startswith("P322U"):
            continue
        if nature is None or valeur == 0:
            continue
        if nature in taux_par_type and taux_par_type[nature] != valeur:
            raise RuntimeError("Taux CFE contradictoires pour le même bénéficiaire.")
        taux_par_type[nature] = valeur

    # Pas de base manquante inventée ; l'API OFGL exclut les valeurs zéro.
    if len(bases) != 6:
        return None
    if not taux_par_type:
        return None
    if "epci_unique" in taux_par_type and any(k in taux_par_type for k in ("commune", "epci_additionnel")):
        # Ne pas additionner deux régimes fiscaux potentiellement incompatibles.
        return None
    taux = sum(taux_par_type.values())
    return {
        "code_insee": code,
        "commune": commune,
        "millesime": annee,
        "taux_global_hors_zone_activite_pct": round(taux, 5),
        "base_minimum_eur": [
            {"tranche": i, "base": bases[i], "chiffre_affaires": str(i)}
            for i in range(1, 7)
        ],
        "citation": "OFGL — fiscalité directe locale, REI DGFiP, millésime " + str(annee),
        "url_page": "https://data.ofgl.fr/explore/dataset/rei/table/",
    }


def recuperer_rei_ofgl(code_insee: str, annee: int):
    """Résultat complet ou None si l'OFGL ne fournit pas ce millésime."""
    try:
        lignes = lire_variables(code_insee, annee)
        return _parser(lignes, annee, code_insee)
    except (requests.RequestException, ValueError, KeyError, TypeError) as exc:
        raise RuntimeError(f"Lecture OFGL indisponible : {exc}") from exc
