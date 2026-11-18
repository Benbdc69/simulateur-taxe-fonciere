import unittest

from montants import euro_arrondi


class MontantsTests(unittest.TestCase):
    def test_seuil_arrondi_a_euro_superieur(self):
        for montant, affiche in [(1234.49, '1 234 €'), (1234.50, '1 235 €'),
                                 (1234.51, '1 235 €'), (0, '0 €')]:
            with self.subTest(montant=montant):
                self.assertEqual(euro_arrondi(montant), affiche)
