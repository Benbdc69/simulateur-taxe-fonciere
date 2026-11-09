"""Habitation H1/H2: surface cadastrale et scénarios tarifaires par série (CGI 324 L à T).
Attention: les dépendances isolées des appartements ne sont PAS chiffrées avec
le tarif d'habitation du logement. Simulation indicative hors exonérations et frais.
"""
from __future__ import annotations
from math import floor, isfinite
import re
from decimal import Decimal, ROUND_FLOOR
from dependances_habitation import valider_dependances, ponderer_surface, SOURCE_PONDERATION

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
    valeur=float(etage)
    if not isfinite(valeur) or valeur<0 or not valeur.is_integer():
        raise ValueError("L'étage doit être un entier positif ou nul")
    n=int(valeur)
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
                   etage=0,ascenseur=False,dependances=None):
    if entretien not in ENTRETIEN or situation_generale not in SITUATION or situation_particuliere not in SITUATION:
        raise ValueError('Correctif inconnu')
    if not .2<=float(coeff_annexes)<=.6 or not .2<=float(coeff_terrasse)<=.6:
        raise ValueError('Coefficient de dépendance hors intervalle 0,2–0,6')
    for x in (surface,annexes,terrasse,baignoires,douches,lavabos,wc,pieces_chauffees):
        if not isfinite(float(x)) or float(x)<0:raise ValueError('Quantité négative ou invalide')
    for x in (baignoires,douches,lavabos,wc,pieces_chauffees):
        if not float(x).is_integer():raise ValueError('Les nombres d’équipements et de pièces doivent être entiers')
    detail_dependances = valider_dependances(dependances)
    dependances_ponderees = sum(r['surface_ponderee'] for r in detail_dependances)
    confort_dependances = sum(r['equivalence_confort'] for r in detail_dependances)
    comparaison=surface_comparative(surface,nature,categorie)
    # Décomposition traçable du barème. Ces champs n'affectent pas le calcul.
    importance, seuil = _config(nature, categorie)
    s_m2 = float(surface)
    tranche_haute = min(s_m2, 20)
    tranche_moyenne = max(0., min(s_m2, seuil) - 20)
    tranche_basse = max(0., s_m2 - seuil)
    detail_comparative = {
        'tranche_haute_m2': tranche_haute, 'importance': importance,
        'tranche_moyenne_m2': tranche_moyenne, 'coeff_moyen': .90,
        'tranche_basse_m2': tranche_basse, 'coeff_bas': .75,
        'total_non_arrondi': tranche_haute * importance + tranche_moyenne * .9 + tranche_basse * .75,
        'seuil_categorie': seuil,
    }
    # Les annexes incorporées de maisons sont évaluées avec leur maison ;
    # les dépendances en copropriété peuvent constituer d'autres unités d'évaluation.
    annexe_calc=ponderer_surface(annexes, coeff_annexes) if nature=='M' else 0
    terrasse_calc=ponderer_surface(terrasse, coeff_terrasse)
    asc=_ascenseur(etage,ascenseur) if nature=='A' else 0.
    base = Decimal(str(ENTRETIEN[entretien])) + Decimal(str(SITUATION[situation_generale])) + Decimal(str(SITUATION[situation_particuliere]))
    coefficient_principal = base + Decimal(str(asc))
    correctif = float(coefficient_principal)
    secondaires = annexe_calc + terrasse_calc + dependances_ponderees
    if nature == 'A':
        principal_brut = Decimal(comparaison) * coefficient_principal
        secondaires_brut = Decimal(secondaires) * base
        principal_net = int(principal_brut.to_integral_value(rounding=ROUND_FLOOR))
        secondaires_net = int(secondaires_brut.to_integral_value(rounding=ROUND_FLOOR))
        nette = principal_net + secondaires_net
        detail_nette = dict(mode='separe', principal_brut=float(principal_brut), principal_net=principal_net,
            secondaires_ponderes=secondaires, coefficient_secondaires=float(base),
            secondaires_brut=float(secondaires_brut), secondaires_net=secondaires_net)
    else:
        nette = int((Decimal(comparaison+secondaires)*base).to_integral_value(rounding=ROUND_FLOOR))
        detail_nette = dict(mode='ensemble', surface_brute=comparaison+secondaires)
    equip=(4 if eau else 0)+(2 if gaz else 0)+(2 if electricite else 0)
    equip+=5*int(baignoires)+4*int(douches)+3*int(lavabos)+3*int(wc)
    equip+=(3 if egout else 0)+(3 if vide_ordures else 0)+2*int(pieces_chauffees)
    equip += confort_dependances
    confort = {
        'Eau courante': 4 if eau else 0,
        'Gaz (installation fixe)': 2 if gaz else 0,
        'Électricité': 2 if electricite else 0,
        'Baignoire(s)': 5 * int(baignoires),
        'Douche(s) / bac(s) à laver': 4 * int(douches),
        'Lavabo(s)': 3 * int(lavabos),
        'WC particulier(s)': 3 * int(wc),
        'Tout-à-l’égout': 3 if egout else 0,
        'Vide-ordures': 3 if vide_ordures else 0,
        'Pièces chauffées admissibles': 2 * int(pieces_chauffees),
    }
    if confort_dependances:
        confort['Équipements propres aux dépendances rattachées'] = confort_dependances
    return {'detail_surface_nette':detail_nette, 'detail_terrasse': {'surface_declaree':float(terrasse), 'surface_reelle_retenue':floor(float(terrasse)),
                'coefficient':float(coeff_terrasse), 'surface_ponderee':terrasse_calc, 'source':SOURCE_PONDERATION},
            'detail_dependances':detail_dependances, 'dependances_ponderees':dependances_ponderees,
            'detail_comparative':detail_comparative, 'detail_confort':confort,
            'detail_correctifs':{
                'entretien':entretien,'coef_entretien':ENTRETIEN[entretien],
                'situation_generale':situation_generale,'correctif_situation_generale':SITUATION[situation_generale],
                'situation_particuliere':situation_particuliere,'correctif_situation_particuliere':SITUATION[situation_particuliere],
                'correctif_ascenseur':asc,
                'ascenseur_immeuble':bool(ascenseur) if nature=='A' else None,
                'niveau_local':int(etage) if nature=='A' else None,
                'source_ascenseur':'CGI, annexe III, article 324 S',
            },
            'comparative':comparaison,'annexes_ponderees':annexe_calc,'terrasse_ponderee':terrasse_calc,
            'correctif':round(correctif,4),'correctif_ascenseur':asc,
            'surface_nette':nette,'equivalence_confort':equip,'surface_ponderee':nette+equip,
            'dependances_a_evaluer_separement':nature=='A' and float(annexes)>0,
            'annexes_separees_m2':float(annexes) if nature=='A' else 0.,
            'terrasse_separee_m2':0.,
            'nature':nature,'categorie':_categ(categorie)}

def simulations_tarifs(surface_ponderee,tarifs,coefficient_cumule=None,taux=None):
    surface=float(surface_ponderee)
    if not isfinite(surface) or surface<=0:raise ValueError('Surface pondérée invalide')
    if taux is not None:
        for valeur in taux.values():
            if valeur is not None and (not isfinite(float(valeur)) or not 0<=float(valeur)<=100):
                raise ValueError('Un taux doit être compris entre 0 et 100 %')
    if not tarifs:return []
    out=[]
    for row in tarifs:
        tarif=float(row['tarif_1970'])
        if not isfinite(tarif) or tarif<=0:raise ValueError('Tarif cadastral invalide')
        obj={'serie':str(row['serie']),'origine':str(row.get('origine','')),
             'tarif_1970':tarif,'vl_1970':round(float(surface_ponderee)*tarif,2),
             'annee_tarif':row.get('annee_tarif',2024),'categorie':row.get('categorie')}
        if coefficient_cumule is not None:
            factor=float(coefficient_cumule)
            if not isfinite(factor) or factor<=0:raise ValueError('Coefficient cumulé invalide')
            obj['coefficient_cumule']=factor
            obj['vl_annee']=round(obj['vl_1970']*factor,2)
            obj['base_tf']=round(obj['vl_annee']*.5,2)
            if taux and all(v is not None for v in taux.values()):
                obj['montants']={k:round(obj['base_tf']*float(v)/100,2) for k,v in taux.items() if v is not None}
                obj['total']=round(sum(obj['montants'].values()),2)
        out.append(obj)
    return out
