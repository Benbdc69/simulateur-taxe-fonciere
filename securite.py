"""Hachage scrypt pour un secret choisi hors du dépôt GitHub.

Protection simple d'accès, pas un système d'identités individuelles ni un
anti-bruteforce global. Sans mot de passe configuré, l'accès cloud est fermé.
"""
from __future__ import annotations
import hashlib
import hmac
import re
import secrets

def generer_empreinte(mot_de_passe: str) -> str:
    if len(mot_de_passe)<14:
        raise ValueError('Utilisez au moins 14 caractères pour le mot de passe partagé.')
    sel=secrets.token_bytes(16)
    digest=hashlib.scrypt(mot_de_passe.encode('utf-8'),salt=sel,n=2**14,r=8,p=1,dklen=32)
    return f'scrypt$16384$8$1${sel.hex()}${digest.hex()}'

def verification_mot_de_passe(mot_de_passe: str, empreinte: str) -> bool:
    if not isinstance(mot_de_passe,str) or len(mot_de_passe)>200:
        return False
    try:
        algo,n,r,p,sel_hex,digest_hex=empreinte.split('$')
        if algo!='scrypt' or (n,r,p)!=('16384','8','1'):
            return False
        if not re.fullmatch(r'[0-9a-f]{32}',sel_hex) or not re.fullmatch(r'[0-9a-f]{64}',digest_hex):
            return False
        digest=hashlib.scrypt(mot_de_passe.encode('utf-8'),salt=bytes.fromhex(sel_hex),n=2**14,r=8,p=1,dklen=32)
        return hmac.compare_digest(digest,bytes.fromhex(digest_hex))
    except (ValueError,TypeError):return False
