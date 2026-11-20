"""Vérifie les fichiers DGFiP pour plusieurs départements et crée une proposition.

Le jeu actif n'est JAMAIS remplacé sans approbation dans l'application.

Exemples :
    python actualiser.py --annee 2026 --departements 42 43 69 01 75
    python actualiser.py --annee 2026 --departements 2A 2B 971
"""
from __future__ import annotations
import argparse
import copy
import hashlib
import json
import sys
from datetime import datetime, timezone
from stockage_fiscal import DONNEES_LIVREES, dossier_fiscal, ecrire_atomiquement
from imports_dgfip import url_fichier, telecharger, importer, construire_source
from referentiel import (DEPARTEMENTS, normaliser_departement,
                         publication_attendue, integrer_jeu)

BASE = DONNEES_LIVREES / 'referentiel_initial.json'
DOSSIER_FISCAL = dossier_fiscal()
ACTIVE = DOSSIER_FISCAL / 'referentiel_local.json'
PENDING = DOSSIER_FISCAL / 'en_attente' / 'proposition.json'
LOG = DOSSIER_FISCAL / 'journal_sync.log'


def journal(message):
    LOG.parent.mkdir(parents=True,exist_ok=True)
    line=f'{datetime.now(timezone.utc).isoformat()} | {message}'
    print(line,flush=True)
    with LOG.open('a',encoding='utf8') as fd:fd.write(line+'\n')


def preparer_proposition(annee,deps, *, fetch=telecharger, parse=importer):
    if PENDING.exists():
        raise ValueError('Une proposition est déjà en attente : validez-la ou rejetez-la avant une nouvelle synchronisation.')
    active_path=ACTIVE if ACTIVE.exists() else BASE
    active_bytes=active_path.read_bytes()
    base=json.loads(active_bytes.decode('utf8'))
    staged=copy.deepcopy(base)
    changes=[]; failures=[]; unchanged=[]
    specs=publication_attendue(annee,inclure_historique=True)
    for departement in deps:
        dep=normaliser_departement(departement)
        for nature,millesime in specs:
            url=url_fichier(dep,nature,millesime)
            source_id=f'{dep}/{nature}/{millesime}'
            if nature=='neutralisations':
                source_id=f'{dep}/neutralisations/{2021 if millesime>=2021 else 2017}'
            try:
                blob=fetch(url)
                parsed,sha=parse(blob,url,nature)
                prior=base.get('sources',{}).get(source_id,{})
                if prior.get('sha256')==sha:
                    unchanged.append(source_id)
                    continue
                source=construire_source(url,sha,nature,millesime,len(parsed))
                integrer_jeu(staged,dep,nature,millesime,parsed,source)
                changes.append({'departement':dep,'type':nature,'millesime':millesime,
                                'nombre_lignes':len(parsed),'source':url,'empreinte_sha256':sha})
                journal(f'À APPROUVER {source_id} ({len(parsed)} éléments)')
            except Exception as ex:
                failures.append(f'{source_id}: {ex}')
                journal(f'INCIDENT {source_id}: {ex}')
    if not changes:
        journal(f'Aucun changement exploitable. Identiques : {len(unchanged)}, incidents : {len(failures)}.')
        return {'changements':0,'identiques':len(unchanged),'echecs':failures,'proposition':None}
    PENDING.parent.mkdir(parents=True,exist_ok=True)
    proposal={'cree_le':datetime.now(timezone.utc).isoformat(),
              'base_sha256':hashlib.sha256(active_bytes).hexdigest(),
              'modifications':changes,'echecs':failures,'referentiel':staged}
    ecrire_atomiquement(PENDING, json.dumps(proposal,ensure_ascii=False,separators=(',',':')).encode('utf8'))
    journal(f'PROPOSITION {len(changes)} modifications, {len(failures)} incidents, {len(unchanged)} identiques.')
    return {'changements':len(changes),'identiques':len(unchanged),'echecs':failures,
            'proposition':str(PENDING)}


def run(annee,deps):
    result=preparer_proposition(annee,deps)
    return 0 if not result['echecs'] else 1


if __name__=='__main__':
    parser=argparse.ArgumentParser(description='Créer une proposition DGFiP multi-départements.')
    parser.add_argument('--annee',type=int,default=min(2026,datetime.now().year))
    parser.add_argument('--departements',nargs='+',default=None,help='Codes de département, ex. 42 75 2A 971. Par défaut : les départements déjà présents dans le référentiel.')
    opts=parser.parse_args()
    if opts.departements is None:
        source=ACTIVE if ACTIVE.exists() else BASE
        existing=json.loads(source.read_text(encoding='utf8'))
        opts.departements=sorted(existing.get('tarifs',{}))
    sys.exit(run(opts.annee,opts.departements))
