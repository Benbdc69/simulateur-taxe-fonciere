"""Tarifs cadastraux nationaux des logements (tarifs de comparaison *1970*).
Le jeu DGFiP 2024 est téléchargeable publiquement (~17 Mo). On lit uniquement
le fichier CSV officiel, sans requête sur les caractéristiques d'un logement.
"""
from __future__ import annotations
import csv,io,re,unicodedata
from functools import lru_cache
import requests

DATASET='descriptif-tarifs-des-locaux-d-habitation_2024'
URL=f'https://data.economie.gouv.fr/api/explore/v2.1/catalog/datasets/{DATASET}/exports/csv?use_labels=true'
URL_ALT='https://www.data.gouv.fr/api/1/datasets/r/629800aa-b887-43f0-b48a-9f07214180a2'

def normaliser(x):
    return ''.join(c for c in unicodedata.normalize('NFKD',str(x).lower()) if not unicodedata.combining(c))

def col(cols,*terms):
    for term in terms:
        t=normaliser(term)
        for k in cols:
            if t==normaliser(k):return k
    for term in terms:
        t=normaliser(term)
        for k in cols:
            if t in normaliser(k):return k
    return None

def parse_csv(text):
    head=text[:1000]
    sep=';' if head.count(';')>=head.count(',') else ','
    reader=csv.DictReader(io.StringIO(text.lstrip('\ufeff')),delimiter=sep)
    cols=reader.fieldnames or []
    cc=col(cols,'code insee de la commune','code insee commune','code commune','insee')
    dep=col(cols,'code departement','departement')
    nature=col(cols,'nature du local','nature local','nature')
    serie=col(cols,'serie tarif bati','serie tarif','serie')
    categ=col(cols,'categorie du local','categorie local','categorie')
    prix=col(cols,'valeur locative au m2','tarif m2','valeur locative','tarif')
    origine=col(cols,'code commune origine du tarif','origine du tarif')
    if not all([cc,nature,serie,categ,prix]):raise ValueError('Colonnes du fichier DGFiP non reconnues : '+', '.join(cols[:20]))
    out=[]
    for r in reader:
        try:
            raw_code=str(r[cc]).strip().replace('.0','')
            raw_dep=str(r.get(dep,'') or '').strip().replace('.0','')
            if re.fullmatch(r'\d{1,3}',raw_code) and raw_dep:
                # Code local 381..389 -> code cadastral 69381...69389 pour Lyon
                code=raw_dep.zfill(2)+raw_code.zfill(3) if raw_dep.isdigit() and len(raw_dep)<=2 else raw_dep+raw_code.zfill(2)
            else:
                code=raw_code.zfill(5) if raw_code.isdigit() else raw_code
            n=str(r[nature]).strip().upper()
            match=re.search(r'(?<!\d)([1-8])(?!\d)',str(r[categ]))
            if not match or n not in ('M','A'):continue
            t=float(str(r[prix]).replace(' ','').replace('\u00a0','').replace(',','.'))
            if not 0<t<100000:continue
            out.append({'insee':code,'nature':n,'categorie':int(match.group(1)),'serie':str(r[serie]).strip(),
                        'origine':str(r.get(origine,'')).strip(),'tarif_1970':t,'annee_tarif':2024})
        except (ValueError,TypeError):continue
    if not out:raise ValueError('Aucune ligne de tarif exploitable')
    return out

@lru_cache(maxsize=1)
def tarifs_nationaux():
    for url in (URL,URL_ALT):
        try:
            response=requests.get(url,timeout=45,headers={'User-Agent':'Axens-Simulateur-Habitation/0.1'})
            response.raise_for_status()
            return parse_csv(response.content.decode('utf-8-sig',errors='replace'))
        except (requests.RequestException,ValueError,UnicodeError):continue
    raise RuntimeError('Tarifs DGFiP temporairement indisponibles : fichier national 2024 non téléchargé.')

def rechercher_tarifs(code_insee,nature,categorie,rows=None):
    rows=tarifs_nationaux() if rows is None else rows
    return sorted([r for r in rows if r['insee']==str(code_insee) and r['nature']==nature and r['categorie']==int(categorie)],
                  key=lambda x:(x['serie'],x['origine']))
