"""Consultation prudente des taux publiés en open data par la DGFiP.

IMPORTANT : le jeu officiel « fiscalité locale des particuliers » publie
notamment un taux GLOBAL TFPB et un taux TEOM. Ne jamais substituer ce taux
GLOBAL à la part communale : les assiettes neutralisées sont distinctes.

Les champs et leur découpage peuvent changer. La détection est vérifiée sur le
schéma transmis par l'API au moment de l'appel. Si une variable est ambiguë,
elle n'est pas affectée automatiquement.
"""
from __future__ import annotations
import datetime
import math
import re
from typing import Dict
import requests
from moteur import norm

SOURCE = 'https://www.data.gouv.fr/datasets/fiscalite-locale-des-particuliers'
API_BASE = 'https://data.economie.gouv.fr/api/explore/v2.1/catalog/datasets/fiscalite-locale-des-particuliers'


def _field_name(entry):
    return str(entry.get('name') or entry.get('id') or '').strip()


def _field_desc(entry):
    return norm(' '.join(str(entry.get(p) or '') for p in ('name','label','description')))


def detecter_champs(fields):
    """Ne sélectionne que des colonnes non ambiguës du schéma public."""
    fields = [f for f in fields if isinstance(f, dict) and _field_name(f)]
    def unique(predicate):
        candidates = [_field_name(f) for f in fields if predicate(norm(_field_name(f)), _field_desc(f))]
        return candidates[0] if len(candidates) == 1 else None
    codes = unique(lambda k,d: k in ('INSEECOM','CODEINSEE','CODGEO','CODCOM','CODECOMMUNE','INSEECOMMUNE'))
    years = unique(lambda k,d: k in ('ANNEE','AN','EXERCICE','MILLESME','MILLESIME','ANNEEIMPOSITION','ANNEEFISCALE'))

    def is_tfb(s):
        return any(x in s for x in ('TFPB','TFB','TAXEFONCIEREBATI','TAXEFONCIEREPROPRIETESBATIES','FONCIERBATI'))
    def is_teom(s):
        return 'TEOM' in s or 'ORDURESMENAGERES' in s
    def is_rate(s):
        return any(x in s for x in ('TAUX','RATE'))
    def is_total(s):
        return any(x in s for x in ('GLOBAL','CUMULE','TOTAL','ENSEMBLE'))
    # Source peut intituler la colonne « TFB » sans précision : volontairement
    # pas de qualification comme total lorsqu'elle n'est pas établie.
    results = {
        'code':codes, 'annee':years,
        'tfb_global':unique(lambda k,d:is_tfb(d) and is_rate(d) and is_total(d)),
        'teom':unique(lambda k,d:is_teom(d) and is_rate(d) and not is_total(d)),
    }
    # Au cas où le taux TEOM serait explicitement « taux global TEOM ».
    if not results['teom']:
        results['teom'] = unique(lambda k,d: is_teom(d) and is_rate(d))
    parts = {
        'commune':('COMMUNAL','PARTCOMMUNE','COMMUNE'),
        'epci':('INTERCOMMUNAL','EPCI','INTERCO'),
        'syndicat':('SYNDICAL','SYNDICAT'),
        'taxes_speciales':('TSE','TAXESPECIALE','TASARIF'),
        'gemapi':('GEMAPI',),
    }
    for part,tokens in parts.items():
        results[part] = unique(lambda k,d,tokens=tokens: is_tfb(d) and is_rate(d) and
                               any(x in d for x in tokens) and not is_total(d))
    return results


def _number(v):
    if v is None or isinstance(v, bool):
        return None
    if isinstance(v, str):
        v = v.replace('\u00a0','').replace('\u202f','').replace(' ','').replace(',','.').replace('%','')
    try:
        result = float(v)
    except (ValueError,TypeError):
        return None
    if not math.isfinite(result) or not 0 <= result <= 100:
        return None
    return result


def _code(v):
    s = str(v or '').strip().upper()
    # INSEE métropole, Corse et départements d'outre-mer. Conserve les zéros.
    if s.endswith('.0') and s[:-2].isdigit():
        s=s[:-2]
    if s.isdigit() and len(s)<5:
        s=s.zfill(5)
    return s


def extraire_taux(records, fields, code_insee, annee_souhaitee):
    """Lecture sans extrapolation : retourne seulement une ligne année/code exacts.

    N'effectue aucune conversion hasardeuse depuis les centimes, taux de base ou
    produits votés. Tous les taux indiqués sont en pourcentage.
    """
    champs=detecter_champs(fields)
    if not champs['code'] or not champs['annee']:
        raise ValueError('Code INSEE et année non identifiables dans le jeu public ; aucune affectation automatique.')
    needle=_code(code_insee)
    wanted=int(annee_souhaitee)
    matching=[]
    for r in records:
        if _code(r.get(champs['code'])) != needle:
            continue
        raw=r.get(champs['annee'])
        try: y=int(float(str(raw)))
        except (TypeError,ValueError):continue
        if y==wanted:
            matching.append(r)
    if len(matching)!=1:
        raise ValueError(f'Attendu : un seul enregistrement DGFiP {needle} / {wanted} ; trouvé : {len(matching)}. '
                         'Ne pas utiliser les taux d’une autre année, ni un taux zoné sans confirmation.')
    row=matching[0]
    data={part:_number(row.get(field)) for part,field in champs.items()
          if field and part not in ('code','annee')}
    data={k:v for k,v in data.items() if v is not None}
    if not data:
        raise ValueError('Aucun taux TFPB ou TEOM clairement identifié dans cette publication.')
    return {'annee':wanted, 'code_insee':needle, 'taux':data,
            'colonnes':{k:v for k,v in champs.items() if k in data},
            'source':SOURCE, 'consulte_le':datetime.datetime.now(datetime.timezone.utc).isoformat(),
            'complet':all(k in data for k in ('commune','epci','syndicat','taxes_speciales','gemapi','teom'))}


def rechercher_taux(code_insee, annee, session=None):
    """Appel direct API officielle Opendatasoft, sans clé API.

    L'API publique nécessite Internet sur le poste utilisateur ; si sa structure
    a changé l'opération échoue sans réutiliser des taux d'une autre année.
    """
    code=_code(code_insee)
    if not re.fullmatch(r'(?:\d{5}|2[AB]\d{3})',code):
        raise ValueError('Code INSEE attendu (5 caractères), ex. 69387.')
    sess=session or requests.Session()
    try:
        schema_resp=sess.get(API_BASE,timeout=15)
        schema_resp.raise_for_status()
        schema=schema_resp.json()
        fields=schema.get('fields',[])
        if not fields:
            raise ValueError('Schéma de la publication DGFiP indisponible.')
        cols=detecter_champs(fields)
        if not cols['code'] or not cols['annee']:
            raise ValueError('Impossible de reconnaître les colonnes code INSEE / année du jeu DGFiP.')
        # La valeur du code est validée avant interpolation. Filtrage ciblé, pas
        # de téléchargement massif du jeu (plusieurs dizaines de Mo).
        where=f'{cols["code"]} = "{code}" AND {cols["annee"]} = {int(annee)}'
        r=sess.get(API_BASE+'/records',params={'where':where,'limit':50},timeout=20)
        r.raise_for_status()
        records=r.json().get('results',[])
        return extraire_taux(records,fields,code,annee)
    except requests.RequestException as e:
        raise ValueError(f'Service public DGFiP indisponible ou requête refusée : {e}') from e
