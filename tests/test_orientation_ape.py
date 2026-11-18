import unittest
from pathlib import Path

from streamlit.testing.v1 import AppTest

from orientation_ape import categories_suggerees


class OrientationApeTests(unittest.TestCase):
    def test_code_precis_avant_la_division_et_formats(self):
        self.assertEqual(categories_suggerees(' 47.30z '), ('MAG6',))
        self.assertEqual(categories_suggerees('4730Z'), ('MAG6',))
        self.assertIn('MAG4', categories_suggerees('47.11D'))
        self.assertEqual(categories_suggerees('68.20B'), ())
        with self.assertRaises(ValueError):
            categories_suggerees('47')

    def test_pistes_en_tete_et_choix_explicitement_conserve(self):
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'parcours_express.py')).run()
        ape = next(w for w in app.text_input if w.label.startswith('Code APE'))
        ape.set_value('47.30Z').run()
        categorie = next(w for w in app.selectbox if w.label == 'Catégorie du local')
        self.assertTrue(categorie.options[0].startswith('MAG6'))
        self.assertIsNone(categorie.value)
        self.assertTrue(any(option.startswith('BUR2') for option in categorie.options))
        categorie.select('BUR2').run()
        next(w for w in app.text_input if w.label.startswith('Code APE')).set_value('55.10Z').run()
        self.assertFalse(app.exception)
        categorie = next(w for w in app.selectbox if w.label == 'Catégorie du local')
        self.assertEqual(categorie.value, 'BUR2')
        self.assertTrue(categorie.options[0].startswith('HOT1'))
