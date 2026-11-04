"""Récupération prudente des taux TFPB par composante.

2026 : deux classeurs DGCL des taux votés commune et EPCI.
2024-2025 : REI DGFiP en API OFGL, variables E12/E22/E32/E52...
Le REI n'est JAMAIS extrapolé d'une année à l'autre.
Les taux TEOM publiés au niveau communal peuvent être zonés.
"""
from __future__ import annotations
import datetime as dt
import hashlib
import io
import math
import re
from urllib.parse import quote

import requests
from moteur import norm
from taux_dgfip import _code, _number

DGCL_PAGE = 'https://www.collectivites-locales.gouv.fr/etudes-et-statistiques/acces-aux-statistiques-par-thematique/fiscalite/taux-de-fiscalite-directe-locale-votes-par-les-collectivites'
REI_PAGE = 'https://data.economie.gouv.fr/explore/dataset/fiscalite-locale-des-particuliers-geo/'
REI_API = 'https://data.economie.gouv.fr/api/explore/v2.1/catalog/datasets/fiscalite-locale-des-particuliers-geo'
GEO_API = 'https://geo.api.gouv.fr/communes/'
DGCL_URL = ('https://www.collectivites-locales.gouv.fr/files/files/Etudes-et-statistiques/'
            'Taux%20de%20fiscalit%C3%A9%20directe%20locale%20vot%C3%A9s%20par%20les%20collectivit%C3%A9s/'
            '{annee}/Taux_{annee}_{nature}.xlsx')

# Codes des communes de Paris/Lyon/Marseille (les tableaux de taux sont par commune).
def code_commune_fiscale(code):
    c = _code(code)
    if re.fullmatch(r'751\d\d', c):
        return '75056'
    if re.fullmatch(r'6938\d', c) or c == '69389':
        return '69123'
    if re.fullmatch(r'132\d\d', c):
        return '13055'
    return c


def controle_codes(annee, code):
    if not 2017 <= int(annee) <= 2026:
        raise ValueError('Le moteur ne couvre pas les impositions après 2026.')
    if not re.fullmatch(r'(?:\d{5}|2[AB]\d{3})', _code(code)):
        raise ValueError('Code INSEE commune invalide.')


def date_utc():
    return dt.datetime.now(dt.timezone.utc).isoformat()


def _get(session, url, params=None, timeout=35):
    try:
        response=session.get(url,params=params,timeout=timeout)
        response.raise_for_status()
        return response
    except requests.RequestException as exc:
        raise ValueError(f'Échec de la source officielle {url}: {exc}') from exc


def source_tableur(annee, nature):
    if int(annee) not in (2025,2026) or nature not in ('communes','EPCI'):
        raise ValueError('Les liens de tableurs DGCL sont vérifiés uniquement pour 2025 et 2026.')
    return DGCL_URL.format(annee=int(annee),nature=nature)


def telecharger_classeur(annee, nature, session=None):
    sess=session or requests.Session()
    url=source_tableur(annee,nature)
    r=_get(sess,url,timeout=50)
    data=r.content
    if len(data)>20_000_000 or not data.startswith(b'PK'):
        raise ValueError(f'{nature} : téléchargement non reconnu comme fichier XLSX.')
    return data,url


def _code_raw(v):
    if v is None or isinstance(v,bool):return ''
    t=str(v).strip().upper()
    if re.fullmatch(r'\d+\.0+',t):t=t.split('.')[0]
    return t


def _percent(v,fmt=''):
    out=_number(v)
    if out is None:return None
    if '%' in str(fmt) and out<=1:
        return round(out*100,8)
    return out


def _name_candidates(label):
    """Identifie TFPB sans confondre TFPB et TFPNB ou taux de variation.

    La DGCL utilise, selon les fichiers, « Taxe sur le foncier bâti »,
    « Taxe foncière sur les propriétés bâties » ou « Taux voté TFB ».
    """
    t=norm(label)
    if not t:return False
    if any(x in t for x in ('NONBATI','NONBATIES','TFPNB','TFNB','FONCIERNONBATI',
                              'EVOLUTION','VARIATION','DELTA','PRODUIT','MONTANT','BASEIMPOSABLE')):
        return False
    return any(x in t for x in (
        'FONCIERBATI','FONCIEREBATIE','PROPRIETESBATIES',
        'TAXEFB','TFPB','TAUXTFB','TAUXFB','TFB')) or bool(re.search(r'\bFB\b',str(label).upper()))


def _classer_colonne(label, nature, annee):
    t=norm(label)
    if nature=='communes':
        if t in ('CODECOMMUNE','CODEINSEE','CODGEO','INSEE','INSEECOMMUNE','CODEINSEECOMMUNE','CODCOM','CODEOFFICIELGEOGRAPHIQUE','CODECOMMUNAL') or 'CODEINSEE' in t and 'EPCI' not in t:
            return 'code'
        if t in ('DEPARTEMENT','CODEDEPARTEMENT','CODEDEP','DEP','DEPT'):return 'departement'
    else:
        if t in ('SIREN','SIRENEPCI','CODEEPCI','CODEGROUPEMENT','NUMEROSIREN','SIRENDUEPCI','CODEINSEEEPCI') or ('SIREN' in t and 'COMMUNE' not in t):
            return 'code'
    if _name_candidates(label) and ('TAUX' in t or 'FONCIERBATI' in t or 'PROPRIETESBATIES' in t or 'TFPB' in t or 'TAUXFB' in t or t == 'TFB'):
        if str(annee-1) in t and str(annee) not in t:
            return None
        return 'taux'
    return None


def lire_tableur_dgcl(contenu, nature, annee):
    """Accepte en-têtes mono/multilignes, refuse colonnes taux ambiguës.

    Conserve la provenance et la numération de taux en pourcents, y compris
    les cellules Excel ayant un format '%' (valeur interne 0.3189).
    """
    from openpyxl import load_workbook
    if nature not in ('communes','EPCI'):
        raise ValueError('Type de document DGCL non reconnu.')
    if len(contenu)>20_000_000:
        raise ValueError('Classeur trop volumineux.')
    try:
        book=load_workbook(io.BytesIO(contenu),read_only=True,data_only=True)
    except Exception as exc:
        raise ValueError('Classeur DGCL illisible : '+str(exc)) from exc
    candidates=[]
    for ws in book.worksheets:
        # Lecture en flux : ne garde que la feuille compatible, 4 lignes de titres max.
        first=list(__import__('itertools').islice(ws.iter_rows(),40))
        for h in range(min(30,len(first))):
            # Utiliser en priorité l'intitulé de la ligne elle-même :
            # concaténer le bandeau supérieur « Statistiques 2026 » avec le
            # titre « Département » empêchait de reconnaître cette colonne,
            # puis les codes communes à 3 chiffres étaient tous écartés.
            labels=[]; mapping={}
            for j in range(len(first[h])):
                raw=first[h][j].value
                direct=str(raw).strip() if raw is not None else ''
                proposed=[direct]
                if h>=1:
                    above=first[h-1][j].value if j<len(first[h-1]) else None
                    if above is not None:
                        proposed.append(str(above).strip()+' '+direct)
                if h>=2:
                    above2=first[h-2][j].value if j<len(first[h-2]) else None
                    above1=first[h-1][j].value if j<len(first[h-1]) else None
                    if above2 is not None or above1 is not None:
                        proposed.append(' '.join(str(z).strip() for z in (above2,above1,raw) if z is not None))
                chosen=direct
                role=None
                for label in proposed:
                    candidate=_classer_colonne(label,nature,annee)
                    if candidate:
                        role=candidate; chosen=label
                        break
                labels.append(chosen)
                if role:mapping.setdefault(role,[]).append(j)
            if len(mapping.get('code',[]))==1 and len(mapping.get('taux',[]))==1:
                # Priorité à une ligne qui donne aussi le département si besoin.
                score=(2 if mapping.get('departement') else 0)+len([x for x in labels if x])*.001
                candidates.append((score,ws.title,h,mapping,labels))
                break
    if not candidates:
        raise ValueError('Colonnes Code commune/SIREN et TFPB non reconnues dans le classeur DGCL. '
                         'Transmettez ce XLSX pour adapter les en-têtes.')
    candidates.sort(key=lambda x:x[0],reverse=True)
    _,sheet_name,h,mapping,labels=candidates[0]
    ws=book[sheet_name]
    col_code=mapping['code'][0]
    col_taux=mapping['taux'][0]
    col_dep=mapping.get('departement',[None])[0]
    result={}
    compte=0
    for row in __import__('itertools').islice(ws.iter_rows(),h+1,None):
        if max([col_code,col_taux]+([col_dep] if col_dep is not None else [])) >= len(row):continue
        code=_code_raw(row[col_code].value)
        if not code:continue
        if nature=='communes':
            if col_dep is not None and len(code)<=3:
                dep=_code_raw(row[col_dep].value)
                code=(dep.zfill(2) if dep.isdigit() and len(dep)<3 else dep)+code.zfill(3)
            elif code.isdigit() and len(code)<5:
                # Ne jamais associer un code 010 à un département arbitraire.
                continue
            code=_code(code)
            if not re.fullmatch(r'(?:\d{5}|2[AB]\d{3})',code):continue
        else:
            if not re.fullmatch(r'\d{9}',code):continue
        taux=_percent(row[col_taux].value,row[col_taux].number_format)
        if taux is None:continue
        if code in result and abs(result[code]-taux)>1e-10:
            raise ValueError(f'Taux contradictoires pour {code} dans le fichier {nature}.')
        result[code]=taux
        compte+=1
    # La DGCL publie >30 000 communes et ~1250 EPCI : éviter les faux positifs.
    minimum=1  # tests et imports partiels autorisés : la source n'est pas certifiée ici.
    if len(result)<minimum:
        raise ValueError('Aucune donnée de taux TFPB exploitable dans le tableau '+sheet_name)
    return {'taux':result,'feuille':sheet_name,'colonnes':{'code':labels[col_code],'taux':labels[col_taux]},
            'nombre_lignes':compte,'nombre_identifiants':len(result),
            'empreinte':hashlib.sha256(contenu).hexdigest()}


def siren_epci(code_insee, session=None):
    code=code_commune_fiscale(code_insee)
    if not re.fullmatch(r'(?:\d{5}|2[AB]\d{3})',code):
        raise ValueError('Code commune invalide pour l’API Géo.')
    sess=session or requests.Session()
    doc=_get(sess,GEO_API+quote(code),params={'fields':'nom,code,codeEpci'},timeout=15).json()
    if str(doc.get('code') or '') != code:
        raise ValueError('Le code de commune renvoyé par API Géo ne correspond pas.')
    siren=str(doc.get('codeEpci') or '')
    if not re.fullmatch(r'\d{9}',siren):
        raise ValueError('Aucun SIREN d’EPCI confirmé par le référentiel géographique.')
    return siren


def rechercher_dgcl(code_insee,annee,session=None,fichier_communes=None,fichier_epci=None,siren=None):
    """Ne considère jamais le taux voté comme nécessairement appliqué à la parcelle.

    Les fichiers (bytes, URL) optionnels permettent l'import manuel hors réseau.
    """
    controle_codes(annee,code_insee)
    if int(annee) not in (2025,2026):
        raise ValueError('Importation directe DGCL proposée pour les millésimes 2025 et 2026.')
    sess=session or requests.Session()
    taux={}; details={}; avertissements=[]
    source_urls={}
    def lire(nature,dossier):
        if dossier is not None:
            if isinstance(dossier,tuple):data,url=dossier
            else:data,url=dossier,'Fichier DGCL fourni par utilisateur'
        else:
            data,url=telecharger_classeur(annee,nature,sess)
        source_urls[nature]=url
        return lire_tableur_dgcl(data,nature,annee)
    ccode=code_commune_fiscale(code_insee)
    try:
        communes=lire('communes',fichier_communes)
        if ccode in communes['taux']:
            taux['commune']=communes['taux'][ccode]
            details['commune']={'source':source_urls['communes'],'methode':'taux voté',
                                 'colonne':communes['colonnes']['taux'],'cle':ccode,
                                 'sha256':communes['empreinte']}
        else:avertissements.append('Taux communal non trouvé pour '+ccode+' dans le classeur '+str(annee)+'.')
    except ValueError as exc:avertissements.append(str(exc))
    try:
        if not siren:
            siren=siren_epci(code_insee,sess)
        epcis=lire('EPCI',fichier_epci)
        if siren in epcis['taux']:
            taux['epci']=epcis['taux'][siren]
            details['epci']={'source':source_urls['EPCI'],'methode':'taux voté',
                               'colonne':epcis['colonnes']['taux'],'cle':siren,
                               'sha256':epcis['empreinte']}
        else:avertissements.append('SIREN EPCI '+str(siren)+' absent du tableau DGCL '+str(annee)+'.')
    except ValueError as exc:avertissements.append(str(exc))
    if not taux:
        raise ValueError('Aucune part de taux DGCL récupérable : '+' | '.join(avertissements))
    return {'annee':int(annee),'code_insee':_code(code_insee),'code_commune_taux':ccode,
            'taux':taux,'preuves':details,'avertissements':avertissements,
            'source':DGCL_PAGE,'consulte_le':date_utc(),'nature':'taux votés',
            'complet':False}


def _recherche_champ(fields, noms):
    available=[f.get('name') for f in fields if isinstance(f,dict)]
    matched=[c for c in available if norm(c) in set(map(norm,noms))]
    return matched[0] if len(matched)==1 else None


def _classifier_libelle_rei(libelle):
    """Classe une seule ligne si elle nomme explicitement la taxe et un taux.

    Les identifiants numériques du REI peuvent varier selon la notice annuelle.
    La classification par un libellé explicite évite de prendre un montant pour
    un taux. Aucun calcul de taux n'est déduit des recettes ou bases.
    """
    texte=norm(libelle)
    if not texte or 'TAUX' not in texte:return None
    if any(x in texte for x in ('TAUXMOYEN','PRODUIT','VARIATION','EVOLUTION','TAUXCFE','BASE')):
        return None
    if texte.startswith('TEOM') or 'ENLEVEMENTDESORDURESMENAGERES' in texte:
        return 'teom'
    if not (texte.startswith('FB') or texte.startswith('TFB') or texte.startswith('TFPB') or
            texte.startswith('TAXEFONCIEREBATI') or texte.startswith('FONCIERBATI')):
        return None
    if any(x in texte for x in ('NONBATI','FNB','TFNB')):return None
    if 'GEMAPI' in texte:return 'gemapi'
    if 'SYNDICAT' in texte:return 'syndicat'
    if any(x in texte for x in ('TSE','TAXESPECIALE','TASA')):return 'taxes_speciales'
    if any(x in texte for x in ('INTERCOMMUNALITE','EPCI','GFP')):return 'epci'
    if 'COMMUNE' in texte or 'COMMUNAL' in texte:return 'commune'
    return None


def extraire_rei(records,annee,code_insee):
    """Extrait des taux REI d'un libellé explicite, y compris 0 % renseigné.

    Plusieurs valeurs différentes d'une même part ou un taux secret statistique
    entraînent un refus plutôt qu'un choix arbitraire.
    """
    candidats={part:[] for part in ('commune','syndicat','epci','taxes_speciales','gemapi','teom')}
    avert=[]
    for r in records:
        if str(r.get('sec_stat') or r.get('secret_statistique') or '').lower().startswith('sec_stat'):
            continue
        libelle=str(r.get('libelle') or r.get('variable_nom') or r.get('var') or '').strip()
        part=_classifier_libelle_rei(libelle)
        if not part:continue
        number=_number(r.get('valeur'))
        if number is None:continue
        candidats[part].append((number,libelle))
    result={}; preuves={}
    for part,values in candidats.items():
        if not values:continue
        # Préférence pour le taux net lorsque le REI contient voté + net ;
        # jamais de somme de variables ni d'interpolation depuis une base.
        net=[x for x in values if 'TAUXNET' in norm(x[1])]
        use=net if net else values
        differences={round(v,6) for v,_ in use}
        if len(differences)>1:
            avert.append('Plusieurs taux '+part+' divergents dans le REI : contrôle nécessaire, non prérempli.')
            continue
        result[part]=use[0][0]
        preuves[part]={'source':REI_PAGE,'methode':'Taux déclaré REI',
                       'variables':[x[1] for x in use], 'cle':code_insee,'annee':annee}
        if part=='teom':
            avert.append('TEOM : taux publié au niveau communal ; zonage cadastral et part incitative à confirmer sur avis.')
    return result,preuves,avert


def rechercher_rei(code_insee, annee, session=None):
    """Les taux détaillés de la DGFiP, fichier fiscalité locale des particuliers (REI 2025).

    Nom conservé pour la compatibilité avec le collecteur et les anciens tests.
    """
    from taux_territoriaux_dgfip import rechercher_taux_detailles
    return rechercher_taux_detailles(code_insee, annee, session=session)
