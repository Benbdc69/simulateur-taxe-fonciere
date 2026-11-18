"""Parcours guidé H1/H2 : adresse confirmée, saisie expliquée, calcul traçable."""
from __future__ import annotations
import json
from datetime import date
from html import escape
from classement_habitation import CLASSEMENT, CRITERES, libelle_categorie
from pathlib import Path
import streamlit as st
from formulaire_h1 import ELEMENTS_H1, MURS, TOITURES, valider_description_h1, valider_elements_incorpores
from saisie_dependances import saisir_dependances
from dependances_habitation import valider_dependances, TYPES, MODES
from saisie_adresse import saisir_adresse
from session_calcul import bouton_nouveau_calcul, cle_calcul
from cadastre import adresses
from recherche_bien import saisir_reference, identifier_par_reference, saisir_commune
from historique_taux import resoudre_tout, COMPOSANTES, LIBELLES
from mise_a_jour_simple import synchroniser_taux
from moteur_habitation import ENTRETIEN, SITUATION, CATEGORIES
from tarifs_habitation import tarifs_nationaux, SOURCE
from dossier_habitation import code_adresse, calculer_scenarios, H2_PIECES
from export_habitation_pdf import generer_pdf_habitation
from saisie_declaration import afficher_declaration
from frais_gestion import afficher_frais

ROOT = Path(__file__).resolve().parent


def load_ref():
    local = ROOT / 'data' / 'referentiel_local.json'
    return json.loads((local if local.exists() else ROOT / 'data' / 'referentiel_initial.json').read_text(encoding='utf-8'))


def fmt(value):
    return f'{float(value):,.2f}'.replace(',', ' ').replace('.', ',') + ' €'


def carte_habitation(titre, valeur, detail, principale=False):
    """Même palette et même hiérarchie que les cartes professionnelles."""
    classe = 'hab-result-card hab-result-main' if principale else 'hab-result-card'
    st.markdown(
        f'<div class="{classe}"><div class="hab-result-label">{escape(str(titre))}</div>'
        f'<div class="hab-result-value">{escape(str(valeur))}</div>'
        f'<div class="hab-result-detail">{escape(str(detail))}</div></div>',
        unsafe_allow_html=True,
    )


def aller(etape):
    st.session_state['hab_etape'] = etape
    st.session_state.pop('hab_resultat', None)
    st.rerun()


bouton_nouveau_calcul()
st.title('Estimez la taxe foncière de votre logement')
st.caption('Maison H1 ou appartement H2 · Estimation indicative, hors frais de gestion et exonérations particulières.')
st.info('Préparez votre déclaration H1/H2 ou votre fiche d’évaluation cadastrale si vous en disposez. L’aide au classement vous accompagne pour choisir une catégorie ; plusieurs séries pourront être comparées dans cette catégorie.')
etape = st.session_state.get('hab_etape', 1)
saisie = st.session_state.setdefault('hab_saisie', {})
st.progress(etape / 3, text=f'Étape {etape} sur 3 · ' + {1: 'Votre logement', 2: 'Surfaces et équipements', 3: 'Vérification et estimation'}[etape])

if etape == 1:
    st.subheader('1 · Identifier le logement')
    mode_recherche = st.radio('Rechercher le bien par', ['Adresse', 'Parcelle cadastrale'], horizontal=True,
        index=1 if saisie.get('mode_recherche') == 'Parcelle cadastrale' else 0, key=cle_calcul('hab_mode'))
    automatique, selection_commune = (False, None)
    if mode_recherche == 'Parcelle cadastrale':
        automatique, selection_commune = saisir_commune(cle_calcul('hab_ref'), saisie.get('reference'))
    with st.container(border=True):
        reference = {}
        adresse = ''
        adresse_selectionnee = None
        if mode_recherche == 'Adresse':
            adresse, adresse_selectionnee = saisir_adresse('Adresse du bien', cle_calcul('hab_adresse'), saisie.get('recherche', ''))
        else:
            reference = saisir_reference(cle_calcul('hab_ref'), saisie.get('reference'), automatique=automatique, selection=selection_commune)
        nature = st.radio('Type de logement', ['Appartement (H2)', 'Maison (H1)'],
            index=1 if saisie.get('nature') == 'M' else 0, horizontal=True, key=cle_calcul('hab_nature'),
            help='H1 correspond aux maisons ; H2 aux appartements. Ce choix détermine le barème de surface et le traitement des dépendances.')
        annee = st.number_input('Année d’imposition', key=cle_calcul('hab_annee'), min_value=2017, value=int(saisie.get('annee', date.today().year)), step=1,
            help='Année de l’avis à estimer, sans plafond de saisie. Le calcul nécessite les coefficients officiels de cette année ; une donnée absente n’est pas extrapolée.')
        st.caption('Vous pouvez saisir une année future. Si son coefficient officiel n’est pas encore intégré, le simulateur vous l’indiquera sans inventer de montant.')
        chercher = st.button('Rechercher cette adresse' if mode_recherche == 'Adresse' else 'Rechercher cette parcelle', type='primary')
    if chercher:
        saisie.update(mode_recherche=mode_recherche, reference=reference, recherche=adresse.strip(), adresse_suggestion=adresse_selectionnee, nature='M' if nature.startswith('Maison') else 'A', annee=int(annee))
        st.session_state.pop('hab_adresses', None)
        saisie.pop('adresse', None)
        if mode_recherche == 'Adresse' and len(adresse.strip()) < 6:
            st.error('Renseignez une adresse complète avec le numéro, la voie et la commune.')
        else:
            try:
                with st.spinner('Recherche du bien…'):
                    st.session_state['hab_adresses'] = ([adresse_selectionnee] if adresse_selectionnee is not None else adresses(adresse)) if mode_recherche == 'Adresse' else identifier_par_reference(reference)
                if not st.session_state['hab_adresses']:
                    st.warning('Aucun bien trouvé. Vérifiez l’adresse ou les références cadastrales saisies.')
            except (ConnectionError, ValueError) as exc:
                st.error('Recherche du bien indisponible : ' + str(exc))
    options = st.session_state.get('hab_adresses', [])
    # Un ancien résultat de recherche ne valide jamais une nouvelle saisie.
    recherche_actuelle = (mode_recherche, reference, adresse.strip(), adresse_selectionnee, 'M' if nature.startswith('Maison') else 'A', int(annee))
    recherche_sauvee = (saisie.get('mode_recherche', 'Adresse'), saisie.get('reference', {}), saisie.get('recherche'), saisie.get('adresse_suggestion'), saisie.get('nature'), saisie.get('annee'))
    if options and recherche_actuelle == recherche_sauvee:
        choix = st.selectbox('Confirmez l’adresse du logement' if mode_recherche == 'Adresse' else 'Confirmez la parcelle du logement', range(len(options)), index=0 if adresse_selectionnee is not None else None,
            placeholder='Sélectionnez le bien exact', format_func=lambda i: options[i]['libelle'],
            key='hab_adresse_choix', help='Vérifiez la commune et l’arrondissement. La recherche peut proposer plusieurs adresses ; aucune n’est choisie automatiquement.')
        if st.button('Continuer vers les surfaces', type='primary', disabled=choix is None):
            saisie['adresse'] = options[choix]
            saisie['parcelle'] = options[choix].get('parcelle')
            aller(2)

elif etape == 2:
    st.subheader('2 · Décrire les surfaces et les équipements')
    st.caption(f"{saisie['adresse']['libelle']} · {'Maison H1' if saisie['nature'] == 'M' else 'Appartement H2'} · {saisie['annee']}")
    params = saisie.get('parametres', {})
    maison = saisie['nature'] == 'M'
    h2 = saisie.get('h2', {})
    h1 = saisie.get('h1', {})
    description = h1 if maison else h2
    elements_h1 = {}
    with st.container(border=True):
        pieces_declares = {}
        st.markdown('#### 41 · Consistance de la maison — H1' if maison else '#### 41 · Consistance du logement — H2')
        st.caption('A · Pièces et annexes affectées à l’habitation. Reprenez les nombres de votre déclaration H1 ou H2 ; chaque pièce doit être comptée une seule fois.')
        for cle, libelle, aide in [
            ('reception', 'Salles à manger et pièces de réception diverses', 'Séjour, salon, salle commune, bibliothèque, etc. Comptez les pièces, pas les mètres carrés.'),
            ('chambres', 'Chambres et autres pièces habitables', 'Chambres et autres pièces habitables, hors pièces déjà déclarées dans une autre rubrique.'),
            ('cuisines_moins_9', 'Cuisines de moins de 9 m²', 'Nombre de cuisines dont la surface est inférieure à 9 m².'),
            ('cuisines_9_plus', 'Cuisines de 9 m² et plus', 'Une cuisine de 9 m² exactement est à compter ici.'),
            ('salles_eau', 'Salles d’eau', 'Salles de bains, salles de douches, cabinets de toilette avec eau courante. Les appareils sanitaires sont à compter séparément au cadre 42.'),
            ('autres_annexes', 'Autres annexes intérieures', 'Entrée, couloir, antichambre, office, rangement, etc., à l’exclusion des terrasses accessibles du cadre B.'),
        ]:
            pieces_declares[cle] = st.number_input(libelle, min_value=0, max_value=100, value=int(description.get('pieces', {}).get(cle, 0)), help=aide)
        st.caption('Reprenez les surfaces déclarées sur H1/H2 ou mesurées au sol. La surface Carrez ou habitable peut différer de la surface cadastrale. Ne comptez jamais deux fois la même surface.')
        surface = st.number_input('Surface totale des pièces et annexes affectées à l’habitation (m²)', min_value=0., max_value=20000.,
            value=float(saisie.get('surface', 0)), step=1.,
            help='Surface réelle des pièces et annexes intérieures du logement, avant correctifs fiscaux. N’y ajoutez pas la terrasse ni les dépendances saisies ci-dessous. Une valeur supérieure à zéro est obligatoire.')
        annexes = 0.
        if maison:
            st.markdown('#### 41 B · Éléments incorporés à la maison')
            st.caption('Éléments reliés à la maison : saisissez chaque surface séparément, hors des pièces du cadre 41 A. Les coefficients sont des hypothèses à confirmer sur la fiche cadastrale.')
            for cle, libelle in ELEMENTS_H1.items():
                element=params.get('elements_incorpores',{}).get(cle,{})
                a,b=st.columns(2)
                with a:
                    surface_element=st.number_input(libelle+' (m²)',min_value=0.,value=float(element.get('surface',0)),key=cle_calcul('h1_'+cle))
                with b:
                    coeff_element=st.number_input('Pondération — '+libelle,min_value=.2,max_value=.6,value=float(element.get('coefficient',.4)),step=.05,key=cle_calcul('h1_'+cle+'_coef'))
                elements_h1[cle]={'surface':surface_element,'coefficient':coeff_element}
            if params.get('annexes',0):
                annexes=st.number_input('Anciennes surfaces regroupées restant à répartir (m²)',min_value=0.,value=float(params['annexes']),help='Répartissez cette ancienne saisie dans les rubriques ci-dessus, puis ramenez ce reliquat à zéro pour éviter un double comptage.')
        else:
            st.markdown('#### 41 B · Éléments incorporés au logement — H2')
        terrasse = st.number_input('Terrasse accessible (m²)' if maison else 'Terrasses et toitures-terrasses accessibles (m²)',min_value=0.,max_value=10000.,value=float(params.get('terrasse',0)),step=1.,help='Surface réelle des terrasses et toitures-terrasses accessibles, hors de la surface des pièces.')
        coef_terrasse=st.number_input('Coefficient de pondération de la terrasse',min_value=.2,max_value=.6,value=float(params.get('coeff_terrasse',.4)),step=.05,help='Entre 0,2 et 0,6 selon le service rendu. La valeur proposée 0,4 est une hypothèse à confirmer.')
        st.caption('La terrasse du cadre 41 B est intégrée après pondération et arrondi au m² inférieur ; ne la comptez pas à nouveau au cadre 5.')
        if not maison:
            st.info('Détaillez les dépendances au cadre 5 ci-dessous. Pour chaque élément, choisissez s’il est rattaché au logement ou évalué distinctement.')
        partie_professionnelle = False
        declaration_6660 = False
        st.caption('B · Terrasses et toitures-terrasses accessibles : surface séparée de la surface totale des pièces. Les garages et caves distincts ne relèvent pas de cette surface totale.')
        partie_professionnelle = st.checkbox('C · Le logement comporte une partie professionnelle', value=description.get('partie_professionnelle', False), help='Reprend le cadre 41 C du H1 ou du H2. La partie professionnelle doit être examinée séparément ; ne la comptez pas dans les surfaces affectées à l’habitation.')
        declaration_6660 = st.checkbox('Une déclaration 6660-REV a été souscrite pour cette partie', value=description.get('declaration_6660', False), help='Information déclarative uniquement : cette case ne calcule pas la taxe de la partie professionnelle.')
        st.markdown('#### 42 · Confort de la maison — H1' if maison else '#### 42 · Confort du logement — H2')
        st.caption('Le calcul transforme les équipements en équivalences de surface. Vérifiez les quantités proposées : elles ne sont pas déduites automatiquement du nombre de pièces.')
        a, b = st.columns(2)
        quantites = {}
        for i, (cle, libelle, valeur, aide) in enumerate([
            ('wc', 'WC' if maison else 'WC particuliers', 0, 'Nombre de WC propres au logement.'),
            ('baignoires', 'Baignoires', 0, 'Nombre de baignoires.'),
            ('douches', 'Receveurs de douches', 0, 'Nombre de receveurs de douche distincts.'),
            ('lavabos', 'Lavabos', 0, 'Lavabos et divers, éviers exclus, conformément aux deux formulaires.')
        ]):
            with [a, b][i % 2]:
                quantites[cle] = st.number_input(libelle, min_value=0, max_value=100, value=int(params.get(cle, valeur)), help=aide)
        a, b = st.columns(2)
        equipements = {}
        for i, (cle, libelle, valeur, aide) in enumerate([
            ('eau', 'Eau courante', True, 'Installation d’eau courante dans le logement.'),
            ('gaz', 'Installation fixe de gaz', False, 'Installation fixe ; une bouteille ou un appareil mobile ne suffit pas.'),
            ('electricite', 'Électricité', True, 'Installation électrique du logement.'),
            ('egout', 'Tout-à-l’égout', True, 'Raccordement au réseau public d’assainissement. Ne cochez pas pour une fosse individuelle.'),
            ('vide_ordures', 'Vide-ordures', False, 'Installation de vide-ordures. Un local à poubelles ou un bac de collecte ne correspond pas à cet équipement.'),
        ]):
            if maison and cle=='vide_ordures':
                equipements[cle]=False
                continue
            with [a, b][i % 2]:
                equipements[cle] = st.checkbox(libelle, value=params.get(cle, False), help=aide)
        escalier_service = False
        ascenseur = False
        chauffage=st.checkbox('Chauffage ou climatisation dans les DOM',value=description.get('chauffage',False),help='Case 6 du cadre 42. Les coefficients de calcul actuels couvrent la métropole.')
        pieces_chauffees_declares=st.number_input('Nombre de pièces chauffées',min_value=0,value=int(description.get('pieces_chauffees',params.get('pieces_chauffees',0))),step=1,help='Nombre saisi librement : 2 m² d’équivalence par pièce desservie, sans comptage automatique.')
        if maison:
            quantites['pieces_chauffees']=pieces_chauffees_declares
            st.caption('La majoration chauffage utilise uniquement le nombre de pièces que vous déclarez.')
        else:
            st.markdown('**Étage et ascenseur de l’immeuble — article 324 S**')
            etage = st.number_input('Niveau du logement pour le correctif d’ascenseur', min_value=0, max_value=80, value=int(params.get('etage', 0)), help='0 = rez-de-chaussée, 1 = premier niveau, etc. Selon l’article 324 S, l’entresol compte pour un étage : avec un entresol sous votre premier étage, saisissez 2. Ne comptez pas deux fois l’entresol.')
            ascenseur = st.checkbox('Ascenseur de l’immeuble desservant l’étage du logement', value=params.get('ascenseur', False), help='Renseigne la colonne « immeuble avec ascenseur » de l’article 324 S. Il s’agit de la desserte de l’étage par l’ascenseur de l’immeuble, pas d’un ascenseur privatif à l’intérieur du logement.')
            st.caption('Correctif ajouté au correctif d’ensemble : avec ascenseur, 0 au RDC et au 1er niveau, +0,05 à partir du 2e ; sans ascenseur, 0 jusqu’au 3e, −0,05 au 4e, −0,10 au 5e, −0,15 à partir du 6e. Ce correctif n’est pas une équivalence de surface en m².')
            escalier_service = st.checkbox('Escalier de service', value=h2.get('escalier_service', False), help='Case 9 du cadre 42. Cette information est conservée dans le dossier ; aucun coefficient supplémentaire n’est inventé.')
            st.caption('La majoration sera de 2 m² × le nombre de pièces chauffées que vous saisissez. Aucun comptage automatique n’est effectué.')
        if maison:
            st.markdown('#### 43 · Caractéristiques générales de la maison')
            st.caption('Ces renseignements descriptifs sont conservés dans le dossier et le PDF. Ils ne déterminent pas automatiquement la catégorie ou un tarif.')
            murs=st.multiselect('Principaux matériaux des gros murs',MURS,default=h1.get('materiaux_murs',[]))
            toitures=st.multiselect('Matériaux des toitures',TOITURES,default=h1.get('materiaux_toitures',[]))
            entretien=st.selectbox('État d’entretien cadastral',list(ENTRETIEN),index=list(ENTRETIEN).index(params.get('entretien','Passable')),help='Cadre 43 C du H1 ; ce choix alimente le correctif d’entretien. À confirmer sur la fiche cadastrale.')
            construction=st.number_input('Année de construction de la maison',min_value=1,max_value=9999,value=h1.get('annee_construction'),placeholder='Si connue')
            niveaux=st.number_input('Nombre de niveaux habitables',min_value=1,value=h1.get('niveaux_habitables'),help='Rez-de-chaussée compris, greniers exclus (cadre 43 E). Ce n’est pas un correctif d’ascenseur.')
        st.markdown('#### Catégorie cadastrale du logement')
        st.caption('Reprenez d’abord la catégorie de votre fiche d’évaluation cadastrale. Si vous ne l’avez pas, utilisez l’aide ci-dessous pour choisir une catégorie indicative ; elle reste à confirmer par le service des impôts fonciers.')
        ordre = sorted(CATEGORIES, key=lambda x: (int(x[0]), len(x)))
        categories = [None] + ordre
        categorie = st.selectbox('Catégorie cadastrale du logement', categories,
            index=categories.index(saisie.get('categorie')),
            format_func=libelle_categorie,
            help='Choix obligatoire pour calculer. Reprenez la fiche cadastrale ou choisissez une hypothèse avec l’aide au classement. La fourchette comparera uniquement les séries publiées dans cette catégorie.')
        st.markdown('#### M’aider à choisir la catégorie la plus pertinente')
        with st.container(border=True):
            st.markdown('**Les critères de classement à examiner ensemble**')
            for critere, explication in CRITERES:
                st.markdown(f'**{critere}** — {explication}')
            st.table([{'Catégorie': k, 'Classement': v[0], 'Repères qualitatifs simplifiés': v[1]} for k,v in CLASSEMENT.items()])
            st.caption('Référence : CGI, annexe III, article 324 H. Ces repères sont une aide de lecture et non la reproduction exhaustive du tableau réglementaire. Le classement s’apprécie par comparaison avec les locaux de référence de la commune.')
            st.write('Examinez d’abord le niveau général de construction et de distribution, puis le confort et les équipements. Par exemple, les catégories 4, 5 et 6 distinguent un ensemble confortable, assez confortable ou ordinaire. La seule présence d’un chauffage ou d’une salle d’eau ne permet pas de trancher.')
            st.caption('Ne déduisez pas la catégorie du prix de vente, du DPE ou d’un seul équipement. L’entretien et la situation du bien font l’objet de correctifs distincts : une dégradation ponctuelle ne suffit pas à reclasser le logement. Les catégories 1M à 7M sont intermédiaires entre deux catégories voisines.')
        source_categorie = st.selectbox('Origine de la catégorie choisie', ['Choix indicatif avec l’aide au classement', 'Catégorie figurant sur ma fiche cadastrale'],
            index=1 if saisie.get('categorie_confirmee') else 0,
            help='Précisez si votre catégorie est documentée ou si elle constitue une hypothèse de simulation.')
        st.markdown('#### Correctifs cadastraux — à vérifier pour chaque calcul')
        with st.container(border=True):
            st.caption('Reprenez les correctifs de la fiche cadastrale si vous les connaissez. À défaut, les correctifs neutres restent des hypothèses de simulation, distinctes de la catégorie choisie.')
            st.markdown('#### État, situation et dépendances')
            if maison:
                st.caption(f'Entretien repris du cadre 43 C : {entretien} (coefficient {ENTRETIEN[entretien]:g}).')
            st.caption('Ces correctifs décrivent l’état et la situation retenus pour l’évaluation cadastrale. Les valeurs proposées sont des hypothèses à vérifier sur votre fiche.')
            a, b = st.columns(2)
            with a:
                if not maison:
                    entretien = st.selectbox('État d’entretien cadastral', list(ENTRETIEN), index=list(ENTRETIEN).index(params.get('entretien', 'Passable')),
                    help='État général du bâtiment : bon, assez bon, passable, médiocre ou mauvais. Il s’agit du correctif cadastral, pas d’une note de décoration. « Passable » applique le coefficient neutre 1.')
                sit_gen = st.selectbox('Situation générale', list(SITUATION), index=list(SITUATION).index(params.get('situation_generale', 'Ordinaire')),
                    help='Appréciation du quartier ou de l’environnement général du bien. « Ordinaire » n’ajoute ni ne retranche de correctif ; confirmez avec la fiche cadastrale.')
            with b:
                sit_part = st.selectbox('Situation particulière', list(SITUATION), index=list(SITUATION).index(params.get('situation_particuliere', 'Ordinaire')),
                    help='Situation propre au logement dans son environnement : exposition, vue, nuisances ou accès, selon l’évaluation cadastrale. Ne confondez pas avec la situation du quartier.')
                if maison and annexes:
                    coef_annexe = st.selectbox('Pondération des dépendances', [.2, .3, .4, .5, .6], index=[.2, .3, .4, .5, .6].index(params.get('coeff_annexes', .4)),
                        help='Coefficient cadastral de 0,2 à 0,6 selon le service rendu. Le choix 0,4 est une hypothèse, pas une valeur déduite de votre adresse. Reprenez la valeur de votre fiche si elle est connue.')
        anciennes_dependances = saisie.get('dependances')
        if anciennes_dependances is None and not maison and params.get('annexes', 0):
            anciennes_dependances = [{'type':'garage', 'designation':'Dépendances antérieurement regroupées', 'surface':params['annexes'], 'mode':None}]
        if maison:
            anciennes_dependances=saisie.get('dependances_h1',[])
        elif anciennes_dependances and any(d.get('type')=='batiment_h1' for d in anciennes_dependances):
            anciennes_dependances=saisie.get('dependances_h2',[])
        dependances_saisies = saisir_dependances(anciennes_dependances,saisie['annee'],maison=maison)
        if maison:
            st.markdown('#### 6 · Renseignements sur la propriété — H1')
            st.caption('Emprises au sol approximatives, descriptives : elles ne s’ajoutent pas aux surfaces fiscales ci-dessus.')
            empreintes={}
            for cle,libelle in [('maison','Emprise au sol de la maison (m²)'),('dependances','Emprise au sol des dépendances (m²)'),('terrains','Cours, voies d’accès, jardins et terrains attenants (m²)')]:
                empreintes[cle]=st.number_input(libelle,min_value=0.,value=h1.get('emprises',{}).get(cle),key=cle_calcul('h1_emprise_'+cle))
        a, b = st.columns(2)
        retour = a.button('Retour au logement')
        suivant = b.button('Vérifier mes informations', type='primary')
    if retour or suivant:
        saisie['dependances'] = dependances_saisies
        saisie['dependances_h1' if maison else 'dependances_h2']=dependances_saisies
        saisie.update(surface=surface, categorie=categorie, categorie_confirmee=source_categorie == 'Catégorie figurant sur ma fiche cadastrale', parametres={
            'annexes': annexes, 'terrasse': terrasse, 'coeff_terrasse':coef_terrasse, 'entretien': entretien,
            'situation_generale': sit_gen, 'situation_particuliere': sit_part,
            **quantites, **equipements,
            **({'coeff_annexes': coef_annexe if annexes else .4,'elements_incorpores':elements_h1} if maison else {'etage': etage, 'ascenseur': ascenseur})})
        if maison:
            saisie['h1']={'pieces':pieces_declares,'chauffage':chauffage,'pieces_chauffees':pieces_chauffees_declares,
                'materiaux_murs':murs,'materiaux_toitures':toitures,'annee_construction':construction,
                'niveaux_habitables':niveaux,'emprises':empreintes,'partie_professionnelle':partie_professionnelle,
                'declaration_6660':declaration_6660}
            saisie.pop('h2', None)
        else:
            saisie['h2'] = {'pieces': pieces_declares, 'chauffage': chauffage, 'pieces_chauffees': pieces_chauffees_declares, 'escalier_service': escalier_service, 'partie_professionnelle': partie_professionnelle, 'declaration_6660': declaration_6660}
        if retour:
            aller(1)
        elif surface <= 0:
            st.error('Indiquez une surface réelle du logement supérieure à zéro.')
        elif categorie is None:
            st.error('Choisissez une catégorie cadastrale à l’aide des critères de classement, ou reprenez celle de votre fiche d’évaluation.')
        elif not maison and not chauffage and pieces_chauffees_declares > 0:
            st.error('Cochez le chauffage ou indiquez zéro pièce chauffée.')
        elif not maison and not sum(pieces_declares.values()):
            st.error('Renseignez au moins une pièce dans le cadre 41 du H2.')
        else:
            try:
                valider_dependances(dependances_saisies)
                if maison:
                    valider_elements_incorpores(elements_h1)
                    valider_description_h1(saisie['h1'])
            except ValueError as exc:
                st.error(str(exc))
            else:
                aller(3)

else:
    st.subheader('3 · Vérifier avant de calculer')
    adr = saisie['adresse']
    params = saisie['parametres']
    st.write(f"**{adr['libelle']}** · {'Maison H1' if saisie['nature'] == 'M' else 'Appartement H2'} · imposition {saisie['annee']}")
    st.write(f"Surface réelle : **{saisie['surface']:g} m²** · Terrasse : **{params['terrasse']:g} m²** · Dépendances : **{params['annexes'] + sum(e['surface'] for e in params.get('elements_incorpores',{}).values()) + sum(d['surface'] for d in saisie.get('dependances', [])):g} m²**")
    if saisie.get('h1'):
        st.table([{'Consistance H1':H2_PIECES[k],'Nombre':v} for k,v in saisie['h1']['pieces'].items()])
        st.table([{'Caractéristique H1':libelle,'Valeur':valeur} for libelle,valeur in [
            ('Gros murs',', '.join(saisie['h1']['materiaux_murs']) or 'Non renseignés'),
            ('Toitures',', '.join(saisie['h1']['materiaux_toitures']) or 'Non renseignées'),
            ('Année de construction',str(saisie['h1'].get('annee_construction') or 'Non renseignée')),
            ('Niveaux habitables',str(saisie['h1'].get('niveaux_habitables') or 'Non renseignés')),
            ('Emprise au sol de la maison (descriptive)',str(saisie['h1'].get('emprises',{}).get('maison') or 'Non renseignée')),
            ('Emprise au sol des dépendances (descriptive)',str(saisie['h1'].get('emprises',{}).get('dependances') or 'Non renseignée'))]])
        st.table([{'Élément incorporé':ELEMENTS_H1[k],'Surface (m²)':e['surface'],'Pondération':e['coefficient']} for k,e in params.get('elements_incorpores',{}).items() if e['surface']])
    if saisie.get('h2'):
        st.table([{'Consistance H2': H2_PIECES[k], 'Nombre': v} for k,v in saisie['h2']['pieces'].items()])
        st.write('Pièces chauffées déclarées : ' + str(saisie['h2'].get('pieces_chauffees', 0)) + ' · Chauffage : ' + ('oui' if saisie['h2']['chauffage'] else 'non') + ' · Escalier de service : ' + ('oui' if saisie['h2']['escalier_service'] else 'non'))
    if saisie.get('dependances'):
        st.table([{'Dépendance': d.get('designation') or TYPES[d['type']], 'Surface (m²)': d['surface'], 'Traitement': MODES[d['mode']]} for d in saisie['dependances']])
    st.write('Catégorie : **' + (libelle_categorie(saisie['categorie']) if saisie.get('categorie') else 'à choisir avant le calcul') + '**')
    with st.expander('Relire les correctifs et les équipements retenus'):
        st.write(f"Entretien : {params['entretien']} · Situation générale : {params['situation_generale']} · Situation particulière : {params['situation_particuliere']}")
        st.write({k: v for k, v in params.items() if k not in ('entretien', 'situation_generale', 'situation_particuliere')})
    st.caption('Les équipements préremplis et les correctifs neutres restent des hypothèses tant que vous ne les avez pas vérifiés. L’adresse ne permet pas de déterminer la catégorie ou la série cadastrale.')
    a, b = st.columns(2)
    if a.button('Modifier mes informations'):
        aller(2)
    if b.button('Calculer mon estimation', type='primary', disabled=not saisie.get('categorie')):
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
    if r and (not saisie.get('categorie') or r.get('categorie') != saisie.get('categorie') or any(('detail_terrasse' not in t.get('surfaces', {}) or 'detail_surface_nette' not in t.get('surfaces', {})) for t in r.get('tarifs', []))):
        st.session_state.pop('hab_resultat', None)
        r = None
        st.info('Les paramètres de calcul ont changé. Vérifiez les informations puis relancez le calcul pour actualiser le résultat.')
    if r:
        st.divider()
        st.markdown("""<style>
.hab-result-card{border:1px solid #DFE8F2;border-radius:18px;background:#FFFFFF;color:#153957;padding:1.15rem 1.2rem;margin:.25rem 0 .8rem;box-shadow:0 5px 22px rgba(22,67,109,.055);border-top:3px solid #246A9D;min-height:148px}
.hab-result-label{font-size:.9rem;font-weight:600;color:#547088;margin-bottom:.5rem}
.hab-result-value{font-size:1.65rem;font-weight:750;line-height:1.2;color:#164C79;overflow-wrap:anywhere}
.hab-result-detail{font-size:.86rem;color:#526B80;line-height:1.5;margin-top:.55rem}
.hab-result-main{background:#EDF4F9;border-left:5px solid #246A9D;border-top:1px solid #DFE8F2;min-height:0;padding:1.4rem 1.5rem}
.hab-result-main .hab-result-value{font-size:clamp(2rem,6vw,3rem)}
.hab-tax-card{border-top:1px solid #DFE8F2;border-left:4px solid #246A9D;min-height:155px}
@media(max-width:640px){.hab-result-card{min-height:0;padding:1rem}.hab-result-value{font-size:1.45rem}}
</style>""", unsafe_allow_html=True)
        st.subheader('Votre estimation habitation')
        st.caption(f"{r['adresse']} · {r['nature']} · Année {r['annee']}")
        for reserve in r.get('reserves_h2', []):
            st.warning(reserve)
        for incident in r['incidents']:
            st.warning(incident)
        if not r.get('categorie_confirmee'):
            st.warning(f"Catégorie {r['categorie']} choisie à titre indicatif avec l’aide au classement : à confirmer sur la fiche d’évaluation cadastrale.")
        scenarios = r['tarifs']
        if len(scenarios) > 1:
            st.info(f"Plusieurs séries tarifaires sont publiées dans la catégorie {r['categorie']}. La série exacte et son origine sont à confirmer sur votre fiche cadastrale.")
            totals = [t['total'] for t in scenarios if 'total' in t]
            if totals:
                st.write(f"**Fourchette des séries — catégorie {r['categorie']} : {fmt(min(totals))} à {fmt(max(totals))}**, pour le nombre de pièces chauffées déclaré et le logement avec ses dépendances rattachées, hors frais, exonérations et dépendances distinctes.")
            else:
                bases = [t['base_tf'] for t in scenarios]
                st.write(f"**Fourchette des bases TFPB — catégorie {r['categorie']} : {fmt(min(bases))} à {fmt(max(bases))}**. Les cotisations restent indisponibles faute de taux documentés.")
        choice = st.selectbox('Scénario à examiner', range(len(scenarios)),
            format_func=lambda i: f"Catégorie {scenarios[i]['categorie']} · Série {scenarios[i]['serie']} · Origine {scenarios[i]['origine'] or 'non précisée'} · {fmt(scenarios[i]['tarif_1970'])}/m²",
            help='Choisissez une série de la catégorie retenue. Ce choix ne confirme pas son attribution au logement.')
        x = scenarios[choice]
        if 'pieces_chauffage_scenario' in x:
            st.info(f"Chauffage pris en compte : {x['pieces_chauffage_scenario']} × 2 m² = +{2*x['pieces_chauffage_scenario']} m² d’équivalence de surface. Cette majoration s’ajoute à la surface nette avant application du tarif cadastral. Le nombre de pièces chauffées est celui que vous avez saisi, sans déduction automatique.")
        sp = x['surfaces']
        if sp.get('terrasse_ponderee', 0) or r.get('terrasse_reelle', 0):
            t = sp['detail_terrasse']
            st.info(f"Terrasse intégrée : {t['surface_declaree']:g} m² déclarés → {t['surface_reelle_retenue']} m² réels retenus × {t['coefficient']:g} → {t['surface_ponderee']} m² pondérés après arrondi inférieur, retenus parmi les éléments secondaires avant leurs correctifs, hors ascenseur. Coefficient à confirmer sur la fiche cadastrale.")
        if sp['dependances_a_evaluer_separement']:
            st.warning('Estimation partielle : des surfaces de dépendances anciennement regroupées ne sont pas ventilées. Précisez leur traitement dans le cadre 5 pour les chiffrer.')
        if not r['taux_complets']:
            missing = [LIBELLES[k] for k in COMPOSANTES if not r['taux'].get(k) or r['taux'][k].get('taux') is None]
            st.warning('Taux non documentés : ' + ', '.join(missing) + '. Aucun total de cotisations n’est affiché ; un taux manquant ne vaut pas zéro.')
        anciens = [f"{LIBELLES[k]} ({v['annee_source']})" for k, v in r['taux'].items() if v and v['annee_source'] < r['annee']]
        if anciens:
            st.warning('Taux antérieurs repris à titre indicatif : ' + ', '.join(anciens) + '.')
        if r['taux'].get('teom') and not r['taux']['teom'].get('zonage_confirme'):
            st.warning('Le zonage TEOM n’est pas confirmé pour cette adresse : la cotisation correspondante reste à vérifier.')
        if sp['nature'] == 'A':
            st.caption(f"Ascenseur de l’immeuble : {'oui' if sp['detail_correctifs']['ascenseur_immeuble'] else 'non'} · Niveau retenu : {sp['detail_correctifs']['niveau_local']} · Correctif article 324 S : {sp['correctif_ascenseur']:+.2f}, appliqué à la partie principale uniquement.")
        if 'montants' in x:
            carte_habitation(
                'Cotisations annuelles estimées — logement et dépendances rattachées', fmt(x['total']),
                'Hors frais de gestion et exonérations. Sous réserve du classement cadastral, des taux et du zonage TEOM. Dépendances distinctes non incluses.',
                principale=True,
            )
        else:
            carte_habitation('Valeur locative estimée', fmt(x['vl_annee']),
                'Il s’agit de la valeur locative, pas du montant de taxe à payer. Les taux manquants empêchent de calculer les cotisations.', principale=True)
        a, b, c = st.columns(3)
        with a:
            carte_habitation('Surface pondérée', f"{sp['surface_ponderee']} m²",
                'Surface cadastrale calculée à partir des surfaces et des équipements déclarés.')
        with b:
            carte_habitation(f"Valeur locative {r['annee']}", fmt(x['vl_annee']),
                'Valeur de référence revalorisée pour l’année d’imposition.')
        with c:
            carte_habitation('Base de taxe foncière', fmt(x['base_tf']),
                '50 % de la valeur locative, avant exonérations particulières.')
        if 'montants' in x:
            st.markdown('#### Répartition par taxe')
            colonnes = st.columns(2)
            for i, (cle, montant) in enumerate(x['montants'].items()):
                taux = r['taux'][cle]
                with colonnes[i % 2]:
                    st.markdown(
                        '<div class="hab-result-card hab-tax-card">'
                        f'<div class="hab-result-label">{escape(LIBELLES[cle])}</div>'
                        f'<div class="hab-result-value">{escape(fmt(montant))}</div>'
                        f'<div class="hab-result-detail">Base : {escape(fmt(x["base_tf"]))} · Taux : {float(taux["taux"]):g} %<br/>'
                        f'Millésime du taux : {int(taux["annee_source"])}</div></div>',
                        unsafe_allow_html=True,
                    )
        with st.expander('Comprendre le calcul, étape par étape', expanded=False):
            st.write(f"1. Surface comparative : **{sp['comparative']} m²**, issue du barème de catégorie {x['categorie']}.")
            net = sp['detail_surface_nette']
            if net['mode'] == 'separe':
                st.write(f"2. Partie principale : {sp['comparative']} × {sp['correctif']} = {net['principal_brut']:g} → **{net['principal_net']} m²**. Éléments secondaires : {net['secondaires_ponderes']} × {net['coefficient_secondaires']} = {net['secondaires_brut']:g} → **{net['secondaires_net']} m²**, sans correctif d’ascenseur. Total net : **{sp['surface_nette']} m²**.")
            else:
                st.write(f"2. Surface pondérée brute : {net['surface_brute']} m² × {sp['correctif']} → **{sp['surface_nette']} m² nets**.")
            st.write(f"3. Équipements : **+ {sp['equivalence_confort']} m²** → surface pondérée **{sp['surface_ponderee']} m²**.")
            st.table([{'Équipement': k, 'Équivalence (m²)': v} for k, v in sp['detail_confort'].items() if v])
            st.write(f"4. Valeur locative 1970 : {sp['surface_ponderee']} m² × {fmt(x['tarif_1970'])}/m² = **{fmt(x['vl_1970'])}**.")
            st.write(f"5. Actualisation 1980 × {r['facteur']['actualisation_1980']} ; revalorisation nationale × {r['facteur']['revalorisation_nationale']} → **{fmt(x['vl_annee'])}**. La moitié forme la base TFPB : **{fmt(x['base_tf'])}**.")
        if r.get('dependances'):
            st.markdown('#### Dépendances déclarées')
            st.table([{'Élément': d['designation'], 'Surface (m²)': d['surface'], 'Traitement': MODES[d['mode']],
                'Surface pondérée rattachée (m²)': f"{d['surface_ponderee']:g} m²" if d['mode']=='incorporee' else 'Évaluation distincte'} for d in r['dependances']])
            for d in r.get('dependances_distinctes', []):
                if 'total' in d:
                    st.write(f"**{d['designation']}** · Base distincte {fmt(d['base_tf'])} · Cotisations : **{fmt(d['total'])}**, avec les taux du logement confirmés pour cette dépendance.")
                else:
                    st.warning(f"{d['designation']} : évaluation distincte non chiffrée. Il faut une base de l’année simulée et des taux/zonage confirmés. Le montant du logement ne constitue pas le total du bien.")
            if r.get('dependances_distinctes') and 'total_bien' in x:
                carte_habitation('Total estimé — logement et dépendances distinctes comprises', fmt(x['total_bien']), 'Hors frais et exonérations ; bases et taux distincts renseignés.', principale=True)
        with st.expander('Sources et millésimes utilisés'):
            st.write('Tarifs cadastraux DGFiP 2024 en valeur de référence 1970 : ' + SOURCE)
            if r.get('terrasse_reelle', 0):
                st.write('Pondération de la terrasse — DGFiP, brochure IDL 2025, p. 23 (articles 324 M/N) : '+sp['detail_terrasse']['source'])
            st.write(r['facteur']['source_departement'])
            st.write(r['facteur']['source_revalorisation'])
            st.table([{'Composante': LIBELLES[k], 'Taux (%)': v['taux'], 'Année source': v['annee_source'], 'Source': v.get('source', '')} for k, v in r['taux'].items() if v])
        frais = None
        perimetre_frais = 'logement et dépendances rattachées'
        if 'montants' in x:
            cotisations = dict(x['montants'])
            distinctes = r.get('dependances_distinctes', [])
            if distinctes and 'total_bien' in x:
                perimetre_frais = 'logement et toutes les dépendances'
                for dependance in distinctes:
                    for cle, montant in dependance['montants'].items():
                        cotisations[cle] += montant
            frais = afficher_frais(cotisations, r['annee'], LIBELLES, fmt,
                                   cle_calcul('frais_teom_habitation'), perimetre_frais)
        dossier_pdf = {**r, 'categorie': x['categorie'], 'surfaces': sp, 'tarifs': scenarios,
                       'frais': frais, 'perimetre_frais': perimetre_frais}
        dossier_pdf['serie_selectionnee'] = dossier_pdf['tarifs'].index(x)
        st.download_button('Télécharger le rapport PDF de ce scénario', data=generer_pdf_habitation(dossier_pdf),
            file_name=f"estimation_habitation_{r['annee']}_{r['code_insee']}.pdf", mime='application/pdf', use_container_width=True)
        afficher_declaration('h1' if saisie['nature'] == 'M' else 'h2', saisie)
