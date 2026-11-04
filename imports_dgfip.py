"""Téléchargement DGFiP et lecture XLSX/ODS avec XML standard (sans Excel)."""
import io
import re
import hashlib
import zipfile
from datetime import datetime, timezone
from xml.etree import ElementTree as ET
import requests
from moteur import norm, parcel_code, comm_code
from referentiel import normaliser_departement

DOMAIN = 'https://www.impots.gouv.fr/sites/default/files/media/rvllp'
PAGE = 'https://www.impots.gouv.fr/revision-des-valeurs-locatives'
MAX_BYTES = 12_000_000


def url_fichier(departement, type_donnee, annee):
    dep = normaliser_departement(departement).lower()
    if type_donnee == 'tarifs':
        return f"{DOMAIN}/tarif/{int(annee)}/tarif-{dep}.{'ods' if int(annee) <= 2020 else 'xlsx'}"
    if type_donnee == 'localisations':
        return f'{DOMAIN}/coef-loc/{int(annee)}/coef-loc-{dep}.ods'
    if type_donnee == 'secteurs':
        return f'{DOMAIN}/secteur/secteur-{dep}.ods'
    if type_donnee == 'neutralisations':
        chemin = 'coef-neut-ap21' if int(annee) >= 2021 else 'coef-neut'
        return f'{DOMAIN}/{chemin}/{chemin}-{dep}.ods'
    raise ValueError('Type inconnu')


def telecharger(url):
    r = requests.get(url, timeout=(6, 30), headers={'User-Agent':'SimulateurRVLLP-V1/1.0'}, stream=True)
    r.raise_for_status()
    parts=[]; n=0
    for chunk in r.iter_content(chunk_size=65536):
        if not chunk:continue
        parts.append(chunk);n += len(chunk)
        if n > MAX_BYTES:raise ValueError('Fichier anormalement volumineux.')
    blob=b''.join(parts)
    if not zipfile.is_zipfile(io.BytesIO(blob)):
        raise ValueError('La réponse DGFiP n’est pas un fichier XLSX/ODS : téléchargement refusé.')
    return blob


def _as_number(s):
    if isinstance(s,(int,float)):
        return float(s)
    t=str(s or '').replace('\u202f','').replace('\xa0','').replace(' ','').replace(',','.')
    try:return float(t)
    except (TypeError,ValueError):return None


def feuilles_xlsx(blob):
    """Toutes les feuilles XLSX, y compris les cellules texte inline et les colonnes vides."""
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        items = set(z.namelist())
        paths = sorted((p for p in items if re.fullmatch(r'xl/worksheets/sheet\d+\.xml', p)),
                       key=lambda p: int(re.search(r'sheet(\d+)\.xml', p).group(1)))
        if not paths:
            raise ValueError('Aucune feuille Excel lisible dans ce fichier.')
        ns = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
        strings = []
        if 'xl/sharedStrings.xml' in items:
            root = ET.fromstring(z.read('xl/sharedStrings.xml'))
            strings = [''.join(n.text or '' for n in si.findall('.//m:t', ns))
                       for si in root.findall('m:si', ns)]
        noms = []
        if 'xl/workbook.xml' in items:
            root = ET.fromstring(z.read('xl/workbook.xml'))
            noms = [s.get('name', '') for s in root.findall('.//m:sheets/m:sheet', ns)]
        out = []
        for n, path in enumerate(paths):
            root = ET.fromstring(z.read(path))
            rows = []
            for row in root.findall('.//m:sheetData/m:row', ns):
                arr = []
                for cell in row.findall('m:c', ns):
                    letters = re.match(r'[A-Z]+', cell.get('r', ''))
                    if not letters:
                        continue
                    col = 0
                    for ch in letters.group():
                        col = col * 26 + ord(ch) - 64
                    col -= 1
                    if col >= 80:
                        continue
                    while len(arr) <= col:
                        arr.append('')
                    typ = cell.get('t')
                    val = cell.find('m:v', ns)
                    if typ == 'inlineStr':
                        arr[col] = ''.join(x.text or '' for x in cell.findall('.//m:t', ns))
                    elif val is not None and val.text is not None:
                        if typ == 's':
                            idx = int(val.text)
                            arr[col] = strings[idx] if idx < len(strings) else ''
                        elif typ in ('str', 'e', 'b'):
                            arr[col] = val.text
                        else:
                            x = _as_number(val.text)
                            arr[col] = x if x is not None else val.text
                if any(str(x).strip() for x in arr):
                    rows.append(arr)
                if len(rows) > 100000:
                    raise ValueError('Feuille Excel anormalement volumineuse.')
            out.append((noms[n] if n < len(noms) else f'Feuille {n+1}', rows))
        return out


def feuilles_ods(blob):
    """Toutes les feuilles ODS, avec les cellules fusionnées et répétées."""
    ns = {'t': 'urn:oasis:names:tc:opendocument:xmlns:table:1.0',
          'o': 'urn:oasis:names:tc:opendocument:xmlns:office:1.0',
          'p': 'urn:oasis:names:tc:opendocument:xmlns:text:1.0'}
    with zipfile.ZipFile(io.BytesIO(blob)) as z:
        if 'content.xml' not in z.namelist():
            raise ValueError('Fichier ODS incomplet : content.xml absent.')
        root = ET.fromstring(z.read('content.xml'))
    tables = root.findall('.//t:table', ns)
    if not tables:
        raise ValueError('Aucune feuille ODS lisible.')
    celltag = '{' + ns['t'] + '}table-cell'
    covered = '{' + ns['t'] + '}covered-table-cell'
    out = []
    for num, tab in enumerate(tables):
        rows = []
        for row in tab.findall('t:table-row', ns):
            arr = []
            for cell in row:
                if cell.tag not in {celltag, covered}:
                    continue
                repeat = min(int(cell.get('{' + ns['t'] + '}number-columns-repeated', '1')), 80)
                val = cell.get('{' + ns['o'] + '}value')
                if val is not None:
                    converted = _as_number(val)
                    val = converted if converted is not None else val
                else:
                    val = ' '.join(''.join(p.itertext()).strip() for p in cell.findall('p:p', ns)).strip()
                arr.extend([val] * min(repeat, max(0, 80 - len(arr))))
                if len(arr) >= 80:
                    break
            if any(str(v).strip() for v in arr):
                count = min(int(row.get('{' + ns['t'] + '}number-rows-repeated', '1')), 1000)
                rows.extend([arr] * count)
            if len(rows) > 100000:
                raise ValueError('Feuille ODS anormalement volumineuse.')
        out.append((tab.get('{' + ns['t'] + '}name') or f'Feuille {num+1}', rows))
    return out


def feuilles(blob, nom_fichier):
    if not zipfile.is_zipfile(io.BytesIO(blob)):
        raise ValueError('Le fichier reçu n’est pas un tableur XLSX/ODS valide.')
    ext = nom_fichier.lower().split('?')[0]
    if ext.endswith('.ods'):
        return feuilles_ods(blob)
    if ext.endswith('.xlsx'):
        return feuilles_xlsx(blob)
    raise ValueError('Format non reconnu : utiliser un fichier officiel .xlsx ou .ods.')


def tableau_xlsx(blob):
    return feuilles_xlsx(blob)[0][1]


def tableau_ods(blob):
    return feuilles_ods(blob)[0][1]


def tableau(blob, nom_fichier):
    return feuilles(blob, nom_fichier)[0][1]


def apercu_fichier(blob, nom_fichier, max_lignes=35):
    """Aperçu non destructif destiné à aider à repérer une mise en page inhabituelle."""
    return [{'nom': name, 'nombre_lignes': len(rows), 'lignes': rows[:max_lignes]}
            for name, rows in feuilles(blob, nom_fichier)]


def _get(row, idx):
    return row[idx] if idx is not None and 0 <= idx < len(row) else ''


def _prefixe(value):
    """Formate un préfixe cadastral en 3 caractères, sans transformer 0.0 en 00."""
    n = _as_number(value)
    if n is not None and n.is_integer() and 0 <= n <= 999:
        return f'{int(n):03d}'
    return str(value or '').strip()


def _col_name(i):
    n = i + 1
    s = ''
    while n:
        n, r = divmod(n - 1, 26)
        s = chr(65 + r) + s
    return s


def _labels(rows, start, span):
    size = min(40, max((len(x) for x in rows[start:start+span]), default=0))
    return [norm(' '.join(str(_get(row, col)) for row in rows[start:start+span]))
            for col in range(size)]


def _match_col(labels, key, used=()):
    def matches(s):
        if not s or s in {'NAN', 'NONE'}:
            return False
        if key == 'nom_commune':
            # Ancienne publication TF (jusqu'en 2020) : l'en-tête est 'LIB-CNE'.
            if s in {'LIBCNE', 'LIBELLECNE', 'NOMCNE'}:
                return True
            return ('COMMUNE' in s and not any(b in s for b in
                    ('CODE','INSEE','CODCOM','COEFFICIENT','COEFF','COMMUNAL','TAUX','NEUTRALISATION','TFPB','TAXEFONCIERE')))
        if key == 'section': return 'SECTION' in s or s in {'SEC', 'SECCAD', 'SECTIONCAD'}
        if key == 'secteur': return 'SECTEUR' in s or s == 'SECT'
        if key == 'coefficient': return any(x in s for x in ('COEFLOCAL','COEFFICIENTLOCAL','COEFDELOCAL','COEFFDELOCAL','COEFFICIENTDELOCAL')) or s in ('COEF','COEFF','COEFFICIENT')
        if key == 'parcelle': return any(x in s for x in ('PARCELLE','NUMEROPLAN','NOPLAN','NUMPLAN','NUMEROPARCELLE'))
        if key == 'prefixe': return 'PREFIXE' in s or s == 'PREFIX'
        if key == 'code_commune': return 'CODEINSEE' in s or 'CODECOMMUNE' in s or s in ('INSEE', 'CODCOM', 'COMMUNEINSEE')
        if key == 'commune':
            # Depuis 2021 : 'COEFFICIENT DE NEUTRALISATION COMMUNE/SYND'.
            # Ne jamais confondre avec le libellé ou le code de commune.
            if ('NEUTRALISATION' in s and 'COMMUNE' in s
                    and not any(x in s for x in ('CODECOMMUNE', 'CODEINSEE', 'LIBELLECOMMUNE'))):
                return True
            return (any(x in s for x in ('COMMUNAL', 'PARTCOMMUNE', 'PARTDELACOMMUNE', 'TFCOMMUNE', 'TAXEFONCIERECOMMUNE', 'TFPBCCOMMUNE'))
                    or ('TAXEFONCIERE' in s and 'COMMUNE' in s)) and 'NOMCOMMUNE' not in s
        if key == 'syndicat': return any(x in s for x in ('SYNDICAT','SIVOM','SYNDICAL'))
        if key == 'epci': return any(x in s for x in ('EPCI','INTERCOMMUNAL','INTERCO','COMMUNAUTEDECOMMUNES','GROUPEMENT'))
        if key == 'taxes_speciales': return any(x in s for x in ('TAXESPECIALE','TAXESSPECIALES','TSE','EQUIPEMENT'))
        if key == 'teom': return any(x in s for x in ('TEOM','ORDURESMENAGERES','ENLEVEMENTDESORDURES'))
        if key == 'gemapi': return 'GEMAPI' in s or 'MILIEUXAQUATIQUES' in s
        if key == 'coef_departement':
            return ('NEUTRALISATION' in s and ('DEPARTEMENTALE' in s or 'DEPARTEMENTAL' in s))
        return False
    candidates = [(i, len(label)) for i, label in enumerate(labels)
                  if i not in used and matches(label)]
    if not candidates:
        return None
    # L'intitulé le plus court correspond généralement à la colonne, pas à un titre fusionné.
    return min(candidates, key=lambda x: x[1])[0]


def _entetes(rows, kind, colonnes=None, ligne_debut=None):
    """Repère les en-têtes sur 1 à 3 lignes, puis vérifie le type des données sous-jacentes."""
    if colonnes is not None:
        return int(ligne_debut or 0), colonnes
    requis = {'secteurs': ['nom_commune','secteur'],
             'localisations': ['nom_commune','coefficient'],
             'neutralisations': ['nom_commune','commune']}
    facultatifs = {'secteurs': ['section','prefixe','code_commune'],
                   'localisations': ['section','parcelle','prefixe','code_commune'],
                   'neutralisations': ['code_commune','prefixe','syndicat','epci','taxes_speciales','teom','gemapi','coef_departement']}
    possibles = []
    for i in range(min(80, len(rows))):
        for span in (1, 2, 3):
            if i + span > len(rows):
                continue
            labels = _labels(rows, i, span)
            used = set()
            cols = {}
            for key in requis[kind] + facultatifs[kind]:
                col = _match_col(labels, key, used)
                if col is not None:
                    cols[key] = col
                    used.add(col)
            if kind == 'neutralisations':
                # La publication 2021+ regroupe explicitement deux composantes
                # dans UNE colonne : COMMUNE/SYND et TSE/GEMAPI. Cette
                # duplication est autorisée uniquement pour ces libellés.
                for index, label in enumerate(labels):
                    if ('NEUTRALISATION' in label and 'COMMUNE' in label
                            and ('COMMUNESYND' in label or 'COMMUNESYNDICAT' in label)):
                        if cols.get('commune') == index:
                            cols['syndicat'] = index
                    if 'TSE' in label and 'GEMAPI' in label:
                        cols['taxes_speciales'] = index
                        cols['gemapi'] = index
            if not all(k in cols for k in requis[kind]):
                continue
            # Il faut retrouver de véritables données à la suite des en-têtes.
            numeric_key = 'secteur' if kind == 'secteurs' else 'coefficient' if kind == 'localisations' else 'commune'
            sample = rows[i+span:i+span+80]
            n_numeric = sum(_as_number(_get(r, cols[numeric_key])) is not None for r in sample)
            n_names = sum(bool(str(_get(r, cols['nom_commune'])).strip()) and
                          _as_number(_get(r, cols['nom_commune'])) is None for r in sample)
            if n_numeric < 1 or n_names < 1:
                continue
            score = len(cols) * 10 + min(n_numeric, 30) + min(n_names, 30) - span * 2 - i * 0.01
            possibles.append((score, i + span, cols))
    if not possibles:
        example = ' | '.join(' / '.join(str(v)[:42] for v in r[:7] if str(v).strip())
                             for r in rows[:5])[:260]
        raise ValueError(f'En-têtes {kind} non reconnus (plusieurs lignes ou libellés atypiques). '
                         f'Utilisez l’import assisté en sélectionnant les colonnes. Aperçu : {example}')
    _, start, cols = max(possibles, key=lambda t: t[0])
    return start, cols


def analyser_tarifs(rows, colonnes=None, ligne_debut=None):
    """Accepte catégories en colonne A/B/C, secteurs dans l'ordre ou intitulés sur plusieurs lignes."""
    if colonnes is not None:
        debut = int(ligne_debut or 0)
        code_idx = colonnes['categorie']
        secteurs = {str(n): colonnes.get(str(n)) for n in range(1, 11)
                    if colonnes.get(str(n)) is not None}
    else:
        debut = 0
        code_idx = None
        best = (-1, None)
        for j in range(6):
            count = sum(bool(re.fullmatch(r'[A-Z]{3}[1-9]', norm(_get(r,j)))) for r in rows[:200])
            if count > best[0]:best=(count,j)
        if best[0] < 20:
            raise ValueError('Les codes catégories (BUR2, MAG1, etc.) ne sont pas détectés. '
                             'Contrôler le type de fichier ou utiliser l’import assisté.')
        code_idx=best[1]
        # Certaines grilles présentent 1 à 7, d’autres 1 à 6 secteurs.
        secteurs={}
        for row in rows[:35]:
            cands={}
            for j, v in enumerate(row[:20]):
                s=norm(v)
                found=re.fullmatch(r'(?:SECTEUR|SECT|S)?0?([1-9]|10)', s)
                if found and j>code_idx:
                    cands[found.group(1)]=j
            if len(cands)>=3 and len(cands)>len(secteurs):
                secteurs=cands
        if not secteurs:
            sample=next((r for r in rows if re.fullmatch(r'[A-Z]{3}[1-9]',norm(_get(r,code_idx)))),[])
            numeric=[j for j in range(code_idx+1,min(len(sample),code_idx+14))
                     if (_as_number(_get(sample,j)) or 0)>0]
            if len(numeric)<2:
                raise ValueError('Secteurs tarifaires non identifiés. Utiliser l’import assisté.')
            secteurs={str(n):j for n,j in enumerate(numeric[:10],start=1)}
    grid={}
    for row in rows[debut:]:
        code=norm(_get(row,code_idx))
        if not re.fullmatch(r'[A-Z]{3}[1-9]',code):
            continue
        vals={str(s):float(x) for s,j in secteurs.items()
              if j is not None and (x:=_as_number(_get(row,j))) is not None and x>0}
        if len(vals)>=2:
            grid[code]=vals
    if not 25 <= len(grid) <= 70:
        raise ValueError(f'Grille tarifaire non conforme : {len(grid)} catégories valides (25 minimum).')
    if len({tuple(sorted(v)) for v in grid.values()})>3:
        raise ValueError('Les catégories ne présentent pas les mêmes colonnes de secteurs.')
    return grid


def analyser_secteurs(rows, colonnes=None, ligne_debut=None):
    debut, c=_entetes(rows,'secteurs',colonnes,ligne_debut)
    out=[]; last_name=''; last_code=''
    for r in rows[debut:]:
        name=str(_get(r,c['nom_commune']) or '').strip()
        code=comm_code(_get(r,c.get('code_commune')))
        sector=_as_number(_get(r,c['secteur']))
        if not name and sector is not None:
            name=last_name;code=code or last_code
        if name:
            last_name=name;last_code=code
        if not name or sector is None or not 1<=sector<=15 or not float(sector).is_integer():
            continue
        out.append({'code_commune':code,'commune':name,
                    'prefixe':(_prefixe(_get(r,c.get('prefixe'))) if 'prefixe' in c else ''),
                    'section':str(_get(r,c.get('section')) or '').strip(),
                    'secteur':int(sector)})
    if len(out)<30:raise ValueError(f'Sectorisation non plausible : {len(out)} lignes (30 minimum).')
    return out



def _ligne_localisation_positionnelle_valide(row, cols):
    """Contrôle une ligne de coefficient DGFiP sans en-têtes explicites.

    Un alignement purement numérique ne suffit pas : nous vérifions ensemble
    le département (si présent), le code commune, le nom, la section cadastrale,
    le numéro de plan et le coefficient fiscal.
    """
    if 'departement' in cols:
        dep = _get(row, cols['departement'])
        if norm(dep) not in {'2A', '2B'}:
            n = _as_number(dep)
            if n is None or not n.is_integer() or not 1 <= n <= 976:
                return False
    code = _as_number(_get(row, cols['code_commune']))
    if code is None or not code.is_integer() or not 1 <= code <= 999:
        return False
    nom = str(_get(row, cols['nom_commune']) or '').strip()
    if len(nom) < 2 or not any(ch.isalpha() for ch in nom) or _as_number(nom) is not None:
        return False
    section = norm(_get(row, cols['section']))
    if not re.fullmatch(r'[A-Z0-9]{1,3}', section) or not any(ch.isalpha() for ch in section):
        return False
    parc = _get(row, cols['parcelle'])
    if str(parc or '').strip():
        number = _as_number(parc)
        if number is None or not number.is_integer() or not 1 <= number <= 9999:
            return False
    coef = _as_number(_get(row, cols['coefficient']))
    return coef is not None and 0.5 <= coef <= 1.5


def _profil_localisation_sans_entetes(rows):
    """Reconnaît les tableaux DGFiP qui commencent directement par les données.

    Format observé dans la publication 69/localisations/2026 :
    [69.0, 10.0, 'L ARBRESLE', 'AT', 70.0, 1.0]
    -> département, code commune, commune, section, parcelle, coefficient.
    La sélection n'est effectuée que si plusieurs lignes concordent avec un
    unique schéma, pour éviter des associations arbitraires de colonnes.
    """
    profils = [
        {'departement': 0, 'code_commune': 1, 'nom_commune': 2,
         'section': 3, 'parcelle': 4, 'coefficient': 5},
        {'code_commune': 0, 'nom_commune': 1,
         'section': 2, 'parcelle': 3, 'coefficient': 4},
        {'departement': 0, 'code_commune': 1, 'nom_commune': 2,
         'prefixe': 3, 'section': 4, 'parcelle': 5, 'coefficient': 6},
    ]
    candidats = []
    for cols in profils:
        indices = [i for i, row in enumerate(rows[:1000])
                   if _ligne_localisation_positionnelle_valide(row, cols)]
        if len(indices) >= 3:
            # Préférence pour le profil couvrant le plus grand nombre de lignes.
            candidats.append((len(indices), indices[0], cols))
    if not candidats:
        return None
    candidats.sort(key=lambda x: x[0], reverse=True)
    if len(candidats) > 1 and candidats[0][0] == candidats[1][0]:
        # Ambiguïté : ne pas deviner si deux mappings sont équivalents.
        return None
    _, start, cols = candidats[0]
    return start, cols


def analyser_localisations(rows, colonnes=None, ligne_debut=None):
    sans_entete = False
    try:
        debut, c = _entetes(rows, 'localisations', colonnes, ligne_debut)
    except ValueError:
        if colonnes is not None:
            raise
        profil = _profil_localisation_sans_entetes(rows)
        if profil is None:
            raise  # Ne pas inventer de correspondance pour un format inconnu.
        debut, c = profil
        sans_entete = True
    if 'section' not in c and 'parcelle' not in c:
        raise ValueError('Ni section ni parcelle : fichier de localisation non exploitable.')
    out=[];last_name='';last_code=''
    for r in rows[debut:]:
        if sans_entete and not _ligne_localisation_positionnelle_valide(r, c):
            continue
        name=str(_get(r,c['nom_commune']) or '').strip()
        code=comm_code(_get(r,c.get('code_commune')))
        value=_as_number(_get(r,c['coefficient']))
        if not name and value is not None:
            name=last_name;code=code or last_code
        if name:
            last_name=name;last_code=code
        if not name or value is None or not 0.5<=value<=1.5:
            continue
        out.append({'code_commune':code,'commune':name,
                    'prefixe':(_prefixe(_get(r,c.get('prefixe'))) if 'prefixe' in c else ''),
                    'section':str(_get(r,c.get('section')) or '').strip(),
                    'parcelle':parcel_code(_get(r,c.get('parcelle'))),'coefficient':value})
    if not out:raise ValueError('Aucun coefficient de localisation exploitable.')
    return out


def analyser_neutralisations(rows, colonnes=None, ligne_debut=None):
    debut,c=_entetes(rows,'neutralisations',colonnes,ligne_debut)
    taxes=['commune','syndicat','epci','taxes_speciales','teom','gemapi']
    out=[]
    for r in rows[debut:]:
        name=str(_get(r,c['nom_commune']) or '').strip()
        values={k:_as_number(_get(r,c.get(k))) for k in taxes}
        if not name or values['commune'] is None:
            continue
        if not 0<values['commune']<2:
            continue
        if any(v is not None and not 0<v<2 for v in values.values()):
            raise ValueError(f'Coefficient hors plage dans la commune {name}. Import arrêté.')
        # Les colonnes non publiées (notamment TEOM dans les fichiers TF)
        # demeurent absentes : NE JAMAIS recopier arbitrairement un coefficient.
        record={'nom_commune':name, **values}
        if 'code_commune' in c:
            record['code_commune']=comm_code(_get(r,c['code_commune']))
        if 'prefixe' in c:
            record['prefixe']=_prefixe(_get(r,c['prefixe'])) if str(_get(r,c['prefixe']) or '').strip() else ''
        if 'coef_departement' in c:
            record['coef_departement']=_as_number(_get(r,c['coef_departement']))
        out.append(record)
    if not out:
        raise ValueError('Aucun coefficient de neutralisation reconnu.')
    # Les coefficients non renseignés par l'administration restent None et
    # devront être saisis et confirmés; ne jamais inventer le coefficient 1.
    # Un fichier peut ne comporter que la part communale.
    return out


PARSERS = {'tarifs': analyser_tarifs, 'secteurs': analyser_secteurs,
           'localisations': analyser_localisations, 'neutralisations': analyser_neutralisations}


def importer(blob, extension, type_donnee, *, feuille=None, colonnes=None, ligne_debut=None):
    if type_donnee not in PARSERS:
        raise ValueError('Nature du fichier inconnue.')
    tabs=feuilles(blob,extension)
    if feuille is not None:
        tabs=[(n,r) for n,r in tabs if n==feuille]
        if not tabs:
            raise ValueError('La feuille sélectionnée est absente du fichier.')
    successful=[];failures=[]
    for nom,rows in tabs:
        try:
            data=PARSERS[type_donnee](rows,colonnes=colonnes,ligne_debut=ligne_debut)
            if type_donnee=='neutralisations' and len(data)<10:
                raise ValueError('Moins de 10 communes : fichier ou feuille suspect(e).')
            if type_donnee=='tarifs' and len(next(iter(data.values())))<3:
                raise ValueError('Moins de 3 secteurs tarifaires : structure suspecte.')
            successful.append((nom,data))
        except (ValueError,KeyError) as ex:
            failures.append(f'{nom} : {str(ex)}')
    if not successful:
        msg=' | '.join(failures[:2])
        raise ValueError('Aucune feuille compatible pour «'+type_donnee+'». '+msg)
    if len(successful)>1:
        # Aucune sélection arbitraire si des feuilles distinctes semblent toutes correctes.
        names=', '.join(n for n,_ in successful)
        raise ValueError('Plusieurs feuilles possibles ('+names+'). Sélectionnez la feuille dans l’import assisté.')
    return successful[0][1],hashlib.sha256(blob).hexdigest()


def construire_source(url,sha,type_donnee,annee,nb):
    return {'origine':'DGFiP', 'url':url,'sha256':sha, 'millesime':int(annee),
            'type':type_donnee,'lignes':nb,'recupere_le':datetime.now(timezone.utc).isoformat(),
            'controle':'structure vérifiée automatiquement; rapprochement métier à effectuer'}
