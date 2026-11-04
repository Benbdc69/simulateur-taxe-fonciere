"""Rapport PDF de simulation : utilise uniquement le résultat déjà calculé.
Aucune requête réseau, aucune réévaluation des paramètres fiscaux.
"""
from io import BytesIO
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.enums import TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether


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
                              fontSize=17, leading=21, textColor=colors.HexColor('#14273E'), spaceAfter=12))
    styles.add(ParagraphStyle(name='PetitTF', parent=styles['Normal'], fontSize=8.5,
                              leading=12, textColor=colors.HexColor('#48556B'), spaceAfter=7))
    styles.add(ParagraphStyle(name='CorpsTF', parent=styles['Normal'], fontSize=10, leading=15, spaceAfter=7))
    styles.add(ParagraphStyle(name='MontantTF', parent=styles['Normal'], fontName='Helvetica-Bold',
                              fontSize=17, leading=22, textColor=colors.HexColor('#14273E'), spaceAfter=12))
    styles.add(ParagraphStyle(name='TableTF', parent=styles['Normal'], fontSize=8, leading=11))
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
    exo = analyse.get('exoneration_neuf', {})
    if dossier.get('construction_nouvelle'):
        story.append(Paragraph('<b>Construction nouvelle :</b> oui ; année d’achèvement : '+_texte(dossier.get('annee_achevement')), styles['CorpsTF']))
        story.append(Paragraph('Exonération de 40 % sur la part communale : '+('appliquée' if exo.get('active') else 'non appliquée ('+_texte(exo.get('raison'))+')'), styles['PetitTF']))
    surface_rows = [['Surface 6660-REV', 'Surface déclarée (m²)']]
    names={'P1':'P1 - Principale', 'P2':'P2 - Secondaire couverte', 'P3':'P3 - Secondaire non couverte',
           'PK1':'PK1 - Stationnement couvert', 'PK2':'PK2 - Stationnement non couvert'}
    for key, label in names.items():
        surface_rows.append([label, _nombre(dossier['surfaces'].get(key, 0))])
    surface_rows.append(['Surface pondérée', _nombre(partial['surface_ponderee'])])
    story.extend([Spacer(1, 9), Paragraph('<b>Surfaces</b>', styles['Heading3'])])
    tab=Table(surface_rows, colWidths=[10.4*cm, 5.6*cm], repeatRows=1)
    tab.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#E9EFF5')),
                             ('GRID',(0,0),(-1,-1),0.35,colors.HexColor('#D9E1E8')),
                             ('PADDING',(0,0),(-1,-1),7),('ALIGN',(1,1),(1,-1),'RIGHT'),
                             ('FONTNAME',(0,-1),(-1,-1),'Helvetica-Bold')]))
    story.append(tab)
    story.append(Spacer(1, 14))
    if result:
        story.append(Paragraph('<b>Montant estimé des taxes, hors frais de gestion</b>',styles['CorpsTF']))
        story.append(Paragraph(_nombre(result['total_estime']) + ' EUR', styles['MontantTF']))
        tax_rows=[['Composante','Base (EUR)','Taux (%)','Montant (EUR)']]
        for line in result['lignes']:
            tax_rows.append([Paragraph(_texte(line['taxe']),styles['TableTF']),
                             _nombre(line['base_taxable']), _nombre(line['taux_pct']), _nombre(line['montant'])])
        table=Table(tax_rows,colWidths=[7.2*cm, 3.1*cm, 2.3*cm, 3.4*cm],repeatRows=1, hAlign='LEFT')
        table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),colors.HexColor('#E9EFF5')),
                                   ('GRID',(0,0),(-1,-1),0.3,colors.HexColor('#D9E1E8')),
                                   ('VALIGN',(0,0),(-1,-1),'TOP'),('PADDING',(0,0),(-1,-1),6),
                                   ('ALIGN',(1,1),(-1,-1),'RIGHT'),('FONTSIZE',(0,0),(-1,0),8)]))
        story.append(table)
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
