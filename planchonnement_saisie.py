"""Validation et application prudente du planchonnement historique RVLLP.

Les montants saisis sont des corrections de BASE IMPOSABLE (signées), par taxe,
documentées pour l'année simulée. Ne jamais les déduire d'une adresse ou des
seuls fichiers de tarifs DGFiP. La règle 2027+ est juridiquement distincte.
"""
from __future__ import annotations
import math
from moteur import TAXES, TAXES_AVANT_2021


def montant_facultatif(value, libelle='Correction de planchonnement'):
    if value is None:
        return None
    if isinstance(value, str):
        value=value.replace('\u202f','').replace('\u00a0','').replace(' ','').replace(',', '.').strip()
        if not value:
            return None
    try:
        f=float(value)
    except (TypeError,ValueError) as exc:
        raise ValueError(f'{libelle} invalide. Renseignez une valeur numérique.') from exc
    if not math.isfinite(f):
        raise ValueError(f'{libelle} invalide. Renseignez une valeur finie.')
    return f


def valider_corrections(values):
    if not isinstance(values,dict):
        raise ValueError('Format des corrections non reconnu.')
    if set(values)-set(TAXES_AVANT_2021):
        raise ValueError('Composante fiscale inconnue dans le planchonnement.')
    parsed={}
    for key,value in values.items():
        number=montant_facultatif(value)
        if number is not None:
            parsed[key]=number
    return parsed


def preparer_planchonnement(annee, historique='inconnu', corrections=None, *, taxes=TAXES):
    annee=int(annee)
    if historique not in ('ancien','recent','inconnu'):
        raise ValueError('Historique du local non reconnu.')
    corr=valider_corrections(corrections or {})
    if annee>=2027:
        return {'corrections':{},'applique':False,'complet':False,
                'reserve':'À compter de 2027, un nouveau mécanisme transitoire remplace le planchonnement initial. Les corrections historiques ne sont pas reprises automatiquement.'}
    if annee<2017:
        return {'corrections':{},'applique':False,'complet':False,
                'reserve':'Année antérieure à la réforme de 2017 : mécanisme non applicable.'}
    if historique=='recent':
        if corr:
            raise ValueError('Les corrections ne peuvent pas être appliquées à un local indiqué comme créé après 2017.')
        return {'corrections':{},'applique':False,'complet':True,'reserve':None}
    if historique=='inconnu':
        if corr:
            raise ValueError('Préciser que le local existait au 1er janvier 2017 avant de saisir ses corrections.')
        return {'corrections':{},'applique':False,'complet':False,
                'reserve':'Existence du local au 1er janvier 2017 non confirmée : estimation hors planchonnement, qui pourrait modifier la taxe.'}
    if not corr:
        return {'corrections':{},'applique':False,'complet':False,
                'reserve':'Local ancien : aucune correction historique fournie. Estimation HORS planchonnement. Les montants 2017–2026 peuvent en être significativement affectés.'}
    absent=set(taxes)-set(corr)
    warning='Les corrections sont renseignées pour certaines taxes seulement : estimation partiellement corrigée, non définitive.' if absent else None
    return {'corrections':corr,'applique':True,'complet':not bool(absent), 'reserve':warning}
