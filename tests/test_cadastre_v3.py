"""Tests locaux à réponses IGN simulées : pas de connexion Internet nécessaire."""
import sys, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
from cadastre import adresses, parcelles_a_l_adresse, rechercher_parcelle, _distance_polygone


class Response:
    def __init__(self, payload):self.payload=payload
    def raise_for_status(self):pass
    def json(self):return self.payload


class CadastreV3Tests(unittest.TestCase):
    def test_lyon7_adresse_normalisee_et_insee_arrondissement(self):
        def get(url, params, **_):
            self.assertIn('69007 Lyon', params['q'])
            return Response({'type':'FeatureCollection','features':[
                {'type':'Feature','geometry':{'type':'Point','coordinates':[4.84,45.75]},
                 'properties':{'label':'18 Cours Gambetta 69007 Lyon','city':'Lyon',
                               'postcode':'69007','citycode':'69123','score':0.96,'type':'housenumber'}}]})
        with patch('cadastre.requests.get',side_effect=get):
            result=adresses('18 Cours Gambetta Lyon 7')
        self.assertEqual(result[0]['insee'],'69387')
        self.assertEqual(result[0]['code_insee_adresse'],'69123')
        self.assertEqual(result[0]['type_geocodage'],'housenumber')

    def test_point_sur_trottoir_fallback_polygone_candidat(self):
        def get(url, params, **_):
            geom=__import__('json').loads(params['geom'])
            if geom['type']=='Point':
                return Response({'type':'FeatureCollection','features':[]})
            self.assertEqual(geom['type'],'Polygon')
            return Response({'type':'FeatureCollection','features':[
                {'geometry':{'type':'Polygon','coordinates':[[[4.8401,45.7501],[4.8403,45.7501],
                    [4.8403,45.7503],[4.8401,45.7503],[4.8401,45.7501]]]},
                 'properties':{'idu':'69387000AC0001','section':'AC','numero':'1','com_abs':'000'}},
                {'geometry':{'type':'Polygon','coordinates':[[[4.8403,45.7502],[4.8405,45.7502],
                    [4.8405,45.7504],[4.8403,45.7504],[4.8403,45.7502]]]},
                 'properties':{'idu':'69387000AC0002','section':'AC','numero':'2','com_abs':'000'}}]})
        with patch('cadastre.requests.get',side_effect=get) as mocked:
            rows=parcelles_a_l_adresse({'lon':4.84,'lat':45.75,'insee':'69387','commune':'Lyon'},rayon_m=40)
        self.assertEqual(mocked.call_count,2)
        self.assertEqual(rows[0]['id'],'69387000AC0001')
        self.assertEqual(rows[0]['insee'],'69387')
        self.assertEqual(rows[0]['numero'],'0001')
        self.assertEqual(rows[0]['prefixe'],'000')
        self.assertEqual(rows[0]['recherche'],'Parcelle voisine — confirmation obligatoire')
        self.assertGreater(rows[0]['distance_m'],0)

    def test_point_exact_pas_de_seconde_requete(self):
        obj={'geometry':{'type':'Polygon','coordinates':[[[4.8399,45.7499],[4.8401,45.7499],
               [4.8401,45.7501],[4.8399,45.7501],[4.8399,45.7499]]]},
             'properties':{'idu':'69387000AC0001','section':'AC','numero':'0001'}}
        with patch('cadastre.requests.get',return_value=Response({'features':[obj]})) as mock:
            found=parcelles_a_l_adresse({'lon':4.84,'lat':45.75,'insee':'69387'})
        self.assertEqual(mock.call_count,1)
        self.assertEqual(found[0]['distance_m'],0)
        self.assertEqual(found[0]['recherche'],'Point dans la parcelle')

    def test_recherche_par_reference_ign_formate_numero(self):
        with patch('cadastre.requests.get',return_value=Response({'features':[]})) as mock:
            rechercher_parcelle('69387','AC',1,'000')
        params=mock.call_args.kwargs['params']
        self.assertEqual(params['numero'],'0001')
        self.assertEqual(params['com_abs'],'000')

if __name__=='__main__':unittest.main()
