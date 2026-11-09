"""Collecte publique et préparation d'un préremplissage N / dernier taux antérieur.

Un échec d'API n'annule pas les autres sources. Aucune donnée n'est écrite
avant une validation explicite de l'utilisateur.
"""
from __future__ import annotations
from taux_composantes import rechercher_dgcl, rechercher_rei
from historique_taux import COMPOSANTES, code_reference


def preparer(code_insee,annee,cherche_dgcl=None,cherche_rei=None):
    year=int(annee)
    code=code_reference(code_insee)
    search_dgcl=cherche_dgcl or rechercher_dgcl
    search_rei=cherche_rei or rechercher_rei
    propositions={}
    incidents=[]
    consulted=[]
    # D'abord les données N puis N-1 : les millésimes d'une même composante
    # ne se mélangent pas, les valeurs antérieures ne deviennent jamais des 2026.
    for y in (year,year-1):
        if y<2017:continue
        publishers=[]
        if y >= 2025:publishers.append(('DGCL',search_dgcl))
        if y == 2025:publishers.append(('DGFiP / REI détaillé',search_rei))
        for nom,call in publishers:
            try:
                res=call(code,y)
                consulted.append(nom+' '+str(y))
                for key,value in res.get('taux',{}).items():
                    if key not in COMPOSANTES:continue
                    proof=res.get('preuves',{}).get(key,{})
                    entry={'composante':key,'taux':value,'annee':y,
                           'source':nom,'url':proof.get('source') or res.get('source',''),
                           'detail':(proof.get('methode','')+' '+str(proof.get('colonne',''))).strip(),
                           'avertissements':list(res.get('avertissements') or []),
                           'zonage_confirme':False}
                    if key not in propositions:
                        propositions[key]=entry
                    elif propositions[key]['annee']==y:
                        # À année identique, priorité au DGCL pour les parts votées,
                        # mais ne masquer jamais un taux divergent.
                        old=propositions[key]
                        if abs(float(old['taux'])-float(value))>0.0001:
                            incidents.append(f'Divergence {key} {y} : {old["source"]} {old["taux"]} % / {nom} {value} %. Vérifier le taux sur avis.')
            except Exception as ex:
                incidents.append(f'{nom} {y} : {ex}')
    for key,entry in propositions.items():
        entry['repli']=entry['annee']<year
        if key=='teom':
            entry['avertissements'].append('TEOM communale potentiellement zonée : taux à confirmer sur la parcelle.')
    return {'code_insee':code,'annee_imposition':year,
            'propositions':propositions,'sources_consultees':consulted,'incidents':incidents}
