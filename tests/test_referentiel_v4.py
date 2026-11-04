import sys
import unittest
from pathlib import Path
from copy import deepcopy
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from referentiel import DEPARTEMENTS, normaliser_departement, integrer_jeu, lignes_neutralisation, publication_attendue
from moteur import neutralisation_automatique
from imports_dgfip import url_fichier

class ReferentielV4Tests(unittest.TestCase):
    def setUp(self):
        self.ref={'tarifs':{'42':{'2025':{'BUR2':{'4':131}}}},'localisations':{'42':{}},
                  'secteurs':{'42':[{'commune':'ANDREZIEUX','secteur':4}]},
                  'neutralisations':{'42':[{'nom_commune':'ANDREZIEUX','commune':0.48, 'teom':0.79}]},
                  'sources':{}}

    def test_departement_metropolitain_corse_dom(self):
        for dep in ('01','42','75','2A','2B','971','974'):
            self.assertIn(dep,DEPARTEMENTS)
            self.assertIn(f'tarif-{dep.lower()}.xlsx',url_fichier(dep,'tarifs',2026))
        self.assertEqual(normaliser_departement('5'),'05')
        self.assertTrue(url_fichier('2B','neutralisations',2020).endswith('coef-neut/coef-neut-2b.ods'))
        self.assertTrue(url_fichier('75','neutralisations',2021).endswith('coef-neut-ap21/coef-neut-ap21-75.ods'))

    def test_import_nouveau_dep_preserve_autres(self):
        original=deepcopy(self.ref['tarifs']['42'])
        integrer_jeu(self.ref,'75','tarifs',2026,{'BUR2':{'1':210}}, {'origine':'DGFiP','sha256':'abc'})
        self.assertEqual(self.ref['tarifs']['42'],original)
        self.assertEqual(self.ref['tarifs']['75']['2026']['BUR2']['1'],210)
        self.assertEqual(self.ref['sources']['75/tarifs/2026']['sha256'],'abc')

    def test_neutralisation_ne_se_report_pas_sur_2020(self):
        vals,msg=neutralisation_automatique(self.ref,'42','ANDREZIEUX',2020)
        self.assertIsNone(vals)
        self.assertIn('2017-2020',msg)
        vals,msg=neutralisation_automatique(self.ref,'42','ANDREZIEUX',2026)
        self.assertEqual(vals['commune'],0.48)
        integrer_jeu(self.ref,'42','neutralisations',2020,
                     [{'nom_commune':'ANDREZIEUX','commune':0.8,'teom':0.9}],{'origine':'DGFiP','sha256':'xy'})
        vals,msg=neutralisation_automatique(self.ref,'42','ANDREZIEUX',2020)
        self.assertEqual(vals['commune'],0.8)
        vals,msg=neutralisation_automatique(self.ref,'42','ANDREZIEUX',2026)
        self.assertEqual(vals['commune'],0.48)

    def test_2026_publications_not_annually_neutralisation(self):
        specs=publication_attendue(2026,inclure_historique=True)
        self.assertIn(('localisations',2026),specs)
        self.assertIn(('neutralisations',2021),specs)
        self.assertIn(('neutralisations',2020),specs)
        self.assertIn(('secteurs',2017),specs)
        self.assertNotIn(('neutralisations',2026),specs)
        self.assertIn(('localisations',2024),publication_attendue(2025))

if __name__=='__main__': unittest.main()
