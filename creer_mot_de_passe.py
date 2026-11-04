"""Exécuter sur votre Mac : python3 creer_mot_de_passe.py.

Le mot de passe n'est pas imprimé ; seule son empreinte est affichée.
"""
from getpass import getpass
from securite import generer_empreinte

if __name__=='__main__':
    password=getpass('Choisir le mot de passe commun (14 caractères minimum) : ')
    confirm=getpass('Confirmer : ')
    if password!=confirm:raise SystemExit('Les mots de passe sont différents.')
    try:
        print('Collez cette ligne dans les secrets de Streamlit (Advanced settings) :')
        print('TF_SHARED_PASSWORD_HASH = "'+generer_empreinte(password)+'"')
    except ValueError as e:raise SystemExit(str(e))
