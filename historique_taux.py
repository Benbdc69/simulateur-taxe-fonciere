"""Historique des taux fiscaux à la commune, avec repli millésimé par composante.

Un taux absent n'est pas zéro. Un taux N-1 n'est pas un taux N :
le millésime de la donnée et la provenance sont conservés à chaque résolution.
Aucun chiffre de source N-1 n'est réenregistré sous le millésime N.
"""
from __future__ import annotations
import copy
import datetime as dt
import math
import re
from taux_composantes import code_commune_fiscale

COMPOSANTES=('commune','syndicat','epci','taxes_speciales','gemapi','teom')
LIBELLES={'commune':'Commune','syndicat':'Syndicat','epci':'Intercommunalité',
          'taxes_speciales':'Taxes spéciales / TSE','gemapi':'GEMAPI','teom':'TEOM'}


def code_reference(code_insee):
    code=code_commune_fiscale(str(code_insee or '').strip())
    if not re.fullmatch(r'(?:\d{5}|2[AB]\d{3})', code):
        raise ValueError('Code INSEE de commune invalide (5 caractères).')
    return code


def _annee(y):
    try: annee=int(y)
    except (ValueError,TypeError): raise ValueError('Millésime du taux invalide.') from None
    if not 2017 <= annee <= 2026:
        raise ValueError('Millésime de taux hors du périmètre 2017-2026.')
    return annee


def _taux(v):
    if v is None or isinstance(v,bool):raise ValueError('Taux manquant ou invalide.')
    try: t=float(str(v).strip().replace(' ','').replace(',','.').replace('%',''))
    except (ValueError,TypeError):raise ValueError('Taux non numérique.') from None
    if not math.isfinite(t) or t < 0 or t > 100:
        raise ValueError('Un taux doit être compris entre 0 et 100 %, y compris zéro.')
    return round(t,8)


def enregistrer(ref,code_insee,annee,composante,taux,source,*,url='',
               detail='',remplacer=False,zonage_confirme=False,date_controle=None):
    """Mutant explicite : ne remplace pas une donnée enregistrée sans autorisation.

    `source` inclut une qualification (DGCL, OFGL/REI, avis fiscal, manuel, etc.).
    """
    code=code_reference(code_insee)
    year=_annee(annee)
    if composante not in COMPOSANTES:raise ValueError('Composante fiscale inconnue.')
    valeur=_taux(taux)
    if not str(source or '').strip():raise ValueError('Source obligatoire pour enregistrer un taux.')
    data=ref.setdefault('taux_annuels',{}).setdefault(code,{})
    ann=data.setdefault(str(year),{})
    if composante in ann and not remplacer:
        ancien=ann[composante]
        if abs(float(ancien['taux'])-valeur)>1e-8 or ancien.get('source') != source:
            raise ValueError('Ce taux existe déjà : confirmer explicitement son remplacement.')
        return False
    ann[composante]={
        'taux':valeur,'annee_source':year,'source':str(source).strip(),
        'url':str(url or '').strip(), 'detail':str(detail or '').strip(),
        'zonage_confirme':bool(zonage_confirme) if composante=='teom' else True,
        'date_controle':date_controle or dt.datetime.now(dt.timezone.utc).isoformat()
    }
    return True


def supprimer(ref,code_insee,annee,composante):
    code=code_reference(code_insee); year=_annee(annee)
    if composante not in COMPOSANTES:raise ValueError('Composante fiscale inconnue.')
    commune=ref.get('taux_annuels',{}).get(code,{})
    obj=commune.get(str(year),{})
    if composante not in obj:return False
    del obj[composante]
    if not obj:del commune[str(year)]
    if not commune:del ref['taux_annuels'][code]
    return True


def _cles_stockage_compatibles(ref, code_insee):
    """Retrouve les taux historiques sous 69123 OU 69387 pour Lyon 7e.

    La clé cadastrale et la clé fiscale étaient utilisées alternativement
    selon les versions. Le moteur fusionne ces versions uniquement si
    leurs montants sont compatibles pour un même millésime.
    """
    code=code_reference(code_insee)
    cles=[code]
    for brut, annuelles in ref.get('taux_annuels',{}).items():
        if brut==code or not isinstance(annuelles,dict):continue
        try:
            if code_reference(brut)==code:
                cles.append(brut)
        except ValueError:
            continue
    return cles


def resoudre(ref,code_insee,annee,composante,repli=True):
    """Privilégie N, puis le dernier taux disponible, même sous l'ancienne clé.

    N'invente jamais une valeur absente. Si deux valeurs différentes existent
    pour la même année sur deux codes fiscalement équivalents, l'erreur est
    levée avant de produire une estimation.
    """
    code=code_reference(code_insee)
    year=_annee(annee)
    if composante not in COMPOSANTES:raise ValueError('Composante fiscale inconnue.')
    choices=[]
    for key in _cles_stockage_compatibles(ref,code):
        annees=ref.get('taux_annuels',{}).get(key,{})
        for y, parts in annees.items():
            if not str(y).isdigit() or int(y)>year or not isinstance(parts,dict):continue
            if not repli and int(y)!=year:continue
            item=parts.get(composante)
            if item is None:continue
            if not isinstance(item,dict) or item.get('taux') is None:continue
            taux=_taux(item['taux'])
            choices.append((int(y),key,item,taux))
    if not choices:return None
    selected_year=max(x[0] for x in choices)
    same_year=[x for x in choices if x[0]==selected_year]
    if len({x[3] for x in same_year})>1:
        raise ValueError(f'Taux {composante} {selected_year} contradictoires entre codes cadastraux et fiscaux : corriger le référentiel.')
    chosen=next((x for x in same_year if x[1]==code),same_year[0])
    result=copy.deepcopy(chosen[2])
    result['annee_source']=selected_year
    result['annee_imposition']=year
    result['decalage']=year-selected_year
    result['statut']='à jour' if selected_year==year else f'⚠ Taux {selected_year} repris pour {year}'
    result['code_commune_taux']=code
    result['composante']=composante
    return result


def resoudre_tout(ref,code_insee,annee):
    return {key:resoudre(ref,code_insee,annee,key) for key in COMPOSANTES}


def lignes_historique(ref,code_insee):
    code=code_reference(code_insee)
    rows=[]
    for y,parts in ref.get('taux_annuels',{}).get(code,{}).items():
        for key,datum in parts.items():
            rows.append({'Année':int(y),'Taxe':LIBELLES.get(key,key),'Clé':key,
                         'Taux (%)':datum.get('taux'),'Source':datum.get('source'),
                         'Précision':datum.get('detail',''),
                         'Zonage TEOM confirmé':datum.get('zonage_confirme'),
                         'Lien':datum.get('url','')})
    return sorted(rows,key=lambda x:(-x['Année'],x['Taxe']))


def integrer_publication(ref,pub,remplacer=False):
    """Enregistre une réponse source en conservant son véritable millésime.

    Exige des métadonnées vérifiables par composante ; pas de taux global.
    """
    if not isinstance(pub,dict) or not pub.get('code_insee'):
        raise ValueError('Publication de taux invalide.')
    y=_annee(pub['annee']); code=code_reference(pub['code_insee'])
    log=[]; incidents=[]
    for key,val in pub.get('taux',{}).items():
        if key not in COMPOSANTES:continue
        preuve=pub.get('preuves',{}).get(key,{})
        provenance=preuve.get('source') or pub.get('source') or ''
        if not provenance:
            incidents.append(key+' : source absente')
            continue
        note=str(preuve.get('methode',''))
        if key=='teom':note+=' · TEOM zonée éventuelle, vérifier la parcelle'
        try:
            ok=enregistrer(ref,code,y,key,val,source=pub.get('nature') or 'Source publique',
                 url=provenance,detail=note,remplacer=remplacer,zonage_confirme=False)
            if ok:log.append(key)
        except ValueError as ex:incidents.append(key+' : '+str(ex))
    return log,incidents
