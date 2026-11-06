"""Repères de lecture du classement cadastral habitation (CGI, annexe III, 324 H).

Aide qualitative, sans barème de points ni attribution automatique : le classement
se fait par comparaison avec les locaux de référence de la commune.
"""
CLASSEMENT = {
    '1': ('Grand luxe', 'Caractère architectural et qualité de construction exceptionnels ; distribution, locaux et équipements d’un niveau exceptionnel.'),
    '2': ('Luxe', 'Construction et aménagements de très grande qualité, distribution ample et équipements de haut niveau.'),
    '3': ('Très confortable', 'Très bonne qualité de construction, distribution et aménagements très confortables, sans caractère de luxe.'),
    '4': ('Confortable', 'Bonne qualité d’ensemble, distribution et aménagements confortables.'),
    '5': ('Assez confortable', 'Qualité et aménagements courants, distribution et confort satisfaisants, sans prestations particulières.'),
    '6': ('Ordinaire', 'Construction et aménagements simples, distribution et confort ordinaires.'),
    '7': ('Médiocre', 'Qualité de construction et aménagements médiocres ; distribution et équipements présentant des insuffisances importantes.'),
    '8': ('Très médiocre', 'Construction et aménagements très médiocres ; insuffisances particulièrement marquées de distribution et d’équipement.'),
}
CRITERES = [
    ('Caractère architectural', 'Aspect d’ensemble, conception et caractère de l’immeuble ou de la maison ; pas uniquement la décoration du logement.'),
    ('Qualité de la construction', 'Matériaux, qualité d’exécution et niveau général de construction.'),
    ('Distribution du local', 'Agencement des pièces, dégagements et commodité de la distribution.'),
    ('Locaux sanitaires et équipements', 'Organisation des sanitaires et niveau d’équipement/confort, appréciés avec les autres critères.'),
]


def libelle_categorie(categorie):
    if categorie is None:
        return 'Choisissez une catégorie'
    if categorie.endswith('M'):
        n = int(categorie[0])
        return f'{categorie} · Intermédiaire entre {n} ({CLASSEMENT[str(n)][0]}) et {n+1} ({CLASSEMENT[str(n+1)][0]})'
    return f'{categorie} · {CLASSEMENT[categorie][0]}'
