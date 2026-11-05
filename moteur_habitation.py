"""Habitation H1/H2: surface cadastrale et scénarios tarifaires par série (CGI 324 L à T).
Attention: les dépendances isolées des appartements ne sont PAS chiffrées avec
le tarif d'habitation du logement. Simulation indicative hors exonérations et frais.
"""
from __future__ import annotations
from math import floor, isfinite
import re

MAISON={1:(3.00,400),2:(2.50,320),3:(2.10,240),4:(1.70,160),5:(1.45,110),6:(1.30,80),7:(1.20,60),8:(1.10,40)}
APPARTEMENT={1:(2.60,350),2:(2.20,260),3:(1.90,200),4:(1.60,140),5:(1.35,90),6:(1.25,70),7:(1.15,50),8:(1.05,30)}
ENTRETIEN={'Bon':1.20,'Assez bon':1.10,'Passable':1.00,'Médiocre':0.90,'Mauvais':0.80}
SITUATION={'Excellente':.10,'Bonne':.05,'Ordinaire':0.,'Médiocre':-.05,'Mauvaise':-.10}
CATEGORIES=[str(x) for x in range(1,9)]+[f'{x}M' for x in range(1,8)]

def _categ(categorie):
    c=str(categorie).strip().upper()
    if c not in CATEGORIES:raise ValueError('Catégorie cadastrale non reconnue (1 à 8, 1M à 7M)')
    return c

def _config(nature,categorie):
    table=MAISON if nature=='M' else APPARTEMENT if nature=='A' else None
    if table is None:raise ValueError('Type de local inconnu')
    c=_categ(categorie)
    if c.endswith('M'):
        x=int(c[0]);v,w=table[x],table[x+1]
        # Catégorie intermédiaire: moyenne simple des coefficients d'importance et seuils.
        return ((v[0]+w[0])/2,(v[1]+w[1])/2)
    return table[int(c)]

def surface_comparative(surface,nature,categorie):
    s=float(surface)
    if not isfinite(s) or s<=0:raise ValueError('Surface principale invalide')
    c,limite=_config(nature,categorie)
    return floor(min(s,20)*c + max(0,min(s,limite)-20)*.9+max(0,s-limite)*.75)

def _ascenseur(etage,ascenseur):
    n=int(etage)
    if n<0:raise ValueError("L'étage ne peut pas être négatif")
    if n<=1:return 0.
    if ascenseur:return .05
    if n==2 or n==3:return 0.
    if n==4:return -.05
    if n==5:return -.10
    return -.15

def surface_totale(surface,nature,categorie,annexes=0,coeff_annexes=.4,
                   entretien='Passable',situation_generale='Ordinaire',situation_particuliere='Ordinaire',
                   eau=True,gaz=False,electricite=True,baignoires=0,douches=1,lavabos=1,wc=1,
                   egout=True,vide_ordures=False,pieces_chauffees=0,terrasse=0,coeff_terrasse=.4,
                   etage=0,ascenseur=False):
    if entretien not in ENTRETIEN or situation_generale not in SITUATION or situation_particuliere not in SITUATION:
        raise ValueError('Correctif inconnu')
    if not .2<=float(coeff_annexes)<=.6 or not .2<=float(coeff_terrasse)<=.6:
        raise ValueError('Coefficient de dépendance hors intervalle 0,2–0,6')
    for x in (surface,annexes,terrasse,baignoires,douches,lavabos,wc,pieces_chauffees):
        if not isfinite(float(x)) or float(x)<0:raise ValueError('Quantité négative ou invalide')
    comparaison=surface_comparative(surface,nature,categorie)
    # Les annexes incorporées de maisons sont évaluées avec leur maison ;
    # les dépendances en copropriété peuvent constituer d'autres unités d'évaluation.
    annexe_calc=floor(float(annexes)*float(coeff_annexes)) if nature=='M' else 0
    terrasse_calc=floor(float(terrasse)*float(coeff_terrasse)) if nature=='M' else 0
    asc=_ascenseur(etage,ascenseur) if nature=='A' else 0.
    correctif=ENTRETIEN[entretien]+SITUATION[situation_generale]+SITUATION[situation_particuliere]+asc
    nette=floor((comparaison+annexe_calc+terrasse_calc)*correctif)
    equip=(4 if eau else 0)+(2 if gaz else 0)+(2 if electricite else 0)
    equip+=5*int(baignoires)+4*int(douches)+3*int(lavabos)+3*int(wc)
    equip+=(3 if egout else 0)+(3 if vide_ordures else 0)+2*int(pieces_chauffees)
    return {'comparative':comparaison,'annexes_ponderees':annexe_calc,'terrasse_ponderee':terrasse_calc,
            'correctif':round(correctif,4),'correctif_ascenseur':asc,
            'surface_nette':nette,'equivalence_confort':equip,'surface_ponderee':nette+equip,
            'dependances_a_evaluer_separement':nature=='A' and (float(annexes)>0 or float(terrasse)>0),
            'annexes_separees_m2':float(annexes) if nature=='A' else 0.,
            'terrasse_separee_m2':float(terrasse) if nature=='A' else 0.,
            'nature':nature,'categorie':_categ(categorie)}

def simulations_tarifs(surface_ponderee,tarifs,coefficient_cumule=None,taux=None):
    if not tarifs:return []
    out=[]
    for row in tarifs:
        tarif=float(row['tarif_1970'])
        obj={'serie':str(row['serie']),'origine':str(row.get('origine','')),
             'tarif_1970':tarif,'vl_1970':round(float(surface_ponderee)*tarif,2),
             'annee_tarif':row.get('annee_tarif',2024),'categorie':row.get('categorie')}
        if coefficient_cumule is not None:
            factor=float(coefficient_cumule)
            if not isfinite(factor) or factor<=0:raise ValueError('Coefficient cumulé invalide')
            obj['coefficient_cumule']=factor
            obj['vl_annee']=round(obj['vl_1970']*factor,2)
            obj['base_tf']=round(obj['vl_annee']*.5,2)
            if taux is not None:
                obj['montants']={k:round(obj['base_tf']*float(v)/100,2) for k,v in taux.items() if v is not None}
                obj['total']=round(sum(obj['montants'].values()),2)
        out.append(obj)
    return out
