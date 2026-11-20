"""Reconstitution des correctifs TFPB à partir de la base d’imposition 2016."""
from __future__ import annotations

import math

from frais_gestion import estimer_frais
from historique_taux import resoudre
from moteur import (
    TAXES_AVANT_2021,
    lissage_2017_2025,
    localisation_automatique,
    neutralisation_automatique,
    planchonnement_2017,
    secteur_automatique,
    tarif_automatique,
)


COEFFICIENT_REVALORISATION = 1.004  # CGI, art. 1518 bis, zk.


def reconstituer_reforme(ref, bien, categorie, surface_ponderee, annee, base_2016,
                        taux_actuels, corrections_documentees, *, localisation_2017=None,
                        montant_lissage=None):
    """Travaille en bases nettes (la base 2016 intègre déjà l'abattement de 50 %)."""
    if not math.isfinite(base_2016) or base_2016 < 0:
        raise ValueError('La base TFPB 2016 doit être un montant positif ou nul.')
    if localisation_2017 is not None and not 0.5 <= localisation_2017 <= 1.5:
        raise ValueError('Le coefficient de localisation 2017 doit être compris entre 0,5 et 1,5.')
    dep, com, code = bien['departement'], bien['commune'], bien['code_insee']
    prefixe, section, parcelle = bien['prefixe'], bien['section'], bien['numero']
    secteur, _ = secteur_automatique(ref, dep, com, prefixe, section, code)
    tarif = tarif_automatique(ref, dep, 2017, categorie, secteur)
    loc, _, _ = localisation_automatique(ref, dep, 2017, com, prefixe, section, parcelle, code)
    if localisation_2017 is not None:
        loc = localisation_2017
    neutralisations, _ = neutralisation_automatique(
        ref, dep, com, 2017, code, prefixe, taxes=TAXES_AVANT_2021)
    neutralisations = neutralisations or {}
    base_ancienne = base_2016 * COEFFICIENT_REVALORISATION
    vl_revisee = surface_ponderee * tarif * loc if tarif is not None and loc is not None else None
    base_revisee = vl_revisee / 2 if vl_revisee is not None else None

    # Depuis le transfert de la part départementale, la correction communale
    # résulte de la même pondération 2020 que le coefficient fusionné de 2021.
    coeffs_actuels = dict(neutralisations)
    if annee >= 2021:
        neutralisation_fusionnee, _ = neutralisation_automatique(ref, dep, com, 2021, code, prefixe)
        coeffs_actuels['commune'] = (neutralisation_fusionnee or {}).get('commune')

    corrections = dict(corrections_documentees)
    manquants = []
    for cle, taux in taux_actuels.items():
        if cle in corrections or taux == 0:
            continue
        coeff = coeffs_actuels.get(cle)
        if coeff and base_revisee is not None:
            corrections[cle] = planchonnement_2017(
                base_ancienne, base_revisee * coeff, deduction_tf=1)['correction_base_tf']
        else:
            manquants.append(TAXES_AVANT_2021[cle])

    parametres_manquants = [nom for nom, donnee in (
        ('secteur d’évaluation', secteur), ('tarif 2017', tarif), ('localisation 2017', loc))
        if donnee is None]
    taux_2017 = {}
    taux_manquants = []
    lissage = None
    cotisations = None
    hypotheses_lissage = []
    if annee == 2026:
        lissage = lissage_2017_2025(annee)
    elif montant_lissage is not None:
        lissage = lissage_2017_2025(annee, montant_avis=montant_lissage)
    else:
        for cle in TAXES_AVANT_2021:
            rec = resoudre(ref, code, 2017, cle, repli=False)
            if rec is None:
                taux_manquants.append(TAXES_AVANT_2021[cle])
            else:
                taux_2017[cle] = rec
        actifs = {cle: rec['taux'] for cle, rec in taux_2017.items() if rec['taux'] > 0}
        neutralisations_manquantes = [TAXES_AVANT_2021[cle] for cle in actifs if not neutralisations.get(cle)]
        if base_revisee is not None and not taux_manquants and not neutralisations_manquantes:
            avant = {cle: base_ancienne * taux / 100 for cle, taux in actifs.items()}
            apres = {cle: (base_ancienne + base_revisee * neutralisations[cle]) / 2 * taux / 100
                     for cle, taux in actifs.items()}
            cotisations = {
                'avant': estimer_frais(avant, 2017, comparaison_2017=True)['total'],
                'apres': estimer_frais(apres, 2017, comparaison_2017=True)['total'],
            }
            lissage = lissage_2017_2025(annee, cotisation_avant_reforme_2017=cotisations['avant'],
                                       cotisation_apres_reforme_2017=cotisations['apres'])
            if actifs.get('teom') and not taux_2017['teom'].get('zonage_confirme'):
                hypotheses_lissage.append('Le taux de TEOM 2017 est à vérifier selon le zonage de la parcelle.')
            if actifs.get('taxes_speciales'):
                hypotheses_lissage.append('Les frais sur les taxes spéciales de 2017 sont estimés à 9 %.')
        elif neutralisations_manquantes:
            parametres_manquants.append('neutralisation 2017 pour ' + ', '.join(neutralisations_manquantes))

    return {
        'base_2016': base_2016, 'base_ancienne_2017': base_ancienne, 'vl_revisee_2017': vl_revisee,
        'tarif_2017': tarif, 'localisation_2017': loc, 'localisation_saisie': localisation_2017 is not None,
        'neutralisations_2017': neutralisations, 'taux_2017': taux_2017,
        'parametres_manquants': parametres_manquants, 'taux_manquants': taux_manquants,
        'corrections': corrections, 'planchonnement_manquant': manquants,
        'cotisations_2017': cotisations, 'lissage': lissage, 'hypotheses_lissage': hypotheses_lissage,
    }
