"""Régressions du pré-audit Word, des versions et du contrôle d’accès aux dossiers."""

from decimal import Decimal
from io import BytesIO
import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import patch

from docx import Document
from streamlit.testing.v1 import AppTest

from preaudit_word import bilan_preaudit, creer_word_preaudit
from securite import generer_empreinte
from stockage_dossiers import StockageDossiers


ROOT = Path(__file__).resolve().parents[1]


class DossiersClientsTests(unittest.TestCase):
    def setUp(self):
        dossier = TemporaryDirectory()
        self.addCleanup(dossier.cleanup)
        self.chemin_base = str(Path(dossier.name) / 'test.sqlite3')
        self.base = StockageDossiers(sqlite=self.chemin_base)
        self.base.initialiser()
        self.evaluation = {
            'adresse': 'Adresse de test', 'annee': 2026, 'categorie': 'BUR2',
            'bien': {'section': 'AB', 'numero': '0001', 'code_insee': '69123'},
            'surfaces': {'P1': 150.0, 'P2': 30.0}, 'mesures': {'surface_batie': 181.0},
            'analyse': {'result': {'total_hors_frais': 1750.0}, 'partial': {'tarif': 245, 'secteur': 2}},
            'frais': {'total': 1850.0, 'frais': 100.0},
        }
        self.audit = {'ventilation': 'documentee', 'montant_avis': 2000.0, 'observation': 'Vérifier les surfaces.'}

    def test_fige_chaque_version_du_calcul(self):
        ancien = self.base.enregistrer('SCI de test', self.evaluation, self.audit, 'camille')
        self.assertEqual(ancien, self.base.enregistrer(' sci DE test ', self.evaluation, self.audit, 'camille'))
        self.evaluation['analyse']['partial']['tarif'] = 300
        nouveau = self.base.enregistrer('SCI de test', self.evaluation, self.audit, 'camille')
        self.assertNotEqual(ancien, nouveau)
        relu = StockageDossiers(sqlite=self.chemin_base)
        self.assertEqual(len(relu.evaluations('sci de test')), 2)
        self.assertEqual(relu.lire('sci de test', ancien)['evaluation']['analyse']['partial']['tarif'], 245)
        self.assertIsNone(relu.lire('autre société', ancien))
        with self.assertRaises(ValueError):
            self.base.modifier_lien('sci de test', 'javascript:alert(1)')

    def test_word_restitue_les_donnees_et_reste_prudent_sans_ventilation(self):
        self.assertEqual(bilan_preaudit(self.evaluation, self.audit)['ecart'], Decimal('150.0'))
        word = Document(BytesIO(creer_word_preaudit(self.evaluation, self.audit, societe='SCI de test')))
        self.assertIn('SCI de test', '\n'.join(p.text for p in word.paragraphs))
        self.assertEqual(word.tables[0].rows[-1].cells[1].text, '150 €')
        autre_audit = {**self.audit, 'ventilation': 'inconnue', 'surface_batie': 181.0}
        self.assertIsNone(bilan_preaudit(self.evaluation, autre_audit)['ecart'])
        word = Document(BytesIO(creer_word_preaudit(self.evaluation, autre_audit)))
        self.assertEqual(word.tables[0].rows[-1].cells[1].text, '—')
        self.assertIn('Surface bâtie mesurée · 181,00 m².', [p.text for p in word.paragraphs])
        self.assertIsNone(bilan_preaudit({**self.evaluation, 'frais': None}, self.audit)['ecart'])
        valeur_arrondie = bilan_preaudit({**self.evaluation, 'frais': {'total': 1850.50}},
                                        {**self.audit, 'montant_avis': 2000.49})
        self.assertEqual(valeur_arrondie['ecart'], Decimal('149'))

    def test_consultation_exige_un_compte_et_respecte_le_role_lecture(self):
        self.base.enregistrer('SCI de test', self.evaluation, self.audit, 'camille')
        mot_de_passe = 'mot de passe de test'
        comptes = {'alex': {'role': 'lecture', 'mot_de_passe_hash': generer_empreinte(mot_de_passe)}}
        with (
            patch.dict(os.environ, {'TF_LOCAL_MODE': '1', 'TF_DOSSIERS_SQLITE_PATH': self.chemin_base}),
            patch('acces_dossiers._comptes', return_value=comptes),
        ):
            at = AppTest.from_file(str(ROOT / 'dossiers_clients.py')).run()
            self.assertFalse(at.selectbox)
            at.text_input[0].input('alex')
            at.text_input[1].input(mot_de_passe)
            next(b for b in at.button if b.label == 'Accéder aux dossiers').click().run()
            self.assertFalse(at.exception)
            self.assertIn('SCI de test', at.selectbox[0].options)
            self.assertTrue(at.get('download_button'))
            self.assertFalse(any(e.label == 'Modifier le lien documentaire' for e in at.expander))

    def test_enregistrement_depuis_la_fenetre_preaudit(self):
        with (
            patch.dict(os.environ, {'TF_LOCAL_MODE': '1', 'TF_DOSSIERS_SQLITE_PATH': self.chemin_base}),
            patch('acces_dossiers._comptes', return_value={'camille': {'role': 'edition'}}),
        ):
            at = AppTest.from_string(
                'from saisie_preaudit import completer_preaudit\n'
                f'completer_preaudit({self.evaluation!r}, enregistrer=True)'
            )
            at.session_state['_dossiers_identite'] = 'camille'
            at.run()
            self.assertFalse(at.exception)
            self.assertEqual(next(x for x in at.number_input if x.label.startswith('Surface bâtie')).value, 181)
            next(x for x in at.text_input if x.label == 'Nom de la société').input('SCI de test')
            next(b for b in at.button if b.label == 'Enregistrer l’évaluation').click().run()
            self.assertFalse(at.exception)
            self.assertTrue(at.success)
            identifiant = self.base.evaluations('sci de test')[0][0]
            fiche = self.base.lire('sci de test', identifiant)
            self.assertEqual(fiche['evaluation']['frais']['total'], 1850)
            self.assertEqual(fiche['audit']['surface_batie'], 181)


if __name__ == '__main__':
    unittest.main()
