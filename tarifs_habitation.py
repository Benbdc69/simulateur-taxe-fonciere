"""DGFiP - tarifs locaux d'habitation 2024 en valeur de référence 1970.
Conserve EXACTEMENT les catégories intermédiaires 1M..7M et l'identité
commune d'origine + série tarifaire. Source nationale 17,2 Mo, cachée en mémoire.
"""
from __future__ import annotations
import csv
import io
import re
import unicodedata
from functools import lru_cache
import requests

DATASET='descriptif-tarifs-des-locaux-d-habitation_2024'
URL=f'https://data.economie.gouv.fr/api/explore/v2.1/catalog/datasets/{DATASET}/exports/csv?use_labels=true'
URL_ALT='https://www.data.gouv.fr/api/1/datasets/r/629800aa-b887-43f0-b48a-9f07214180a2'
URL_MIROIR=f'https://data.opendatasoft.com/api/explore/v2.1/catalog/datasets/{DATASET}%40opendatamef/exports/csv?use_labels=true'
SOURCE='https://www.data.gouv.fr/datasets/taxe-fonciere-sur-les-proprietes-baties-tarifs-des-locaux-dhabitation-2024'

def normaliser(x):
    text=unicodedata.normalize('NFKD',str(x or '').lower())
    return ''.join(c for c in text if not unicodedata.combining(c)).replace('_',' ').replace('²','2').strip()

def col(cols,*terms):
    vals={normaliser(k):k for k in cols}
    for t in terms:
        if normaliser(t) in vals:return vals[normaliser(t)]
    for t in terms:
        matches=[k for k in cols if normaliser(t) in normaliser(k)]
        if matches:return matches[0]
    return None

def normaliser_insee(code):
    s=str(code or '').strip().upper()
    if s.isdigit():return s.zfill(5)
    return s

def code_pour_tarif(departement,code_commune):
    dep=str(departement or '').strip().upper()
    raw=str(code_commune or '').strip()
    if raw.endswith('.0'):raw=raw[:-2]
    # Dans la source, la commune est une référence locale au département (387 pour Lyon 7e).
    if re.fullmatch(r'\d{5}',raw):return raw
    if dep in ('2A','2B') and raw.isdigit():return dep+raw.zfill(3)
    if dep.isdigit() and len(dep)==2 and raw.isdigit():return dep+raw.zfill(3)
    if dep.isdigit() and len(dep)==3 and raw.isdigit():return dep+raw.zfill(2)
    raise ValueError(f'Code commune tarif inexploitable ({dep}/{raw})')

def _categorie(v):
    s=str(v or '').strip().upper().replace(' ','')
    return s if re.fullmatch('[1-8]|[1-7]M',s) else None

def parse_csv(text):
    text=text.lstrip('\ufeff')
    head=text.splitlines()[0]
    delimiter=';' if head.count(';')>=head.count(',') else ','
    reader=csv.DictReader(io.StringIO(text),delimiter=delimiter)
    cols=reader.fieldnames or []
    dep=col(cols,'Département','departement','code département')
    cc=col(cols,'Code Commune','code_commune','code insee de la commune')
    nature=col(cols,'Nature locaux','nature_locaux','nature du local')
    serie=col(cols,'Série tarif bâti','serie_tarif_bati','serie tarif')
    categ=col(cols,'Catégorie','categorie')
    prix=col(cols,'VL au m²','vl_au_m2','valeur locative au m2')
    origine=col(cols,'Code commune origine du tarif','code_commune_origine_du_tarif')
    if not all((cc,nature,serie,categ,prix)):
        raise ValueError('En-têtes DGFiP non reconnus : '+', '.join(cols[:12]))
    result=[]
    for r in reader:
        try:
            if not r or r.get(cc) in (None,''):continue
            code=code_pour_tarif(r[dep] if dep else '',r[cc]); n=str(r[nature]).strip().upper()
            c=_categorie(r[categ]); t=float(str(r[prix]).strip().replace('\u202f','').replace('\xa0','').replace(' ','').replace(',','.'))
            if c is None or n not in ('M','A','D') or not (0<t<100000):continue
            result.append({'insee':code,'nature':n,'categorie':c,'serie':str(r[serie]).strip(),
              'origine':str(r.get(origine,'') or '').strip(),'tarif_1970':t,'annee_tarif':2024})
        except (ValueError,TypeError):continue
    if not result:raise ValueError('Le jeu DGFiP ne contient aucune ligne de tarif reconnue')
    return result

@lru_cache(maxsize=1)
def tarifs_nationaux():
    fails=[]
    for url in (URL,URL_ALT,URL_MIROIR):
        try:
            r=requests.get(url,timeout=(15,90),headers={'User-Agent':'Axens-Simulateur-Taxe-Fonciere/1.0'})
            r.raise_for_status()
            # N'acceptons pas une page HTML ou une réponse bloquée par un pare-feu
            if 'html' in r.headers.get('content-type','').lower():raise ValueError('HTML à la place du CSV')
            return parse_csv(r.content.decode('utf-8-sig'))
        except (requests.RequestException,ValueError,UnicodeError) as ex:
            fails.append(type(ex).__name__)
    raise RuntimeError('Données tarifaires DGFiP 2024 momentanément inaccessibles via les trois serveurs. '+', '.join(fails))

def rechercher_tarifs(code_insee,nature,categorie,rows=None):
    data=tarifs_nationaux() if rows is None else rows
    code=normaliser_insee(code_insee);cat=_categorie(categorie)
    if cat is None:raise ValueError('Catégorie tarifaire inconnue')
    matches=[r for r in data if r['insee']==code and r['nature']==nature and r['categorie']==cat]
    # Une même lettre de série peut exister pour deux origines de tarif différentes.
    return sorted(matches,key=lambda x:(str(x['serie']),str(x.get('origine',''))))
