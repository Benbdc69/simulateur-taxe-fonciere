"""Estimation de la cotisation PRINCIPALE minimum de CFE (hors taxes annexes)."""
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

SEUILS = (10000, 32600, 100000, 250000, 500000)


def _decimal(valeur, libelle):
    try:
        nombre = Decimal(str(valeur).replace(",", "."))
    except (InvalidOperation, ValueError, TypeError) as exc:
        raise ValueError(f"{libelle} invalide.") from exc
    if not nombre.is_finite() or nombre < 0:
        raise ValueError(f"{libelle} doit être un nombre positif ou nul.")
    return nombre


def calculer_cfe_minimum(donnees: dict, chiffre_affaires, *, taux_override=None) -> dict:
    """Calcule uniquement la cotisation principale sur base minimum, pour le millésime REI.

    Le CA doit déjà être celui retenu au plan fiscal (N-2 et annualisé le cas échéant).
    L'exonération <= 5 000 € porte sur la cotisation minimum, pas la CFE sur valeur locative.
    """
    ca = _decimal(chiffre_affaires, "Chiffre d'affaires")
    tranche = next((i + 1 for i, seuil in enumerate(SEUILS) if ca <= seuil), 6)
    lignes = donnees.get("base_minimum_eur") or []
    ligne = next((x for x in lignes if isinstance(x, dict) and str(x.get("tranche")) == str(tranche)), None)
    if ligne is None or ligne.get("base") is None:
        raise ValueError(f"Base minimum indisponible pour la tranche {tranche}.")

    base = _decimal(ligne["base"], "Base minimum")
    valeur_taux = donnees.get("taux_global_hors_zone_activite_pct") if taux_override is None else taux_override
    if valeur_taux is None:
        raise ValueError("Taux de CFE indisponible.")
    taux = _decimal(valeur_taux, "Taux CFE")
    exempt = ca <= 5000
    cotisation = Decimal("0") if exempt else base * taux / Decimal("100")
    euros = lambda v: float(v.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))

    return {
        "commune": donnees.get("commune", "Commune inconnue"),
        "code_insee": donnees.get("code_insee"),
        "millesime": donnees.get("millesime"),
        "chiffre_affaires": euros(ca),
        "tranche": tranche,
        "libelle_tranche": ligne.get("chiffre_affaires"),
        "base_minimum": euros(base),
        "taux_cfe_pct": float(taux),
        "exonere_cotisation_minimum": exempt,
        "cotisation_principale_minimum": euros(cotisation),
        "citation": donnees.get("citation"),
        "url_page": donnees.get("url_page"),
    }
