"""Dossiers professionnels et évaluations figées, sur PostgreSQL ou SQLite local."""

from contextlib import closing, contextmanager
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import unicodedata
from urllib.parse import urlsplit
from uuid import uuid4


def _cle(texte):
    return ' '.join(unicodedata.normalize('NFKC', texte).casefold().split())


def lien_documentaire(lien):
    lien = lien.strip()
    if lien:
        url = urlsplit(lien)
        if (url.scheme != 'https' or not url.hostname or url.username or url.password
                or any(c.isspace() for c in lien)):
            raise ValueError('Renseignez une adresse HTTPS vers le dossier documentaire.')
    return lien


class StockageDossiers:
    def __init__(self, *, postgres='', sqlite=''):
        if bool(postgres) == bool(sqlite):
            raise ValueError('Configurez un seul stockage de dossiers.')
        self.postgres = postgres
        self.sqlite = Path(sqlite).expanduser() if sqlite else None

    @contextmanager
    def connexion(self):
        if self.postgres:
            from psycopg import connect
            connexion = connect(self.postgres, connect_timeout=6)
        else:
            self.sqlite.parent.mkdir(parents=True, exist_ok=True)
            connexion = sqlite3.connect(self.sqlite, timeout=6)
            connexion.execute('PRAGMA foreign_keys = ON')
        with closing(connexion), connexion:
            yield connexion

    def executer(self, connexion, requete, params=()):
        return connexion.execute(requete.replace('?', '%s') if self.postgres else requete, params)

    def initialiser(self):
        with self.connexion() as connexion:
            # L'initialisation est aussi sûre si deux processus démarrent ensemble.
            if self.postgres:
                connexion.execute('SELECT pg_advisory_xact_lock(761026660)')
            connexion.execute("""
                CREATE TABLE IF NOT EXISTS tf_societes (
                    cle TEXT PRIMARY KEY,
                    nom TEXT NOT NULL,
                    lien TEXT NOT NULL DEFAULT ''
                )
            """)
            connexion.execute("""
                CREATE TABLE IF NOT EXISTS tf_evaluations (
                    id TEXT PRIMARY KEY,
                    societe TEXT NOT NULL REFERENCES tf_societes(cle),
                    local TEXT NOT NULL,
                    adresse TEXT NOT NULL,
                    annee INTEGER NOT NULL,
                    enregistre_le TEXT NOT NULL,
                    auteur TEXT NOT NULL,
                    empreinte TEXT NOT NULL,
                    contenu TEXT NOT NULL,
                    UNIQUE (societe, empreinte)
                )
            """)
            connexion.execute("""
                CREATE INDEX IF NOT EXISTS tf_evaluations_societe_date
                ON tf_evaluations (societe, enregistre_le DESC)
            """)

    def enregistrer(self, nom, evaluation, audit, auteur, *, local='', lien=''):
        """Insère une nouvelle version. Un enregistrement identique renvoie la version existante."""
        nom = ' '.join(nom.split())
        if not nom:
            raise ValueError('Indiquez le nom de la société.')
        societe = _cle(nom)
        local = local.strip() or evaluation['adresse']
        lien = lien_documentaire(lien)
        contenu = json.dumps({'evaluation': evaluation, 'audit': audit},
                             ensure_ascii=False, sort_keys=True, allow_nan=False)
        empreinte = sha256((_cle(local) + '\n' + contenu).encode()).hexdigest()
        identifiant = uuid4().hex
        date = datetime.now(timezone.utc).isoformat()
        with self.connexion() as connexion:
            self.executer(connexion, """
                INSERT INTO tf_societes (cle, nom, lien) VALUES (?, ?, ?)
                ON CONFLICT (cle) DO NOTHING
            """, (societe, nom, lien))
            if lien:
                self.executer(connexion, 'UPDATE tf_societes SET lien = ? WHERE cle = ?', (lien, societe))
            self.executer(connexion, """
                INSERT INTO tf_evaluations
                    (id, societe, local, adresse, annee, enregistre_le, auteur, empreinte, contenu)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT (societe, empreinte) DO NOTHING
            """, (identifiant, societe, local, evaluation['adresse'], evaluation['annee'],
                  date, auteur, empreinte, contenu))
            return self.executer(connexion,
                'SELECT id FROM tf_evaluations WHERE societe = ? AND empreinte = ?',
                (societe, empreinte)).fetchone()[0]

    def societes(self):
        with self.connexion() as connexion:
            return self.executer(connexion, 'SELECT cle, nom, lien FROM tf_societes ORDER BY cle').fetchall()

    def modifier_lien(self, societe, lien):
        with self.connexion() as connexion:
            self.executer(connexion, 'UPDATE tf_societes SET lien = ? WHERE cle = ?',
                          (lien_documentaire(lien), societe))

    def evaluations(self, societe):
        with self.connexion() as connexion:
            return self.executer(connexion, """
                SELECT id, local, adresse, annee, enregistre_le, auteur FROM tf_evaluations
                WHERE societe = ? ORDER BY enregistre_le DESC
            """, (societe,)).fetchall()

    def lire(self, societe, identifiant):
        with self.connexion() as connexion:
            ligne = self.executer(connexion, 'SELECT contenu FROM tf_evaluations WHERE societe = ? AND id = ?',
                                  (societe, identifiant)).fetchone()
        return json.loads(ligne[0]) if ligne else None
