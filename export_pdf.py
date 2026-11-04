"""Rapport PDF de simulation : utilise uniquement le résultat déjà calculé.
Aucune requête réseau, aucune réévaluation des paramètres fiscaux.
"""
from io import BytesIO
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT, TA_LEFT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether


# Palette éditoriale inspirée d'Axens, indépendante du thème Streamlit
BLEU = colors.HexColor('#246A9D')
BLEU_FONCE = colors.HexColor('#164C79')
BLEU_PALE = colors.HexColor('#EAF2F8')
FOND = colors.HexColor('#F6F9FC')
BORDURE = colors.HexColor('#DFE8F2')
TEXTE = colors.HexColor('#153957')
SECONDAIRE = colors.HexColor('#526B80')

def _nombre(value, decimals=2):
    if value is None:
        return 'Indisponible'
    return f'{float(value):,.{decimals}f}'.replace(',', ' ').replace('.', ',')


def _texte(value):
    return escape(str(value if value is not None else ''))


def creer_pdf_estimation(dossier):
    """Retourne les octets PDF pour un dossier issu de ``finaliser``."""
    analyse = dossier['analyse']
    result = analyse.get('result')
    partial = analyse['partial']
    bien = dossier['bien']
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='TitreTF', parent=styles['Title'], fontName='Helvetica-Bold',
                              fontSize=19, leading=24, textColor=BLEU_FONCE, spaceAfter=12))
    styles.add(ParagraphStyle(name='PetitTF', parent=styles['Normal'], fontSize=8.5,
                              leading=12, textColor=SECONDAIRE, spaceAfter=7))
    styles.add(ParagraphStyle(name='CorpsTF', parent=styles['Normal'], fontSize=10, leading=15, spaceAfter=7))
    styles.add(ParagraphStyle(name='MontantTF', parent=styles['Normal'], fontName='Helvetica-Bold',
                              fontSize=20, leading=24, textColor=BLEU_FONCE, spaceAfter=12))
    styles.add(ParagraphStyle(name='TableTF', parent=styles['Normal'], fontSize=8, leading=11))
    styles.add(ParagraphStyle(name='CardLabelTF', parent=styles['Normal'], fontName='Helvetica', fontSize=9,
                              leading=12, textColor=SECONDAIRE))
    styles.add(ParagraphStyle(name='CardAmountTF', parent=styles['Normal'], fontName='Helvetica-Bold', fontSize=16,
                              leading=20, textColor=BLEU_FONCE))
    styles.add(ParagraphStyle(name='CardMetaTF', parent=styles['Normal'], fontSize=8, leading=11,
                              textColor=SECONDAIRE))
    buffer = BytesIO()
    pdf = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=1.7*cm, rightMargin=1.7*cm,
                            topMargin=1.7*cm, bottomMargin=1.6*cm,
                            title='Estimation de taxe foncière - local professionnel')
    story = [Paragraph('Estimation de taxe foncière', styles['TitreTF']),
             Paragraph('Document de simulation - local professionnel, non opposable à l’administration fiscale', styles['PetitTF']),
             Paragraph(f"<b>Adresse :</b> {_texte(dossier.get('adresse', ''))}", styles['CorpsTF']),
             Paragraph(f"<b>Année :</b> {_texte(dossier['annee'])} &nbsp;&nbsp; <b>Catégorie :</b> {_texte(dossier['categorie'])}", styles['CorpsTF']),
             Paragraph(f"<b>Parcelle :</b> {_texte(bien.get('section',''))} {_texte(bien.get('numero',''))} "
                       f"(INSEE cadastral {_texte(bien.get('code_insee',''))})", styles['CorpsTF'])]
    story.insert(2, Table([['']], colWidths=[16*cm], rowHeights=[0.08*cm], style=TableStyle([('BACKGROUND',(0,0),(-1,-1),BLEU),('BOTTOMPADDING',(0,0),(-1,-1),0),('TOPPADDING',(0,0),(-1,-1),0)])))
    story.insert(3, Spacer(1, 9))
    exo = analyse.get('exoneration_neuf', {})
    if dossier.get('construction_nouvelle'):
        story.append(Paragraph('<b>Construction nouvelle :</b> oui ; année d’achèvement : '+_texte(dossier.get('annee_achevement')), styles['CorpsTF']))
        story.append(Paragraph('Exonération de 40 % sur la part communale et les taxes additionnelles éligibles (GEMAPI, TSE et syndicats sans fiscalité propre) : '+('appliquée' if exo.get('active') else 'non appliquée ('+_texte(exo.get('raison'))+')'), styles['PetitTF']))
    surface_rows = [['Surface 6660-REV', 'Surface déclarée (m²)']]
    names={'P1':'P1 - Principale', 'P2':'P2 - Secondaire couverte', 'P3':'P3 - Secondaire non couverte',
           'PK1':'PK1 - Stationnement couvert', 'PK2':'PK2 - Stationnement non couvert'}
    for key, label in names.items():
        surface_rows.append([label, _nombre(dossier['surfaces'].get(key, 0))])
    surface_rows.append(['Surface pondérée', _nombre(partial['surface_ponderee'])])
    story.extend([Spacer(1, 9), Paragraph('<b>Surfaces</b>', styles['Heading3'])])
    tab=Table(surface_rows, colWidths=[10.4*cm, 5.6*cm], repeatRows=1)
    tab.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),BLEU_PALE),
                             ('GRID',(0,0),(-1,-1),0.35,BORDURE),
                             ('PADDING',(0,0),(-1,-1),7),('ALIGN',(1,1),(1,-1),'RIGHT'),
                             ('FONTNAME',(0,-1),(-1,-1),'Helvetica-Bold')]))
    story.append(tab)
    story.append(Spacer(1, 14))
    if result:
        total_card = Table([[
            [Paragraph('MONTANT ESTIMÉ DE TAXE FONCIÈRE', styles['CardLabelTF']),
             Spacer(1, 7),
             Paragraph(_nombre(result['total_estime']) + ' EUR', styles['MontantTF']),
             Paragraph('Estimation ' + _texte(dossier['annee']) + ' - hors frais de gestion', styles['CardMetaTF'])]
        ]], colWidths=[16*cm])
        total_card.setStyle(TableStyle([
            ('BACKGROUND',(0,0),(-1,-1),BLEU_PALE),
            ('BOX',(0,0),(-1,-1),0.8,BORDURE),
            ('LINEBEFORE',(0,0),(0,0),4,BLEU),
            ('LEFTPADDING',(0,0),(-1,-1),15),
            ('RIGHTPADDING',(0,0),(-1,-1),15),
            ('TOPPADDING',(0,0),(-1,-1),12),
            ('BOTTOMPADDING',(0,0),(-1,-1),9),
        ]))
        story.extend([total_card, Spacer(1, 15)])
        story.append(Paragraph('<font color="#164C79"><b>Répartition par taxe</b></font>', styles['Heading3']))
        lignes = result['lignes']
        cards = []
        for line in lignes:
            label = _texte(line['taxe'])
            amount = _nombre(line['montant'])
            base = _nombre(line['base_taxable'])
            taux = _nombre(line['taux_pct'])
            exo_pct = _nombre(line['abattement_pct'])
            card = [
                Paragraph(label, styles['CardLabelTF']),
                Spacer(1, 6),
                Paragraph(f'{amount} EUR', styles['CardAmountTF']),
                Spacer(1, 7),
                Paragraph(f'Base : {base} EUR · Taux : {taux} %', styles['CardMetaTF']),
                Paragraph(f'Exonération : {exo_pct} %', styles['CardMetaTF']),
            ]
            cards.append(card)
        for i in range(0, len(cards), 2):
            pair = cards[i:i+2]
            if len(pair) == 1:
                pair.append('')
            tile_table = Table([pair], colWidths=[7.8*cm, 7.8*cm], hAlign='LEFT')
            tile_table.setStyle(TableStyle([
                ('BACKGROUND', (0,0),(-1,-1), colors.white),
                ('BOX', (0,0),(-1,-1), 0.6, BORDURE),
                ('INNERGRID', (0,0),(-1,-1), 1.8, colors.HexColor('#F6F9FC')),
                ('VALIGN',(0,0),(-1,-1),'TOP'),
                ('LINEBEFORE',(0,0),(-1,-1),2.5,BLEU),
                ('LEFTPADDING',(0,0),(-1,-1),11),
                ('RIGHTPADDING',(0,0),(-1,-1),9),
                ('TOPPADDING',(0,0),(-1,-1),12),
                ('BOTTOMPADDING',(0,0),(-1,-1),12),
            ]))
            story.append(KeepTogether([tile_table, Spacer(1, 8)]))

    else:
        story.append(Paragraph('<b>Estimation complète indisponible</b>',styles['Heading3']))
        story.append(Paragraph('Certains paramètres requis sont indisponibles : aucun montant global de taxe n’est présenté.',styles['CorpsTF']))
        missing=', '.join(analyse.get('missing') or [])
        if missing:
            story.append(Paragraph('<b>Données manquantes :</b> '+_texte(missing),styles['PetitTF']))
    story.extend([Spacer(1, 12), Paragraph('<b>Paramètres de calcul</b>',styles['Heading3']),
                  Paragraph('Secteur : '+_texte(partial.get('secteur'))+' ; tarif : '+_nombre(partial.get('tarif'))+
                            ' EUR/m² ; coefficient de localisation : '+_nombre(partial.get('localisation'),4), styles['PetitTF']),
                  Paragraph('Valeur locative brute : '+_nombre(partial.get('valeur_locative_brute'))+' EUR',styles['PetitTF'])])
    out_of_date=[f"{key} ({rate['annee_source']})" for key,rate in analyse.get('taux',{}).items()
                 if rate and rate.get('decalage',0)>0]
    if out_of_date:
        story.append(Paragraph('Taux repris de millésimes antérieurs : '+_texte(', '.join(out_of_date)),styles['PetitTF']))
    if analyse.get('neutral_warnings'):
        story.append(Paragraph('Certaines neutralisations historiques ont été reprises à titre provisoire.',styles['PetitTF']))
    story.append(Spacer(1, 12))
    story.append(Paragraph('<b>Réserves importantes</b>',styles['Heading3']))
    story.append(Paragraph('Estimation sans autres exonérations particulières, sans frais de gestion et sans corrections historiques non documentées. '
                           'Pour un local existant avant 2017, le planchonnement et, jusqu’en 2025, le lissage peuvent modifier sensiblement la cotisation. '
                           'Les taux repris d’années antérieures et les zones TEOM doivent être vérifiés. Pour une construction nouvelle, l’exonération de l’article 1383 II du CGI suppose le respect des formalités déclaratives (90 jours).',styles['PetitTF']))
    pdf.build(story)
    return buffer.getvalue()
