"""Art. 1383 II CGI : construction nouvelle à usage autre que l'habitation.

Règle applicable aux impositions à compter de 2021 : 40 % de la base de la
part communale et des taxes additionnelles éligibles (syndicat sans fiscalité
propre, TSE et GEMAPI), pendant deux ans. Les parts EPCI à fiscalité propre et
TEOM restent dues. BOI-IF-TFB-10-60-20 § 100 et 105.
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
    return {'active': active, 'taux': {k: 40.0 for k in ('commune', 'syndicat', 'taxes_speciales', 'gemapi')} if active else {},
            'raison': ('Exonération de 40 % sur la part communale et les taxes additionnelles éligibles, sous réserve de déclaration régulière'
                       if active else 'Hors des deux années qui suivent l’achèvement'),
            'annee_achevement': completion,
            'a_verifier': active}
