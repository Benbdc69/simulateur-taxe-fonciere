"""Taux des différentes composantes TFPB à partir de l'open data officiel DGFiP.

Source : « Fiscalité locale des particuliers - Géo » (REI 2025),
https://data.economie.gouv.fr/explore/dataset/fiscalite-locale-des-particuliers-geo/

Les champs E12VOTE / E22 / E32VOTE / E52 / E52A / E52TASA /
E52gGEMAPI / Taux_Plein_TEOM sont explicitement documentés.
Ce référentiel n'est pas un avis d'imposition du bien : taux votés, TEOM
susceptible de zonage et harmonisation des taux à vérifier.

IMPORTANT : le millésime 2025 est fixé explicitement. Il ne faut pas
présumer qu'une réédition ultérieure de la source vaut pour 2025 : la
version et le millésime du référentiel doivent être revus à chaque
nouvelle publication annuelle.
"""
from __future__ import annotations
import datetime as dt
import math
import re
from urllib.parse import quote

import requests
from taux_dgfip import _code, _number

SOURCE_PAGE='https://data.economie.gouv.fr/explore/dataset/fiscalite-locale-des-particuliers-geo/'
API='https://data.economie.gouv.fr/api/explore/v2.1/catalog/datasets/fiscalite-locale-des-particuliers-geo'
EXERCICE_REFERENCE=2025
CHAMPS={'commune':'e12vote','syndicat':'e22','epci':'e32vote',
        'gemapi':'e52ggemapi','teom':'taux_plein_teom'}
CHAMPS_TSE=('e52','e52a','e52tasa')
GLOBAL='taux_global_tfb'


def analyser_taux_dgfip_2025(records, *, code_insee, fields=None, millesime=2025):
    """Reçoit UNE commune REI. Aucune interpolation ni résultat autre année.

    Les 3 champs TSE sont des lignes d'imposition distinctes. Leur somme est
    proposée comme taxes spéciales, sous réserve du contrôle de cohérence
    avec le taux global officiel (quand disponible).
    """
    if int(millesime)!=EXERCICE_REFERENCE:
        raise ValueError('Ce référentiel détaillé a pour millésime officiel 2025 uniquement.')
    code=_code(code_insee)
    if not re.fullmatch(r'(?:\d{5}|2[AB]\d{3})',code):
        raise ValueError('Code commune fiscal invalide.')
    rows=[r for r in records if _code(r.get('insee_com'))==code]
    if len(rows)!=1:
        raise ValueError(f'REI 2025 : attendu un enregistrement pour {code}, obtenu {len(rows)}.')
    row=rows[0]
    known=set(fields) if fields else set(row)
    if not {'insee_com','e12vote','e22','e32vote','e52ggemapi',GLOBAL}.intersection(known):
        raise ValueError('Le jeu DGFiP ne comporte pas les champs attendus de la taxe foncière bâtie.')
    data={};preuves={};avert=[]
    for key,column in CHAMPS.items():
        if column not in known: continue
        value=_number(row.get(column))
        if value is None:continue
        data[key]=value
        preuves[key]={'source':SOURCE_PAGE,'methode':'DGFiP REI 2025 : taux publié',
                      'colonne':column,'cle':code,'annee':2025}
    # E52 / E52A / E52TASA sont distingués pour ne pas confondre un total global TFPB
    # avec les parts de taxes spéciales. Une colonne absente n'est jamais un zéro.
    if all(c in known for c in CHAMPS_TSE):
        t_values=[_number(row.get(c)) for c in CHAMPS_TSE]
        if all(v is not None for v in t_values):
            total=round(sum(t_values),8)
            if total<=100:
                data['taxes_speciales']=total
                preuves['taxes_speciales']={'source':SOURCE_PAGE,'methode':'DGFiP REI 2025 : E52 + E52A + E52TASA',
                                             'colonne':' + '.join(CHAMPS_TSE),'cle':code,'annee':2025}
        else:avert.append('Taxes spéciales : une sous-composante est absente ; aucun taux agrégé supposé.')
    else:
        avert.append('Taxes spéciales : les 3 champs TSE nécessaires ne sont pas disponibles.')
    global_officiel=_number(row.get(GLOBAL)) if GLOBAL in known else None
    if global_officiel is not None:
        # Vérification seulement si chaque part est effectivement documentée.
        keys=('commune','syndicat','epci','taxes_speciales','gemapi')
        if all(k in data for k in keys):
            somme=round(sum(data[k] for k in keys),6)
            if abs(somme-global_officiel)>0.055:
                avert.append(f'Contrôle TFPB : somme des composantes {somme:.3f} %, taux global '
                              f'{global_officiel:.3f} %. Incohérence : vérifier la décomposition REI et l’avis.')
                # Le résultat peut cacher une composante hors périmètre ; ne pas
                # enregistrer un taux de taxes spéciales agrégé potentiellement erroné.
                data.pop('taxes_speciales',None)
                preuves.pop('taxes_speciales',None)
    if 'teom' in data:
        avert.append('TEOM : taux plein au niveau communal ; vérifier le zonage et la part incitative du bien.')
    if not data:
        raise ValueError(f'Aucun taux TFPB/TEOM détaillé reconnu pour {code}.')
    return {'code_insee':code,'annee':2025,'taux':data,'preuves':preuves,
            'avertissements':avert,'source':SOURCE_PAGE,
            'nature':'Taux détaillés DGFiP / REI 2025','complet':len(data)==6}


def rechercher_taux_detailles(code_insee,annee,session=None):
    """Lecture du jeu DGFiP en API Opendatasoft. Ne met pas de valeurs en cache disque.

    Ce jeu ne possède pas toujours un champ millésime sur chaque ligne.
    La version cible est fixée à 2025 (source officielle publiée en 2026),
    et l'API refusera une année différente plutôt que de rebaptiser des taux.
    """
    if int(annee)!=EXERCICE_REFERENCE:
        raise ValueError('Le jeu détaillé DGFiP intégré concerne 2025 uniquement (repli pour 2026).')
    # Local : les arrondissements sont des subdivisions cadastrales, mais les taux
    # de commune sont votés pour Lyon, Paris et Marseille globalement.
    from taux_composantes import code_commune_fiscale
    code=code_commune_fiscale(code_insee)
    if not re.fullmatch(r'(?:\d{5}|2[AB]\d{3})',code):
        raise ValueError('Code INSEE fiscal invalide.')
    sess=session or requests.Session()
    try:
        schema_resp=sess.get(API,timeout=20)
        schema_resp.raise_for_status()
        schema=schema_resp.json()
        names={str(f.get('name','')).lower() for f in schema.get('fields',[]) if isinstance(f,dict)}
        if 'insee_com' not in names or 'e12vote' not in names:
            raise ValueError('Jeu DGFiP non reconnu : colonnes insee_com et e12vote absentes.')
        # La description de la publication peut explicitement fournir un millésime.
        # Le cas échéant, rejeter une réédition postérieure à 2025.
        # Les métadonnées "last_modified" concernent la publication, pas l'année fiscale.
        year_fields=sorted(names.intersection({'annee','exercice','millesime','annee_imposition'}))
        where=f'insee_com = "{code}"'
        if year_fields:
            where+=f' AND {year_fields[0]} = 2025'
        response=sess.get(API+'/records',params={'where':where,'limit':10},timeout=25)
        response.raise_for_status()
        payload=response.json()
        if payload.get('total_count',len(payload.get('results',[])))!=1:
            raise ValueError(f'DGFiP 2025 : commune {code} absente ou plusieurs réponses, contrôle manuel requis.')
        rows=payload.get('results') or []
        if year_fields:
            for r in rows:
                if str(r.get(year_fields[0])) not in ('2025','2025.0'):
                    raise ValueError('Millésime de l’enregistrement fiscal différent de 2025.')
        result=analyser_taux_dgfip_2025(rows,code_insee=code,fields=names)
        result.update({'consulte_le':dt.datetime.now(dt.timezone.utc).isoformat(),
                       'code_commune_taux':code})
        return result
    except requests.RequestException as ex:
        raise ValueError(f'API DGFiP indisponible : {ex}') from ex
