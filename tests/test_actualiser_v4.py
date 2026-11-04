import hashlib, json, sys, tempfile, unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]))
import actualiser

class ActualiserV4Tests(unittest.TestCase):
    def test_multi_departement_staged_no_silent_overwrite(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp)
            base=root/'base.json'; active=root/'local.json'; pending=root/'en_attente'/'proposition.json'
            ref={'tarifs':{'42':{'2025':{'BUR2':{'4':111}}}},
                 'localisations':{'42':{}},'secteurs':{'42':[]},
                 'neutralisations':{'42':[]},'sources':{}}
            base.write_text(json.dumps(ref),encoding='utf8')
            def fetch(url):return url.encode('utf8')
            def parse(blob,url,kind):
                if kind=='tarifs':rows={'BUR2':{'1':200}}
                elif kind=='secteurs':rows=[{'nom_commune':'PARIS','secteur':1}]
                elif kind=='localisations':rows=[{'nom_commune':'PARIS','coefficient':1.1}]
                else:rows=[{'nom_commune':'PARIS','commune':0.5,'teom':0.88}]
                return rows,hashlib.sha256(blob).hexdigest()
            with patch.object(actualiser,'BASE',base),patch.object(actualiser,'ACTIVE',active),\
                patch.object(actualiser,'PENDING',pending),patch.object(actualiser,'LOG',root/'log.txt'):
                result=actualiser.preparer_proposition(2026,['75','42'],fetch=fetch,parse=parse)
                self.assertEqual(result['changements'],10)
                self.assertFalse(active.exists())
                self.assertTrue(pending.exists())
                proposal=json.loads(pending.read_text(encoding='utf8'))
                self.assertEqual(proposal['referentiel']['tarifs']['42']['2025'],ref['tarifs']['42']['2025'])
                self.assertIn('75',proposal['referentiel']['tarifs'])
                self.assertIn('2021+',proposal['referentiel']['neutralisations_versions']['75'])
                self.assertIn('2017-2020',proposal['referentiel']['neutralisations_versions']['75'])
                with self.assertRaisesRegex(ValueError,'déjà en attente'):
                    actualiser.preparer_proposition(2026,['75'],fetch=fetch,parse=parse)

if __name__=='__main__':unittest.main()
