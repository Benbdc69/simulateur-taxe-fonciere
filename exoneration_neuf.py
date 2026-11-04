"""Art. 1383 II CGI : construction nouvelle à usage autre que l'habitation.

Règle applicable aux impositions à compter de 2021 (40 % part communale de TFPB
pour les deux années suivant l'achèvement). Aucune exonération automatique des
parts EPCI, TEOM ou taxes annexes. Sous réserve des conditions déclaratives.
"""
from __future__ import annotations


def exon_neuf_non_habitation(annee_imposition: int, annee_achevement: int | None, construction_nouvelle: bool) -> dict:
    year = int(annee_imposition)
    if not construction_nouvelle:
        return {'active': False, 'taux': {}, 'raison': 'Non demandé', 'annee_achevement': None}
    if annee_achevement is None:
        raise ValueError("L'année d'achèvement est nécessaire pour une construction nouvelle.")
    completion = int(annee_achevement)
    if completion > year:
        raise ValueError("L'année d'achèvement ne peut pas être postérieure à l'année d'imposition.")
    if year < 2021:
        return {'active': False, 'taux': {}, 'raison': 'Régime antérieur à 2021 à vérifier séparément', 'annee_achevement': completion, 'a_verifier': True}
    active = year in (completion + 1, completion + 2)
    return {'active': active, 'taux': {'commune': 40.0} if active else {},
            'raison': ('Exonération de 40 % de la part communale, sous réserve de déclaration régulière'
                       if active else 'Hors des deux années qui suivent l’achèvement'),
            'annee_achevement': completion,
            'a_verifier': active}
