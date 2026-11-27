"""Lecture des champs déclaratifs des trois modèles Cerfa interactifs."""
from datetime import date, datetime
from io import BytesIO
import re

from pypdf import PdfReader
from pypdf.errors import PyPdfError

from dependances_habitation import nombre
from export_cerfa import CATEGORIES_6660, ENTRETIEN_CODES, MURS_CODES, SANITAIRES, TOITURES_CODES
from moteur import COEFF_SURFACES
from referentiel_formulaires import (EQUIPEMENTS_H1, EQUIPEMENTS_H2, LIGNES_DEP_H2, PIECES_HABITATION,
                                    PREMIERE_CASE_DEP_H2, SURFACES_DEP_H1)

TAILLE_MAX_CERFA = 10 * 1024 * 1024
SIGNATURES = {
    'h1': {'a26', 'b7', 'b16', 'b42', 'cac19', 'ldcm1'},
    'h2': {'a28', 'b11', 'b14bis', 'b93', 'cac0', 'cacb1'},
    '6660-rev': {'a43', 'a44', 'cac6', 'd1', 'd5', 'd17'},
}


class ChampsCerfa:
    def __init__(self, champs):
        self.champs = champs
        self.renseigne = False
        self.a_verifier = []

    def texte(self, nom):
        valeur = self.champs.get(nom, {}).get('/V')
        if not isinstance(valeur, str) or valeur in ('/Off', '/None'):
            return ''
        valeur = ' '.join(valeur.split())
        self.renseigne |= bool(valeur)
        return valeur

    def nombre(self, nom, libelle, *, entier=False, mini=0, maxi=None, defaut=0):
        valeur = self.texte(nom)
        if not valeur:
            return defaut
        try:
            resultat = nombre(valeur.replace(' ', '').replace(',', '.'), libelle, entier=entier)
            if resultat >= mini and (maxi is None or resultat <= maxi):
                return resultat
        except ValueError:
            pass
        self.a_verifier.append(libelle)
        return defaut

    def cases(self, nom):
        champ = self.champs.get(nom)
        if champ is None:
            return set()
        ref = champ.indirect_reference
        original = ref.get_object() if ref is not None else champ
        valeurs = [champ.get('/V'), original.get('/AS')]
        valeurs.extend(enfant.get_object().get('/AS') for enfant in champ.get('/Kids', ()))
        actives = {str(v) for v in valeurs if isinstance(v, str) and v not in ('', '/Off', '/None')}
        self.renseigne |= bool(actives)
        return actives

    def choix(self, nom, options, libelle):
        actives = self.cases(nom)
        if not actives:
            return None
        if len(actives) == 1 and (valeur := next(iter(actives))) in options:
            return options[valeur]
        self.a_verifier.append(libelle)
        return None


def _adresse(pdf, professionnel):
    departement, commune = pdf.texte('a1'), pdf.texte('a2')
    numero, voie = ('a3', 'a4') if professionnel else ('a4', 'a3')
    rue = ' '.join(filter(None, (pdf.texte(numero), pdf.texte(voie))))
    if not rue or not commune:
        pdf.a_verifier.append('adresse du bien')
    return ', '.join(filter(None, (rue, commune))), commune, departement


def _etage_h2(pdf):
    valeur = pdf.texte('a7').upper()
    if valeur in ('RC', 'RDC', 'REZ-DE-CHAUSSÉE', 'REZ-DE-CHAUSSEE'):
        return 0
    if valeur in ('E', 'ENTRESOL'):
        return 1
    niveau = re.fullmatch(r'(\d{1,2})(?:ER|E|ÈME|EME|ᵉ)?', valeur, re.IGNORECASE)
    if niveau and int(niveau[1]) <= 80:
        return int(niveau[1])
    pdf.a_verifier.append('niveau du logement pour le correctif d’ascenseur')
    return 0


def _dependances_h1(pdf):
    lignes = []
    for i in range(3):
        debut = 18 + i * 6
        composition = {cle: {'surface': pdf.nombre(f'b{debut+n}', f'dépendance {i+1} · {libelle}')}
                       for n, (cle, libelle) in enumerate(SURFACES_DEP_H1.items())}
        surface = sum(element['surface'] for element in composition.values())
        nature = pdf.texte(f'b{debut+5}')
        eau = bool(pdf.cases(f'cac{25+i*2}'))
        electricite = bool(pdf.cases(f'cac{26+i*2}'))
        codes_murs = pdf.texte(f'ldcm{1+i*3}').split()
        codes_toiture = pdf.texte(f'ldcm{2+i*3}').split()
        code_entretien = pdf.texte(f'ldcm{3+i*3}')
        if surface or nature or eau or electricite or codes_murs or codes_toiture or code_entretien:
            lignes.append(dict(type='batiment_h1', composition=composition, surface=surface, designation=f'Dépendance {i+1}',
                               nature_agrement=nature, eau=eau, electricite=electricite,
                               materiaux_murs=[m for m, code in MURS_CODES.items() if code in codes_murs],
                               materiaux_toitures=[m for m, code in TOITURES_CODES.items() if code in codes_toiture],
                               etat_entretien=next((e for e, code in ENTRETIEN_CODES.items() if code == code_entretien), None)))
    return lignes


def _dependances_h2(pdf):
    lignes = []
    for type_, debuts in LIGNES_DEP_H2.items():
        for i, debut in enumerate(debuts):
            case = PREMIERE_CASE_DEP_H2[type_] + 2 * i
            ligne = dict(type=type_, lot=pdf.texte(f'b{debut}'), designation=pdf.texte(f'b{debut+1}'),
                         batiment=pdf.texte(f'b{debut+2}'), etage_description=pdf.texte(f'b{debut+3}'),
                         surface=pdf.nombre(f'b{debut+4}', f'surface de la dépendance {type_} {i+1}'),
                         eau=bool(pdf.cases(f'cacb{case}')), electricite=bool(pdf.cases(f'cacb{case+1}')))
            if type_ == 'piece':
                ligne.update({cle: pdf.nombre(f'b{debut+5+n}', f'{cle} · chambre de service {i+1}', entier=True)
                              for n, cle in enumerate(SANITAIRES)})
                ligne['pieces_chauffees'] = int(bool(pdf.cases(f'cacb{27+i}')))
            if any(v for cle, v in ligne.items() if cle != 'type'):
                lignes.append(ligne)
    return lignes


def _habitation(pdf, modele):
    maison = modele == 'h1'
    adresse, _, _ = _adresse(pdf, False)
    pieces = {cle: pdf.nombre(f'b{i}', libelle, entier=True, maxi=100)
              for i, (cle, libelle) in enumerate(PIECES_HABITATION.items(), 1 if maison else 5)}
    surface = pdf.nombre('b7' if maison else 'b11', 'surface du logement', maxi=20_000)
    if not surface:
        pdf.a_verifier.append('surface du logement')
    if not sum(pieces.values()):
        pdf.a_verifier.append('nombre de pièces du logement')
    equipements = {cle: bool(pdf.cases(f'cac{i}'))
                   for i, cle in enumerate(EQUIPEMENTS_H1 if maison else EQUIPEMENTS_H2, 2 if maison else 1)}
    chauffage = equipements.pop('chauffage')
    partie_pro = pdf.choix('cac1' if maison else 'cac0',
                          {'/Oui': True, '/Non': False} if maison else {'/1': True, '/2': False},
                          'déclaration de la partie professionnelle')
    description = dict(pieces=pieces, chauffage=chauffage, partie_professionnelle=partie_pro is not None,
                       declaration_6660=partie_pro is True)
    sanitaires = ('b12', 'b13', 'b14', 'b15') if maison else ('b14', 'b14bis', 'b14ter', 'b14quater')
    params = dict(equipements, terrasse=pdf.nombre('b11' if maison else 'b12', 'terrasse', maxi=10_000))
    params.update({cle: pdf.nombre(nom, cle, entier=True, maxi=100) for nom, cle in zip(sanitaires, SANITAIRES)})
    if maison:
        description.update(
            annee_construction=pdf.nombre('b16', 'année de construction', entier=True, mini=1, maxi=9999, defaut=None),
            niveaux_habitables=pdf.nombre('b17', 'niveaux habitables', entier=True, mini=1, defaut=None),
            emprises={cle: pdf.nombre(f'b{i}', 'emprise ' + cle, defaut=None)
                      for i, cle in enumerate(('maison', 'dependances', 'terrains'), 40)},
            materiaux_murs=[m for i, m in enumerate(MURS_CODES, 7) if pdf.cases(f'cac{i}')],
            materiaux_toitures=[m for i, m in enumerate(TOITURES_CODES, 14) if pdf.cases(f'cac{i}')],
        )
        entretien = pdf.choix('cac19', {f'/{code}': e for e, code in ENTRETIEN_CODES.items()}, 'état d’entretien')
        if entretien:
            params['entretien'] = entretien
        params['elements_incorpores'] = {cle: {'surface': pdf.nombre(f'b{i}', cle + ' incorporés')}
                                         for i, cle in enumerate(('garages', 'caves', 'greniers'), 8)}
        dependances = _dependances_h1(pdf)
    else:
        description['escalier_service'] = params.pop('escalier_service')
        params['etage'] = _etage_h2(pdf)
        dependances = _dependances_h2(pdf)
    if dependances and any(not ligne['surface'] for ligne in dependances):
        pdf.a_verifier.append('surfaces des dépendances')
    return dict(recherche=adresse, nature='M' if maison else 'A', surface=surface,
                parametres=params, dependances=dependances, **{modele: description, f'dependances_{modele}': dependances})


def _achevement(pdf):
    valeur = pdf.texte('a18')
    if not valeur:
        return None
    chiffres = re.sub(r'[ ./-]', '', valeur)
    try:
        annee = int(chiffres) if re.fullmatch(r'\d{4}', chiffres) else datetime.strptime(chiffres, '%d%m%Y').year
        if 1900 <= annee <= date.today().year:
            return annee
    except ValueError:
        pass
    pdf.a_verifier.append('année d’achèvement des travaux')
    return None


def _professionnel(pdf):
    adresse, commune, departement = _adresse(pdf, True)
    categorie = pdf.choix('cac6', {f'/{i}': v for i, v in enumerate(CATEGORIES_6660, 1)}, 'catégorie du local')
    parcelle = pdf.texte('a9')
    parties = re.fullmatch(r'(?:(\d{3})[ -]*)?([A-Z]{1,2}|0[A-Z]|\d{2})[ -]*(\d{1,4})', parcelle.upper())
    reference = {'commune': commune, 'departement': departement}
    if parties and int(parties[3]):
        reference.update(prefixe=parties[1] or '', section=parties[2], numero=parties[3])
    surfaces = {cle: pdf.nombre(f'd{i}', 'surface ' + cle, maxi=1_000_000)
                for i, cle in enumerate(COEFF_SURFACES, 1)}
    if not categorie:
        pdf.a_verifier.append('catégorie du local')
    if not any(surfaces.values()):
        pdf.a_verifier.append('surfaces professionnelles')
    neuf = bool(pdf.cases('construction_neuve')) or '/1' in pdf.cases('cac')
    annee = _achevement(pdf)
    if neuf and annee is None:
        pdf.a_verifier.append('année d’achèvement des travaux')
    return dict(recherche=adresse, reference=reference, parcelle_declaree=parcelle, categorie=categorie,
                surfaces=surfaces, construction_nouvelle=neuf, annee_achevement=annee)


def lire_cerfa(contenu):
    """Importe les données de simulation, sans reprendre les coordonnées du propriétaire."""
    if len(contenu) > TAILLE_MAX_CERFA:
        raise ValueError('Choisissez un PDF de 10 Mo maximum.')
    try:
        lecteur = PdfReader(BytesIO(contenu))
        if lecteur.is_encrypted:
            raise ValueError('Ouvrez puis enregistrez une copie du Cerfa sans mot de passe avant de l’importer.')
        champs = lecteur.get_fields() or {}
        if not champs:
            raise ValueError('Ce PDF ne contient aucun champ de formulaire. Importez le Cerfa interactif rempli ou utilisez la saisie manuelle.')
        modeles = [modele for modele, signature in SIGNATURES.items() if signature <= champs.keys()]
        if len(modeles) != 1:
            raise ValueError('Version de Cerfa non reconnue. Utilisez un H1, H2 ou 6660-REV au format PDF interactif pris en charge par le simulateur.')
        modele = modeles[0]
        pdf = ChampsCerfa(champs)
        saisie = _professionnel(pdf) if modele == '6660-rev' else _habitation(pdf, modele)
        if not pdf.renseigne:
            raise ValueError('Aucune donnée de simulation renseignée dans ce Cerfa. Vérifiez que vous avez enregistré le PDF après l’avoir rempli.')
        if modele != '6660-rev' and any(pdf.texte(cle) for cle in champs if cle.startswith('annexe_dependance_')):
            pdf.a_verifier.append('dépendances sur les feuilles complémentaires, à reporter dans le cadre 5')
        return modele, saisie, list(dict.fromkeys(pdf.a_verifier))
    except (PyPdfError, KeyError, TypeError, AttributeError, RecursionError) as exc:
        raise ValueError('Le PDF est illisible. Ouvrez le document et enregistrez une nouvelle copie avant de réessayer.') from exc
