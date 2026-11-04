"""Diagnostic volontaire de récupération des taux (sans écrire dans la base).

Sur Mac : python3 diagnostic_taux.py 69387 2026
Ne contient ni mot de passe ni donnée de client.
"""
from __future__ import annotations
import json
import sys
from historique_taux import code_reference
from collecte_taux import preparer


def run():
    code=sys.argv[1] if len(sys.argv)>1 else '69387'
    annee=int(sys.argv[2]) if len(sys.argv)>2 else 2026
    fiscal=code_reference(code)
    print(f'Commune cadastrale : {code} | commune fiscale : {fiscal} | année : {annee}')
    p=preparer(code,annee)
    print('Sources consultées :',', '.join(p['sources_consultees']))
    for k,v in p['propositions'].items():
        status='À ACTUALISER' if v['repli'] else 'À JOUR'
        print(f"{k:<17} {v['taux']:>8.3f} %  | année {v['annee']} | {status} | {v['source']}")
    if p['incidents']:
        print('\nErreurs / contrôles à partager pour diagnostic :')
        for x in p['incidents']:print('-',str(x)[:500])
    if not p['propositions']:print('\nAucun taux récupéré, consultez les erreurs ci-dessus.')
    print('\nRappel : les valeurs proposées ne sont pas validées pour un bien cadastral sans contrôle (notamment TEOM).')

if __name__=='__main__':run()
