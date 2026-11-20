"""Moteur RVLLP / estimation TFPB — règles explicites, aucune source implicite."""
from __future__ import annotations
from dataclasses import dataclass, asdict
from decimal import Decimal
import math
import re
import unicodedata
from referentiel import lignes_neutralisation

COEFF_SURFACES = {'P1': 1.0, 'P2': 0.5, 'P3': 0.2, 'PK1': 0.5, 'PK2': 0.2}
TAXES = {
    'commune': 'Taxe foncière communale',
    'syndicat': 'Syndicat de communes',
    'epci': 'Intercommunalité / EPCI',
    'taxes_speciales': 'Taxes spéciales',
    'teom': 'Taxe d’enlèvement des ordures ménagères',
    'gemapi': 'GEMAPI',
}


def norm(text):
    text = unicodedata.normalize('NFKD', str(text or ''))
    text = ''.join(c for c in text if not unicodedata.combining(c))
    return re.sub(r'[^A-Z0-9]+', '', text.upper())


def _chiffres_identifiant_cadastral(value):
    """Conserve le sens d'un identifiant lu comme nombre dans Excel/ODS.

    Exemple : 10.0 est le code 010, et 70.0 est la parcelle 0070.
    La conversion chaîne->chiffres directe produisait 100 et 0700.
    """
    if value is None or isinstance(value, bool):
        return ''
    if isinstance(value, (int, float)):
        if not math.isfinite(float(value)) or not float(value).is_integer():
            return ''
        return str(int(value))
    raw = str(value).strip()
    if not raw:
        return ''
    if re.fullmatch(r'\d+(?:[\.,]0+)?', raw):
        return raw.split('.')[0].split(',')[0]
    return ''.join(ch for ch in raw if ch.isdigit())


def comm_code(value):
    t = _chiffres_identifiant_cadastral(value)
    return t[-3:].zfill(3) if t else ''


def parcel_code(value):
    t = _chiffres_identifiant_cadastral(value)
    return t.zfill(4) if t and int(t) != 0 else ''


def _by_commune(rows, commune, code_commune=''):
    c = comm_code(code_commune)
    n = norm(commune)
    if c:
        by_code = [x for x in rows if comm_code(x.get('code_commune')) == c]
        if by_code:
            return by_code
    return [x for x in rows if norm(x.get('commune')) == n] if n else []


def section_cadastrale(section):
    section = norm(section)
    return section[1:] if re.fullmatch(r'0[A-Z]', section) else section


def secteur_automatique(ref, dep, commune, prefixe, section, code_commune=''):
    """N'identifie le secteur que si la section/préfixe conduit à une valeur unique."""
    rows = _by_commune(ref.get('secteurs', {}).get(dep, []), commune, code_commune)
    if not rows:
        return None, 'Commune absente du référentiel des secteurs.'
    pref, sec = norm(prefixe), section_cadastrale(section)
    if not sec and any(section_cadastrale(r.get('section')) for r in rows):
        return None, 'Indiquer la section cadastrale pour identifier le secteur.'
    candidates = []
    for r in rows:
        rsec, rpref = section_cadastrale(r.get('section')), norm(r.get('prefixe'))
        if rsec and rsec != sec:
            continue
        if rpref and rpref != pref:
            continue
        specificity = 2 * bool(rsec) + bool(rpref)
        candidates.append((specificity, r))
    if not candidates:
        return None, 'Aucun secteur trouvé pour cette commune / section / préfixe.'
    best = max(i for i, _ in candidates)
    vals = {int(x['secteur']) for i, x in candidates if i == best}
    if len(vals) != 1:
        return None, 'Plusieurs secteurs possibles : contrôler la référence cadastrale.'
    return next(iter(vals)), 'Correspondance retrouvée dans le référentiel de sectorisation.'


def annee_localisation(year):
    y = int(year)
    if y >= 2026:
        return 2026
    if y >= 2024:
        return 2024
    if y >= 2020:
        return 2020
    return None


def localisation_automatique(ref, dep, year, commune, prefixe, section, parcelle, code_commune=''):
    ay = annee_localisation(year)
    if ay is None:
        return None, 'Millésime de localisation antérieur à 2020 non chargé.', None
    d = ref.get('localisations', {}).get(dep, {})
    if str(ay) not in d:
        return None, f'Fichier DGFiP de localisation {ay} absent : pas de report du barème précédent.', ay
    if not section or not parcelle:
        return None, 'Section et numéro de parcelle requis pour contrôler les coefficients particuliers.', ay
    pref, sec, num = norm(prefixe), section_cadastrale(section), parcel_code(parcelle)
    rows = _by_commune(d[str(ay)], commune, code_commune)
    matches = []
    for r in rows:
        rsec, rpref, rnum = section_cadastrale(r.get('section')), norm(r.get('prefixe')), parcel_code(r.get('parcelle'))
        if rsec and rsec != sec:
            continue
        if rpref and rpref != pref:
            continue
        if rnum and rnum != num:
            continue
        specificity = 4 * bool(rnum) + 2 * bool(rsec) + bool(rpref)
        matches.append((specificity, r))
    if not matches:
        return 1.0, f'Aucun coefficient dérogatoire publié pour cette parcelle en {ay} : coefficient 1 retenu.', ay
    top = max(x[0] for x in matches)
    coeffs = {float(r['coefficient']) for score, r in matches if score == top}
    if len(coeffs) != 1:
        return None, 'Coefficients contradictoires pour cette parcelle.', ay
    return next(iter(coeffs)), 'Coefficient identifié dans le tableau DGFiP de localisation.', ay


def _cle_libelle_commune(nom):
    """Uniformise les variantes des arrondissements de Paris/Lyon/Marseille.

    Ne fusionne pas, par exemple, Lyon 2e et Lyon 7e. Pour les autres communes,
    conserve la normalisation habituelle (accents, espaces, apostrophes).
    """
    v = norm(nom)
    m = re.match(r'^(LYON|PARIS|MARSEILLE)0?(\d{1,2})(?:EME|ERE|ER|E|ARRONDISSEMENT|ARR|$)', v)
    if m:
        return m.group(1) + '#' + str(int(m.group(2)))
    return v


def _cle_arrondissement_code(insee):
    code = _chiffres_identifiant_cadastral(insee)
    if len(code) != 5:
        return None
    number = int(code)
    if 69381 <= number <= 69389:
        return 'LYON#' + str(number-69380)
    if 75101 <= number <= 75120:
        return 'PARIS#' + str(number-75100)
    if 13201 <= number <= 13216:
        return 'MARSEILLE#' + str(number-13200)
    return None


def insee_cadastral_adresse(code_insee, code_postal):
    """Convertit le code municipal de Lyon en arrondissement si le CP est précis.

    Ne modifie pas un identifiant cadastral déjà défini (69381 à 69389).
    Le code postal ne suffit jamais à corriger un code de commune différent.
    """
    insee = str(code_insee or '').strip()
    postal = str(code_postal or '').strip()
    if insee == '69123' and postal in {f'6900{i}' for i in range(1, 10)}:
        return '6938' + postal[-1]
    return insee


def nom_commune_cadastrale(ref, dep, code_insee, nom_geocode=''):
    """Privilégie la commune cadastrale du référentiel, sans saisie doublon.

    Si le département n'est pas encore sectorisé, l'arrondissement est encore
    reconnaissable à son code INSEE, notamment pour Lyon 7e (69387).
    """
    code = comm_code(code_insee)
    rows = [r for r in ref.get('secteurs',{}).get(dep,[])
            if code and comm_code(r.get('code_commune')) == code]
    noms = {str(r.get('commune','')).strip() for r in rows if str(r.get('commune','')).strip()}
    if len(noms) == 1:
        return next(iter(noms))
    key = _cle_arrondissement_code(code_insee)
    if key:
        city, ordinal = key.split('#')
        return f'{city.title()} {ordinal}ème' if int(ordinal)>1 else f'{city.title()} 1er'
    return str(nom_geocode or '').strip()


def _choisir_neutralisation(rows, *, dep, commune, code_commune='', prefixe=''):
    """Rattachement fiable : code cadastral > arrondissement > libellé fiscal.

    Un code 69387 désigne Lyon 7e, jamais un autre arrondissement. Les lignes
    sur plusieurs préfixes ne sont fusionnées que si les coefficients concordent.
    """
    searched = _cle_arrondissement_code(code_commune) or _cle_libelle_commune(commune)
    insee = _chiffres_identifiant_cadastral(code_commune)
    cadastral = comm_code(code_commune) if insee else ''
    pref = _chiffres_identifiant_cadastral(prefixe).zfill(3) if str(prefixe or '').strip() else ''
    clean = []
    for r in rows:
        row_pref = _chiffres_identifiant_cadastral(r.get('prefixe'))
        if row_pref and pref and row_pref.zfill(3) != pref:
            continue
        clean.append(r)
    # Si l'import contient un code parcellaire précis, celui-ci l'emporte sur
    # le texte (les libellés diffèrent beaucoup selon les millésimes DGFiP).
    direct = [r for r in clean if cadastral and r.get('code_commune') is not None
              and comm_code(r.get('code_commune')) == cadastral]
    if direct:
        return direct, 'code cadastral'
    by_name = [r for r in clean if _cle_libelle_commune(r.get('nom_commune', r.get('commune',''))) == searched]
    if by_name:
        # Ne prendre que les lignes non codées ou sur le territoire cible.
        # Le code fiscal 69123 peut figurer sur une ligne nommée LYON 7E.
        code_fiscal = {'LYON':'123','PARIS':'056','MARSEILLE':'055'}
        city = searched.split('#')[0] if '#' in searched else ''
        autorises = {'', cadastral}
        if city in code_fiscal and '#' in searched:
            autorises.add(code_fiscal[city])
        allowed = [r for r in by_name if not cadastral
                   or comm_code(r.get('code_commune')) in autorises]
        if allowed:
            return allowed, 'libellé cadastral normalisé'
    # Certaines éditions neutralisation raisonnent sur la commune fiscale
    # LYON (69123) tandis que le cadastre repère LYON 7E (69387).
    if searched.startswith('LYON#') and dep=='69':
        commune_fiscale = [r for r in clean
            if _cle_libelle_commune(r.get('nom_commune',r.get('commune',''))) == 'LYON'
            and comm_code(r.get('code_commune')) in ('','123')]
        if commune_fiscale:
            return commune_fiscale, 'commune fiscale de Lyon (69123)'
    return [], ''


def neutralisation_automatique(ref, dep, commune, annee=2025, code_commune='', prefixe=''):
    """Rapproche les coefficients 2017-2020 / 2021+ sans supposer de valeurs.

    Les noms Lyon 7e, Lyon 7ème, Lyon 7e Arrondissement et LYON 07 sont
    équivalents dès lors que l'identifiant cadastral désigne le 7e.
    """
    rows, period, origine = lignes_neutralisation(ref, dep, annee)
    matchs, methode = _choisir_neutralisation(
        rows, dep=dep, commune=commune, code_commune=code_commune, prefixe=prefixe)
    if not matchs:
        return None, (f'Neutralisation TF {period} introuvable pour {commune} '
                      f'(code cadastral {code_commune or "non indiqué"}). '
                      'Vérifier les coefficients importés et leurs codes communaux.')
    vals = {}
    for k in TAXES:
        values = {round(float(r[k]), 12) for r in matchs if r.get(k) is not None}
        if len(values)>1:
            return None, f'Coefficients TF {period} contradictoires pour {commune} ({k}).'
        vals[k]=next(iter(values)) if values else None
    return vals, f'Coefficients TF {period} · {origine} · rapprochement par {methode}.'


def neutralisation_avec_teom_reference(ref, original_ref, dep, commune, annee=2025,
                                         code_commune='', prefixe=''):
    """Résout chaque composante de neutralisation dans le bon ordre de priorité.

    1) Coefficients DGFiP millésimés du référentiel actif, si le rattachement
       à la commune fiscale/cadastrale est non ambigu.
    2) Coefficients réellement présents dans le référentiel fourni au départ,
       seulement si la composante est absente/non rapprochable dans les données
       actives ; cette valeur est clairement signalée comme historique à vérifier.

    Important : ne jamais masquer une *contradiction* entre lignes DGFiP sous un
    fallback : dans ce cas, on bloque et on affiche le conflit.
    """
    vals, info = neutralisation_automatique(ref, dep, commune, annee, code_commune, prefixe)
    alertes = []
    # Une incohérence explicite ne doit pas être effacée en reprenant une ancienne
    # base potentiellement obsolète.
    if vals is None and 'contradictoires' in info:
        return vals, info, [info + ' : vérification manuelle nécessaire.']

    historique, info_h = (None, '')
    if original_ref is not None:
        historique, info_h = neutralisation_automatique(
            original_ref, dep, commune, annee, code_commune, prefixe)

    if vals is None:
        if historique is None:
            return vals, info, []
        # Si aucun raccordement n'est possible avec la version officielle,
        # retrouver exactement la donnée que savait lire la V10.
        vals = dict(historique)
        alertes.append(
            'Les coefficients de neutralisation du référentiel actif ne sont '
            'pas rattachables à cette parcelle. Les valeurs du classeur initial '
            'sont utilisées provisoirement : contrôler leur applicabilité et '
            'la période fiscale avant de valider cette estimation. '
            'Diagnostic du référentiel actif : ' + info)
        return vals, 'Référentiel historique initial · solution de repli provisoire.', alertes

    if historique is None:
        return vals, info, alertes

    vals = dict(vals)
    for k, label in TAXES.items():
        if vals.get(k) is None and historique.get(k) is not None:
            vals[k] = historique[k]
            alertes.append(
                f'{label}'+ (' (TEOM)' if k == 'teom' else '') + ' : coefficient absent de la publication DGFiP active, '
                'valeur du référentiel historique initial reprise à titre '
                'provisoire et à confirmer.')
    return vals, info, alertes


def diagnostic_neutralisation(ref, dep, commune, annee, code_commune='', prefixe=''):
    """Diagnostic reproductible, sans informations nominatives de dossiers.

    Le résultat est destiné à être affiché à l'utilisateur lorsqu'une base
    importée ne peut pas être rapprochée du code cadastral.
    """
    rows, period, origin = lignes_neutralisation(ref, dep, annee)
    selection, method = _choisir_neutralisation(
        rows, dep=dep, commune=commune, code_commune=code_commune, prefixe=prefixe)
    vals, message = neutralisation_automatique(
        ref, dep, commune, annee, code_commune, prefixe)
    return {
        'departement':dep,
        'code_cadastral':str(code_commune),
        'commune_reconnue':str(commune),
        'prefixe':str(prefixe),
        'periode':period,
        'origine':origin,
        'nombre_lignes_importees':len(rows),
        'nombre_lignes_rapprochees':len(selection),
        'methode':method or 'aucune',
        'message':message,
        'coefficients':vals,
    }

def tarif_automatique(ref, dep, year, categorie, secteur):
    if secteur is None:
        return None
    return ref.get('tarifs', {}).get(dep, {}).get(str(year), {}).get(categorie, {}).get(str(secteur))


def regime_reforme(annee, existait_au_01012017, type_changement='aucun', annee_effet=None, variation_surface_pct=None):
    """Conditions indicatives CGI 1518 A quinquies III et 1518 E.

    Le changement doit être caractérisé selon l'article 1406. Son effet ne vaut
    qu'à compter de l'année où il est pris en compte dans les bases.
    """
    y=int(annee)
    if y < 2017:
        raise ValueError('Le simulateur RVLLP ne couvre pas les impositions avant 2017.')
    if y >= 2027:
        raise ValueError('À partir de 2027, un nouveau régime transitoire s’applique : calcul 2027+ non disponible dans cette version.')
    if not existait_au_01012017:
        return {'planchonnement':False,'lissage':False,'raison':'Local non évalué comme local professionnel au 1er janvier 2017.'}
    if type_changement not in ('aucun','consistance','affectation_utilisation','inconnu'):
        raise ValueError('Type de changement inconnu.')
    if type_changement=='inconnu':
        raise ValueError('Historique des changements inconnu : vérifier la situation avant de calculer.')
    si_effectif=annee_effet is None or y >= int(annee_effet)
    exclu=False
    if type_changement!='aucun' and si_effectif:
        if type_changement=='consistance':
            if variation_surface_pct is None:
                raise ValueError('Variation de surface inconnue : impossible de déterminer si le seuil de 10 % est atteint.')
            if not math.isfinite(float(variation_surface_pct)) or float(variation_surface_pct)<0:
                raise ValueError('Variation de surface invalide.')
            exclu=float(variation_surface_pct)>=10
        else:
            exclu=True
    return {'planchonnement':not exclu,'lissage':not exclu and y<=2025,
            'raison':('Changement postérieur à 2017 excluant les atténuations.' if exclu
                     else 'Planchonnement applicable jusqu’en 2026 ; lissage uniquement jusqu’en 2025.')}


def planchonnement_2017(vl_ancienne_2017, vl_revisee_neutralisee_2017, deduction_tf=0.50):
    """Correctif figé à partir des VL historiques 2017, distinct pour chaque taxe.

    La correction est calculée en valeur locative; elle est ensuite convertie en
    base taxable TF après la déduction légale, avant les autres abattements.
    Ne PAS utiliser les VL du millésime courant à la place des valeurs 2017.
    """
    old=float(vl_ancienne_2017); new=float(vl_revisee_neutralisee_2017)
    if not all(math.isfinite(v) and v>=0 for v in (old,new)):
        raise ValueError('Les valeurs locatives historiques doivent être positives ou nulles et finies.')
    if not 0<deduction_tf<=1:
        raise ValueError('Coefficient de conversion en base invalide.')
    correction_vl=(old-new)/2.0
    return {'vl_ancienne_2017':old,'vl_revisee_neutralisee_2017':new,
            'correction_valeur_locative':correction_vl,
            'correction_base_tf':correction_vl*deduction_tf}


def lissage_2017_2025(annee, *, cotisation_avant_reforme_2017=None,
                      cotisation_apres_reforme_2017=None, pas_annuel=None,
                      montant_avis=None, eligible=True):
    """Correction SIGNEE sur la cotisation TFPB (et annexes concernées).

    Delta 2017 = cotisation avec réforme - cotisation sans réforme.
    Correction(y) = -(2026-y) * Delta/10, pour 2017 <= y <= 2025.
    Entrée alternative : pas_annuel SIGNÉ (Delta/10) ou montant_avis déjà signé.
    Le lissage est nul à compter de 2026, sans reconduction implicite.
    """
    y=int(annee)
    if y<2017:
        raise ValueError('Le lissage RVLLP ne couvre pas les impositions antérieures à 2017.')
    if y>=2027:
        raise ValueError('Le régime 2027 et suivants est distinct : ne pas prolonger le lissage 2017.')
    if not eligible or y==2026:
        return {'montant':0.0,'annees_restantes':0,'mode':'non applicable',
                'pas_annuel':0.0}
    paire=(cotisation_avant_reforme_2017 is not None or cotisation_apres_reforme_2017 is not None)
    if paire and (cotisation_avant_reforme_2017 is None or cotisation_apres_reforme_2017 is None):
        raise ValueError('Renseigner les deux cotisations 2017, sans et avec réforme.')
    modes=int(paire)+int(pas_annuel is not None)+int(montant_avis is not None)
    if modes!=1:
        raise ValueError('Pour 2017–2025, fournir exactement une source de lissage : deux cotisations 2017, pas annuel ou montant d’avis.')
    restent=2026-y
    if paire:
        old=float(cotisation_avant_reforme_2017)
        new=float(cotisation_apres_reforme_2017)
        if not all(math.isfinite(v) and v>=0 for v in (old,new)):
            raise ValueError('Cotisations historiques 2017 invalides.')
        pas=(new-old)/10
        mode='comparaison des cotisations 2017'
        montant=-(restent*pas)
    elif pas_annuel is not None:
        pas=float(pas_annuel)
        montant=-(restent*pas)
        mode='pas annuel signé 2017'
    else:
        montant=float(montant_avis)
        pas=-montant/restent
        mode='montant signé de l’avis du millésime'
    if not all(math.isfinite(v) for v in (pas,montant)):
        raise ValueError('Montant de lissage invalide.')
    return {'montant':montant,'annees_restantes':restent,
            'pas_annuel':pas,'mode':mode}


def estimation(surfaces, tarif, coefficient_localisation, coeff_neutralisations, taux, abattements=None, planchonnements=None, frais_pct=0, correction_lissage=0.0):
    """Retourne toutes les étapes, ou lève ValueError pour un paramètre manquant/invalide.

    * VL brute = surface pondérée × tarif × coefficient de localisation.
    * Assiette TF avant neutralisation = VL brute × 50 %.
    * Neutralisation / planchonnement : par composante (en base, après abattement de 50 %).
    * Exonérations/abattements et taux sont MANUELLEMENT fournis et non inférés.
    """
    if tarif is None or coefficient_localisation is None or coeff_neutralisations is None:
        raise ValueError('Tarif, coefficient de localisation et coefficients de neutralisation sont requis.')
    if float(tarif) <= 0 or float(coefficient_localisation) <= 0:
        raise ValueError('Tarif et coefficient de localisation doivent être positifs.')
    for k in COEFF_SURFACES:
        if float(surfaces.get(k, 0)) < 0:
            raise ValueError(f'Surface {k} négative.')
    weighted = {k: float(surfaces.get(k, 0)) * weight for k, weight in COEFF_SURFACES.items()}
    total_surface = sum(weighted.values())
    vl_brute = total_surface * float(tarif) * float(coefficient_localisation)
    assiette_tf = vl_brute / 2.0
    comp = []
    abattements = abattements or {}
    planchonnements = planchonnements or {}
    for k, label in TAXES.items():
        neutral = coeff_neutralisations.get(k)
        rate = taux.get(k)
        if neutral is None or rate is None:
            raise ValueError(f'Paramètres manquants pour {label}.')
        neutral, rate = float(neutral), float(rate)
        abattement = float(abattements.get(k, 0))
        planchonnement = float(planchonnements.get(k, 0))
        if neutral <= 0 or not 0 <= rate <= 100 or not 0 <= abattement <= 100:
            raise ValueError(f'Paramètres hors limites pour {label}.')
        base_neutralisee = assiette_tf * neutral
        base_planchonnee = base_neutralisee + planchonnement
        if base_planchonnee < 0:
            raise ValueError(f'Base négative après planchonnement : {label}.')
        base_taxable = base_planchonnee * (1 - abattement/100.0)
        montant = base_taxable * rate / 100.0
        comp.append({'cle': k, 'taxe':label, 'coefficient_neutralisation':neutral,
                     'base_neutralisee':base_neutralisee, 'correction_planchonnement':planchonnement,
                     'base_avant_abattement':base_planchonnee, 'abattement_pct':abattement,
                     'base_taxable':base_taxable, 'taux_pct':rate, 'montant':montant})
    total_taxes = sum(r['montant'] for r in comp)
    if not 0 <= float(frais_pct) <= 20:
        raise ValueError('Taux indicatif de frais de gestion hors intervalle 0–20 %.')
    if not math.isfinite(float(correction_lissage)):
        raise ValueError('Correction de lissage invalide.')
    frais = total_taxes * float(frais_pct) / 100
    return {'surfaces_ponderees': weighted, 'surface_ponderee_totale': total_surface,
            'tarif_m2':float(tarif), 'coefficient_localisation':float(coefficient_localisation),
            'valeur_locative_brute':vl_brute, 'assiette_tf_avant_neutralisation':assiette_tf,
            'lignes':comp, 'total_hors_frais':total_taxes, 'frais_gestion_estimes':frais,
            'correction_lissage':float(correction_lissage),
            'total_avant_lissage':total_taxes+frais,
            'total_estime':total_taxes+frais+float(correction_lissage)}
