"""Recherche cadastrale partagée, sans géocodage ni adresse obligatoire."""
import re
import streamlit as st
import requests
from cadastre import rechercher_parcelle


def rechercher_communes(nom, departement=""):
    query = str(nom).strip()
    if len(query) < 2:
        raise ValueError('Saisissez au moins deux caractères du nom de la commune.')
    departement = str(departement).strip().upper()
    if departement and not re.fullmatch(r'(?:\d{2}|2[AB]|9[78]\d)', departement):
        raise ValueError('Indiquez un code de département valide, par exemple 42, 2A ou 971.')
    params = {'nom': query, 'fields': 'nom,code,codeDepartement', 'limit': 30}
    if departement:
        params['codeDepartement'] = departement
    try:
        response = requests.get('https://geo.api.gouv.fr/communes', params=params, timeout=(5, 15))
        response.raise_for_status()
        rows = response.json()
    except (requests.RequestException, ValueError) as exc:
        raise ConnectionError('La recherche officielle des communes est indisponible. Vous pouvez saisir le code INSEE manuellement.') from exc
    if not isinstance(rows, list):
        raise ConnectionError('Réponse inattendue du service des communes.')
    resultats = {}
    for row in rows:
        if not isinstance(row, dict):
            continue
        code = str(row.get('code') or '').upper()
        if re.fullmatch(r'(?:\d{5}|2[AB]\d{3})', code) and row.get('nom'):
            dep = str(row.get('codeDepartement') or (code[:3] if code.startswith(('97','98')) else code[:2]))
            if departement and dep != departement:
                continue
            resultats[code] = {'commune': str(row['nom']), 'insee': code, 'departement': dep}
    return sorted(resultats.values(), key=lambda x: (x['commune'], x['departement'], x['insee']))


def code_arrondissement(code, numero):
    limites = {'75056': (20, 75100), '69123': (9, 69380), '13055': (16, 13200)}
    if code not in limites:
        raise ValueError('Cette commune ne comporte pas de sélection d’arrondissement.')
    maximum, base = limites[code]
    if isinstance(numero, bool) or not isinstance(numero, int) or not 1 <= numero <= maximum:
        raise ValueError('Choisissez un arrondissement valide.')
    return str(base + numero)


def saisir_commune(cle, valeurs=None):
    """Sélection hors formulaire : une recherche réseau seulement sur clic."""
    valeurs = valeurs or {}
    mode = st.radio('Choisir la commune', ['Rechercher par nom', 'Saisir le code INSEE'],
        index=0 if valeurs.get('recherche_commune_auto', True) else 1, horizontal=True, key=cle+'_mode_commune')
    if mode == 'Saisir le code INSEE':
        return False, None
    nom = st.text_input('Nom de la commune', value=st.session_state.get(cle+'_commune_query', valeurs.get('commune', '')),
        key=cle+'_nom_recherche', help='Saisissez le nom de la commune, par exemple Andrézieux-Bouthéon. Pour Paris, Lyon ou Marseille, vous choisirez ensuite l’arrondissement.')
    departement = st.text_input('Département (facultatif)', value=st.session_state.get(cle+'_commune_departement', ''), key=cle+'_dept_recherche', help='Pour affiner une recherche en cas d’homonymes : par exemple 42, 2A ou 971. Vous pouvez laisser vide.')
    if st.button('Rechercher la commune', key=cle+'_chercher_commune'):
        st.session_state[cle+'_communes'] = []
        st.session_state[cle+'_commune_query'] = nom.strip()
        st.session_state[cle+'_commune_departement'] = departement.strip().upper()
        try:
            st.session_state[cle+'_communes'] = rechercher_communes(nom, departement)
            if not st.session_state[cle+'_communes']:
                st.warning('Aucune commune trouvée. Précisez le nom ou utilisez la saisie manuelle du code INSEE.')
        except (ValueError, ConnectionError) as exc:
            st.error(str(exc))
    rows = st.session_state.get(cle+'_communes', [])
    if rows and nom.strip() == st.session_state.get(cle+'_commune_query') and departement.strip().upper() == st.session_state.get(cle+'_commune_departement'):
        if len(rows) >= 30:
            st.caption('Résultats limités à 30 communes : précisez le département ou le nom pour affiner la recherche.')
        choix = st.selectbox('Commune à retenir', range(len(rows)), index=None, key=cle+'_choix_commune',
            placeholder='Sélectionnez votre commune',
            format_func=lambda i: f"{rows[i]['commune']} · département {rows[i]['departement']} · INSEE {rows[i]['insee']}",
            help='En cas de communes homonymes, vérifiez le département. Aucune commune n’est choisie automatiquement.')
        if choix is not None:
            selection = dict(rows[choix])
            if selection['insee'] in ('75056', '69123', '13055'):
                maximum = {'75056': 20, '69123': 9, '13055': 16}[selection['insee']]
                n = st.selectbox('Arrondissement cadastral', list(range(1, maximum+1)), index=None,
                    key=cle+'_arrondissement', placeholder='Choisissez l’arrondissement')
                if n is None:
                    return True, None
                selection['insee'] = code_arrondissement(selection['insee'], n)
                selection['commune'] += f' — {n}e arrondissement'
            return True, selection
    return True, None


def saisir_reference(cle, valeurs=None, automatique=False, selection=None):
    valeurs = valeurs or {}
    st.caption('Reprenez les références de votre avis, titre de propriété ou plan cadastral. Une parcelle peut contenir plusieurs locaux : le calcul portera sur le local que vous décrivez ensuite.')
    if automatique:
        commune = selection['commune'] if selection else ''
        insee = selection['insee'] if selection else ''
        if selection:
            st.caption(f"Commune retenue : {commune} · Code INSEE cadastral : {insee}")
        else:
            st.info('Recherchez et sélectionnez une commune ci-dessus avant de rechercher la parcelle.')
    else:
        commune = st.text_input('Commune de la parcelle', value=valeurs.get('commune', ''), key=cle+'_commune', help='Nom de la commune cadastrale. Pour Lyon, indiquez l’arrondissement si nécessaire.')
        insee = st.text_input('Code INSEE cadastral de la commune', value=valeurs.get('insee', ''), key=cle+'_insee', help='Code à 5 caractères, différent du code postal. Exemple : 69387 pour Lyon 7e. Pour la Corse, le code peut commencer par 2A ou 2B.')
    a, b, c = st.columns(3)
    with a:
        prefixe = st.text_input('Préfixe cadastral (facultatif)', value=valeurs.get('prefixe', ''), key=cle+'_prefixe', help='Trois chiffres, souvent 000. Laissez vide si inconnu : plusieurs parcelles pourront être proposées en cas d’anciennes communes.')
    with b:
        section = st.text_input('Section cadastrale', value=valeurs.get('section', ''), key=cle+'_section', help='Exemple : AC, 01, ou A qui sera recherché sous 0A. Ce n’est pas le numéro de lot de copropriété.')
    with c:
        numero = st.text_input('Numéro de parcelle', value=valeurs.get('numero', ''), key=cle+'_numero', help='Exemple : 123 ou 0123. Ne saisissez pas le numéro de lot, de porte ou le numéro fiscal du local.')
    return dict(commune=commune, insee=insee, prefixe=prefixe, section=section, numero=numero, recherche_commune_auto=automatique)


def normaliser_reference(reference):
    r = {k: str(reference.get(k) or '').strip().upper() for k in ('commune', 'insee', 'prefixe', 'section', 'numero')}
    if not r['commune']:
        raise ValueError('Renseignez le nom de la commune de la parcelle.')
    if not re.fullmatch(r'(?:\d{5}|2[AB]\d{3})', r['insee']):
        raise ValueError('Le code INSEE cadastral doit comporter 5 caractères ; ne renseignez pas le code postal.')
    if not re.fullmatch(r'[A-Z0-9]{1,2}', r['section']):
        raise ValueError('Section cadastrale invalide : utilisez par exemple AC ou 0A.')
    if not re.fullmatch(r'\d{1,4}', r['numero']) or int(r['numero']) == 0:
        raise ValueError('Le numéro de parcelle doit être compris entre 1 et 9999.')
    if r['prefixe'] and not re.fullmatch(r'\d{1,3}', r['prefixe']):
        raise ValueError('Le préfixe cadastral doit comporter au plus trois chiffres, ou rester vide.')
    r.update(section=r['section'].zfill(2), numero=r['numero'].zfill(4), prefixe=r['prefixe'].zfill(3) if r['prefixe'] else '')
    return r


def identifier_par_reference(reference):
    r = normaliser_reference(reference)
    rows = rechercher_parcelle(r['insee'], r['section'], r['numero'], r['prefixe'] or None)
    resultats = []
    vus = set()
    for p in rows:
        identifiant = str(p.get('idu') or p.get('id') or '')
        code = str(p.get('code_insee') or '')
        if not code and p.get('code_dep') is not None and p.get('code_com') is not None:
            dep = str(p['code_dep']).zfill(2)
            code = dep + str(p['code_com']).zfill(2 if len(dep) == 3 else 3)
        if not code and len(identifiant) >= 14:
            code = identifiant[:5]
        pref = str(p.get('com_abs') if p.get('com_abs') is not None else p.get('prefixe') or '').strip()
        if not pref and len(identifiant) >= 14:
            pref = identifiant[5:8]
        sec = str(p.get('section') or '').strip().upper().zfill(2)
        num = str(p.get('numero') or '').strip().zfill(4)
        pref = pref.zfill(3) if pref else ''
        # Ne pas accepter une autre commune, section ou parcelle renvoyée par erreur.
        if (code.upper(), sec, num) != (r['insee'], r['section'], r['numero']):
            continue
        if not re.fullmatch(r'\d{3}', pref) or (r['prefixe'] and pref != r['prefixe']):
            continue
        key = (code, pref, sec, num)
        if key in vus:
            continue
        vus.add(key)
        commune = str(p.get('nom_com') or p.get('nom_commune') or r['commune'])
        parcelle = dict(insee=code, commune=commune, departement=code[:3] if code.startswith(('97','98')) else code[:2],
                        prefixe=pref, section=sec, numero=num, id=identifiant,
                        recherche='Référence cadastrale — confirmation obligatoire', distance_m=None,
                        geometry=p.get('geometry'))
        resultats.append(dict(libelle=f'Parcelle {pref} {sec} {num} · {commune} ({code})',
                              commune=commune, insee=code, code_postal='', parcelle=parcelle))
    return resultats


def libelle_parcelle(parcelle):
    texte = f"Préfixe {parcelle.get('prefixe') or 'non précisé'} · {parcelle['section']} {parcelle['numero']} · {parcelle['insee']}"
    if parcelle.get('distance_m') is not None:
        texte += f" · {parcelle['distance_m']} m du point d’adresse"
    return texte
