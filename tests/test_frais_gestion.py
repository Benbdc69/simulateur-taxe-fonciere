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

    def test_taxe_speciale_positive_incluse_selon_le_beneficiaire(self):
        frais = estimer_frais({'commune': 100, 'taxes_speciales': 1}, 2025)
        self.assertEqual(frais['frais'], 3.09)
        self.assertEqual(frais['total'], 104.09)
        self.assertIn('9 %', frais['note'])
        alternatif = estimer_frais({'commune': 100, 'taxes_speciales': 1}, 2025, taux_taxes_speciales=8)
        self.assertEqual(alternatif['total'], 104.08)

    def test_annees_hors_bareme(self):
        for annee in (2022, 2027):
            self.assertIsNone(estimer_frais({'commune': 100}, annee))
