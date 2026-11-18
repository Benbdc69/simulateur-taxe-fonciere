from io import BytesIO
import unittest
from unittest.mock import patch

from openpyxl import Workbook
from streamlit.testing.v1 import AppTest

from saisie_cfe import taux_cfe_public
from neutralisation_cfe import lire_neutralisation_cfe
from taux_composantes import lire_tableur_dgcl


class CfeTests(unittest.TestCase):
    def test_taux_cfe_isole_de_la_taxe_fonciere(self):
        wb = Workbook()
        ws = wb.active
        ws.append(['Code INSEE', 'Taux TFPB 2026', 'Base CFE', 'Taux CFE 2025', 'Taux CFE 2026'])
        ws.append(['42005', 30, 1000, 24, 0.25])
        ws['E2'].number_format = '0.00%'
        fichier = BytesIO()
        wb.save(fichier)
        self.assertEqual(lire_tableur_dgcl(fichier.getvalue(), 'communes', 2026, taxe='CFE')['taux'],
                         {'42005': 25})
        self.assertEqual(lire_tableur_dgcl(fichier.getvalue(), 'communes', 2026)['taux'], {'42005': 30})

    def test_conserve_uniquement_le_taux_public_disponible(self):
        with patch('saisie_cfe.rechercher_dgcl', return_value={'taux': {'epci': 25}}):
            self.assertEqual(taux_cfe_public('42005', 2026), {'epci': 25})

    def test_estime_avec_deux_bases_net_cfe_et_taux_publics(self):
        app = AppTest.from_string("from saisie_cfe import afficher_cfe\nafficher_cfe('42005', 2026)").run()
        self.assertEqual(app.metric[0].value, 'À compléter')
        with patch('saisie_cfe.taux_cfe_public', return_value={'commune': 5, 'epci': 20}):
            next(b for b in app.button if b.label.startswith('Rechercher les taux')).click().run()
        self.assertFalse(app.exception)
        self.assertEqual(app.metric[0].value, 'À compléter')
        app.radio[0].set_value('Reprendre les bases de l’avis').run()
        app.checkbox[0].check().run()
        app.number_input[0].set_value(1000.0)
        app.number_input[1].set_value(1500.0).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.metric[0].value, '350 €')

    def test_valeur_locative_brute_sans_abattement_et_neutralisations_distinctes(self):
        app = AppTest.from_string("from saisie_cfe import afficher_cfe\nafficher_cfe('42005', 2026, 5000)").run()
        app.checkbox[0].check().run()
        champs = {champ.label: champ for champ in app.number_input}
        champs['Coefficient de neutralisation CFE · commune'].set_value(0.8)
        champs['Coefficient de neutralisation CFE · intercommunalité'].set_value(0.9)
        champs['Taux CFE · commune (%)'].set_value(5.0)
        champs['Taux CFE · intercommunalité (%)'].set_value(20.0).run()
        self.assertFalse(app.exception)
        self.assertEqual(app.metric[0].value, '1 100 €')

    def test_neutralisation_cfe_distincte_de_la_tfpb(self):
        wb = Workbook()
        ws = wb.active
        ws.append(['Code INSEE', 'Coefficient de neutralisation TFPB commune',
                   'Coefficient de neutralisation CFE commune', 'Coefficient de neutralisation CFE EPCI'])
        ws.append(['42005', 0.5, 0.8, 0.9])
        ws.append(['42006', 0.6, 0.7, 0.85])
        f = BytesIO()
        wb.save(f)
        self.assertEqual(lire_neutralisation_cfe(f.getvalue(), 'test.xlsx', '42005'),
                         {'commune': 0.8, 'epci': 0.9})
