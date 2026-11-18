"""Cadre 5 H2 : ajout et suppression de lignes sans perdre les autres saisies."""
import streamlit as st
from dependances_habitation import TYPES, MODES
from session_calcul import cle_calcul
from formulaire_h1 import SURFACES_DEP_H1, MURS, TOITURES


def ajouter_dependance(etat):
    numero = max(st.session_state.get(etat+'_numero', 0),max((r['id'] for r in st.session_state[etat]),default=0)) + 1
    st.session_state[etat+'_numero'] = numero
    st.session_state[etat].append({'id': numero})


def supprimer_dependance(identifiant, etat):
    st.session_state[etat] = [r for r in st.session_state[etat] if r['id'] != identifiant]


def saisir_dependances(valeurs, annee, maison=False):
    etat='hab_dependances_h1' if maison else 'hab_dependances'
    if etat not in st.session_state:
        lignes = [dict(r, id=i) for i, r in enumerate(valeurs or [], 1)]
        st.session_state[etat] = lignes
        st.session_state[etat+'_numero'] = len(lignes)
    st.markdown('#### 5 · Consistance et confort des dépendances — '+('H1' if maison else 'H2'))
    st.caption('Ajoutez une ligne par élément. Ne reportez pas ces surfaces dans celles des pièces du logement. Le mode de traitement est à choisir pour chaque ligne, d’après le dossier cadastral.')
    st.button('＋ Ajouter une dépendance', key=cle_calcul('ajouter_dependance'), on_click=ajouter_dependance, args=(etat,))
    for i, ligne in enumerate(st.session_state[etat], 1):
        cle = cle_calcul(f"dependance_{'h1' if maison else 'h2'}_{ligne['id']}")
        with st.expander(f"Dépendance {i} · {ligne.get('designation') or 'à renseigner'}", expanded=True):
            types = [k for k in TYPES if k!='batiment_h1']
            if maison:
                ligne['type']='batiment_h1'
            else:
                ligne['type'] = st.selectbox('Type de dépendance', types, index=types.index(ligne.get('type', 'garage')), format_func=TYPES.get, key=cle+'_type')
            ligne['designation'] = st.text_input('Désignation de l’élément', value=ligne.get('designation', ''), key=cle+'_designation', placeholder='Garage, cave, chambre de service…')
            a,b = st.columns(2)
            with a:
                if not maison:
                    ligne['lot'] = st.text_input('Numéro de lot (facultatif)', value=ligne.get('lot', ''), key=cle+'_lot')
                if not maison:
                    ligne['surface'] = st.number_input('Surface de la dépendance (m²)', min_value=0., value=float(ligne.get('surface', 0)), key=cle+'_surface')
            with b:
                ligne['situation'] = st.text_input('Situation dans la propriété', value=ligne.get('situation', ''), key=cle+'_situation', placeholder='Sous-sol, cour, bâtiment B…')
                modes = [None]+list(MODES)
                ligne['mode'] = st.selectbox('Traitement fiscal de cette dépendance', modes, index=modes.index(ligne.get('mode')), format_func=lambda v: MODES.get(v, 'Choisissez le traitement'), key=cle+'_mode', help='Un garage peut avoir sa propre évaluation. Vérifiez le rattachement sur la fiche cadastrale ; aucune dépendance n’est automatiquement incorporée.')
            if not maison:
                a,b=st.columns(2)
                with a:
                    ligne['batiment']=st.text_input('Bâtiment de la dépendance',value=ligne.get('batiment',''),key=cle+'_batiment')
                with b:
                    ligne['etage_description']=st.text_input('Étage de la dépendance',value=ligne.get('etage_description',''),key=cle+'_etage_description',placeholder='Sous-sol, RDC, étage…')
            if maison:
                st.markdown('**51 · Surfaces de chaque dépendance**')
                composition=ligne.setdefault('composition',{})
                for code,libelle in SURFACES_DEP_H1.items():
                    element=composition.setdefault(code,{})
                    a,b=st.columns(2)
                    with a:
                        element['surface']=st.number_input(libelle+' (m²)',min_value=0.,value=float(element.get('surface',0)),key=cle+'_'+code)
                    if ligne['mode']=='incorporee' and code!='agrement':
                        with b:
                            element['coefficient']=st.number_input('Pondération — '+libelle,min_value=.2,max_value=.6,value=float(element.get('coefficient',.4)),step=.05,key=cle+'_'+code+'_coef')
                ligne['surface']=sum(e.get('surface',0) for e in composition.values())
                ligne['nature_agrement']=st.text_input('Nature des éléments de pur agrément',value=ligne.get('nature_agrement',''),key=cle+'_nature_agrement',placeholder='Piscine, jardin d’hiver…')
                st.caption('Une ligne décrit une dépendance. Les surfaces de ses composantes sont séparées ; les éléments de pur agrément relèvent d’une évaluation distincte.')
                st.markdown('**52 · Équipement de la dépendance**')
            if ligne['mode'] == 'incorporee' and not maison:
                aide = 'Reprenez le coefficient de la fiche cadastrale. La valeur initiale 0,4 est une hypothèse à confirmer.'
                if ligne['type'] == 'cave':
                    aide += (
                        '\n\nRepères indicatifs pour une cave :\n\n'
                        '- **0,2** — Cave ordinaire de faible valeur d’usage.\n'
                        '- **0,4** — Cave présentant une valeur d’usage importante.\n'
                        '- **0,5** — Cave particulièrement valorisable.'
                    )
                ligne['coefficient'] = st.number_input(
                    'Coefficient de pondération', min_value=.2, max_value=.6,
                    value=float(ligne.get('coefficient', .4)), step=.05, key=cle+'_coefficient', help=aide,
                )
                st.caption('La surface pondérée rejoint le groupe des éléments secondaires, corrigé et arrondi séparément, sans correctif d’ascenseur ; le même tarif est ensuite appliqué. Ne comptez pas deux fois les mêmes équipements.')
            if ligne['mode'] == 'distincte':
                if ligne.get('annee_base') != annee:
                    ligne.update(base_tf=None, taux_logement_confirmes=False, annee_base=annee)
                ligne['base_tf'] = st.number_input(f'Base imposable TFPB {annee} de la dépendance (€)', min_value=0., value=ligne.get('base_tf'), key=cle+f'_base_{annee}', placeholder='Facultatif, si documentée', help='Base imposable annuelle de cette dépendance seule, après déduction de 50 %, issue de son évaluation ou de l’avis. Ce n’est pas le montant de taxe ni une valeur locative brute. Laissez vide si inconnue.')
                ligne['taux_logement_confirmes'] = st.checkbox('Les mêmes taux et le même zonage TEOM que le logement sont confirmés pour cette dépendance', value=ligne.get('taux_logement_confirmes', False), key=cle+f'_taux_{annee}')
                st.caption('Aucun tarif du logement principal n’est appliqué à une évaluation distincte. Sans base et taux confirmés, elle reste signalée comme non chiffrée.')
            a,b = st.columns(2)
            with a:
                ligne['eau'] = st.checkbox('Eau courante dans la dépendance', value=ligne.get('eau', False), key=cle+'_eau')
            with b:
                ligne['electricite'] = st.checkbox('Électricité dans la dépendance', value=ligne.get('electricite', False), key=cle+'_electricite')
            if ligne['type'] == 'piece':
                for champ, libelle in [('wc','WC particuliers'),('baignoires','Baignoires'),('douches','Receveurs de douches'),('lavabos','Lavabos (éviers exclus)'),('pieces_chauffees','Nombre de pièces chauffées')]:
                    ligne[champ] = st.number_input(libelle+' — dépendance', min_value=0, value=int(ligne.get(champ, 0)), key=cle+'_'+champ)
            if maison:
                st.markdown('**53 · Caractéristiques générales de la dépendance**')
                ligne['materiaux_murs']=st.multiselect('Matériaux des murs — dépendance',MURS,default=ligne.get('materiaux_murs',[]),key=cle+'_murs')
                ligne['materiaux_toitures']=st.multiselect('Matériaux des toitures — dépendance',TOITURES,default=ligne.get('materiaux_toitures',[]),key=cle+'_toitures')
                ligne['etat_entretien']=st.selectbox('État d’entretien — dépendance',[None,'Bon','Assez bon','Passable','Médiocre','Mauvais'],index=[None,'Bon','Assez bon','Passable','Médiocre','Mauvais'].index(ligne.get('etat_entretien')),key=cle+'_entretien',placeholder='Si connu')
                st.caption('Caractéristiques conservées dans le dossier ; aucun classement fiscal n’est déduit automatiquement de ces descriptions.')
            st.button('Supprimer cette dépendance', key=cle+'_supprimer', on_click=supprimer_dependance, args=(ligne['id'],etat))
    return [dict(r) for r in st.session_state[etat]]
