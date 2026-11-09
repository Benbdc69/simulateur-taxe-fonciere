"""Cadre 5 H2 : ajout et suppression de lignes sans perdre les autres saisies."""
import streamlit as st
from dependances_habitation import TYPES, MODES
from session_calcul import cle_calcul


def ajouter_dependance():
    numero = st.session_state.get('hab_dependance_numero', 0) + 1
    st.session_state['hab_dependance_numero'] = numero
    st.session_state['hab_dependances'].append({'id': numero})


def supprimer_dependance(identifiant):
    st.session_state['hab_dependances'] = [r for r in st.session_state['hab_dependances'] if r['id'] != identifiant]


def saisir_dependances(valeurs, annee):
    if 'hab_dependances' not in st.session_state:
        lignes = [dict(r, id=i) for i, r in enumerate(valeurs or [], 1)]
        st.session_state['hab_dependances'] = lignes
        st.session_state['hab_dependance_numero'] = len(lignes)
    st.markdown('#### 5 · Éléments bâtis formant dépendances — H2')
    st.caption('Ajoutez une ligne par élément. Ne reportez pas ces surfaces dans celles des pièces du logement. Le mode de traitement est à choisir pour chaque ligne, d’après le dossier cadastral.')
    st.button('＋ Ajouter une dépendance', key=cle_calcul('ajouter_dependance'), on_click=ajouter_dependance)
    for i, ligne in enumerate(st.session_state['hab_dependances'], 1):
        cle = cle_calcul(f"dependance_{ligne['id']}")
        with st.expander(f"Dépendance {i} · {ligne.get('designation') or 'à renseigner'}", expanded=True):
            types = list(TYPES)
            ligne['type'] = st.selectbox('Type de dépendance', types, index=types.index(ligne.get('type', 'garage')), format_func=TYPES.get, key=cle+'_type')
            ligne['designation'] = st.text_input('Désignation de l’élément', value=ligne.get('designation', ''), key=cle+'_designation', placeholder='Garage, cave, chambre de service…')
            a,b = st.columns(2)
            with a:
                ligne['lot'] = st.text_input('Numéro de lot (facultatif)', value=ligne.get('lot', ''), key=cle+'_lot')
                ligne['surface'] = st.number_input('Surface de la dépendance (m²)', min_value=0., value=float(ligne.get('surface', 0)), key=cle+'_surface')
            with b:
                ligne['situation'] = st.text_input('Situation dans la propriété', value=ligne.get('situation', ''), key=cle+'_situation', placeholder='Sous-sol, cour, bâtiment B…')
                modes = [None]+list(MODES)
                ligne['mode'] = st.selectbox('Traitement fiscal de cette dépendance', modes, index=modes.index(ligne.get('mode')), format_func=lambda v: MODES.get(v, 'Choisissez le traitement'), key=cle+'_mode', help='Un garage peut avoir sa propre évaluation. Vérifiez le rattachement sur la fiche cadastrale ; aucune dépendance n’est automatiquement incorporée.')
            if ligne['mode'] == 'incorporee':
                ligne['coefficient'] = st.number_input('Coefficient de pondération', min_value=.2, max_value=.6, value=float(ligne.get('coefficient', .4)), step=.05, key=cle+'_coefficient', help='Reprenez le coefficient de la fiche cadastrale. La valeur initiale 0,4 est une hypothèse à confirmer.')
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
            st.button('Supprimer cette dépendance', key=cle+'_supprimer', on_click=supprimer_dependance, args=(ligne['id'],))
    return [dict(r) for r in st.session_state['hab_dependances']]
