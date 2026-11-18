from io import BytesIO
import unittest
from unittest.mock import patch

from openpyxl import Workbook
from streamlit.testing.v1 import AppTest

from saisie_cfe import taux_cfe_public
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

    def test_refuse_un_taux_public_partiel(self):
        with patch('saisie_cfe.rechercher_dgcl', return_value={'taux': {'epci': 25}}):
            with self.assertRaises(ValueError):
                taux_cfe_public('42005', 2026)

    def test_estime_avec_deux_bases_net_cfe_et_taux_publics(self):
        app = AppTest.from_string("from saisie_cfe import afficher_cfe\nafficher_cfe('42005', 2026)").run()
        self.assertEqual(app.metric[0].value, 'À compléter')
        with patch('saisie_cfe.taux_cfe_public', return_value={'commune': 5, 'epci': 20}):
            app.button[0].click().run()
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
