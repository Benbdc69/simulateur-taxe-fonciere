from io import BytesIO
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle

def generer_pdf_habitation(d):
    out=BytesIO()
    pdf=SimpleDocTemplate(out,pagesize=A4,leftMargin=1.8*cm,rightMargin=1.8*cm,
                          topMargin=1.8*cm,bottomMargin=1.8*cm)
    styles=getSampleStyleSheet()
    styles.add(ParagraphStyle(name='TitreAxensH',parent=styles['Title'],fontSize=18,
       textColor=colors.HexColor('#164C79'),spaceAfter=15))
    story=[Paragraph('Estimation de taxe foncière — habitation',styles['TitreAxensH']),
           Paragraph('Simulation indicative, non opposable à l’administration fiscale.',styles['Normal']),Spacer(1,16)]
    for k,v in [('Adresse',d['adresse']),('Type',d['nature']),('Catégorie',d['categorie']),('Année',d['annee']),
                 ('Surface pondérée',str(d['surfaces']['surface_ponderee'])+' m²')]:
        story.append(Paragraph(f'<b>{escape(str(k))}</b> : {escape(str(v))}',styles['Normal']))
        story.append(Spacer(1,5))
    story.append(Spacer(1,12))
    for row in d['tarifs'][:15]:
        title=f"Série {row['serie']} — VL de référence 1970 : {row['vl_1970']:,.2f} EUR"
        story.append(Paragraph(escape(title),styles['Heading3']))
        if 'total' in row:
            story.append(Paragraph(f"Cotisation estimée hors frais : {row['total']:,.2f} EUR",styles['Normal']))
        elif 'vl_annee' in row:
            story.append(Paragraph(f"VL actualisée : {row['vl_annee']:,.2f} EUR ; taux fiscaux non renseignés.",styles['Normal']))
    story.append(Spacer(1,15))
    issues=[]
    if len(d['tarifs'])>1:issues.append('Plusieurs séries tarifaires : série applicable non identifiée.')
    if d['facteur'] is None:issues.append('Coefficient cumulé de revalorisation non documenté : montant de taxe indisponible.')
    elif not d.get('taux_complets'):issues.append('Taux fiscaux incomplets : aucun total n’est présenté.')
    if d['surfaces']['dependances_a_evaluer_separement']:issues.append('Dépendances d’appartement à évaluer séparément.')
    issues.append('Estimation hors exonérations spécifiques, frais de gestion et éventuelles taxes annexes non documentées.')
    story.append(Paragraph('<b>Réserves</b>',styles['Heading3']))
    for s in issues:story.append(Paragraph(escape(s),styles['Normal']))
    pdf.build(story)
    return out.getvalue()
