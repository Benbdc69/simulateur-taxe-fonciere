import pathlib
import sys
import unittest
from io import StringIO

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from moteur import regime_reforme, planchonnement_2017, lissage_2017_2025, estimation
from taux_historiques_tf import _lire_csv


class ReformesTests(unittest.TestCase):
    def test_planchonnement_positif(self):
        r = planchonnement_2017(20000, 30000)
        self.assertEqual(r['correction_valeur_locative'], -5000)
        self.assertEqual(r['correction_base_tf'], -2500)

    def test_planchonnement_negatif_ecart_positif(self):
        r = planchonnement_2017(30000, 20000)
        self.assertEqual(r['correction_base_tf'], 2500)

    def test_regime_local_ancien_2026(self):
        self.assertEqual(regime_reforme(2026, True)['planchonnement'], True)
        self.assertEqual(regime_reforme(2026, True)['lissage'], False)

    def test_regime_local_nouveau(self):
        self.assertFalse(regime_reforme(2025, False)['planchonnement'])
        self.assertFalse(regime_reforme(2025, False)['lissage'])

    def test_changement_majoritaire(self):
        self.assertFalse(regime_reforme(2025,True,'consistance',2023,10)['planchonnement'])
        self.assertTrue(regime_reforme(2025,True,'consistance',2023,9.99)['planchonnement'])
        self.assertTrue(regime_reforme(2022,True,'consistance',2023,20)['planchonnement'])
        self.assertFalse(regime_reforme(2025,True,'affectation_utilisation',2023)['planchonnement'])

    def test_historique_inconnu_bloque(self):
        with self.assertRaises(ValueError):
            regime_reforme(2026,True,'inconnu')
        with self.assertRaises(ValueError):
            regime_reforme(2026,True,'consistance',2018,None)

    def test_lissage_degressif_signe(self):
        # La réforme augmente la cotisation de 1 000 € en 2017,
        # d'où un lissage NEGATIF de 900 € en 2017 et -100 € en 2025.
        self.assertEqual(lissage_2017_2025(2017,cotisation_avant_reforme_2017=1000,
                    cotisation_apres_reforme_2017=2000)['montant'],-900)
        self.assertEqual(lissage_2017_2025(2025,cotisation_avant_reforme_2017=1000,
                    cotisation_apres_reforme_2017=2000)['montant'],-100)
        self.assertEqual(lissage_2017_2025(2026,cotisation_avant_reforme_2017=1000,
                    cotisation_apres_reforme_2017=2000)['montant'],0)
        # La réforme réduit la cotisation : le lissage compense POSITIVEMENT.
        self.assertEqual(lissage_2017_2025(2025,pas_annuel=-100)['montant'],100)
        self.assertEqual(lissage_2017_2025(2024,montant_avis=250)['montant'],250)

    def test_lissage_obligatoire_sans_document(self):
        with self.assertRaises(ValueError):lissage_2017_2025(2025)
        with self.assertRaises(ValueError):lissage_2017_2025(2025,
                   cotisation_avant_reforme_2017=100)

    def test_pas_de_regime_2017_en_2027(self):
        with self.assertRaises(ValueError):regime_reforme(2027,True)
        with self.assertRaises(ValueError):lissage_2017_2025(2027,pas_annuel=100)

    def test_integration_totale_signe(self):
        taux={k:0 for k in ['commune','syndicat','epci','taxes_speciales','teom','gemapi']}
        taux['commune']=20
        c={k:1.0 for k in taux}
        p={k:0 for k in taux}
        p['commune']=-250
        r=estimation({'P1':100},100,1.0,c,taux,planchonnements=p,
                     correction_lissage=-100)
        # Assiette=5000 ; planch=-250 => base 4750 ; 20%=950 ; -100 => 850.
        self.assertEqual(r['lignes'][0]['base_taxable'],4750)
        self.assertEqual(r['total_avant_lissage'],950)
        self.assertEqual(r['total_estime'],850)

    def test_archive_rei_respecte_commune_millesime_et_taux_nuls(self):
        archive = StringIO(
            'DEP;COM;ANNEE;E12;E22;E32;E42;E52;E52A;E52TASA;E52gGEMAPI;Taux_Plein_TEOM\n'
            '69;029;2017;20;0;0;10;1,2;0,3;0;0;0\n'
            '69;029;2018;21;0;0;11;0;0;0;0;0\n'
            '69;030;2017;22;0;0;12;0;0;0;0;0\n')
        taux = _lire_csv(archive, '69029', 2017)
        self.assertEqual(taux, {'commune': 20, 'departement': 10, 'syndicat': 0, 'epci': 0,
                                'taxes_speciales': 1.5, 'gemapi': 0, 'teom': 0})

if __name__=='__main__':unittest.main()
