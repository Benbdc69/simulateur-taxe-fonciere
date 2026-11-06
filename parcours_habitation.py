"""Parcours guidé H1/H2 : adresse confirmée, saisie expliquée, calcul traçable."""
from __future__ import annotations
import json
from pathlib import Path
import streamlit as st
from cadastre import adresses
from historique_taux import resoudre_tout, COMPOSANTES, LIBELLES
from mise_a_jour_simple import synchroniser_taux
from moteur_habitation import ENTRETIEN, SITUATION, CATEGORIES
from tarifs_habitation import tarifs_nationaux, SOURCE
from dossier_habitation import code_adresse, calculer_scenarios
from export_habitation_pdf import generer_pdf_habitation

ROOT = Path(__file__).resolve().parent


def load_ref():
    local = ROOT / 'data' / 'referentiel_local.json'
    return json.loads((local if local.exists() else ROOT / 'data' / 'referentiel_initial.json').read_text(encoding='utf-8'))


def fmt(value):
    return f'{float(value):,.2f}'.replace(',', ' ').replace('.', ',') + ' €'


def aller(etape):
    st.session_state['hab_etape'] = etape
    st.session_state.pop('hab_resultat', None)
    st.rerun()


st.title('Estimez la taxe foncière de votre logement')
st.caption('Maison H1 ou appartement H2 · Estimation indicative, hors frais de gestion et exonérations particulières.')
st.info('Préparez votre déclaration H1/H2 ou votre fiche d’évaluation cadastrale si vous en disposez. Vous pourrez explorer plusieurs scénarios si la catégorie cadastrale est inconnue.')
etape = st.session_state.get('hab_etape', 1)
saisie = st.session_state.setdefault('hab_saisie', {})
st.progress(etape / 3, text=f'Étape {etape} sur 3 · ' + {1: 'Votre logement', 2: 'Surfaces et équipements', 3: 'Vérification et estimation'}[etape])

if etape == 1:
    st.subheader('1 · Identifier le logement')
    with st.form('hab_adresse'):
        adresse = st.text_input('Adresse du bien', value=saisie.get('recherche', ''),
            placeholder='18 cours Gambetta, 69007 Lyon',
            help='Saisissez le numéro, la voie, le code postal et la commune du logement imposé. Ce n’est pas votre adresse de correspondance si elle est différente.')
        nature = st.radio('Type de logement', ['Appartement (H2)', 'Maison (H1)'],
            index=1 if saisie.get('nature') == 'M' else 0, horizontal=True,
            help='H1 correspond aux maisons ; H2 aux appartements. Ce choix détermine le barème de surface et le traitement des dépendances.')
        annee = st.selectbox('Année d’imposition', [2026, 2025, 2024],
            index=[2026, 2025, 2024].index(saisie.get('annee', 2026)),
            help='Année de l’avis de taxe foncière à estimer, et non année d’achat. Les tarifs publics de référence 1970 sont revalorisés jusqu’à cette année.')
        chercher = st.form_submit_button('Rechercher cette adresse', type='primary')
    if chercher:
        saisie.update(recherche=adresse.strip(), nature='M' if nature.startswith('Maison') else 'A', annee=int(annee))
        st.session_state.pop('hab_adresses', None)
        saisie.pop('adresse', None)
        if len(adresse.strip()) < 6:
            st.error('Renseignez une adresse complète avec le numéro, la voie et la commune.')
        else:
            try:
                with st.spinner('Recherche de l’adresse…'):
                    st.session_state['hab_adresses'] = adresses(adresse)
                if not st.session_state['hab_adresses']:
                    st.warning('Aucune adresse trouvée. Précisez le numéro, le code postal et la commune.')
            except (ConnectionError, ValueError) as exc:
                st.error('Recherche d’adresse indisponible : ' + str(exc))
    options = st.session_state.get('hab_adresses', [])
    # Un ancien résultat de recherche ne valide jamais une nouvelle saisie.
    recherche_actuelle = (adresse.strip(), 'M' if nature.startswith('Maison') else 'A', int(annee))
    recherche_sauvee = (saisie.get('recherche'), saisie.get('nature'), saisie.get('annee'))
    if options and recherche_actuelle == recherche_sauvee:
        choix = st.selectbox('Confirmez l’adresse du logement', range(len(options)), index=None,
            placeholder='Choisissez l’adresse exacte', format_func=lambda i: options[i]['libelle'],
            key='hab_adresse_choix', help='Vérifiez la commune et l’arrondissement. La recherche peut proposer plusieurs adresses ; aucune n’est choisie automatiquement.')
        if st.button('Continuer vers les surfaces', type='primary', disabled=choix is None):
            saisie['adresse'] = options[choix]
            aller(2)

elif etape == 2:
    st.subheader('2 · Décrire les surfaces et les équipements')
    st.caption(f"{saisie['adresse']['libelle']} · {'Maison H1' if saisie['nature'] == 'M' else 'Appartement H2'} · {saisie['annee']}")
    params = saisie.get('parametres', {})
    maison = saisie['nature'] == 'M'
    with st.form('hab_description'):
        st.markdown('#### Surfaces réelles, avant pondération')
        st.caption('Reprenez les surfaces déclarées sur H1/H2 ou mesurées au sol. La surface Carrez ou habitable peut différer de la surface cadastrale. Ne comptez jamais deux fois la même surface.')
        surface = st.number_input('Surface des pièces et annexes intérieures (m²)', min_value=0., max_value=20000.,
            value=float(saisie.get('surface', 0)), step=1.,
            help='Surface réelle des pièces et annexes intérieures du logement, avant correctifs fiscaux. N’y ajoutez pas la terrasse ni les dépendances saisies ci-dessous. Une valeur supérieure à zéro est obligatoire.')
        a, b = st.columns(2)
        with a:
            terrasse = st.number_input('Terrasse accessible (m²)', min_value=0., max_value=10000., value=float(params.get('terrasse', 0)), step=1.,
                help='Surface réelle de la terrasse accessible. Laissez 0 s’il n’y en a pas. Ne l’ajoutez pas à la surface des pièces.')
        with b:
            annexes = st.number_input('Garage, cave, grenier et autres dépendances (m²)', min_value=0., max_value=10000., value=float(params.get('annexes', 0)), step=1.,
                help='Uniquement les surfaces qui ne sont pas déjà comptées dans le logement. Pour un appartement, ces dépendances peuvent être des unités fiscales séparées et ne sont pas chiffrées avec le tarif du logement.')
        if not maison:
            st.info('Pour un appartement, les terrasses et dépendances renseignées seront signalées à part, sans les incorporer automatiquement au calcul de la partie principale.')
        st.markdown('#### Classement cadastral')
        ordre = sorted(CATEGORIES, key=lambda x: (int(x[0]), len(x)))
        categories = [None] + ordre
        categorie = st.selectbox('Catégorie cadastrale du logement', categories,
            index=categories.index(saisie.get('categorie')),
            format_func=lambda c: 'Je ne connais pas ma catégorie' if c is None else f'Catégorie {c}',
            help='Reprenez le classement de la fiche d’évaluation cadastrale (6675). Les catégories vont de 1 à 8 ; M indique une catégorie intermédiaire. Ce classement fiscal ne se déduit pas du prix du logement ou de son DPE.')
        st.caption('Catégorie inconnue : le résultat présentera les catégories et séries disponibles comme des scénarios, sans attribuer automatiquement un classement à votre bien.')
        st.markdown('#### État, situation et dépendances')
        st.caption('Ces correctifs décrivent l’état et la situation retenus pour l’évaluation cadastrale. Les valeurs proposées sont des hypothèses à vérifier sur votre fiche.')
        a, b = st.columns(2)
        with a:
            entretien = st.selectbox('État d’entretien cadastral', list(ENTRETIEN), index=list(ENTRETIEN).index(params.get('entretien', 'Passable')),
                help='État général du bâtiment : bon, assez bon, passable, médiocre ou mauvais. Il s’agit du correctif cadastral, pas d’une note de décoration. « Passable » applique le coefficient neutre 1.')
            sit_gen = st.selectbox('Situation générale', list(SITUATION), index=list(SITUATION).index(params.get('situation_generale', 'Ordinaire')),
                help='Appréciation du quartier ou de l’environnement général du bien. « Ordinaire » n’ajoute ni ne retranche de correctif ; confirmez avec la fiche cadastrale.')
        with b:
            sit_part = st.selectbox('Situation particulière', list(SITUATION), index=list(SITUATION).index(params.get('situation_particuliere', 'Ordinaire')),
                help='Situation propre au logement dans son environnement : exposition, vue, nuisances ou accès, selon l’évaluation cadastrale. Ne confondez pas avec la situation du quartier.')
            if maison:
                coef_annexe = st.selectbox('Pondération des dépendances', [.2, .3, .4, .5, .6], index=[.2, .3, .4, .5, .6].index(params.get('coeff_annexes', .4)),
                    help='Coefficient cadastral de 0,2 à 0,6 selon le service rendu. Le choix 0,4 est une hypothèse, pas une valeur déduite de votre adresse. Reprenez la valeur de votre fiche si elle est connue.')
                coef_terrasse = st.selectbox('Pondération de la terrasse', [.2, .3, .4, .5, .6], index=[.2, .3, .4, .5, .6].index(params.get('coeff_terrasse', .4)),
                    help='Coefficient de 0,2 à 0,6 à confirmer sur le dossier cadastral. Il s’applique uniquement à la terrasse et non aux pièces du logement.')
            else:
                etage = st.number_input('Étage du logement', min_value=0, max_value=80, value=int(params.get('etage', 0)),
                    help='0 pour le rez-de-chaussée, 1 pour le premier étage, etc. L’étage intervient dans le correctif d’ascenseur des appartements.')
                ascenseur = st.checkbox('Ascenseur desservant le logement', value=params.get('ascenseur', False),
                    help='Cochez si un ascenseur dessert le logement. Ce correctif ne concerne pas les maisons.')
        st.markdown('#### Équipements du logement')
        st.caption('Le calcul transforme les équipements en équivalences de surface. Vérifiez les quantités proposées : elles ne sont pas déduites automatiquement du nombre de pièces.')
        a, b = st.columns(2)
        quantites = {}
        for i, (cle, libelle, valeur, aide) in enumerate([
            ('wc', 'WC privatifs', 1, 'Nombre de WC privatifs dans le logement. Ne comptez pas les sanitaires communs de l’immeuble.'),
            ('lavabos', 'Lavabos', 1, 'Nombre de lavabos ; ne comptez pas les éviers de cuisine dans cette rubrique.'),
            ('douches', 'Douches', 1, 'Nombre de douches. Ne comptez pas une baignoire équipée d’un flexible comme un second appareil distinct.'),
            ('baignoires', 'Baignoires', 0, 'Nombre de baignoires. Évitez de compter deux fois un même équipement dans la rubrique douches.'),
            ('pieces_chauffees', 'Pièces avec chauffage admissible', 0, 'Nombre de pièces disposant d’un chauffage fixe assimilable au chauffage central pour l’évaluation cadastrale. Ne comptez pas les couloirs ou WC ; des radiateurs mobiles seuls ne suffisent pas.'),
        ]):
            with [a, b][i % 2]:
                quantites[cle] = st.number_input(libelle, min_value=0, max_value=100, value=int(params.get(cle, valeur)), help=aide)
        a, b = st.columns(2)
        equipements = {}
        for i, (cle, libelle, valeur, aide) in enumerate([
            ('eau', 'Eau courante', True, 'Installation d’eau courante dans le logement.'),
            ('electricite', 'Électricité', True, 'Installation électrique du logement.'),
            ('gaz', 'Installation fixe de gaz', False, 'Installation fixe ; une bouteille ou un appareil mobile ne suffit pas.'),
            ('egout', 'Tout-à-l’égout', True, 'Raccordement au réseau public d’assainissement. Ne cochez pas pour une fosse individuelle.'),
            ('vide_ordures', 'Vide-ordures', False, 'Installation de vide-ordures. Un local à poubelles ou un bac de collecte ne correspond pas à cet équipement.'),
        ]):
            with [a, b][i % 2]:
                equipements[cle] = st.checkbox(libelle, value=params.get(cle, valeur), help=aide)
        a, b = st.columns(2)
        retour = a.form_submit_button('Retour au logement')
        suivant = b.form_submit_button('Vérifier mes informations', type='primary')
    if retour or suivant:
        saisie.update(surface=surface, categorie=categorie, parametres={
            'annexes': annexes, 'terrasse': terrasse, 'entretien': entretien,
            'situation_generale': sit_gen, 'situation_particuliere': sit_part,
            **quantites, **equipements,
            **({'coeff_annexes': coef_annexe, 'coeff_terrasse': coef_terrasse} if maison else {'etage': etage, 'ascenseur': ascenseur})})
        if retour:
            aller(1)
        elif surface <= 0:
            st.error('Indiquez une surface réelle du logement supérieure à zéro.')
        else:
            aller(3)

else:
    st.subheader('3 · Vérifier avant de calculer')
    adr = saisie['adresse']
    params = saisie['parametres']
    st.write(f"**{adr['libelle']}** · {'Maison H1' if saisie['nature'] == 'M' else 'Appartement H2'} · imposition {saisie['annee']}")
    st.write(f"Surface réelle : **{saisie['surface']:g} m²** · Terrasse : **{params['terrasse']:g} m²** · Dépendances : **{params['annexes']:g} m²**")
    st.write('Catégorie : **' + (saisie.get('categorie') or 'inconnue — exploration des scénarios disponibles') + '**')
    with st.expander('Relire les correctifs et les équipements retenus'):
        st.write(f"Entretien : {params['entretien']} · Situation générale : {params['situation_generale']} · Situation particulière : {params['situation_particuliere']}")
        st.write({k: v for k, v in params.items() if k not in ('entretien', 'situation_generale', 'situation_particuliere')})
    st.caption('Les équipements préremplis et les correctifs neutres restent des hypothèses tant que vous ne les avez pas vérifiés. L’adresse ne permet pas de déterminer la catégorie ou la série cadastrale.')
    a, b = st.columns(2)
    if a.button('Modifier mes informations'):
        aller(2)
    if b.button('Calculer mon estimation', type='primary'):
        st.session_state.pop('hab_resultat', None)
        with st.spinner('Recherche des tarifs et des taux documentés…'):
            try:
                ref = load_ref()
                rates = resoudre_tout(ref, code_adresse(adr), saisie['annee'])
                incidents = []
                if any(v is None for v in rates.values()):
                    try:
                        synchroniser_taux(saisie['annee'], code_adresse(adr))
                        ref = load_ref()
                    except Exception:
                        incidents.append('Actualisation des taux indisponible ; seuls les taux déjà documentés sont utilisés.')
                r = calculer_scenarios(saisie, adr, ref, tarifs_nationaux())
                st.session_state['hab_resultat'] = {**r, 'incidents': incidents, 'source_tarifs': SOURCE}
            except (ValueError, RuntimeError, ConnectionError) as exc:
                st.error('Estimation indisponible : ' + str(exc))

    r = st.session_state.get('hab_resultat')
    if r:
        st.divider()
        st.subheader('Votre estimation expliquée')
        for incident in r['incidents']:
            st.warning(incident)
        if r['categorie_inconnue']:
            st.warning('Catégorie non confirmée : ces scénarios explorent les catégories publiées. Leur intervalle n’est ni une prévision ni une attribution de catégorie à votre logement.')
        if len(r['tarifs']) > 1:
            st.info('Plusieurs catégories ou séries sont possibles. Reprenez la catégorie, la série et la commune d’origine figurant sur votre fiche d’évaluation pour identifier votre scénario.')
            totals = [x['total'] for x in r['tarifs'] if 'total' in x]
            if totals:
                st.write(f"**Étendue des scénarios disponibles : {fmt(min(totals))} à {fmt(max(totals))}**, hors frais, exonérations et dépendances distinctes.")
        choice = st.selectbox('Scénario à examiner', range(len(r['tarifs'])),
            format_func=lambda i: f"Catégorie {r['tarifs'][i]['categorie']} · Série {r['tarifs'][i]['serie']} · Origine {r['tarifs'][i]['origine'] or 'non précisée'} · {fmt(r['tarifs'][i]['tarif_1970'])}/m²",
            help='Ce choix sert à examiner un scénario ; il ne confirme pas le classement cadastral de votre logement.')
        x = r['tarifs'][choice]
        sp = x['surfaces']
        if sp['dependances_a_evaluer_separement']:
            st.warning('Estimation partielle : terrasse et/ou dépendances d’appartement sont signalées mais non chiffrées. Les montants portent sur la partie principale uniquement.')
        if not r['taux_complets']:
            missing = [LIBELLES[k] for k in COMPOSANTES if not r['taux'].get(k) or r['taux'][k].get('taux') is None]
            st.warning('Taux non documentés : ' + ', '.join(missing) + '. Aucun total de cotisations n’est affiché ; un taux manquant ne vaut pas zéro.')
        anciens = [f"{LIBELLES[k]} ({v['annee_source']})" for k, v in r['taux'].items() if v and v['annee_source'] < r['annee']]
        if anciens:
            st.warning('Taux antérieurs repris à titre indicatif : ' + ', '.join(anciens) + '.')
        if r['taux'].get('teom') and not r['taux']['teom'].get('zonage_confirme'):
            st.warning('Le zonage TEOM n’est pas confirmé pour cette adresse : la cotisation correspondante reste à vérifier.')
        a, b, c = st.columns(3)
        a.metric('Surface pondérée cadastrale', f"{sp['surface_ponderee']} m²")
        b.metric(f"Valeur locative {r['annee']}", fmt(x['vl_annee']))
        c.metric('Base TFPB après déduction de 50 %', fmt(x['base_tf']))
        with st.expander('Comprendre le calcul, étape par étape', expanded=True):
            st.write(f"1. Surface comparative : **{sp['comparative']} m²**, issue du barème de catégorie {x['categorie']}.")
            st.write(f"2. Ajout des dépendances pondérées retenues : **{sp['annexes_ponderees'] + sp['terrasse_ponderee']} m²** ; correctif global **× {sp['correctif']}** → surface nette **{sp['surface_nette']} m²**.")
            st.write(f"3. Équipements : **+ {sp['equivalence_confort']} m²** → surface pondérée **{sp['surface_ponderee']} m²**.")
            st.table([{'Équipement': k, 'Équivalence (m²)': v} for k, v in sp['detail_confort'].items() if v])
            st.write(f"4. Valeur locative 1970 : {sp['surface_ponderee']} m² × {fmt(x['tarif_1970'])}/m² = **{fmt(x['vl_1970'])}**.")
            st.write(f"5. Actualisation 1980 × {r['facteur']['actualisation_1980']} ; revalorisation nationale × {r['facteur']['revalorisation_nationale']} → **{fmt(x['vl_annee'])}**. La moitié forme la base TFPB : **{fmt(x['base_tf'])}**.")
        if 'montants' in x:
            st.metric('Cotisations estimées — hors frais et exonérations', fmt(x['total']))
            st.caption('Sur le périmètre calculé, sous réserve du classement, des taux et du zonage TEOM.')
            st.table([{'Composante': LIBELLES[k], 'Base (€)': x['base_tf'], 'Taux (%)': r['taux'][k]['taux'], 'Montant (€)': v} for k, v in x['montants'].items()])
        with st.expander('Sources et millésimes utilisés'):
            st.write('Tarifs cadastraux DGFiP 2024 en valeur de référence 1970 : ' + SOURCE)
            st.write(r['facteur']['source_departement'])
            st.write(r['facteur']['source_revalorisation'])
            st.table([{'Composante': LIBELLES[k], 'Taux (%)': v['taux'], 'Année source': v['annee_source'], 'Source': v.get('source', '')} for k, v in r['taux'].items() if v])
        dossier_pdf = {**r, 'categorie': x['categorie'], 'surfaces': sp,
            'tarifs': [t for t in r['tarifs'] if t['categorie'] == x['categorie']]}
        dossier_pdf['serie_selectionnee'] = dossier_pdf['tarifs'].index(x)
        st.download_button('Télécharger le rapport PDF de ce scénario', data=generer_pdf_habitation(dossier_pdf),
            file_name=f"estimation_habitation_{r['annee']}_{r['code_insee']}.pdf", mime='application/pdf', use_container_width=True)
