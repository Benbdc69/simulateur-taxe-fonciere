"""Rapport de pré-audit produit à partir d'une évaluation et de ses hypothèses saisies."""

from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO

from docx import Document
from docx.shared import Cm, Pt, RGBColor

from montants import euro_arrondi
from moteur import COEFF_SURFACES, TAXES_AVANT_2021


VENTILATIONS = {
    'inconnue': 'Ventilation à confirmer',
    'documentee': 'Déclaration 6660-REV ou fiche d’évaluation cadastrale',
    'estimee': 'Ventilation estimée',
}


def bilan_preaudit(evaluation, audit):
    analyse = evaluation['analyse']
    resultat = analyse.get('result') or {}
    montant_avis = audit.get('montant_avis')
    ventilation = audit.get('ventilation', 'inconnue')
    total = (evaluation.get('frais') or {}).get('total')
    montant = total if total is not None else resultat.get('total_hors_frais')
    if ventilation == 'inconnue':
        montant = None
        suite = 'Confirmer la ventilation P1/P2 avec la 6660-REV, la fiche cadastrale ou un plan coté.'
    elif montant is None:
        suite = 'Vérifier les paramètres fiscaux manquants indiqués en annexe.'
    elif montant_avis is None:
        suite = 'Isoler le montant de l’avis pour ce local et ce millésime.'
    elif total is None:
        suite = 'Vérifier les frais pour rapprocher le montant estimé du total de l’avis.'
    else:
        suite = 'Vérifier les bases et le classement retenus sur la fiche d’évaluation cadastrale.'
    ecart = None
    if montant_avis is not None and montant is not None and total is not None:
        avis_arrondi = Decimal(str(montant_avis)).quantize(Decimal(1), rounding=ROUND_HALF_UP)
        estimation_arrondie = Decimal(str(montant)).quantize(Decimal(1), rounding=ROUND_HALF_UP)
        ecart = avis_arrondi - estimation_arrondie
    return {
        'avis': montant_avis, 'estimation': montant, 'ecart': ecart,
        'frais_inclus': total is not None, 'suite': suite,
    }


def _nb(valeur, decimales=2):
    return '—' if valeur is None else f'{float(valeur):,.{decimales}f}'.replace(',', ' ').replace('.', ',')


def _table(document, titres, lignes):
    table = document.add_table(rows=1, cols=len(titres))
    table.style = 'Light Shading Accent 1'
    for cellule, titre in zip(table.rows[0].cells, titres):
        cellule.text = titre
    for valeurs in lignes:
        for cellule, valeur in zip(table.add_row().cells, valeurs):
            cellule.text = str(valeur)
    for ligne in table.rows:
        for cellule in ligne.cells:
            paragraphe = cellule.paragraphs[0]
            paragraphe.paragraph_format.space_after = Pt(2)
            for texte in paragraphe.runs:
                texte.font.size = Pt(10)


def creer_word_preaudit(evaluation, audit, *, societe='', local=''):
    doc = Document()
    doc.core_properties.title = 'Pré-audit de taxe foncière'
    section = doc.sections[0]
    section.page_width, section.page_height = Cm(21), Cm(29.7)
    section.top_margin, section.bottom_margin = Cm(1.8), Cm(1.8)
    section.left_margin, section.right_margin = Cm(2), Cm(2)
    normal = doc.styles['Normal']
    normal.font.name, normal.font.size = 'Calibri', Pt(11)
    normal.paragraph_format.space_after = Pt(6)
    for nom in ('Title', 'Heading 1', 'Heading 2'):
        doc.styles[nom].font.color.rgb = RGBColor.from_string('164C50')

    analyse = evaluation['analyse']
    resultat = analyse.get('result') or {}
    partial = analyse.get('partial', {})
    bien = evaluation['bien']
    surfaces = evaluation.get('surfaces', {})
    ventilation = audit.get('ventilation', 'inconnue')
    bilan = bilan_preaudit(evaluation, audit)
    doc.add_heading('Pré-audit de taxe foncière', level=0)
    doc.add_paragraph(' · '.join(filter(None, (societe, local if local != evaluation['adresse'] else '',
        evaluation['adresse'], str(evaluation['annee'])))))
    doc.add_paragraph(f"Catégorie {evaluation['categorie']} · Parcelle {bien.get('section', '')} {bien.get('numero', '')} · INSEE {bien.get('code_insee', '')}")

    doc.add_heading('Montants comparés', level=1)
    libelle_estimation = 'Estimation frais inclus' if bilan['frais_inclus'] else 'Estimation hors frais'
    lignes = [
        ('Montant de l’avis', bilan['avis']),
        (libelle_estimation, bilan['estimation']),
        ('Écart indicatif · avis moins estimation', bilan['ecart']),
    ]
    _table(doc, ('Montant', 'Valeur'), [(nom, euro_arrondi(val) if val is not None else '—') for nom, val in lignes])

    doc.add_heading('Constats', level=1)
    surface_batie = audit.get('surface_batie')
    total_saisi = surfaces.get('P1', 0) + surfaces.get('P2', 0)
    if surface_batie is not None:
        doc.add_paragraph(f"Surface bâtie mesurée · {_nb(surface_batie)} m².")
    if total_saisi and (surface_batie is None or ventilation == 'documentee'):
        doc.add_paragraph(f"Surface bâtie saisie (P1 + P2) · {_nb(total_saisi)} m².")
    doc.add_paragraph(VENTILATIONS[ventilation] + '.')
    if analyse.get('missing') or analyse.get('neutral_warnings') or (analyse.get('planchonnement') or {}).get('reserve'):
        doc.add_paragraph('Les paramètres à confirmer figurent en annexe.')
    if audit.get('observation'):
        doc.add_paragraph(' '.join(audit['observation'].split()))
    doc.add_heading('Vérification prioritaire', level=1)
    doc.add_paragraph(bilan['suite'])
    doc.add_paragraph('Montants indicatifs arrondis à l’euro et soumis à confirmation des données cadastrales.', style='Caption')

    doc.add_page_break()
    doc.add_heading('Annexe · Données de la simulation', level=0)
    doc.add_paragraph(
        f"Secteur {partial.get('secteur') or '—'} · Tarif {_nb(partial.get('tarif'))} €/m² "
        f"· Localisation {_nb(partial.get('localisation'), 4)}"
    )
    doc.add_paragraph(f"Valeur locative brute · {_nb(partial.get('valeur_locative_brute'))} €.")
    pk2_mesure = (evaluation.get('mesures') or {}).get('pk2')
    if pk2_mesure is not None:
        doc.add_paragraph(f"Stationnement non couvert mesuré · {_nb(pk2_mesure)} m².")
    if ventilation == 'inconnue':
        doc.add_paragraph('Les valeurs P1 et P2 ci-dessous sont les hypothèses saisies dans le simulateur.')
    _table(doc, ('Surface', 'm² saisis', 'Pondération'),
           [(cle, _nb(surfaces.get(cle, 0)), _nb(poids)) for cle, poids in COEFF_SURFACES.items()])
    if resultat.get('lignes'):
        doc.add_heading('Calcul par composante', level=1)
        _table(doc, ('Taxe', 'Taux (%)', 'Neutralisation', 'Planchonnement (€)', 'Base (€)', 'Cotisation (€)'),
               [(ligne['taxe'], _nb(ligne.get('taux_pct')), _nb(ligne.get('coefficient_neutralisation'), 6),
                 _nb(ligne.get('correction_planchonnement')), _nb(ligne.get('base_taxable')), _nb(ligne.get('montant')))
                for ligne in resultat['lignes']])
    frais = evaluation.get('frais') or {}
    if frais.get('frais') is not None:
        doc.add_paragraph(f"Frais de gestion estimés · {_nb(frais['frais'])} €.")
    if frais.get('note'):
        doc.add_paragraph(frais['note'])
    if analyse.get('missing'):
        doc.add_paragraph('Données manquantes · ' + ', '.join(analyse['missing']) + '.')
    reserve = (analyse.get('planchonnement') or {}).get('reserve')
    if reserve:
        doc.add_paragraph(reserve)
    for alerte in analyse.get('neutral_warnings') or ():
        doc.add_paragraph(alerte)
    taux = analyse.get('taux') or {}
    if any(taux.values()):
        doc.add_heading('Sources des taux', level=1)
        _table(doc, ('Part', 'Taux (%)', 'Année de source', 'Source'),
               [(TAXES_AVANT_2021.get(cle, cle), _nb(taux_cle.get('taux')),
                 taux_cle.get('annee_source') or '—', taux_cle.get('source') or '—')
                for cle, taux_cle in taux.items() if taux_cle])
    flux = BytesIO()
    doc.save(flux)
    return flux.getvalue()


MIME_WORD = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
