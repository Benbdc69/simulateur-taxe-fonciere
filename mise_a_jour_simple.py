"""Activation un clic de données officielles validées, avec sauvegarde préalable.

Le clic explicite constitue l'accord d'activation ; aucune opération automatique
programmée. Une publication partielle est signalée, jamais remplie au hasard.
"""
from __future__ import annotations
import copy
import hashlib
import json
import os
from datetime import datetime
from pathlib import Path
from actualiser import preparer_proposition, PENDING, ACTIVE, BASE
from collecte_taux import preparer as proposer_taux
from historique_taux import code_reference, enregistrer

HISTORY=BASE.parent/'historique'

def ouvrir_referentiel():
    path=ACTIVE if ACTIVE.exists() else BASE
    return json.loads(path.read_text(encoding='utf-8'))


def enregistrer_referentiel(ref, *, expected_sha256=None):
    path=ACTIVE if ACTIVE.exists() else BASE
    if expected_sha256 is not None:
        checksum=hashlib.sha256(path.read_bytes()).hexdigest()
        if checksum!=expected_sha256:
            raise ValueError('Le référentiel a changé pendant cette opération. Actualisez la page.')
    ACTIVE.parent.mkdir(parents=True,exist_ok=True)
    if ACTIVE.exists():
        HISTORY.mkdir(parents=True,exist_ok=True)
        t=datetime.now().strftime('%Y%m%d-%H%M%S-%f')
        (HISTORY/f'referentiel-{t}.json').write_bytes(ACTIVE.read_bytes())
    tmp=ACTIVE.with_suffix('.tmp')
    tmp.write_text(json.dumps(ref,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    os.replace(tmp,ACTIVE)


def verifier_proposition(proposition,departement,annee):
    if not isinstance(proposition,dict):raise ValueError('Proposition invalide.')
    mods=proposition.get('modifications',[])
    if not isinstance(mods,list) or not mods:raise ValueError('Proposition vide.')
    for m in mods:
        if m.get('departement')!=departement:
            raise ValueError('Département différent dans la proposition : contrôle manuel requis.')
        if m.get('type') not in ('secteurs','tarifs','neutralisations','localisations'):
            raise ValueError('Type de données non reconnu : contrôle manuel requis.')
        if not isinstance(m.get('nombre_lignes'),int) or m['nombre_lignes']<=0:
            raise ValueError('Fichier officiel vide ou non validé.')
    if not isinstance(proposition.get('referentiel'),dict):raise ValueError('Référentiel cible invalide.')
    return True


def synchroniser_dgfip(annee,dep,*, prepare=preparer_proposition):
    if PENDING.exists():
        raise ValueError('Une mise à jour attend déjà une validation dans les réglages avancés. Vérifiez-la avant de recommencer.')
    bilan=prepare(int(annee),[dep])
    if not bilan.get('changements'):
        return bilan
    if not PENDING.exists():raise ValueError('La proposition DGFiP ne peut pas être relue.')
    prop=json.loads(PENDING.read_text(encoding='utf-8'))
    verifier_proposition(prop,dep,int(annee))
    enregistrer_referentiel(prop['referentiel'],expected_sha256=prop['base_sha256'])
    PENDING.unlink()
    return bilan


def synchroniser_taux(annee,code_insee, *, preparer=proposer_taux):
    code=code_reference(code_insee)
    proposal=preparer(code,int(annee))
    ref=ouvrir_referentiel()
    start=hashlib.sha256((ACTIVE if ACTIVE.exists() else BASE).read_bytes()).hexdigest()
    changed=[]; existing=[]
    for k, rec in proposal.get('propositions',{}).items():
        y=str(rec.get('annee',''))
        if not y.isdecimal() or int(y)>int(annee):continue
        # Les données saisies/vérifiées précédemment ne sont pas écrasées.
        previous=ref.get('taux_annuels',{}).get(code,{}).get(y,{}).get(k)
        if previous is not None:
            existing.append(k);continue
        try:
            if enregistrer(ref,code,int(y),k,rec['taux'],rec['source'],url=rec.get('url',''),
                 detail=rec.get('detail',''),zonage_confirme=False):
                changed.append(f'{k} ({y})')
        except (ValueError,KeyError):continue
    if changed:enregistrer_referentiel(ref,expected_sha256=start)
    return {'ajoutes':changed,'deja_presents':existing,'incidents':proposal.get('incidents',[]),
            'sources':proposal.get('sources_consultees',[])}
