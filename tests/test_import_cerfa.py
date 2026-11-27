"""Contrôle l'import des trois PDF avec les champs réels des modèles Cerfa."""
from io import BytesIO
import unittest

from pypdf import PdfWriter
from reportlab.pdfgen.canvas import Canvas

from export_cerfa import MODELES, creer_cerfa
from import_cerfa import lire_cerfa


ADRESSE = {'libelle': '12 rue Victor Hugo, Lyon', 'voie': 'rue Victor Hugo',
           'numero_voirie': '12', 'commune': 'Lyon', 'insee': '69382'}


class ImportCerfaTests(unittest.TestCase):
    def test_h1_recupere_pieces_confort_entretien_et_dependances(self):
        donnees = dict(
            adresse=ADRESSE, surface=92.8,
            h1={'pieces': {'reception': 1, 'chambres': 3}, 'annee_construction': 1990, 'chauffage': True},
            parametres={'eau': True, 'lavabos': 2, 'entretien': 'Assez bon', 'elements_incorpores': {
                'caves': {'surface': 9.3}}},
            dependances=[{'type': 'batiment_h1', 'composition': {'garages': {'surface': 20.3}},
                          'materiaux_murs': ['Bois'], 'electricite': True}],
        )
        modele, saisie, alertes = lire_cerfa(creer_cerfa('h1', donnees, {'a7': 'Nom du propriétaire'}))
        self.assertEqual(modele, 'h1')
        self.assertEqual(alertes, [])
        self.assertEqual(saisie['recherche'], '12 rue Victor Hugo, Lyon 2ème')
        self.assertEqual(saisie['surface'], 92)
        self.assertNotIn('categorie', saisie)
        self.assertNotIn('Nom du propriétaire', repr(saisie))
        self.assertEqual(saisie['h1']['pieces']['chambres'], 3)
        self.assertTrue(saisie['h1']['chauffage'])
        self.assertEqual(saisie['parametres']['entretien'], 'Assez bon')
        self.assertEqual(saisie['parametres']['lavabos'], 2)
        self.assertEqual(saisie['parametres']['elements_incorpores']['caves']['surface'], 9)
        self.assertEqual(saisie['dependances_h1'][0]['surface'], 20)
        self.assertEqual(saisie['dependances_h1'][0]['materiaux_murs'], ['Bois'])
        self.assertNotIn('mode', saisie['dependances_h1'][0])

    def test_h2_recupere_etage_ascenseur_et_rubriques_de_dependances(self):
        donnees = dict(
            adresse=ADRESSE, surface=45, h2={'pieces': {'chambres': 2}, 'chauffage': True},
            parametres={'terrasse': 10, 'ascenseur': True, 'douches': 1},
            dependances=[{'type': 'cave', 'designation': 'Cave', 'surface': 8, 'lot': '15'},
                         {'type': 'piece', 'surface': 9, 'wc': 1, 'pieces_chauffees': 1}],
        )
        modele, saisie, alertes = lire_cerfa(creer_cerfa('h2', donnees, {'a7': '2e'}))
        self.assertEqual(modele, 'h2')
        self.assertEqual(alertes, [])
        self.assertEqual(saisie['parametres']['etage'], 2)
        self.assertTrue(saisie['parametres']['ascenseur'])
        self.assertEqual(saisie['parametres']['terrasse'], 10)
        self.assertEqual(saisie['parametres']['douches'], 1)
        piece, cave = saisie['dependances']
        self.assertEqual((piece['wc'], piece['pieces_chauffees']), (1, 1))
        self.assertEqual((cave['type'], cave['surface'], cave['lot']), ('cave', 8, '15'))
        self.assertNotIn('coefficient', cave)

    def test_6660_origine_et_categorie_lues_sur_le_modele_officiel(self):
        pdf = PdfWriter(clone_from=MODELES / '6660-rev.pdf')
        pdf.update_page_form_field_values(pdf.pages[0], {
            'a1': '69', 'a2': 'Lyon 2ème', 'a3': '12', 'a4': 'rue Victor Hugo', 'a9': '000 AB 0123',
            'a18': '03022025', 'cac': '/1',
        }, auto_regenerate=False)
        pdf.update_page_form_field_values(pdf.pages[2], {'cac6': '/24'}, auto_regenerate=False)
        pdf.update_page_form_field_values(pdf.pages[3], {'d1': '1\u202f600,5', 'd5': '22'}, auto_regenerate=False)
        flux = BytesIO()
        pdf.write(flux)
        modele, saisie, alertes = lire_cerfa(flux.getvalue())
        self.assertEqual(modele, '6660-rev')
        self.assertEqual(alertes, [])
        self.assertEqual(saisie['categorie'], 'SPE1')
        self.assertEqual(saisie['surfaces']['P1'], 1600.5)
        self.assertEqual(saisie['surfaces']['PK2'], 22)
        self.assertEqual(saisie['reference']['numero'], '0123')
        self.assertTrue(saisie['construction_nouvelle'])
        self.assertEqual(saisie['annee_achevement'], 2025)
        self.assertNotIn('annee', saisie)
        self.assertNotIn('historique', saisie)

    def test_pdf_vierge_aplati_ou_invalide(self):
        with self.assertRaisesRegex(ValueError, 'Aucune donnée de simulation'):
            lire_cerfa((MODELES / 'h1.pdf').read_bytes())
        flux = BytesIO()
        pdf = Canvas(flux)
        pdf.drawString(10, 10, 'Cerfa sans champ interactif')
        pdf.save()
        with self.assertRaisesRegex(ValueError, 'aucun champ de formulaire'):
            lire_cerfa(flux.getvalue())
        with self.assertRaisesRegex(ValueError, 'illisible'):
            lire_cerfa(b'PDF incorrect')
