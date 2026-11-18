"""Régressions du dossier habitation et des entrées numériques."""
from io import BytesIO
import sys
import unittest
from pathlib import Path
from pypdf import PdfReader
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from dossier_habitation import code_adresse, calculer_scenarios
from historique_taux import COMPOSANTES, enregistrer
from moteur_habitation import surface_totale, simulations_tarifs
from export_habitation_pdf import generer_pdf_habitation
from tarifs_habitation import SOURCE


class HabitationGuideeTests(unittest.TestCase):
    def setUp(self):
        self.adr = {'insee': '69123', 'code_postal': '69007', 'commune': 'Lyon', 'libelle': '18 cours Gambetta, 69007 Lyon'}
        self.saisie = {'annee': 2026, 'nature': 'A', 'categorie': '5', 'surface': 45., 'parametres': {}}
        self.rows = [dict(insee='69387', nature='A', categorie=c, serie=s, origine='387', tarif_1970=t, annee_tarif=2024)
                     for c, s, t in [('5', 'A', 10.), ('5', 'B', 12.), ('6', 'A', 8.)]]
        self.ref = {}
        for k in COMPOSANTES:
            enregistrer(self.ref, '69387', 2026, k, 30 if k == 'commune' else 0, 'Fixture avis', zonage_confirme=True)

    def calculer(self):
        return calculer_scenarios(self.saisie, self.adr, self.ref, self.rows)

    def test_lyon_arrondissement_conserve_depuis_adresse_confirmee(self):
        self.assertEqual(code_adresse(self.adr), '69387')
        self.assertEqual(code_adresse({**self.adr, 'insee': '69386'}), '69386')

    def test_formule_et_taux_nuls_documentes(self):
        r = self.calculer()
        self.assertEqual(len(r['tarifs']), 2)
        x = r['tarifs'][0]
        self.assertEqual(x['surfaces']['surface_ponderee'], 68)
        self.assertEqual(x['vl_1970'], 680)
        self.assertEqual(x['vl_annee'], round(680 * r['facteur']['coefficient_cumule'], 2))
        self.assertEqual(x['base_tf'], round(x['vl_annee'] * .5, 2))
        self.assertEqual(x['total'], round(x['base_tf'] * .30, 2))
        self.assertEqual(len(x['montants']), 6)

    def test_taux_absent_ne_devient_pas_zero(self):
        del self.ref['taux_annuels']['69123']['2026']['teom']
        r = self.calculer()
        self.assertFalse(r['taux_complets'])
        self.assertTrue(all('total' not in x for x in r['tarifs']))
        self.assertTrue(all('base_tf' in x for x in r['tarifs']))

    def test_categorie_obligatoire_et_series_limitees_a_la_categorie(self):
        self.saisie['categorie'] = None
        with self.assertRaisesRegex(ValueError, 'Choisissez une catégorie'):
            self.calculer()
        self.saisie['categorie'] = '5'
        r = self.calculer()
        self.assertEqual({x['categorie'] for x in r['tarifs']}, {'5'})
        self.assertEqual({x['serie'] for x in r['tarifs']}, {'A', 'B'})
        self.assertNotEqual(r['tarifs'][0]['total'], r['tarifs'][1]['total'])
        self.assertFalse(r['categorie_confirmee'])
        self.saisie['categorie_confirmee'] = True
        self.assertTrue(self.calculer()['categorie_confirmee'])

    def test_dependances_appartement_exclues_maison_ponderees(self):
        self.saisie['parametres'] = {'annexes': 20., 'terrasse': 10.}
        x = self.calculer()['tarifs'][0]
        self.assertTrue(x['surfaces']['dependances_a_evaluer_separement'])
        self.assertEqual(x['surfaces']['surface_ponderee'], 72)
        self.assertEqual(x['surfaces']['terrasse_ponderee'], 4)
        maison = surface_totale(45, 'M', '5', annexes=20, terrasse=10)
        self.assertEqual(maison['annexes_ponderees'], 8)
        self.assertEqual(maison['terrasse_ponderee'], 4)
        self.assertFalse(maison['dependances_a_evaluer_separement'])

    def test_pas_de_repli_sur_une_autre_categorie_ou_commune(self):
        self.saisie['categorie'] = '8'
        with self.assertRaisesRegex(ValueError, 'Aucun tarif'):
            self.calculer()
        self.saisie['categorie'] = '5'
        self.adr['insee'] = '69386'
        with self.assertRaisesRegex(ValueError, 'Aucun tarif'):
            self.calculer()

    def test_pdf_du_scenario_selectionne(self):
        r = self.calculer()
        x = r['tarifs'][-1]
        dossier = {**r, 'categorie': x['categorie'], 'surfaces': x['surfaces'],
                   'tarifs': [x], 'serie_selectionnee': 0, 'source_tarifs': SOURCE}
        pages = PdfReader(BytesIO(generer_pdf_habitation(dossier))).pages
        synthese = pages[0].extract_text()
        self.assertIn('Ne vaut pas avis d’imposition', synthese)
        self.assertIn(f"Série {x['serie']}", synthese)
        self.assertIn('Cotisations par composante', synthese)
        self.assertIn('Annexe — détail du calcul', pages[1].extract_text())

    def test_h2_nombre_chauffe_libre_sans_comptage_automatique(self):
        self.saisie['h2'] = {'pieces': {'reception': 1, 'chambres': 2, 'cuisines_moins_9': 1,
                                      'salles_eau': 1, 'autres_annexes': 1}, 'chauffage': True, 'pieces_chauffees': 3}
        self.saisie['parametres']['pieces_chauffees'] = 99
        r = self.calculer()
        self.assertEqual(len(r['tarifs']), 2)
        x = r['tarifs'][0]
        self.assertEqual(x['pieces_chauffage_scenario'], 3)
        self.assertEqual(x['surfaces']['detail_confort']['Pièces chauffées admissibles'], 6)
        self.assertEqual(x['surfaces']['surface_ponderee'], 74)
        self.saisie['h2']['pieces_chauffees'] = 1
        self.assertEqual(self.calculer()['tarifs'][0]['surfaces']['surface_ponderee'], 70)
        dossier = {**r, 'categorie': '5', 'surfaces': x['surfaces'], 'serie_selectionnee': 0, 'source_tarifs': SOURCE}
        self.assertTrue(generer_pdf_habitation(dossier).startswith(b'%PDF'))

    def test_h2_nombre_chauffe_non_deduit_si_manquant(self):
        for valeur in [None, -1, 1.5, float('nan')]:
            with self.subTest(valeur=valeur), self.assertRaises(ValueError):
                self.saisie['h2'] = {'pieces': {'chambres': 3}, 'chauffage': True, 'pieces_chauffees': valeur}
                self.calculer()

    def test_h2_sans_chauffage_aucune_equivalence_ajoutee(self):
        self.saisie['h2'] = {'pieces': {'reception': 1}, 'chauffage': False,
                             'escalier_service': True, 'partie_professionnelle': True}
        self.saisie['parametres']['pieces_chauffees'] = 99
        r = self.calculer()
        self.assertEqual(len(r['tarifs']), 2)
        self.assertEqual(r['tarifs'][0]['surfaces']['detail_confort']['Pièces chauffées admissibles'], 0)
        self.assertEqual(len(r['reserves_h2']), 2)

    def test_h2_nombre_de_pieces_requis_et_entier(self):
        for pieces in [{}, {'chambres': 0}, {'chambres': 1.5}, {'chambres': -1}, {'chambres': float('nan')}]:
            with self.subTest(pieces=pieces), self.assertRaises(ValueError):
                self.saisie['h2'] = {'pieces': pieces, 'chauffage': True}
                self.calculer()

    def test_bareme_ascenseur_immeuble_article_324_s(self):
        for niveau, avec, sans in [(0, 0, 0), (1, 0, 0), (2, .05, 0), (3, .05, 0),
                                    (4, .05, -.05), (5, .05, -.10), (6, .05, -.15), (10, .05, -.15)]:
            for present, attendu in [(True, avec), (False, sans)]:
                with self.subTest(niveau=niveau, ascenseur=present):
                    r = surface_totale(45, 'A', '5', etage=niveau, ascenseur=present)
                    self.assertEqual(r['correctif_ascenseur'], attendu)
                    self.assertEqual(r['correctif'], round(1 + attendu, 4))
                    self.assertEqual(r['detail_correctifs']['niveau_local'], niveau)
                    self.assertEqual(r['detail_correctifs']['ascenseur_immeuble'], present)
                    self.assertEqual(r['equivalence_confort'], 19)
        self.assertEqual(surface_totale(45, 'M', '5', etage=6, ascenseur=True)['correctif_ascenseur'], 0)

    def test_quantites_fractionnaires_et_non_finies_refusees(self):
        for params in [{'douches': 1.5}, {'wc': float('nan')}, {'etage': 2.5}]:
            with self.subTest(params=params), self.assertRaises(ValueError):
                surface_totale(45, 'A', '5', **params)
        for sp, prix, taux in [(float('nan'), 10, 30), (45, -1, 30), (45, 10, float('inf'))]:
            with self.subTest(sp=sp, prix=prix, taux=taux), self.assertRaises(ValueError):
                simulations_tarifs(sp, [{'serie': 'A', 'tarif_1970': prix}], 10, {'commune': taux})
        for rates in [{}, {'commune': None}]:
            self.assertNotIn('total', simulations_tarifs(45, [{'serie': 'A', 'tarif_1970': 10}], 10, rates)[0])


if __name__ == '__main__':
    unittest.main()
