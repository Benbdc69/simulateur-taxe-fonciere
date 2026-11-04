"""Régression de l'incident remonté : Lyon 7e, parcelle AC, neutralisation.

Les exemples 2021 sont simulés sur la base des intitulés officiels déjà
validés dans les tests V6 ; aucun appel réseau n'est effectué.
"""
import copy
import json
import sys
import unittest
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from moteur import (nom_commune_cadastrale, secteur_automatique, estimation,
                    neutralisation_automatique, neutralisation_avec_teom_reference, TAXES)

class LyonV11(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.base=json.loads((ROOT/'data'/'referentiel_initial.json').read_text(encoding='utf8'))

    def test_commune_cadastrale_inferree_sans_ressaisie(self):
        self.assertEqual(nom_commune_cadastrale(self.base,'69','69387','Lyon'),'LYON 7EME')
        self.assertEqual(nom_commune_cadastrale({'secteurs':{}},'69','69387','Lyon'),'Lyon 7ème')
        self.assertEqual(nom_commune_cadastrale({'secteurs':{}},'42','42005','Abœn'),'Abœn')

    def test_lyon_7_libelles_codes_variants(self):
        for nom in ('Lyon','Lyon 7e','Lyon 7ème','Lyon 07',
                    'Lyon 7eme Arrondissement','LYON 7 EME'):
            with self.subTest(nom=nom):
                vals, info=neutralisation_automatique(self.base,'69',nom,2026,'69387','000')
                self.assertIsNotNone(vals,info)
                self.assertAlmostEqual(vals['commune'],.447584)
                self.assertAlmostEqual(vals['teom'],.451676)
                secteur,_=secteur_automatique(self.base,'69',nom,'000','AC','69387')
                self.assertEqual(secteur,4)

    def test_2021_importe_avec_teom_absente(self):
        ref=copy.deepcopy(self.base)
        ref['neutralisations_versions']={'69':{'2021+':[
            {'code_commune':'387','nom_commune':'Lyon 7e Arrondissement',
             'prefixe':'000', 'commune':.5,'syndicat':.5,'epci':.45,
             'taxes_speciales':.49,'gemapi':.49,'teom':None}
        ]}}
        vals,msg,alertes=neutralisation_avec_teom_reference(
            ref,self.base,'69','Lyon',2026,'69387','000')
        self.assertEqual(vals['commune'],.5)
        self.assertEqual(vals['epci'],.45)
        self.assertEqual(vals['gemapi'],.49)
        self.assertAlmostEqual(vals['teom'],.451676)
        self.assertTrue(any('TEOM' in a for a in alertes))

    def test_estimation_non_bloquee_avec_neutralisations_2021_et_teom_reference(self):
        ref=copy.deepcopy(self.base)
        ref['neutralisations_versions']={'69':{'2021+':[
            {'code_commune':'387','nom_commune':'LYON 7E','commune':.5,
             'syndicat':.5,'epci':.45,'taxes_speciales':.49,
             'gemapi':.49,'teom':None}
        ]}}
        values,_,alerts=neutralisation_avec_teom_reference(
            ref,self.base,'69','Lyon 7e',2026,'69387','000')
        self.assertTrue(all(values[k] is not None for k in TAXES))
        rates={'commune':31.89,'syndicat':0,'epci':.55,
               'taxes_speciales':0,'teom':5.19,'gemapi':0}
        result=estimation({'P1':100,'P2':0,'P3':0,'PK1':0,'PK2':0},
                          200.5,1.0,values,rates)
        self.assertGreater(result['total_estime'],0)
        self.assertTrue(alerts)

    def test_2021_avec_code_fiscal_et_nom_arrondissement(self):
        ref={'neutralisations_versions':{'69':{'2021+':[
            {'code_commune':'123','nom_commune':'LYON 07','commune':.333,
             'syndicat':.333,'epci':.444,'taxes_speciales':.555,'gemapi':.555}
        ]}}}
        vals,_=neutralisation_automatique(ref,'69','Lyon',2026,'69387')
        self.assertAlmostEqual(vals['commune'],.333)

    def test_pas_de_confusion_lyon_2_et_lyon_7(self):
        ref={'neutralisations_versions':{'69':{'2021+':[
            {'code_commune':'382','nom_commune':'LYON 2EME','commune':.222,
             'syndicat':.222,'epci':.44},
            {'code_commune':'387','nom_commune':'LYON 7EME','commune':.777,
             'syndicat':.777,'epci':.44}
        ]}}}
        v,_=neutralisation_automatique(ref,'69','Lyon',2026,'69387')
        self.assertAlmostEqual(v['commune'],.777)
        v,_=neutralisation_automatique(ref,'69','Lyon',2026,'69382')
        self.assertAlmostEqual(v['commune'],.222)

    def test_pas_de_teom_inventee_si_aucun_historique(self):
        ref={'neutralisations_versions':{'69':{'2021+':[
            {'code_commune':'387','nom_commune':'LYON 7EME','commune':.3,
             'epci':.4, 'teom':None}
        ]}}}
        v,_,alerts=neutralisation_avec_teom_reference(ref,None,'69','Lyon',2026,'69387')
        self.assertIsNone(v['teom'])
        self.assertEqual(alerts,[])

    def test_conflit_coefficients_refuse(self):
        ref={'neutralisations_versions':{'69':{'2021+':[
            {'code_commune':'387','nom_commune':'LYON 7EME','commune':.2},
            {'code_commune':'387','nom_commune':'LYON 7EME','commune':.3}
        ]}}}
        vals,msg=neutralisation_automatique(ref,'69','Lyon',2026,'69387')
        self.assertIsNone(vals)
        self.assertIn('contradictoires',msg)

if __name__=='__main__':unittest.main()
