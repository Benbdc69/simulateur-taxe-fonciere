"""Vérifie les champs des modèles officiels exportés, y compris après édition."""
from io import BytesIO
from pathlib import Path
import unittest
from unittest.mock import patch

from pypdf import PdfReader, PdfWriter
from streamlit.testing.v1 import AppTest

from export_cerfa import creer_cerfa

RACINE = Path(__file__).resolve().parents[1]
ADRESSE = {'libelle': '12 rue Victor Hugo, Lyon', 'voie': 'rue Victor Hugo',
           'numero_voirie': '12', 'commune': 'Lyon', 'insee': '69387'}
SITUATION = {'adresse': ADRESSE, 'annee': 2026, 'categorie': '5', 'surface': 92.8,
             'parametres': {'terrasse': 12.9, 'eau': True, 'lavabos': 2, 'entretien': 'Assez bon'}}


class ExportCerfaTests(unittest.TestCase):
    def verifier_champs(self, pdf, attendus):
        champs = pdf.get_fields()
        for nom, valeur in attendus.items():
            with self.subTest(champ=nom):
                self.assertEqual(champs[nom].get('/V'), valeur)

    def test_h1_prefill_et_renseignements_proprietaire_editables(self):
        saisie = {
            **SITUATION, 'h1': {'pieces': {'reception': 1, 'chambres': 3}, 'annee_construction': 1990,
                               'materiaux_murs': ['Pierre', 'Béton'], 'emprises': {'maison': 75.2}},
            'dependances': [{'type': 'batiment_h1', 'composition': {'garages': {'surface': 20.3}},
                             'materiaux_murs': ['Béton', 'Bois'], 'electricite': True}],
        }
        pdf = PdfReader(BytesIO(creer_cerfa('h1', saisie)))
        self.assertEqual(len(pdf.pages), 4)
        self.verifier_champs(pdf, {
            'a1': '69', 'a2': 'Lyon 7ème', 'a3': 'rue Victor Hugo', 'a4': '12',
            'b1': '1', 'b2': '3', 'b7': '92', 'b11': '12', 'b15': '2', 'b16': '1990',
            'b18': '20', 'b40': '75', 'cac2': '/Oui', 'cac7': '/Oui', 'cac9': '/Oui',
            'cac19': '/2', 'cac26': '/Oui', 'ldcm1': '3 6',
        })
        self.assertIsNone(pdf.get_fields()['a7'].get('/V'))
        writer = PdfWriter(clone_from=pdf)
        writer.update_page_form_field_values(writer.pages[0], {'a7': 'DUPONT'}, auto_regenerate=False)
        flux = BytesIO()
        writer.write(flux)
        self.verifier_champs(PdfReader(flux), {'a7': 'DUPONT', 'b7': '92'})

    def test_h2_dependances_annexe_et_coefficient_administratif_non_editable(self):
        cave = {'type': 'cave', 'designation': 'Cœur d’été', 'lot': 'C', 'surface': 6.8}
        saisie = {
            **SITUATION, 'h2': {'pieces': {'chambres': 2}, 'chauffage': True,
                               'partie_professionnelle': True, 'declaration_6660': False},
            'dependances': [{'type': 'piece', 'designation': 'Chambre de service', 'lot': '2',
                             'batiment': 'B', 'etage_description': '3', 'surface': 12.6,
                             'eau': True, 'wc': 1, 'pieces_chauffees': 1}, *([cave] * 5)],
        }
        pdf = PdfReader(BytesIO(creer_cerfa('h2', saisie)))
        self.assertEqual(len(pdf.pages), 5)
        self.verifier_champs(pdf, {
            'b6': '2', 'b11': '92', 'b12': '12', 'cac5': '/a', 'cac0': '/2',
            'b16': '2', 'b17': 'Chambre de service', 'b18': 'B', 'b19': '3', 'b20': '12',
            'cacb1': '/Oui', 'b21': '1', 'cacb27': '/Oui', 'b59': 'Cœur d’été',
        })
        self.assertNotIn('b13', pdf.get_fields())
        self.assertIn('Cœur d’été', pdf.get_fields()['annexe_dependance_1']['/V'])
        for ref in pdf.pages[1]['/Annots']:
            self.assertNotEqual(ref.get('/T'), 'b13')

    def test_6660_categorie_page_3_surfaces_et_origine_independante(self):
        saisie = {
            'bien': {'code_insee': '69387', 'section': 'AB', 'numero': '0123', 'prefixe': '000'},
            'adresse_declaree': ADRESSE, 'categorie': 'SPE1', 'construction_nouvelle': True,
            'annee_achevement': 2025, 'surfaces': {'P1': 80.9, 'P2': 10, 'P3': 0, 'PK1': 12.7, 'PK2': 4},
        }
        pdf = PdfReader(BytesIO(creer_cerfa('6660-rev', saisie)))
        self.assertEqual(len(pdf.pages), 4)
        self.verifier_champs(pdf, {
            'a1': '69', 'a3': '12', 'a4': 'rue Victor Hugo', 'a9': '000 AB 0123',
            'a18': '    2025', 'construction_neuve': '/1', 'cac6': '/24',
            'd1': '80', 'd2': '10', 'd3': '0', 'd4': '12', 'd5': '4',
        })
        champs = pdf.get_fields()
        self.assertIsNone(champs['modification_local'].get('/V'))
        self.assertIsNone(champs['a26'].get('/V'))
        self.assertIsNone(champs['d17'].get('/V'))
        self.assertNotIn('/Names', pdf.root_object)
        self.assertEqual([ref['/AS'] for ref in pdf.pages[2]['/Annots']
                          if ref.get('/AS') and ref['/AS'] != '/Off'], ['/24'])

    def test_pas_de_declaration_avant_estimation_habitation(self):
        for nature, modele in (('M', 'H1'), ('A', 'H2')):
            with self.subTest(nature=nature):
                app = AppTest.from_file(str(RACINE / 'parcours_habitation.py'))
                app.session_state['hab_etape'] = 3
                description = {'pieces': {}, 'materiaux_murs': [], 'materiaux_toitures': []} if nature == 'M' else {
                    'pieces': {}, 'chauffage': False, 'escalier_service': False,
                }
                app.session_state['hab_saisie'] = {
                    **SITUATION, 'nature': nature, modele.lower(): description,
                    'parametres': {**SITUATION['parametres'], 'annexes': 0, 'situation_generale': 'Ordinaire',
                                   'situation_particuliere': 'Ordinaire'},
                }
                app.run()
                self.assertFalse(app.exception, [x.value for x in app.exception])
                self.assertFalse(app.get('download_button'))
                self.assertNotIn(f'Télécharger le {modele}', [bouton.label for bouton in app.button])

    def test_complements_saisis_en_interface_et_exportes(self):
        professionnel = {'bien': {'code_insee': '69387'}, 'adresse': ADRESSE['libelle'],
                         'adresse_declaree': ADRESSE, 'categorie': 'BUR2', 'surfaces': {'P1': 80}}
        cas = (
            ('h1', SITUATION, 'Nom de naissance ou dénomination sociale', 'a7'),
            ('h2', SITUATION, 'Nom de naissance ou dénomination sociale', 'a9'),
            ('6660-rev', professionnel, 'Nom', 'a26'),
        )
        for modele, dossier, libelle_nom, champ_nom in cas:
            with self.subTest(modele=modele):
                app = AppTest.from_string(
                    'import streamlit as st\n'
                    'from saisie_declaration import afficher_declaration, completer_declaration\n'
                    'if st.session_state.get("dialogue_ouvert"):\n'
                    '    completer_declaration(st.session_state.modele, st.session_state.dossier)\n'
                    'else:\n'
                    '    afficher_declaration(st.session_state.modele, st.session_state.dossier)\n'
                )
                app.session_state['modele'] = modele
                app.session_state['dossier'] = dossier
                app.run()
                self.assertFalse(app.exception)
                self.assertFalse(app.get('download_button'))
                next(w for w in app.button if w.label == f'Télécharger le {modele.upper()}').click().run()
                self.assertTrue(app.get('download_button'))
                # AppTest relance le script complet lors de la soumission.
                app.session_state['dialogue_ouvert'] = True
                next(w for w in app.text_input if w.label == libelle_nom).input('DUPONT')
                if modele == 'h1':
                    next(w for w in app.checkbox if w.label == 'Pierre').check()
                    next(w for w in app.checkbox if w.label == 'Tuiles').check()
                with patch('saisie_declaration.creer_cerfa', wraps=creer_cerfa) as exporter:
                    next(w for w in app.button if w.label == 'Enregistrer les compléments').click().run()
                self.assertFalse(app.exception)
                self.assertTrue(app.success)
                complements = exporter.call_args.args[2]
                pdf = PdfReader(BytesIO(creer_cerfa(modele, dossier, complements)))
                self.verifier_champs(pdf, {champ_nom: 'DUPONT', 'a2': 'Lyon 7ème'})
                if modele == 'h1':
                    self.verifier_champs(pdf, {'cac7': '/Oui', 'cac14': '/Oui'})
                self.assertEqual([bouton.proto.label for bouton in app.get('download_button')],
                                 [f'Télécharger le {modele.upper()} prérempli'])
