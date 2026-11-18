"""Présentation commune des rapports de simulation Axens."""
from pathlib import Path
from xml.sax.saxutils import escape

import reportlab

from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase.pdfmetrics import registerFont
from reportlab.pdfbase.ttfonts import TTFont
from reportlab.platypus import Paragraph, Spacer, Table, TableStyle

ENCRE = colors.HexColor('#172F44')
VERT = colors.HexColor('#27675E')
PALE = colors.HexColor('#ECF5F2')
LIGNE = colors.HexColor('#C9D8DE')
GRIS = colors.HexColor('#4A6071')
LARGEUR = 16.9 * cm
POLICES = Path(reportlab.__file__).resolve().parent / 'fonts'
NORMALE = 'AxensRapport'
GRASSE = 'AxensRapportGras'
registerFont(TTFont(NORMALE, str(POLICES / 'Vera.ttf')))
registerFont(TTFont(GRASSE, str(POLICES / 'VeraBd.ttf')))


def montant_pdf(valeur, suffixe=' €'):
    if valeur is None:
        return '—'
    return f'{float(valeur):,.2f}'.replace(',', ' ').replace('.', ',') + suffixe


def synthese_pdf(annee, nature, adresse, reference, profil, lignes, sous_total, frais,
                 valeur_locative=None, reserve=''):
    def paragraphe(texte, taille=10, couleur=ENCRE, gras=False, alignement=0):
        style = ParagraphStyle('Synthese', fontName=GRASSE if gras else NORMALE,
                               fontSize=taille, leading=taille * 1.3, textColor=couleur,
                               alignment=alignement)
        return Paragraph(escape(str(texte)), style)

    total = frais.get('total') if frais else None
    if total is not None:
        montant, libelle = total, 'Total estimé, frais de gestion inclus'
    elif sous_total is not None:
        montant, libelle = sous_total, 'Cotisations estimées hors frais'
    elif valeur_locative is not None:
        montant, libelle = valeur_locative, 'Valeur locative estimée'
    else:
        montant, libelle = None, 'Montant non calculable'

    bloc = Table([[
        [paragraphe('AXENS  /  SIMULATION FISCALE', 9, colors.white, True),
         Spacer(1, 9), paragraphe('Taxe foncière', 25, colors.white, True),
         paragraphe(f'{nature}  ·  {annee}', 11, colors.white)],
        [paragraphe(libelle, 9, colors.white, alignement=TA_RIGHT),
         Spacer(1, 5), paragraphe(montant_pdf(montant) if montant is not None else '—',
                                  23, colors.white, True, TA_RIGHT)],
    ]], colWidths=[10 * cm, LARGEUR - 10 * cm], hAlign='LEFT')
    bloc.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), ENCRE), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 16), ('RIGHTPADDING', (0, 0), (-1, -1), 16),
        ('TOPPADDING', (0, 0), (-1, -1), 18), ('BOTTOMPADDING', (0, 0), (-1, -1), 18),
    ]))
    story = [bloc, Spacer(1, 8),
             paragraphe('Document de simulation · Ne vaut pas avis d’imposition', 9, GRIS, True),
             Spacer(1, 22), paragraphe('Bien concerné', 13, VERT, True), Spacer(1, 7),
             paragraphe(adresse or 'Adresse non renseignée', 10, ENCRE, True),
             paragraphe(reference, 9, GRIS), paragraphe(profil, 9, GRIS), Spacer(1, 20),
             paragraphe('Cotisations par composante', 13, VERT, True), Spacer(1, 8)]

    tableau = [['Composante', 'Base imposable', 'Taux', 'Cotisation']]
    tableau.extend([[paragraphe(nom, 9), montant_pdf(base), montant_pdf(taux, ' %'), montant_pdf(cotisation)]
                    for nom, base, taux, cotisation in lignes])
    if not lignes:
        tableau.append([paragraphe('Cotisations indisponibles', 9), '—', '—', '—'])
    tableau.append(['Sous-total des cotisations', '', '', montant_pdf(sous_total)])
    libelle_frais = 'Frais de gestion estimés' if not frais or not frais.get('note') else 'Frais de gestion calculables'
    tableau.append([libelle_frais, '', '', montant_pdf(frais.get('frais') if frais else None)])
    tableau.append(['Total estimé avec frais', '', '', montant_pdf(total)])
    tab = Table(tableau, colWidths=[7.6 * cm, 3.1 * cm, 2.5 * cm, 3.7 * cm], hAlign='LEFT')
    tab.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), VERT), ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('BACKGROUND', (0, -3), (-1, -1), PALE), ('FONTNAME', (0, 0), (-1, 0), GRASSE),
        ('FONTNAME', (0, -1), (-1, -1), GRASSE), ('TEXTCOLOR', (0, 1), (-1, -1), ENCRE),
        ('FONTNAME', (0, 1), (-1, -2), NORMALE), ('FONTSIZE', (0, 0), (-1, -1), 9),
        ('ALIGN', (1, 0), (-1, -1), 'RIGHT'), ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('LEFTPADDING', (0, 0), (-1, -1), 9), ('RIGHTPADDING', (0, 0), (-1, -1), 9),
        ('TOPPADDING', (0, 0), (-1, -1), 7), ('BOTTOMPADDING', (0, 0), (-1, -1), 7),
        ('LINEBELOW', (0, 1), (-1, -1), 0.4, LIGNE),
    ]))
    story.extend([tab, Spacer(1, 10)])
    if reserve:
        story.append(paragraphe(reserve, 9, GRIS))
    if frais and frais.get('note'):
        story.append(paragraphe(frais['note'], 9, GRIS))
    if sous_total is not None and total is None:
        story.append(paragraphe('Le total avec frais reste indéterminé.', 9, GRIS))
    story.extend([Spacer(1, 18), paragraphe('Voir l’annexe pour les calculs, les hypothèses et les sources.', 9, VERT, True)])
    return story


def pied_rapport(canvas, doc):
    canvas.saveState()
    largeur, _ = doc.pagesize
    marge = doc.leftMargin
    canvas.setStrokeColor(LIGNE)
    canvas.line(marge, 34, largeur - marge, 34)
    canvas.setFillColor(GRIS)
    canvas.setFont(NORMALE, 8)
    canvas.drawString(marge, 22, 'AXENS  /  SIMULATION DE TAXE FONCIÈRE')
    canvas.drawRightString(largeur - marge, 22, f'Page {doc.page}')
    canvas.restoreState()
