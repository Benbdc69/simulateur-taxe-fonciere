"""Préremplissage des PDF Cerfa interactifs à partir des données déclaratives."""
from io import BytesIO
from math import floor
from pathlib import Path
import re

from pypdf import PdfReader, PdfWriter
from pypdf.generic import NameObject, NumberObject, TextStringObject
from reportlab.pdfgen import canvas

from dependances_habitation import TYPES
from moteur import nom_commune_cadastrale
from moteur_habitation import ENTRETIEN
from referentiel_formulaires import (EQUIPEMENTS_H1, EQUIPEMENTS_H2, LIGNES_DEP_H2, MURS, PIECES_HABITATION,
                                    PREMIERE_CASE_DEP_H2, SURFACES_DEP_H1, TOITURES)

MODELES = Path(__file__).resolve().parent / 'data' / 'cerfa'
GROUPES_6660 = {'MAG': 7, 'BUR': 3, 'DEP': 5, 'ATE': 3, 'HOT': 5,
                'SPE': 7, 'ENS': 2, 'CLI': 4, 'IND': 2, 'EXC': 1}
CATEGORIES_6660 = [f'{groupe}{i}' for groupe, total in GROUPES_6660.items()
                   for i in range(1, total + 1)]
SANITAIRES = ('wc', 'baignoires', 'douches', 'lavabos')
MURS_CODES = dict(zip(MURS, '1234569'))
TOITURES_CODES = dict(zip(TOITURES, '12349'))
ENTRETIEN_CODES = dict(zip(ENTRETIEN, '12345'))
GROUPES_EXCLUSIFS = {'6660-rev': {'cac6', 'cac11'}, 'h2': {'cac0'}, 'h1': {'cac1', 'cac19'}}


def surface_declaree(surface):
    return floor(surface) if surface is not None else None


def cocher(etat, valeur='/Oui'):
    return valeur if etat else None


def situation(adresse, parcelle):
    commune = adresse.get('commune') or parcelle.get('commune', '')
    insee = parcelle.get('code_insee') or parcelle.get('insee') or adresse.get('insee', '')
    departement = parcelle.get('departement') or adresse.get('departement')
    if not departement and insee:
        departement = insee[:3] if insee.startswith(('97', '98')) else insee[:2]
    commune = nom_commune_cadastrale({}, departement, insee, commune)
    return departement, commune, adresse.get('voie'), adresse.get('numero_voirie')


def champs_professionnel(dossier):
    bien = dossier['bien']
    departement, commune, voie, numero = situation(dossier.get('adresse_declaree', {}), bien)
    parcelle = ' '.join(bien[k] for k in ('prefixe', 'section', 'numero') if bien.get(k))
    categorie = dossier['categorie']
    return {
        'a1': departement, 'a2': commune, 'a3': numero, 'a4': voie, 'a9': parcelle,
        'a18': f"    {dossier['annee_achevement']:04d}" if dossier.get('annee_achevement') else None,
        'construction_neuve': cocher(dossier.get('construction_nouvelle'), '/1'),
        'cac6': f'/{CATEGORIES_6660.index(categorie) + 1}' if categorie in CATEGORIES_6660 else None,
        **{f'd{i}': surface_declaree(dossier['surfaces'].get(cle))
           for i, cle in enumerate(('P1', 'P2', 'P3', 'PK1', 'PK2'), 1)},
    }


def champs_habitation(saisie, modele):
    maison = modele == 'h1'
    adresse = saisie['adresse']
    departement, commune, voie, numero = situation(adresse, saisie.get('parcelle') or {})
    description = saisie.get(modele, {})
    params = saisie['parametres']
    champs = {'a1': departement, 'a2': commune, 'a3': voie, 'a4': numero}
    for i, cle in enumerate(PIECES_HABITATION, 1 if maison else 5):
        champs[f'b{i}'] = description.get('pieces', {}).get(cle)
    champs['b7' if maison else 'b11'] = surface_declaree(saisie.get('surface'))
    champs['b11' if maison else 'b12'] = surface_declaree(params.get('terrasse'))
    numeros = ('b12', 'b13', 'b14', 'b15') if maison else ('b14', 'b14bis', 'b14ter', 'b14quater')
    champs.update({champ: params.get(cle) for champ, cle in zip(numeros, SANITAIRES)})

    equipements = {**params, **description}
    if maison:
        champs.update({f'cac{i}': cocher(equipements.get(cle)) for i, cle in enumerate(EQUIPEMENTS_H1, 2)})
        for i, cle in enumerate(('garages', 'caves', 'greniers'), 8):
            champs[f'b{i}'] = surface_declaree(params.get('elements_incorpores', {}).get(cle, {}).get('surface'))
        for champ, materiau in zip(range(7, 14), MURS):
            champs[f'cac{champ}'] = cocher(materiau in description.get('materiaux_murs', []))
        for champ, materiau in zip(range(14, 19), TOITURES):
            champs[f'cac{champ}'] = cocher(materiau in description.get('materiaux_toitures', []))
        entretien = ENTRETIEN_CODES.get(params.get('entretien'))
        champs.update(cac19=f'/{entretien}' if entretien else None,
                      b16=description.get('annee_construction'), b17=description.get('niveaux_habitables'))
        for champ, cle in zip(('b40', 'b41', 'b42'), ('maison', 'dependances', 'terrains')):
            champs[champ] = surface_declaree(description.get('emprises', {}).get(cle))
    else:
        champs.update({f'cac{i}': cocher(equipements.get(cle), f'/{chr(96 + i)}' if i <= 3 else '/a')
                       for i, cle in enumerate(EQUIPEMENTS_H2, 1)})
    if description.get('partie_professionnelle'):
        declaree = description.get('declaration_6660')
        champ = 'cac1' if maison else 'cac0'
        champs[champ] = ('/Oui' if declaree else '/Non') if maison else ('/1' if declaree else '/2')
    return champs


def dependances_h1(champs, dependances):
    for i, ligne in enumerate(dependances[:3]):
        debut = 18 + i * 6
        for n, cle in enumerate(SURFACES_DEP_H1):
            champs[f'b{debut+n}'] = surface_declaree(ligne.get('composition', {}).get(cle, {}).get('surface'))
        champs[f'b{debut+5}'] = ligne.get('nature_agrement')
        champs[f'cac{25+i*2}'] = cocher(ligne.get('eau'))
        champs[f'cac{26+i*2}'] = cocher(ligne.get('electricite'))
        champs[f'ldcm{1+i*3}'] = ' '.join(MURS_CODES[m] for m in ligne.get('materiaux_murs', []) if m in MURS_CODES)
        champs[f'ldcm{2+i*3}'] = ' '.join(TOITURES_CODES[m] for m in ligne.get('materiaux_toitures', []) if m in TOITURES_CODES)
        champs[f'ldcm{3+i*3}'] = ENTRETIEN_CODES.get(ligne.get('etat_entretien'))
    return dependances[3:]


def dependances_h2(champs, dependances):
    index = dict.fromkeys(LIGNES_DEP_H2, 0)
    excedent = []
    for ligne in dependances:
        type_ = ligne['type']
        i = index.get(type_, 0)
        if i >= len(LIGNES_DEP_H2.get(type_, ())):
            excedent.append(ligne)
            continue
        index[type_] += 1
        debut = LIGNES_DEP_H2[type_][i]
        designation = ligne.get('designation') or TYPES[type_]
        valeurs = (ligne.get('lot'), designation, ligne.get('batiment'),
                   ligne.get('etage_description'), surface_declaree(ligne.get('surface')))
        champs.update({f'b{debut+n}': valeur for n, valeur in enumerate(valeurs)})
        case = PREMIERE_CASE_DEP_H2[type_] + i * 2
        champs[f'cacb{case}'] = cocher(ligne.get('eau'))
        champs[f'cacb{case+1}'] = cocher(ligne.get('electricite'))
        if type_ == 'piece':
            champs.update({f'b{debut+5+n}': ligne.get(cle) for n, cle in enumerate(SANITAIRES)})
            champs[f'cacb{27+i}'] = cocher(ligne.get('pieces_chauffees', 0) > 0)
    return excedent


def ajouter_annexe(writer, modele, dependances):
    """Ajoute une feuille complémentaire éditable si le tableau Cerfa est plein."""
    flux = BytesIO()
    pdf = canvas.Canvas(flux, pagesize=(595, 842))
    valeurs = {}
    for i, ligne in enumerate(dependances, 1):
        emplacement = (i - 1) % 4
        if emplacement == 0:
            pdf.setFont('Helvetica-Bold', 13)
            pdf.drawString(35, 803, f'Déclaration {modele.upper()} – Suite du cadre 5')
        y = 770 - emplacement * 185
        pdf.setFont('Helvetica', 10)
        pdf.drawString(35, y, f'Dépendance supplémentaire {i}')
        libelles = {
            'type': 'Type', 'designation': 'Désignation', 'lot': 'Lot',
            'batiment': 'Bâtiment', 'etage_description': 'Étage',
            'situation': 'Situation', 'nature_agrement': 'Pur agrément',
            'etat_entretien': 'État d’entretien',
        }
        details = [f'{libelle} : {TYPES.get(ligne.get(cle), ligne.get(cle)) if cle == "type" else ligne[cle]}'
                   for cle, libelle in libelles.items() if ligne.get(cle)]
        if modele == 'h1':
            details.extend(f'{libelle} : {surface_declaree(element["surface"])} m²'
                           for cle, libelle in SURFACES_DEP_H1.items()
                           if (element := ligne.get('composition', {}).get(cle, {})).get('surface'))
            details.extend(', '.join(ligne[cle]) for cle in ('materiaux_murs', 'materiaux_toitures') if ligne.get(cle))
        elif ligne.get('surface') is not None:
            details.append(f'Surface : {surface_declaree(ligne["surface"])} m²')
        confort = [libelle for cle, libelle in (('eau', 'Eau courante'), ('electricite', 'Électricité'))
                   if ligne.get(cle)]
        confort.extend(f'{cle.replace("_", " ")} : {ligne[cle]}'
                       for cle in (*SANITAIRES, 'pieces_chauffees') if ligne.get(cle))
        if confort:
            details.append('Confort : ' + ', '.join(confort))
        champ = f'annexe_dependance_{i}'
        valeurs[champ] = '\n'.join(details)
        pdf.acroForm.textfield(name=champ, x=35, y=y-155, width=525, height=144,
                               maxlen=2500, fontSize=9, fieldFlags='multiline', forceBorder=True)
        if emplacement == 3 or i == len(dependances):
            pdf.showPage()
    pdf.save()
    debut = len(writer.pages)
    writer.append(PdfReader(flux), import_outline=False)
    writer.update_page_form_field_values(list(writer.pages[debut:]), valeurs, auto_regenerate=False)


def preparer_pdf(modele):
    reader = PdfReader(MODELES / f'{modele}.pdf')
    writer = PdfWriter()
    writer.append(reader, import_outline=False)
    acroform = writer.root_object['/AcroForm']
    champs = acroform['/Fields']
    for page in writer.pages:
        page.pop('/AA', None)
    for ref in list(champs):
        champ = ref.get_object()
        nom = champ.get('/T')
        if modele == 'h2' and nom == 'b13':
            # Coefficient de terrasse dans la zone teintée du cadre 41 B.
            champs.remove(ref)
            writer.pages[1]['/Annots'].remove(ref)
            continue
        for objet in (champ, *(enfant.get_object() for enfant in champ.get('/Kids', ()))):
            objet.pop('/AA', None)
            objet.pop('/A', None)
        if modele == '6660-rev' and nom == 'cac':
            # Le fichier source regroupe deux cases déclaratives différentes sous le même nom.
            champs.remove(ref)
            for enfant, nom_independant in zip(champ['/Kids'], ('construction_neuve', 'modification_local')):
                widget = enfant.get_object()
                widget.pop('/Parent', None)
                widget[NameObject('/FT')] = NameObject('/Btn')
                widget[NameObject('/T')] = TextStringObject(nom_independant)
                champs.append(enfant)
        if modele == 'h1' and re.fullmatch(r'ldcm[1-9]', nom or ''):
            # La notice autorise plusieurs codes de matériaux, même si le PDF source impose un seul choix.
            champ[NameObject('/FT')] = NameObject('/Tx')
            champ[NameObject('/Ff')] = NumberObject(0)
            for cle in ('/Opt', '/I', '/AP', '/V', '/DV'):
                champ.pop(cle, None)
        if nom in GROUPES_EXCLUSIFS[modele]:
            champ[NameObject('/Ff')] = NumberObject(1 << 15)
    return writer


def creer_cerfa(modele, dossier, complements=None):
    writer = preparer_pdf(modele)
    if modele == '6660-rev':
        champs = champs_professionnel(dossier)
        excedent = []
    else:
        champs = champs_habitation(dossier, modele)
        dependances = dossier.get('dependances', [])
        exporter_dependances = dependances_h1 if modele == 'h1' else dependances_h2
        excedent = exporter_dependances(champs, dependances)

    champs.update(complements or {})
    valeurs = {nom: str(valeur) for nom, valeur in champs.items() if valeur is not None and valeur != ''}
    for page in writer.pages:
        if page.get('/Annots'):
            writer.update_page_form_field_values(page, valeurs, auto_regenerate=False)
    if excedent:
        ajouter_annexe(writer, modele, excedent)
    flux = BytesIO()
    writer.write(flux)
    return flux.getvalue()
