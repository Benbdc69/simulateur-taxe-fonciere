"""Rapport de pré-audit produit à partir d'une évaluation et de ses hypothèses saisies."""

from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
from pathlib import Path

from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor

from montants import euro_arrondi
from moteur import COEFF_SURFACES, TAXES_AVANT_2021


LOGO_AXENS = Path(__file__).resolve().parent / 'data' / 'identite_axens' / 'logo.png'
BLEU_AXENS = '0E3047'
GRIS_AXENS = '5F6E6C'
IVOIRE_AXENS = 'EEEDE3'

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
    if ventilation == 'inconnue' or evaluation['categorie'] == 'EXC1':
        montant = None
    ecart = None
    if montant_avis is not None and montant is not None and total is not None:
        avis_arrondi = Decimal(str(montant_avis)).quantize(Decimal(1), rounding=ROUND_HALF_UP)
        estimation_arrondie = Decimal(str(montant)).quantize(Decimal(1), rounding=ROUND_HALF_UP)
        ecart = avis_arrondi - estimation_arrondie
    constat, suite = _conclusion_preaudit(evaluation, ventilation, montant_avis, montant, ecart)
    return {
        'avis': montant_avis, 'estimation': montant, 'ecart': ecart,
        'frais_inclus': total is not None, 'constat': constat, 'suite': suite,
    }


def _conclusion_preaudit(evaluation, ventilation, montant_avis, estimation, ecart):
    if evaluation['categorie'] == 'EXC1':
        return (
            'Ce local relève d’une méthode d’évaluation particulière.',
            'Vérifiez la valeur vénale retenue dans la fiche d’évaluation cadastrale pour établir une estimation '
            'comparable et apprécier l’intérêt d’une démarche.',
        )
    if ventilation == 'inconnue':
        return (
            'La ventilation des surfaces est nécessaire pour chiffrer l’écart.',
            'Demandez la fiche d’évaluation cadastrale ou la déclaration 6660-REV pour distinguer les surfaces '
            'principales et secondaires. La mesure de l’emprise donne un repère pour la surface au sol. '
            'Une fois la répartition vérifiée, nous pourrons reprendre la comparaison.',
        )
    if estimation is None:
        return (
            'L’estimation reste à compléter.',
            'Vérifiez les données fiscales signalées en annexe pour reconstituer la cotisation et apprécier l’écart.',
        )
    if montant_avis is None:
        return (
            'Le montant de l’avis pour ce local reste à isoler.',
            'Identifiez la cotisation propre au local et à l’année étudiés, avec les mêmes taxes annexes et frais '
            'que l’estimation, avant de décider d’une suite.',
        )
    if ecart is None:
        return (
            'L’estimation est disponible hors frais de gestion.',
            'Vérifiez les frais et les taxes annexes figurant sur l’avis pour comparer des montants à périmètre identique.',
        )

    if ecart > 0:
        constat = f'Le montant de votre avis dépasse notre estimation de {euro_arrondi(ecart)}.'
    elif ecart < 0:
        constat = f'Votre avis est inférieur de {euro_arrondi(-ecart)} à notre estimation.'
    else:
        constat = 'Votre avis et notre estimation concordent à l’euro près.'

    analyse = evaluation['analyse']
    taux = analyse.get('taux') or {}
    taux_anterieurs = any(part and part.get('decalage', 0) > 0 for part in taux.values())
    teom = taux.get('teom') or {}
    zonage_a_verifier = teom.get('zonage_confirme') is False and teom.get('taux', 0) > 0
    reserves = [libelle for a_verifier, libelle in (
        (ventilation == 'estimee', 'la répartition des surfaces'),
        (taux_anterieurs, 'les taux de l’année étudiée'),
        (zonage_a_verifier, 'le zonage de la taxe d’enlèvement des ordures ménagères'),
        (analyse.get('neutral_warnings'), 'les coefficients de neutralisation'),
        ((analyse.get('planchonnement') or {}).get('reserve'), 'le planchonnement'),
        ((analyse.get('exoneration_neuf') or {}).get('a_verifier'), 'l’exonération de construction nouvelle'),
    ) if a_verifier]
    if reserves:
        suite = (
            f'Le rapprochement reste provisoire. Vérifiez {", ".join(reserves)}, puis recalculez la cotisation '
            'avant de vous prononcer sur l’intérêt d’une réclamation.'
        )
    elif ecart > 0:
        suite = (
            'Rapprochez la fiche d’évaluation cadastrale de la déclaration 6660-REV et de la situation du local '
            'au 1er janvier de l’année d’imposition (CGI, art. 1415). Vérifiez en priorité le classement, '
            'les surfaces et leur répartition. Envisagez une réclamation si ce contrôle documente une erreur '
            'qui majore la cotisation et si le gain attendu justifie le coût de la démarche.'
        )
    else:
        suite = (
            'Une demande de réduction paraît peu opportune au vu des montants comparés. Si vous avez relevé '
            'une erreur précise dans la description ou le classement du local, un contrôle ciblé de la fiche '
            'd’évaluation reste utile.'
        )
    return constat, suite


def _nb(valeur, decimales=2):
    return '—' if valeur is None else f'{float(valeur):,.{decimales}f}'.replace(',', ' ').replace('.', ',')


def _table(document, titres, lignes, largeurs, colonnes_numeriques):
    table = document.add_table(rows=1, cols=len(titres))
    table.autofit = False
    for colonne, largeur in zip(table.columns, largeurs):
        colonne.width = Cm(largeur)
    for numero, valeurs in enumerate((titres, *lignes)):
        entete = numero == 0
        ligne = table.rows[0] if entete else table.add_row()
        proprietes = ligne._tr.get_or_add_trPr()
        proprietes.append(OxmlElement('w:cantSplit'))
        fond = IVOIRE_AXENS if numero % 2 else 'FFFFFF'
        if entete:
            fond = BLEU_AXENS
            proprietes.append(OxmlElement('w:tblHeader'))
        for index, (cellule, valeur, largeur) in enumerate(zip(ligne.cells, valeurs, largeurs)):
            cellule.width = Cm(largeur)
            trame = OxmlElement('w:shd')
            trame.set(qn('w:fill'), fond)
            cellule._tc.get_or_add_tcPr().append(trame)
            paragraphe = cellule.paragraphs[0]
            paragraphe.paragraph_format.space_before = Pt(3)
            paragraphe.paragraph_format.space_after = Pt(3)
            paragraphe.paragraph_format.keep_with_next = entete
            if index in colonnes_numeriques:
                paragraphe.alignment = WD_ALIGN_PARAGRAPH.RIGHT
            texte = paragraphe.add_run(str(valeur))
            texte.font.size = Pt(9)
            if entete:
                texte.bold = True
                texte.font.color.rgb = RGBColor.from_string('FFFFFF')


def _mise_en_page(doc):
    section = doc.sections[0]
    section.page_width, section.page_height = Cm(21), Cm(29.7)
    section.top_margin, section.bottom_margin = Cm(2.25), Cm(1.8)
    section.left_margin, section.right_margin = Cm(2), Cm(2)
    section.header_distance, section.footer_distance = Cm(0.9), Cm(0.8)

    for nom, taille, couleur, gras, avant, apres in (
        ('Normal', 10, BLEU_AXENS, False, 0, 6),
        ('Title', 25, BLEU_AXENS, True, 0, 10),
        ('Heading 1', 13, BLEU_AXENS, True, 13, 5),
        ('Caption', 8.5, GRIS_AXENS, False, 7, 3),
    ):
        style = doc.styles[nom]
        style.font.name = 'Lexend'
        style.font.size = Pt(taille)
        style.font.color.rgb = RGBColor.from_string(couleur)
        style.font.bold = gras
        polices = style.element.rPr.rFonts
        for attribut in ('asciiTheme', 'hAnsiTheme', 'eastAsiaTheme', 'cstheme'):
            polices.attrib.pop(qn(f'w:{attribut}'), None)
        format_paragraphe = style.paragraph_format
        format_paragraphe.line_spacing = 1.12
        format_paragraphe.space_before = Pt(avant)
        format_paragraphe.space_after = Pt(apres)

    titre = doc.styles['Title']
    bordure = titre.element.pPr.find(qn('w:pBdr'))
    if bordure is not None:
        titre.element.pPr.remove(bordure)
    titre.paragraph_format.keep_with_next = True

    entete = section.header.paragraphs[0]
    entete.add_run().add_picture(str(LOGO_AXENS), width=Cm(3.15))
    pied = section.footer.paragraphs[0]
    pied.style = 'Caption'
    pied.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    numero_page = OxmlElement('w:fldSimple')
    numero_page.set(qn('w:instr'), 'PAGE')
    pied._p.append(numero_page)


def creer_word_preaudit(evaluation, audit):
    doc = Document()
    doc.core_properties.title = 'Pré-audit de taxe foncière'
    _mise_en_page(doc)

    analyse = evaluation['analyse']
    resultat = analyse.get('result') or {}
    partial = analyse.get('partial', {})
    bien = evaluation['bien']
    surfaces = evaluation.get('surfaces', {})
    ventilation = audit.get('ventilation', 'inconnue')
    bilan = bilan_preaudit(evaluation, audit)
    doc.add_heading('Pré-audit de taxe foncière', level=0)
    doc.add_paragraph(f"{evaluation['adresse']} · {evaluation['annee']}")
    doc.add_paragraph(f"Catégorie {evaluation['categorie']} · Parcelle {bien.get('section', '')} {bien.get('numero', '')} · INSEE {bien.get('code_insee', '')}")

    doc.add_heading('Montants comparés', level=1)
    libelle_estimation = 'Notre estimation'
    if bilan['estimation'] is not None:
        libelle_estimation += ' (frais inclus)' if bilan['frais_inclus'] else ' (hors frais)'
    lignes = [
        ('Montant de l’avis', bilan['avis']),
        (libelle_estimation, bilan['estimation']),
        ('Écart indicatif · avis moins estimation', bilan['ecart']),
    ]
    _table(doc, ('Montant', 'Valeur'),
           [(nom, euro_arrondi(val) if val is not None else '—') for nom, val in lignes],
           (12, 5), (1,))
    constat = doc.add_paragraph()
    constat.paragraph_format.space_before = Pt(7)
    constat.add_run(bilan['constat']).bold = True

    doc.add_heading('Suite proposée', level=1)
    doc.add_paragraph(bilan['suite'])
    if bilan['ecart'] is not None and bilan['ecart'] > 0:
        doc.add_paragraph(
            'Le délai de réclamation court, en règle générale, jusqu’au 31 décembre de l’année suivant celle de '
            'la mise en recouvrement de l’impôt (CGI, art. 1507 et LPF, art. R*196-2).'
        )

    doc.add_heading('Éléments examinés', level=1)
    surface_batie = audit.get('surface_batie')
    total_saisi = surfaces.get('P1', 0) + surfaces.get('P2', 0)
    if surface_batie is not None:
        doc.add_paragraph(f"Surface bâtie mesurée · {_nb(surface_batie)} m².")
    if total_saisi and (surface_batie is None or ventilation == 'documentee'):
        doc.add_paragraph(f"Surface bâtie saisie (P1 + P2) · {_nb(total_saisi)} m².")
    doc.add_paragraph('Source de la ventilation P1/P2 · ' + VENTILATIONS[ventilation] + '.')
    if analyse.get('missing') or analyse.get('neutral_warnings') or (analyse.get('planchonnement') or {}).get('reserve'):
        doc.add_paragraph('Les paramètres à confirmer figurent en annexe.')
    if audit.get('observation'):
        doc.add_paragraph(' '.join(audit['observation'].split()))
    doc.add_heading('Cadre fiscal', level=1)
    if evaluation['categorie'] == 'EXC1':
        doc.add_paragraph(
            'Les locaux présentant des caractéristiques exceptionnelles suivent les règles '
            'd’évaluation particulières prévues à l’article 1498, III du code général des impôts (CGI).'
        )
    else:
        doc.add_paragraph(
            'La valeur locative résulte de la surface pondérée et du tarif applicable à la catégorie du local '
            'dans son secteur d’évaluation, ajusté le cas échéant par un coefficient de localisation '
            '(CGI, art. 1498, II). La pondération tient compte de l’usage des surfaces, notamment des réserves '
            'et des stationnements (CGI, annexe III, art. 324 Z).'
        )
    doc.add_paragraph(
        'La taxe foncière repose sur la valeur locative cadastrale après déduction forfaitaire de 50 % '
        '(CGI, art. 1388). Les taux s’appliquent après les correctifs et exonérations propres à chaque part.'
    )
    planchonnement = analyse.get('planchonnement') or {}
    if evaluation.get('historique') == 'ancien' or planchonnement.get('applique'):
        doc.add_paragraph(
            'Pour les locaux éligibles, le planchonnement atténue l’écart entre la valeur locative '
            'non révisée de 2017 et la valeur locative révisée neutralisée (CGI, art. 1518 A quinquies).'
        )
    doc.add_paragraph('Montants indicatifs arrondis à l’euro et soumis à confirmation des données cadastrales.', style='Caption')

    doc.add_heading('Annexe · Données de la simulation', level=0).paragraph_format.page_break_before = True
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
           [(cle, _nb(surfaces.get(cle, 0)), _nb(poids)) for cle, poids in COEFF_SURFACES.items()],
           (7, 5, 5), (1, 2))
    if resultat.get('lignes'):
        doc.add_heading('Calcul par composante', level=1)
        _table(doc, ('Taxe', 'Taux (%)', 'Neutralisation', 'Planchonnement (€)', 'Base (€)', 'Cotisation (€)'),
               [(ligne['taxe'], _nb(ligne.get('taux_pct')), _nb(ligne.get('coefficient_neutralisation'), 6),
                 _nb(ligne.get('correction_planchonnement')), _nb(ligne.get('base_taxable')), _nb(ligne.get('montant')))
                for ligne in resultat['lignes']],
               (4.1, 1.85, 2.95, 3.25, 2.25, 2.6), (1, 2, 3, 4, 5))
    frais = evaluation.get('frais') or {}
    if frais.get('frais') is not None:
        doc.add_paragraph(f"Frais de gestion estimés · {_nb(frais['frais'])} €.")
    if frais.get('note'):
        doc.add_paragraph(frais['note'])
    if analyse.get('missing'):
        doc.add_paragraph('Données manquantes · ' + ', '.join(analyse['missing']) + '.')
    reserve = planchonnement.get('reserve')
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
                for cle, taux_cle in taux.items() if taux_cle],
               (5.4, 2.1, 3.3, 6.2), (1, 2))
    flux = BytesIO()
    doc.save(flux)
    return flux.getvalue()


MIME_WORD = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
