"""Rubriques propres à la page 2 du H1 (fourni par l'utilisateur)."""
from dependances_habitation import nombre, valider_dependances

from referentiel_formulaires import ELEMENTS_H1, SURFACES_DEP_H1, MURS, TOITURES, PIECES_HABITATION


def valider_elements_incorpores(elements):
    if not isinstance(elements, dict) or set(elements)-set(ELEMENTS_H1):
        raise ValueError('Rubriques des éléments incorporés H1 invalides.')
    lignes = []
    for cle, element in elements.items():
        surface = nombre(element.get('surface', 0), ELEMENTS_H1[cle])
        if surface:
            lignes.append(dict(type='garage' if cle=='garages' else 'cave', mode='incorporee',
                designation=ELEMENTS_H1[cle], surface=surface, coefficient=element.get('coefficient', .4)))
    return valider_dependances(lignes)


def valider_description_h1(description):
    pieces = description.get('pieces', {})
    if set(pieces)-set(PIECES_HABITATION):
        raise ValueError('Rubrique de pièces H1 inconnue.')
    if sum(nombre(v,'Nombre de pièces H1',entier=True) for v in pieces.values()) <= 0:
        raise ValueError('Renseignez au moins une pièce dans le cadre 41 A du H1.')
    for champ in ('annee_construction','niveaux_habitables'):
        valeur = description.get(champ)
        if valeur is not None:
            n = nombre(valeur,champ,entier=True)
            if (champ=='annee_construction' and not 1<=n<=9999) or (champ=='niveaux_habitables' and n<1):
                raise ValueError('Année de construction ou nombre de niveaux H1 invalide.')
    if set(description.get('materiaux_murs',[]))-set(MURS) or set(description.get('materiaux_toitures',[]))-set(TOITURES):
        raise ValueError('Matériau H1 inconnu.')
    if not description.get('chauffage') and description.get('pieces_chauffees', 0):
        raise ValueError('Cochez le chauffage ou indiquez zéro pièce chauffée.')

    for valeur in description.get('emprises',{}).values():
        if valeur is not None:
            nombre(valeur,'Emprise au sol H1')
