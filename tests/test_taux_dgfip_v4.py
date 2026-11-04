import sys
import unittest
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from taux_dgfip import detecter_champs, extraire_taux, rechercher_taux

FIELDS=[{'name':'insee_com','label':'Code INSEE'},
        {'name':'annee','label':'Année'},
        {'name':'taux_global_tfb','label':'Taux global taxe foncière bâtie'},
        {'name':'taux_teom','label':'Taux TEOM'},
        {'name':'taux_tfb_commune','label':'Taux TFB communal'}]
REC={'insee_com':'69387','annee':2025,'taux_global_tfb':31.2,
     'taux_teom':8.3,'taux_tfb_commune':25.3}

class TauxDgfipTests(unittest.TestCase):
    def test_detection_provenance_et_global_distinct(self):
        cols=detecter_champs(FIELDS)
        self.assertEqual(cols['tfb_global'],'taux_global_tfb')
        t=extraire_taux([REC],FIELDS,'69387',2025)
        self.assertEqual(t['taux']['commune'],25.3)
        self.assertEqual(t['taux']['tfb_global'],31.2)
        self.assertFalse(t['complet'])

    def test_millesime_non_disponible_ne_se_reutilise_pas(self):
        with self.assertRaisesRegex(ValueError,'2026'):
            extraire_taux([REC],FIELDS,'69387',2026)
        with self.assertRaisesRegex(ValueError,'69388'):
            extraire_taux([REC],FIELDS,'69388',2025)

    def test_code_ambigu_blocage(self):
        doubled=FIELDS+[{'name':'code_insee','label':'Code INSEE'}]
        with self.assertRaisesRegex(ValueError,'INSEE'):
            extraire_taux([REC],doubled,'69387',2025)

    def test_interrogation_api_simulee(self):
        class Resp:
            def __init__(self,data):self.data=data
            def raise_for_status(self):pass
            def json(self):return self.data
        class Sess:
            def get(self,url,params=None,timeout=None):
                if url.endswith('/records'):
                    self.where=params['where'];return Resp({'results':[REC]})
                return Resp({'fields':FIELDS})
        fake=Sess()
        r=rechercher_taux('69387',2025,session=fake)
        self.assertEqual(r['taux']['teom'],8.3)
        self.assertIn('69387',fake.where)

if __name__=='__main__':unittest.main()
