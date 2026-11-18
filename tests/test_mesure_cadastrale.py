import unittest
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from mesure_cadastrale import GEODE, surface_dessinee


def rectangle(x=4.84, y=45.75):
    est, _, _ = GEODE.fwd(x, y, 90, 10)
    _, nord, _ = GEODE.fwd(x, y, 0, 10)
    return {'type': 'Feature', 'geometry': {'type': 'Polygon',
            'coordinates': [[(x, y), (est, y), (est, nord), (x, nord), (x, y)]]}}


class MesureCadastraleTests(unittest.TestCase):
    def test_surface_metrique_et_chevauchement(self):
        contour = rectangle()
        self.assertAlmostEqual(surface_dessinee([contour]), 100, delta=0.05)
        self.assertEqual(surface_dessinee([contour, contour]), surface_dessinee([contour]))
        self.assertAlmostEqual(surface_dessinee([contour, rectangle(x=4.85)]), 200, delta=0.10)
        self.assertEqual(surface_dessinee([]), 0)

    def test_report_automatique_du_total_ventile_et_du_parking(self):
        parcelle = {'geometry': rectangle()['geometry'], 'insee': '69387', 'section': 'AB', 'numero': '0123', 'prefixe': '000'}
        app = AppTest.from_file(str(Path(__file__).resolve().parents[1] / 'parcours_express.py'))
        with patch('saisie_adresse.saisir_adresse', return_value=('12 rue Test', {'libelle': '12 rue Test'})), \
             patch('mesure_cadastrale.parcelles_a_l_adresse', return_value=[parcelle]), \
             patch('mesure_cadastrale.carte_mesure', side_effect=lambda _, cle: 100 if cle.endswith('_local') else 45):
            app.run()
            next(b for b in app.button if b.label == 'Charger la carte du bien').click().run()
            self.assertFalse(app.exception, [x.value for x in app.exception])
            next(n for n in app.number_input if n.label.startswith('Nombre de niveaux occupés')).set_value(3).run()
            self.assertIn('300 m²', [m.value for m in app.metric])
            next(n for n in app.number_input if n.label.startswith('Part du total')).set_value(240.0).run()
            next(b for b in app.button if b.label == 'Reporter P1 et P2 dans l’estimation').click().run()
            next(b for b in app.button if b.label == 'Reporter dans PK2').click().run()
            self.assertFalse(app.exception, [x.value for x in app.exception])
            attendus = {'P1 · Principale': 240, 'P2 · Secondaire couverte': 60,
                        'PK2 · Stationnement non couvert': 45}
            for libelle, valeur in attendus.items():
                self.assertEqual(next(n.value for n in app.number_input if n.label == libelle), valeur)
