"""Calcul de surface pondérée d'habitation selon les articles 324 O à 324 U CGI.
Valeurs locatives des tarifs ouverts = valeur de référence 1970, non revalorisée.
Aucune cotisation n'est présentée sans actualisation/revalorisation documentée.
"""
from __future__ import annotations
from dataclasses import dataclass
from math import floor, isfinite

# Catégorie : (première tranche, borne de fin de deuxième tranche)
MAISON={1:(3.00,400),2:(2.50,320),3:(2.10,240),4:(1.70,160),5:(1.45,110),6:(1.30,80),7:(1.20,60),8:(1.10,40)}
APPARTEMENT={1:(2.60,350),2:(2.20,260),3:(1.90,200),4:(1.60,140),5:(1.35,90),6:(1.25,70),7:(1.15,50),8:(1.05,30)}
ENTRETIEN={'Bon':1.20,'Assez bon':1.10,'Passable':1.00,'Médiocre':0.90,'Mauvais':0.80}
SITUATION={'Excellente':.10,'Bonne':.05,'Ordinaire':0.,'Médiocre':-.05,'Mauvaise':-.10}


def surface_comparative(surface:float, nature:str, categorie:int)->float:
    s=float(surface)
    if not isfinite(s) or s<0: raise ValueError('Surface principale invalide')
    cfg=(MAISON if nature=='M' else APPARTEMENT if nature=='A' else None)
    if cfg is None or categorie not in cfg:raise ValueError('Nature ou catégorie inconnue')
    coeff,limite=cfg[categorie]
    return floor(min(s,20)*coeff+max(0,min(s,limite)-20)*.90+max(0,s-limite)*.75)


def surface_totale(surface, nature, categorie, annexes=0, coeff_annexes=.4,
                   entretien='Passable',situation_generale='Ordinaire',situation_particuliere='Ordinaire',
                   eau=True,gaz=False,electricite=True,baignoires=0,douches=1,lavabos=1,wc=1,
                   egout=True,vide_ordures=False,pieces_chauffees=0):
    """Estimation standard de la partie principale, hors dépendances évaluées séparément.
    Maison: garages/caves intégrés au groupe de la maison comme annexes pondérées.
    Appartement: dépendances peuvent relever d'une évaluation distincte, exclues ici.
    """
    if entretien not in ENTRETIEN or situation_generale not in SITUATION or situation_particuliere not in SITUATION:
        raise ValueError('Correctif inconnu')
    if not 0.2<=float(coeff_annexes)<=0.6:raise ValueError('La pondération des annexes doit être entre 0,2 et 0,6')
    values=(annexes,baignoires,douches,lavabos,wc,pieces_chauffees)
    if any(float(v)<0 or not isfinite(float(v)) for v in values):raise ValueError('Quantité négative ou invalide')
    comparaison=surface_comparative(surface,nature,categorie)
    annexes_pond=floor(float(annexes)*float(coeff_annexes)) if nature=='M' else 0
    coef=ENTRETIEN[entretien]+SITUATION[situation_generale]+SITUATION[situation_particuliere]
    nette=floor((comparaison+annexes_pond)*coef)
    equip= (4 if eau else 0)+(2 if gaz else 0)+(2 if electricite else 0)
    equip+=5*int(baignoires)+4*int(douches)+3*int(lavabos)+3*int(wc)
    equip+=(3 if egout else 0)+(3 if vide_ordures else 0)+2*int(pieces_chauffees)
    return {'comparative':comparaison,'annexes_ponderees':annexes_pond,'correctif':coef,
            'surface_nette':nette,'equivalence_confort':equip,'surface_ponderee':nette+equip,
            'dependances_a_evaluer_separement':nature=='A' and annexes>0}


def simulations_tarifs(surface_ponderee,tarifs,coefficient_cumule=None,taux=None):
    """Scénarios par tarif/série : pas d'agrégation trompeuse des séries."""
    if not tarifs: return []
    result=[]
    for row in tarifs:
        tarif=float(row['tarif_1970'])
        obj={'serie':row['serie'],'origine':row.get('origine'),'tarif_1970':tarif,
             'vl_1970':round(float(surface_ponderee)*tarif,2),'annee_tarif':row.get('annee_tarif',2024)}
        if coefficient_cumule is not None:
            factor=float(coefficient_cumule)
            if not isfinite(factor) or factor<=0:raise ValueError('Coefficient cumulé invalide')
            obj['coefficient_cumule']=factor
            obj['vl_annee']=round(obj['vl_1970']*factor,2)
            obj['base_tf']=round(obj['vl_annee']*.5,2)
            if taux is not None:
                obj['montants']={k:round(obj['base_tf']*float(v)/100,2) for k,v in taux.items() if v is not None}
                obj['total']=round(sum(obj['montants'].values()),2)
        result.append(obj)
    return result
