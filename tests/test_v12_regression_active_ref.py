import copy
import json
import sys
import unittest
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from moteur import (neutralisation_automatique,neutralisation_avec_teom_reference,
                    diagnostic_neutralisation,insee_cadastral_adresse, TAXES)

class RegressionV12(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.historic=json.loads((ROOT/'data'/'referentiel_initial.json').read_text())

    def test_import_2021_non_rattache_recupere_l_historique_signale(self):
        """La V11 perdait toute neutralisation si le lookup DGFiP échouait."""
        active=copy.deepcopy(self.historic)
        active['neutralisations_versions']={'69':{'2021+':[
           {'code_commune':'387','nom_commune':'LYON 7EME','prefixe':'001',
            'commune':.28,'syndicat':.28,'epci':.35,'taxes_speciales':.31,'gemapi':.31,'teom':None},
        ]}}
        bad,msg=neutralisation_automatique(active,'69','Lyon 7ème',2026,'69387','000')
        self.assertIsNone(bad)
        out,info,alerts=neutralisation_avec_teom_reference(
            active,self.historic,'69','Lyon 7ème',2026,'69387','000')
        self.assertEqual(out['commune'],.447584)
        self.assertEqual(out['teom'],.451676)
        self.assertEqual(set(TAXES)-out.keys(),set())
        self.assertIn('historique',info.lower())
        self.assertTrue(any('provisoirement' in a for a in alerts))

    def test_import_2021_partiel_priorite_au_officiel_avec_historique_par_composante(self):
        active=copy.deepcopy(self.historic)
        active['neutralisations_versions']={'69':{'2021+':[
            {'code_commune':'387','nom_commune':'LYON 7EME','prefixe':'000',
             'commune':.333,'syndicat':None,'epci':.444,
             'taxes_speciales':.555,'gemapi':.555,'teom':None}
        ]}}
        out,info,alerts=neutralisation_avec_teom_reference(
            active,self.historic,'69','Lyon 7eme',2026,'69387','000')
        self.assertEqual(out['commune'],.333)
        self.assertEqual(out['epci'],.444)
        self.assertEqual(out['syndicat'],.447584)
        self.assertEqual(out['teom'],.451676)
        self.assertEqual(len(alerts),2)
        self.assertTrue(all('à confirmer' in a for a in alerts))

    def test_import_officiel_complet_pas_de_fallback(self):
        active=copy.deepcopy(self.historic)
        imported={k:(i+1)/10 for i,k in enumerate(TAXES)}
        active['neutralisations_versions']={'69':{'2021+':[
            {'code_commune':'387','nom_commune':'LYON 7EME',**imported}
        ]}}
        out,_,alerts=neutralisation_avec_teom_reference(
            active,self.historic,'69','Lyon 7eme',2026,'69387','000')
        self.assertEqual(out,imported)
        self.assertEqual(alerts,[])

    def test_les_contradictions_n_ouvrent_pas_de_fallback(self):
        active=copy.deepcopy(self.historic)
        active['neutralisations_versions']={'69':{'2021+':[
            {'code_commune':'387','nom_commune':'LYON 7EME','commune':.333},
            {'code_commune':'387','nom_commune':'LYON 7EME','commune':.444},
        ]}}
        out,info,alerts=neutralisation_avec_teom_reference(
            active,self.historic,'69','Lyon',2026,'69387','000')
        self.assertIsNone(out)
        self.assertIn('contradictoires',info)
        self.assertTrue(alerts)

    def test_lyon_code_postal_convertit_seulement_le_municipal(self):
        self.assertEqual(insee_cadastral_adresse('69123','69007'),'69387')
        self.assertEqual(insee_cadastral_adresse('69387','69001'),'69387')
        self.assertEqual(insee_cadastral_adresse('42005','69007'),'42005')
        self.assertEqual(insee_cadastral_adresse('69123','69000'),'69123')

    def test_diagnostic_montre_absence_de_match_import(self):
        active=copy.deepcopy(self.historic)
        active['neutralisations_versions']={'69':{'2021+':[
           {'nom_commune':'LYON 7EME','code_commune':'387','prefixe':'001','commune':.3}
        ]}}
        d=diagnostic_neutralisation(active,'69','Lyon 7eme',2026,'69387','000')
        self.assertEqual(d['periode'],'2021+')
        self.assertEqual(d['nombre_lignes_importees'],1)
        self.assertEqual(d['nombre_lignes_rapprochees'],0)
        self.assertIsNone(d['coefficients'])

    def test_pas_de_fallback_faux_periode_historique(self):
        active=copy.deepcopy(self.historic)
        out, info, alerts=neutralisation_avec_teom_reference(
            active,self.historic,'69','Lyon 7eme',2019,'69387','000')
        self.assertIsNone(out)
        self.assertEqual(alerts,[])

if __name__=='__main__':unittest.main()
