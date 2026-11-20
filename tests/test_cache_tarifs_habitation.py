import os
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from unittest.mock import Mock, patch

import requests

from tarifs_habitation import tarifs_nationaux


CSV = (
    'Département;Code Commune;Nature locaux;Série tarif bâti;Catégorie;VL au m²\n'
    '69;387;A;B;5;12,5\n'
).encode('utf-8')


class CacheTarifsHabitationTests(unittest.TestCase):
    def tearDown(self):
        tarifs_nationaux.cache_clear()

    def test_tarifs_relus_sur_disque_apres_redemarrage(self):
        with TemporaryDirectory() as dossier, patch.dict(os.environ, {'TF_DATA_DIR': dossier}):
            tarifs_nationaux.cache_clear()
            reponse = Mock(content=CSV, headers={'content-type': 'text/csv'})
            with patch('tarifs_habitation.requests.get', return_value=reponse) as get:
                en_ligne = tarifs_nationaux()
                get.assert_called_once()

            self.assertEqual(Path(dossier, 'tarifs_habitation_2024.csv').read_bytes(), CSV)
            tarifs_nationaux.cache_clear()
            with patch('tarifs_habitation.requests.get', side_effect=requests.ConnectionError) as get:
                self.assertEqual(tarifs_nationaux(), en_ligne)
                get.assert_not_called()
