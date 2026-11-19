"""Sélection d'un millésime CFE sans mélange implicite de taux et de bases."""
from datetime import date
import json
from pathlib import Path
from .cfe_rei import recuperer_cfe
from .rei_a_la_demande import rechercher_rei_annuel
from .rei_ofgl import recuperer_rei_ofgl

DOSSIER_ARCHIVES = Path(__file__).parent / "donnees_rei"


def _archives(code_insee: str, annee: int):
    """Une archive normalisée, alimentée à partir d'un REI vérifié, si elle existe."""
    # Référentiel national archivé par le workflow GitHub Actions.
    national = DOSSIER_ARCHIVES / f"{annee}.json"
    if national.exists():
        with national.open(encoding="utf-8") as fichier:
            archive = json.load(fichier)
        donnees = archive.get("communes", {}).get(code_insee.upper())
        if donnees is not None:
            if int(donnees.get("millesime", -1)) != annee:
                raise ValueError("Millésime incohérent dans le référentiel CFE.")
            return donnees

    # Compatibilité avec une archive individuelle éventuelle.
    chemin = DOSSIER_ARCHIVES / str(annee) / f"{code_insee}.json"
    if not chemin.exists():
        return None
    with chemin.open(encoding="utf-8") as fichier:
        donnees = json.load(fichier)
    if str(donnees.get("code_insee", "")).upper() != code_insee.upper():
        raise ValueError("Code INSEE incohérent dans le fichier REI local.")
    if int(donnees.get("millesime", -1)) != annee:
        raise ValueError("Millésime incohérent dans le fichier REI local.")
    return donnees


def recuperer_pour_annee(code_insee: str, annee: int) -> dict:
    """Renvoie la bonne année, ou N-1 si disponible, jamais une autre année.

    L'API Emet actuelle expose un millésime unique dans sa réponse : il est
    impérativement contrôlé avant de l'employer pour une année demandée.
    Des archives REI normalisées peuvent être ajoutées dans donnees_rei/AAAA/.
    """
    annee = int(annee)
    if annee < 2009 or annee > date.today().year + 1:
        raise ValueError("Année de CFE en dehors de la période prise en charge.")

    # Interrogation à la demande uniquement, jamais de tâche programmée.
    distant = None
    erreur_api = None
    try:
        distant = recuperer_cfe(code_insee)
    except (RuntimeError, ValueError) as exc:
        erreur_api = str(exc)

    erreurs_sources = []
    for candidate in (annee, annee - 1):
        donnees = _archives(code_insee, candidate)
        if donnees is None and distant is not None and str(distant.get("millesime")) == str(candidate):
            donnees = distant
        if donnees is None:
            # REI DGFiP publiés par l'OFGL, interrogation commune + millésime.
            try:
                donnees = recuperer_rei_ofgl(code_insee, candidate)
            except RuntimeError as exc:
                erreurs_sources.append(f"OFGL {candidate} : {exc}")
                donnees = None
        if donnees is None:
            try:
                donnees = rechercher_rei_annuel(code_insee, candidate)
            except RuntimeError as exc:
                erreurs_sources.append(f"Archives REI {candidate} : {exc}.")
                donnees = None

        if donnees is None:
            continue
        taux = donnees.get("taux_global_hors_zone_activite_pct")
        bareme = donnees.get("base_minimum_eur")
        if taux is None or not bareme:
            continue
        return {
            "donnees": donnees,
            "annee_demandee": annee,
            "annee_utilisee": candidate,
            "estimation_n_moins_1": candidate == annee - 1,
        }

    erreurs = erreurs_sources + ([erreur_api] if erreur_api else [])
    details = " " + " ".join(erreurs) if erreurs else ""
    raise ValueError(
        f"Aucun jeu complet de taux et bases minimum pour {annee} ou {annee-1}. "
        "Le calcul exige des données exploitables pour l’un de ces deux millésimes." + details
    )
