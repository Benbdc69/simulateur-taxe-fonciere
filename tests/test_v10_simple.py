import copy
import hashlib
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import mise_a_jour_simple as maj
from securite import generer_empreinte, verification_mot_de_passe

class TestsSecurite(unittest.TestCase):
    def test_bon_mot_de_passe_et_mauvais(self):
        h=generer_empreinte('Mot de passe très long 2026 #!')
        self.assertTrue(verification_mot_de_passe('Mot de passe très long 2026 #!',h))
        self.assertFalse(verification_mot_de_passe('Mot de passe incorrect !',h))
        self.assertFalse(verification_mot_de_passe('',h))
    def test_password_not_stored_in_plaintext(self):
        phrase='Long et privé #2026 TF'
        h=generer_empreinte(phrase)
        self.assertNotIn(phrase,h)
        self.assertNotEqual(h,generer_empreinte(phrase))
    def test_short_password_rejected(self):
        with self.assertRaises(ValueError):generer_empreinte('court')
    def test_malformed_hash_fails_closed(self):
        self.assertFalse(verification_mot_de_passe('test','plain'))

class TestsMiseAJour(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory()
        folder=Path(self.tmp.name)
        self.base=folder/'data'/'referentiel_initial.json'
        self.base.parent.mkdir()
        self.base.write_text(json.dumps({'tarifs':{},'secteurs':{},'categories':[]}),encoding='utf8')
        self.active=folder/'data'/'referentiel_local.json'
        self.pending=folder/'data'/'en_attente'/'proposition.json'
        self.history=folder/'data'/'historique'
        self.patchers=[patch.object(maj,'BASE',self.base),patch.object(maj,'ACTIVE',self.active),
                       patch.object(maj,'PENDING',self.pending),patch.object(maj,'HISTORY',self.history)]
        for pp in self.patchers:pp.start()
    def tearDown(self):
        for pp in reversed(self.patchers):pp.stop()
        self.tmp.cleanup()
    def test_first_save_and_backup(self):
        first={'tarifs':{},'secteurs':{},'categories':[],'foo':1}
        maj.enregistrer_referentiel(first)
        self.assertEqual(maj.ouvrir_referentiel()['foo'],1)
        maj.enregistrer_referentiel({**first,'foo':2})
        self.assertEqual(maj.ouvrir_referentiel()['foo'],2)
        self.assertEqual(len(list(self.history.glob('*.json'))),1)
    def test_checksum_conflict_prevents_overwrite(self):
        with self.assertRaises(ValueError):
            maj.enregistrer_referentiel({'foo':2},expected_sha256='not-the-current-hash')
        self.assertFalse(self.active.exists())
    def test_bad_publication_cannot_activate(self):
        prop={'referentiel':{},'modifications':[{'departement':'69','type':'tarifs','nombre_lignes':0}]}
        with self.assertRaises(ValueError):maj.verifier_proposition(prop,'69',2026)
    def test_batch_updates_and_keeps_other_departments(self):
        new={'tarifs':{'42':{'2025':{'BUR1':{'1':10}}},'69':{'2026':{'BUR1':{'1':30}}}},
             'secteurs':{},'categories':[]}
        def prepare(year,deps):
            self.pending.parent.mkdir(parents=True,exist_ok=True)
            self.pending.write_text(json.dumps({'base_sha256':hashlib.sha256(self.base.read_bytes()).hexdigest(),
                'referentiel':new,'modifications':[{'departement':'69','type':'tarifs','nombre_lignes':1}]}),encoding='utf8')
            return {'changements':1,'identiques':0,'echecs':[]}
        bilan=maj.synchroniser_dgfip(2026,'69',prepare=prepare)
        self.assertEqual(bilan['changements'],1)
        self.assertEqual(maj.ouvrir_referentiel()['tarifs']['42']['2025']['BUR1']['1'],10)
        self.assertFalse(self.pending.exists())
    def test_rates_same_year_not_overwritten(self):
        existing={'tarifs':{},'secteurs':{},'categories':[],
                  'taux_annuels':{'69123':{'2026':{'commune':{'taux':31.89,'source':'Manuel','annee_source':2026}}}}}
        self.active.write_text(json.dumps(existing),encoding='utf8')
        def fake(code,year):
            return {'propositions':{'commune':{'annee':2026,'taux':40,'source':'DGCL'},
                 'teom':{'annee':2025,'taux':5.19,'source':'REI'}},'incidents':[],'sources_consultees':[]}
        v=maj.synchroniser_taux(2026,'69387',preparer=fake)
        self.assertEqual(maj.ouvrir_referentiel()['taux_annuels']['69123']['2026']['commune']['taux'],31.89)
        self.assertEqual(maj.ouvrir_referentiel()['taux_annuels']['69123']['2025']['teom']['taux'],5.19)
        self.assertTrue(v['ajoutes'])

if __name__=='__main__':unittest.main()
