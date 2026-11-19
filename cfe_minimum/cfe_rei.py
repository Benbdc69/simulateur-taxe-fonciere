"""Lecture des données de CFE publiées par l'observatoire Emet Expertise (REI DGFiP)."""
import re
import requests

API_BASE = "https://emetexpertise.fr/api/cfe"
CODE_INSEE = re.compile(r"^(?:[0-9]{5}|2[AB][0-9]{3})$")


def recuperer_cfe(code_insee: str) -> dict:
    code = str(code_insee).strip().upper()
    if not CODE_INSEE.fullmatch(code):
        raise ValueError("Code INSEE invalide (5 caractères, ex. 69123 ou 2A004).")

    try:
        response = requests.get(
            f"{API_BASE}/{code}.json",
            timeout=15,
            headers={"Accept": "application/json", "User-Agent": "module-cfe-rei/1.0"},
        )
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as exc:
        raise RuntimeError(f"Récupération impossible pour {code} : {exc}") from exc
    except ValueError as exc:
        raise RuntimeError("L'API n'a pas renvoyé un JSON valide.") from exc

    if not isinstance(data, dict) or data.get("code_insee", "").upper() != code:
        raise ValueError("Réponse incohérente : code INSEE différent.")
    if data.get("etat") not in (None, "ok"):
        raise ValueError("Données non exploitables pour cette commune.")
    return data
