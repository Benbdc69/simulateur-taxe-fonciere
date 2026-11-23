"""Régressions du rapport client et de son téléchargement."""

from decimal import Decimal
from io import BytesIO
import unittest

from docx import Document
from streamlit.testing.v1 import AppTest

from preaudit_word import bilan_preaudit, creer_word_preaudit


EVALUATION = {
    'adresse': 'Adresse de test', 'annee': 2026, 'categorie': 'BUR2',
    'bien': {'section': 'AB', 'numero': '0001', 'code_insee': '69123'},
    'surfaces': {'P1': 150.0, 'P2': 30.0}, 'mesures': {'surface_batie': 181.0},
    'analyse': {'result': {'total_hors_frais': 1750.0}, 'partial': {'tarif': 245, 'secteur': 2}},
    'frais': {'total': 1850.0, 'frais': 100.0},
}
AUDIT = {'ventilation': 'documentee', 'montant_avis': 2000.0, 'observation': 'Vérifier les surfaces.'}


class PreauditWordTests(unittest.TestCase):
    def test_word_restitue_les_montants_et_la_surface(self):
        self.assertEqual(bilan_preaudit(EVALUATION, AUDIT)['ecart'], Decimal('150'))
        word = Document(BytesIO(creer_word_preaudit(EVALUATION, AUDIT)))
        self.assertEqual(word.tables[0].rows[-1].cells[1].text, '150 €')
        audit = {**AUDIT, 'ventilation': 'inconnue', 'surface_batie': 181.0}
        word = Document(BytesIO(creer_word_preaudit(EVALUATION, audit)))
        self.assertEqual(word.tables[0].rows[-1].cells[1].text, '—')
        self.assertIn('Surface bâtie mesurée · 181,00 m².', [p.text for p in word.paragraphs])
        self.assertIsNone(bilan_preaudit({**EVALUATION, 'frais': None}, AUDIT)['ecart'])
        arrondi = bilan_preaudit({**EVALUATION, 'frais': {'total': 1850.50}},
                                 {**AUDIT, 'montant_avis': 2000.49})
        self.assertEqual(arrondi['ecart'], Decimal('149'))

    def test_cadre_fiscal_adapte_au_local(self):
        def contenu(evaluation):
            word = Document(BytesIO(creer_word_preaudit(evaluation, AUDIT)))
            return '\n'.join(p.text for p in word.paragraphs)

        courant = contenu(EVALUATION)
        for reference in ('Cadre fiscal', 'art. 1498, II', 'art. 324 Z', 'art. 1388'):
            self.assertIn(reference, courant)
        self.assertNotIn('art. 1518 A quinquies', courant)
        self.assertIn('art. 1518 A quinquies', contenu({**EVALUATION, 'historique': 'ancien'}))
        exceptionnel = contenu({**EVALUATION, 'categorie': 'EXC1'})
        self.assertIn('article 1498, III', exceptionnel)
        self.assertNotIn('art. 1498, II)', exceptionnel)

    def test_telechargement_word_depuis_la_fenetre(self):
        at = AppTest.from_string(
            'from saisie_preaudit import actions_preaudit\n'
            f'actions_preaudit({EVALUATION!r})'
        ).run()
        self.assertEqual([bouton.label for bouton in at.button], ['Préparer le pré-audit Word'])
        at.button[0].click().run()
        self.assertFalse(at.exception)
        self.assertEqual(len(at.get('dialog')), 1)
        self.assertEqual(next(x for x in at.number_input if x.label.startswith('Surface bâtie')).value, 181)
        self.assertTrue(any(x.proto.label == 'Télécharger le pré-audit Word' for x in at.get('download_button')))


if __name__ == '__main__':
    unittest.main()
