"""Tests sans Streamlit : fonctions métier extraites sans exécuter l'interface."""
import ast
import json
import unittest
from io import BytesIO
from pathlib import Path
from pypdf import PdfReader
from moteur import (COEFF_SURFACES, TAXES, TAXES_AVANT_2021, insee_cadastral_adresse, nom_commune_cadastrale,
                    secteur_automatique, localisation_automatique,
                    neutralisation_automatique, neutralisation_avec_teom_reference, tarif_automatique, estimation)
from historique_taux import resoudre, resoudre_tout, enregistrer
from exoneration_neuf import exon_neuf_non_habitation
from export_pdf import creer_pdf_estimation
from frais_gestion import estimer_frais
from planchonnement_saisie import preparer_planchonnement
from reforme_2017 import reconstituer_reforme

HERE=Path(__file__).resolve().parents[1]


def functions():
    tree=ast.parse((HERE/'parcours_express.py').read_text(encoding='utf-8'))
    selected=[node for node in tree.body if isinstance(node,ast.FunctionDef)
              and node.name in ('normaliser_identite','calculer_dossier')]
    ns=globals().copy()
    exec(compile(ast.Module(body=selected,type_ignores=[]),'parcours_express.py','exec'),ns)
    return ns

class TestParcoursExpress(unittest.TestCase):
    def setUp(self):
        self.fn=functions();self.ref=json.loads((HERE/'data/referentiel_initial.json').read_text(encoding='utf8'))
        self.bien=self.fn['normaliser_identite'](
            {'insee':'69387','departement':'69','section':'AC','numero':'0001','prefixe':'000'},
            {'insee':'69123','code_postal':'69007','commune':'Lyon'},self.ref)
        self.surfaces={'P1':100,'P2':20,'P3':0,'PK1':5,'PK2':0}

    def test_lyon_arrondissement_sans_commune_manuelle(self):
        self.assertEqual(self.bien['commune'],'LYON 7EME')
        self.assertEqual(self.bien['code_insee'],'69387')

    def test_ne_pas_inventer_total_sans_taux(self):
        result=self.fn['calculer_dossier'](self.ref,self.ref,self.bien,'BUR2',self.surfaces,2025)
        self.assertIsNone(result['result'])
        self.assertEqual(result['partial']['secteur'],4)
        self.assertGreater(result['partial']['valeur_locative_brute'],0)
        self.assertTrue(any('taux' in missing for missing in result['missing']))

    def test_un_total_avec_taux_documentes(self):
        import copy
        d=copy.deepcopy(self.ref)
        for k in TAXES:
            enregistrer(d,'69123',2025,k,0 if k not in ('commune','epci') else 0.55,
                        'Fixture de test')
        result=self.fn['calculer_dossier'](d,self.ref,self.bien,'BUR2',self.surfaces,2025)
        self.assertIsNotNone(result['result'])
        self.assertEqual(len(result['result']['lignes']),6)
        self.assertGreater(result['result']['total_estime'],0)

    def test_base_2016_planchonnement_et_lissage_millesimes(self):
        ref = {
            'secteurs': {'69': [{'commune': 'LYON 7EME', 'secteur': 4}]},
            'tarifs': {'69': {'2017': {'BUR2': {'4': 200}}, '2025': {'BUR2': {'4': 300}},
                              '2026': {'BUR2': {'4': 300}}}},
            'localisations': {'69': {
                '2017': [{'commune': 'LYON 7EME', 'section': 'AC', 'parcelle': '0001', 'coefficient': 1.1}],
                '2024': [], '2026': [],
            }},
            'neutralisations_versions': {'69': {
                '2017-2020': [{'nom_commune': 'LYON 7EME', 'commune': .5, 'coef_departement': .7}],
                '2021+': [{'nom_commune': 'LYON 7EME', **dict.fromkeys(TAXES, .8)}],
            }},
        }
        for cle in TAXES_AVANT_2021:
            enregistrer(ref, '69123', 2017, cle, {'commune': 20, 'departement': 10}.get(cle, 0), 'Fixture')
        for annee in (2025, 2026):
            for cle in TAXES:
                enregistrer(ref, '69123', annee, cle, 20 if cle == 'commune' else 0, 'Fixture')
        calculer = self.fn['calculer_dossier']
        args = (ref, ref, self.bien, 'BUR2', {'P1': 100})
        ancien = calculer(*args, 2025, historique='ancien', base_2016=10000)
        self.assertEqual(ancien['reforme_2017']['base_ancienne_2017'], 10040)
        self.assertAlmostEqual(ancien['reforme_2017']['vl_revisee_2017'], 22000)
        self.assertAlmostEqual(ancien['planchonnement']['corrections']['commune'], 620)
        self.assertEqual(ancien['reforme_2017']['cotisations_2017'], {'avant': 3102.36, 'apres': 2514.23})
        self.assertAlmostEqual(ancien['result']['correction_lissage'], 58.813)
        self.assertAlmostEqual(ancien['result']['total_estime'], 2582.813)
        frais = estimer_frais({l['cle']: l['montant'] for l in ancien['result']['lignes']}, 2025)
        pdf = creer_pdf_estimation({'annee': 2025, 'categorie': 'BUR2', 'bien': self.bien,
                                    'surfaces': {'P1': 100}, 'analyse': ancien, 'frais': frais})
        lecteur = PdfReader(BytesIO(pdf))
        self.assertIn('2 659 €', lecteur.pages[0].extract_text())
        self.assertIn('Correction de lissage', lecteur.pages[0].extract_text())
        self.assertAlmostEqual(calculer(*args, 2026, historique='ancien', base_2016=10000)['result']['total_estime'], 2524)
        imposition_2017 = calculer(*args, 2017, historique='ancien', base_2016=10000)
        self.assertTrue(any(ligne['cle'] == 'departement' for ligne in imposition_2017['result']['lignes']))
        self.assertIsNone(calculer(*args, 2025, historique='recent', base_2016=10000)['reforme_2017'])

        ref['taux_annuels']['69123']['2017'].pop('departement')
        ref['localisations']['69'].pop('2017')
        incomplet = calculer(*args, 2025, historique='ancien', base_2016=10000)
        self.assertFalse(incomplet['planchonnement']['applique'])
        self.assertIn('localisation 2017', incomplet['reforme_2017']['reserve_lissage'])
        self.assertIn('départementale', incomplet['reforme_2017']['reserve_lissage'])
        self.assertEqual(incomplet['result']['total_estime'], 2400)

if __name__=='__main__': unittest.main()
