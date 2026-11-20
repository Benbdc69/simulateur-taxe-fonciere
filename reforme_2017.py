"""Reconstitution des correctifs TFPB à partir de la base d’imposition 2016."""
from __future__ import annotations

import math

from moteur import (
    TAXES_AVANT_2021,
    localisation_automatique,
    neutralisation_automatique,
    planchonnement_2017,
    secteur_automatique,
    tarif_automatique,
)


COEFFICIENT_REVALORISATION = 1.004  # CGI, art. 1518 bis, zk.


def reconstituer_reforme(ref, bien, categorie, surface_ponderee, annee, base_2016,
                        taux_actuels, corrections_documentees, *, localisation_2017=None,
                        coefficients_actuels=None, avec_replis=True):
    """Travaille en bases nettes (la base 2016 intègre déjà l'abattement de 50 %)."""
    if not math.isfinite(base_2016) or base_2016 < 0:
        raise ValueError('La base TFPB 2016 doit être un montant positif ou nul.')
    if localisation_2017 is not None and not 0.5 <= localisation_2017 <= 1.5:
        raise ValueError('Le coefficient de localisation 2017 doit être compris entre 0,5 et 1,5.')
    dep, com, code = bien['departement'], bien['commune'], bien['code_insee']
    prefixe, section, parcelle = bien['prefixe'], bien['section'], bien['numero']
    secteur, _ = secteur_automatique(ref, dep, com, prefixe, section, code)
    tarif = tarif_automatique(ref, dep, 2017, categorie, secteur)
    loc, message_loc, _ = localisation_automatique(ref, dep, 2017, com, prefixe, section, parcelle, code)
    hypotheses = []
    if localisation_2017 is not None:
        loc = localisation_2017
        message_loc = 'Coefficient de localisation 2017 relevé sur la fiche cadastrale.'
    elif avec_replis and loc is None and section and parcelle and 'contradictoires' not in message_loc:
        # Le barème légal prévoit 1 en l'absence de modulation parcellaire.
        # Tant que l'archive 2017 manque, tout autre millésime reste indicatif.
        for millesime in (2018, 2019, 2020):
            loc, _, _ = localisation_automatique(ref, dep, millesime, com, prefixe, section, parcelle, code)
            if loc is not None:
                message_loc = (f'Localisation 2017 indisponible. Le coefficient publié en {millesime} '
                               f'({loc:g}) sert à l’estimation.')
                break
        if loc is None:
            loc = 1.0
            message_loc = 'Localisation 2017 indisponible. Le coefficient de droit commun de 1 sert à l’estimation.'
        hypotheses.append(message_loc)
    neutralisations, message_neutralisation = neutralisation_automatique(
        ref, dep, com, 2017, code, prefixe, taxes=TAXES_AVANT_2021)
    neutralisations = neutralisations or {}
    base_ancienne = base_2016 * COEFFICIENT_REVALORISATION
    vl_revisee = surface_ponderee * tarif * loc if tarif is not None and loc is not None else None
    base_revisee = vl_revisee / 2 if vl_revisee is not None else None

    # Depuis le transfert de la part départementale, la correction communale
    # résulte de la même pondération 2020 que le coefficient fusionné de 2021.
    coefficients = dict(neutralisations)
    messages = dict.fromkeys(TAXES_AVANT_2021, message_neutralisation)
    if annee >= 2021:
        fusion, message_fusion = neutralisation_automatique(ref, dep, com, 2021, code, prefixe)
        coefficients['commune'] = (fusion or {}).get('commune')
        messages['commune'] = message_fusion

    corrections = dict(corrections_documentees)
    bases_neutralisees = {}
    manquants = []
    neutralisations_de_repli = []
    for cle, taux in taux_actuels.items():
        if cle in corrections or taux == 0:
            continue
        coeff = coefficients.get(cle)
        if (avec_replis and annee >= 2021 and coeff is None
                and 'contradictoires' not in messages[cle] and base_revisee is not None):
            coeff = (coefficients_actuels or {}).get(cle)
            if coeff:
                neutralisations_de_repli.append(TAXES_AVANT_2021[cle])
        if coeff and base_revisee is not None:
            bases_neutralisees[cle] = base_revisee * coeff
            corrections[cle] = planchonnement_2017(
                base_ancienne, bases_neutralisees[cle], deduction_tf=1)['correction_base_tf']
        else:
            manquants.append(TAXES_AVANT_2021[cle])

    if neutralisations_de_repli:
        hypotheses.append(
            'Coefficient de neutralisation de l’année simulée utilisé à titre indicatif pour '
            + ', '.join(neutralisations_de_repli) + '.')
    parametres_manquants = [nom for nom, donnee in (
        ('secteur d’évaluation', secteur), ('tarif 2017', tarif), ('localisation 2017', loc))
        if donnee is None]

    return {
        'base_2016': base_2016, 'base_ancienne_2017': base_ancienne, 'vl_revisee_2017': vl_revisee,
        'tarif_2017': tarif, 'localisation_2017': loc, 'message_localisation': message_loc,
        'bases_neutralisees': bases_neutralisees, 'parametres_manquants': parametres_manquants,
        'corrections': corrections, 'planchonnement_manquant': manquants,
        'hypotheses': hypotheses,
    }
