import unittest

from frais_gestion import estimer_frais


class FraisGestionTests(unittest.TestCase):
    def test_frais_par_cotisation_et_total(self):
        montants = {'commune': 200, 'epci': 50, 'gemapi': 10, 'syndicat': 30,
                    'teom': 100, 'taxes_speciales': 0}
        frais = estimer_frais(montants, 2026)
        self.assertEqual(frais['frais'], 18.2)
        self.assertEqual(frais['total'], 408.2)
        self.assertEqual(frais['lignes']['syndicat'], {'taux': 8, 'montant': 2.4})
        self.assertEqual(estimer_frais(montants, 2026, True)['total'], 403.2)

    def test_taxe_speciale_positive_empeche_le_total_complet(self):
        frais = estimer_frais({'commune': 100, 'taxes_speciales': 1}, 2025)
        self.assertEqual(frais['frais'], 3)
        self.assertIsNone(frais['total'])
        self.assertTrue(frais['note'])

    def test_annees_hors_bareme(self):
        for annee in (2022, 2027):
            self.assertIsNone(estimer_frais({'commune': 100}, annee))
