"""Emplacement et écriture atomique des données fiscales locales."""
import os
from pathlib import Path
from tempfile import NamedTemporaryFile

DONNEES_LIVREES = Path(__file__).resolve().parent / 'data'


def dossier_fiscal():
    dossier = os.environ.get('TF_DATA_DIR')
    return Path(dossier).expanduser().resolve() if dossier else DONNEES_LIVREES


def ecrire_atomiquement(destination, contenu):
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporaire = None
    try:
        with NamedTemporaryFile(dir=destination.parent, prefix=f'.{destination.name}.',
                                suffix='.tmp', delete=False) as fichier:
            temporaire = Path(fichier.name)
            fichier.write(contenu)
        temporaire.replace(destination)
    finally:
        if temporaire is not None:
            temporaire.unlink(missing_ok=True)
