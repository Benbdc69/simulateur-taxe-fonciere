"""Identification indicative des parcelles : géocodage IGN puis API Carto.

Ne fait jamais de rapprochement juridique automatique entre une adresse et une parcelle.
Un point BAN peut être placé sur la chaussée : la recherche s'étend donc aux
parcelles situées autour du point, puis exige une confirmation humaine.
"""
from __future__ import annotations
import json
import math
import re
import requests

GEOCODAGE = 'https://data.geopf.fr/geocodage/search'
CADASTRE = 'https://apicarto.ign.fr/api/cadastre/parcelle'


def _variantes_adresse(query):
    """Rend plus explicite un arrondissement lyonnais saisi sous « Lyon 7 »."""
    query = ' '.join(query.strip().split())
    result = [query]
    m = re.search(r'\bLyon\s*([1-9])\s*(?:e|ème|eme)?\s*(?:arr(?:ondissement)?\.?)?\b', query, re.I)
    if m:
        post = '6900' + m.group(1)
        q2 = query[:m.start()] + post + ' Lyon' + query[m.end():]
        if q2 != query:
            result.insert(0, q2.strip())
    return result


def _get_json(url, params, timeout):
    try:
        response = requests.get(url, params=params, timeout=timeout,
                                headers={'User-Agent':'Simulateur-TF-professionnels/3.1'})
        response.raise_for_status()
        data = response.json()
    except requests.RequestException as ex:
        raise ConnectionError(f'Le service officiel est indisponible ou inaccessible : {ex}') from ex
    except ValueError as ex:
        raise ValueError('Le service officiel n’a pas renvoyé de réponse JSON lisible.') from ex
    if not isinstance(data, dict) or not isinstance(data.get('features'), list):
        raise ValueError('La réponse du service officiel ne contient pas de parcelles/adresses GeoJSON.')
    return data['features']


def adresses(query):
    if len(query.strip()) < 5:
        raise ValueError('Renseigner une adresse suffisamment précise.')
    out = []
    seen = set()
    for q in _variantes_adresse(query):
        features = _get_json(GEOCODAGE, {'q':q, 'index':'address', 'limit':8}, 15)
        for feature in features:
            p = feature.get('properties') or {}
            xy = (feature.get('geometry') or {}).get('coordinates') or []
            if len(xy) < 2 or not all(isinstance(n, (int,float)) for n in xy[:2]):
                continue
            if (xy[0],xy[1]) in seen:
                continue
            seen.add((xy[0],xy[1]))
            citycode = str(p.get('citycode') or p.get('city_code') or '')
            postcode = str(p.get('postcode') or '')
            # La commune de Lyon a le code INSEE 69123, le cadastre du 7e 69387.
            # L'API Carto reste prioritaire pour le véritable code cadastral.
            insee_cadastral = citycode
            if postcode in {f'6900{i}' for i in range(1,10)} and citycode in ('', '69123'):
                insee_cadastral = '6938' + postcode[-1]
            out.append({'libelle': p.get('label') or p.get('name') or q,
                        'commune': p.get('city') or p.get('municipality') or '',
                        'insee': insee_cadastral,
                        'code_insee_adresse': citycode,
                        'code_postal': postcode,
                        'departement': (insee_cadastral or citycode)[:2],
                        'lon':xy[0], 'lat':xy[1],
                        'precision': p.get('score'),
                        'type_geocodage': p.get('type') or ''})
        if out:
            break
    return out


def _rectangle(lon, lat, rayon_m):
    """Rectangle WGS84 approximatif, limité au voisinage de l'adresse."""
    dy = rayon_m / 111320.0
    dx = rayon_m / max(111320.0 * math.cos(math.radians(lat)), 1000.0)
    return {'type':'Polygon', 'coordinates':[[
        [lon-dx,lat-dy], [lon+dx,lat-dy], [lon+dx,lat+dy],
        [lon-dx,lat+dy], [lon-dx,lat-dy]
    ]]}


def _distance_segment(px, py, ax, ay, bx, by):
    dx,dy=bx-ax,by-ay
    t=0.0 if dx*dx+dy*dy==0 else max(0.,min(1.,((px-ax)*dx+(py-ay)*dy)/(dx*dx+dy*dy)))
    return math.hypot(px-(ax+t*dx),py-(ay+t*dy))


def _distance_polygone(geom, lon, lat):
    """Distance indicative en mètres au polygone (0 si le point est dedans)."""
    if not geom or not geom.get('coordinates'):
        return None
    typ=geom.get('type')
    multi = [geom['coordinates']] if typ == 'Polygon' else geom['coordinates'] if typ == 'MultiPolygon' else []
    if not multi:
        return None
    coslat = math.cos(math.radians(lat))
    def proj(x,y):
        return ((x-lon)*111320*coslat,(y-lat)*111320)
    best = float('inf')
    for poly in multi:
        if not poly: continue
        outer=poly[0]
        if len(outer)<3:continue
        points = [proj(x,y) for x,y in outer]
        inside=False
        for a,b in zip(points,points[1:]+points[:1]):
            if (a[1]>0)!=(b[1]>0):
                x_hit=a[0]+(b[0]-a[0])*(-a[1])/(b[1]-a[1])
                if x_hit>0:inside=not inside
            best=min(best,_distance_segment(0,0,*a,*b))
        # Si trou intérieur, on ne déclare pas abusivement une correspondance exacte.
        if inside:
            in_hole=False
            for hole in poly[1:]:
                pts=[proj(x,y) for x,y in hole]
                odd=False
                for a,b in zip(pts,pts[1:]+pts[:1]):
                    if (a[1]>0)!=(b[1]>0) and a[0]+(b[0]-a[0])*(-a[1])/(b[1]-a[1])>0:
                        odd=not odd
                if odd:in_hole=True
            if not in_hole:return 0.0
    return round(best, 1) if math.isfinite(best) else None


def _normaliser_parcelle(feature, adresse, mode, rayon_m):
    p=feature.get('properties') or {}
    idu=str(p.get('idu') or p.get('id') or '')
    code_insee=str(p.get('code_insee') or '')
    if len(code_insee)!=5 and len(idu)>=5 and idu[:5].isdigit():
        code_insee=idu[:5]
    if len(code_insee)!=5 and p.get('code_dep') is not None and p.get('code_com') is not None:
        code_insee=str(p['code_dep']).zfill(2)+str(p['code_com']).zfill(3)
    if len(code_insee)!=5:
        code_insee=str(adresse.get('insee') or '')
    section=str(p.get('section') or '').strip().upper()
    numero=str(p.get('numero') or '').strip().zfill(4)
    if not section or not numero or numero=='0000':
        return None
    prefixe=str(p.get('com_abs') if p.get('com_abs') is not None else p.get('prefixe') or '').strip()
    if not prefixe and len(idu)>=8 and idu[5:8].isdigit():
        prefixe=idu[5:8]
    if prefixe.isdigit():prefixe=prefixe.zfill(3)
    dist=_distance_polygone(feature.get('geometry'),adresse['lon'],adresse['lat'])
    return {'insee':code_insee, 'commune':adresse.get('commune',''),
            'departement':code_insee[:2] or adresse.get('departement',''),
            'section':section, 'numero':numero, 'prefixe':prefixe, 'id':idu,
            'distance_m':dist, 'recherche':'Point dans la parcelle' if mode=='point' else 'Parcelle voisine — confirmation obligatoire',
            'rayon_recherche_m':0 if mode=='point' else rayon_m}


def parcelles_a_l_adresse(adresse, rayon_m=40):
    """Retourne la parcelle au point et, à défaut, plusieurs candidates voisines.

    Une correspondance géométrique approximative n'est PAS une identification
    cadastrale certaine : toujours confirmer la parcelle sur le plan officiel.
    """
    if not all(k in adresse for k in ('lon','lat')):
        raise ValueError('Coordonnées géographiques de l’adresse absentes.')
    lon,lat=float(adresse['lon']),float(adresse['lat'])
    if not (-180 <= lon <= 180 and -90 <= lat <= 90):
        raise ValueError('Coordonnées géographiques invalides.')
    rayon_m=int(rayon_m)
    if not (5<=rayon_m<=100):
        raise ValueError('Le rayon de recherche doit être compris entre 5 et 100 mètres.')
    geom=json.dumps({'type':'Point','coordinates':[lon,lat]},separators=(',',':'))
    direct=_get_json(CADASTRE,{'geom':geom, '_limit':20},18)
    mode='point'
    features=direct
    if not features:
        mode='proximite'
        geom=json.dumps(_rectangle(lon,lat,rayon_m),separators=(',',':'))
        features=_get_json(CADASTRE,{'geom':geom,'_limit':120},22)
    parcelles=[];seen=set()
    for feature in features:
        obj=_normaliser_parcelle(feature,adresse,mode,rayon_m)
        if not obj:continue
        key=(obj['insee'],obj['prefixe'],obj['section'],obj['numero'])
        if key in seen:continue
        seen.add(key)
        parcelles.append(obj)
    parcelles.sort(key=lambda r:(r['distance_m'] is None,r['distance_m'] if r['distance_m'] is not None else float('inf'),r['section'],r['numero']))
    return parcelles[:50]


def rechercher_parcelle(insee,section,numero,prefixe=None):
    if not insee or not section or not numero:
        raise ValueError('Code INSEE, section et numéro requis.')
    params={'code_insee':str(insee), 'section':str(section).strip().upper(),
            'numero':str(numero).strip().zfill(4), '_limit':25}
    if prefixe is not None and str(prefixe).strip():
        params['com_abs']=str(prefixe).strip().zfill(3)
    return [f.get('properties',{}) for f in _get_json(CADASTRE,params,18)]
