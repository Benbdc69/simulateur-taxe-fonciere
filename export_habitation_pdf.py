"""Export PDF Axens - Habitation H1/H2 (ne modifie pas export_pdf professionnel)."""
from io import BytesIO
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,KeepTogether

BLUE=colors.HexColor('#164C79');PALE=colors.HexColor('#EDF4F9');LINE=colors.HexColor('#CFDEE9')

def eur(x):return f'{float(x):,.2f}'.replace(',',' ').replace('.',',')+' €'
def ph(x):return escape(str(x))

def generer_pdf_habitation(d):
    out=BytesIO()
    doc=SimpleDocTemplate(out,pagesize=A4,leftMargin=1.7*cm,rightMargin=1.7*cm,topMargin=1.7*cm,bottomMargin=1.7*cm)
    st=getSampleStyleSheet()
    st.add(ParagraphStyle(name='AxTitleH',parent=st['Title'],fontName='Helvetica-Bold',fontSize=19,leading=23,textColor=BLUE,spaceAfter=12))
    st.add(ParagraphStyle(name='AxHeadH',parent=st['Heading2'],fontSize=11,leading=14,spaceBefore=13,spaceAfter=8,textColor=BLUE))
    st.add(ParagraphStyle(name='AxTinyH',parent=st['Normal'],fontSize=8,leading=11,textColor=colors.HexColor('#50667B')))
    st.add(ParagraphStyle(name='AxNormalH',parent=st['Normal'],fontSize=9,leading=13))
    story=[Paragraph('Simulation de taxe foncière - Habitation',st['AxTitleH']),
           Paragraph('Rapport indicatif, non opposable à l’administration fiscale. Source tarifs : DGFiP, fichier 2024.',st['AxTinyH']),Spacer(1,14)]
    fields=[('Adresse',d['adresse']),('Commune (INSEE)',d['code_insee']),('Nature',d['nature']),
            ('Catégorie cadastrale',d['categorie']),('Année d’imposition',d['annee']),
            ('Surface principale déclarée',str(d.get('surface_reelle','?'))+' m²'),
            ('Surface pondérée principale',str(d['surfaces']['surface_ponderee'])+' m²'),
            ('Terrasse déclarée',str(d.get('terrasse_reelle',0))+' m²'),
            ('Dépendances déclarées',str(d.get('autres_dependances',0))+' m²')]
    for k,v in fields:
        story.append(Paragraph(f'<b>{ph(k)} :</b> {ph(v)}',st['AxNormalH']))
        story.append(Spacer(1,3))
    story.append(Paragraph('Paramètres de revalorisation',st['AxHeadH']))
    fac=d['facteur']
    for title,val in [('Actualisation départementale 1980',fac['actualisation_1980']),
                      ('Revalorisation nationale cumulée',fac['revalorisation_nationale']),
                      ('Coefficient de conversion global',fac['coefficient_cumule'])]:
        story.append(Paragraph(f'{ph(title)} : <b>{float(val):.6f}</b>',st['AxNormalH']))
    story.append(Paragraph('Valeurs locatives et cotisations estimées',st['AxHeadH']))
    rates=d.get('taux',{})
    h=Table([[Paragraph('<b>Série</b>',st['AxNormalH']),Paragraph('<b>Tarif 1970/m²</b>',st['AxNormalH']),
              Paragraph('<b>VL 1970</b>',st['AxNormalH']),Paragraph('<b>VL année</b>',st['AxNormalH']),
              Paragraph('<b>Base TFPB</b>',st['AxNormalH']),Paragraph('<b>Sous-total*</b>',st['AxNormalH'])]]+
          [[ph(x['serie'])+' / '+ph(x.get('origine') or '—'),eur(x['tarif_1970']),eur(x['vl_1970']),
            eur(x.get('vl_annee',0)),eur(x.get('base_tf',0)),eur(x['total']) if 'total' in x else 'Non calculé']
           for x in d['tarifs'][:16]],colWidths=[2.65*cm,2.45*cm,2.45*cm,2.45*cm,2.45*cm,3.0*cm],repeatRows=1)
    h.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),PALE),('TEXTCOLOR',(0,0),(-1,0),BLUE),
                          ('GRID',(0,0),(-1,-1),0.35,LINE),('VALIGN',(0,0),(-1,-1),'MIDDLE'),
                          ('ROWBACKGROUNDS',(0,1),(-1,-1),[colors.white,colors.HexColor('#FAFCFE')]),
                          ('FONTSIZE',(0,1),(-1,-1),7),('BOTTOMPADDING',(0,0),(-1,-1),8),('TOPPADDING',(0,0),(-1,-1),8)]))
    story.append(h)
    selected=int(d.get('serie_selectionnee',0))
    chosen=d['tarifs'][min(max(selected,0),len(d['tarifs'])-1)]
    story.append(Spacer(1,12))
    if chosen.get('montants'):
        story.append(Paragraph('Détail du scénario sélectionné : série '+ph(chosen['serie']),st['AxHeadH']))
        detail=[[Paragraph('<b>Composante</b>',st['AxNormalH']),Paragraph('<b>Montant</b>',st['AxNormalH']),Paragraph('<b>Millésime taux</b>',st['AxNormalH'])]]
        LIBELLES={'commune':'Commune','syndicat':'Syndicat','epci':'Intercommunalité','taxes_speciales':'Taxes spéciales / TSE','gemapi':'GEMAPI','teom':'TEOM'}
        for key,value in chosen['montants'].items():
            obj=rates.get(key) or {}
            detail.append([ph(LIBELLES.get(key,key)),eur(value),str(obj.get('annee_source','—'))])
        detail.append(['TOTAL PARTIE PRINCIPALE',eur(chosen['total']),'*'])
        t=Table(detail,colWidths=[8.0*cm,4.5*cm,4.0*cm],repeatRows=1)
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),PALE),('GRID',(0,0),(-1,-1),0.3,LINE),
                              ('FONTNAME',(0,-1),(-1,-1),'Helvetica-Bold'),('TEXTCOLOR',(0,-1),(-1,-1),BLUE),
                              ('FONTSIZE',(0,0),(-1,-1),9),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
        story.append(t)
    story.append(Paragraph('Périmètre et réserves',st['AxHeadH']))
    notes=[]
    if len(d['tarifs'])>1:notes.append('Plusieurs séries de tarifs : la série exacte du local doit être confirmée dans la fiche cadastrale.')
    if d['surfaces'].get('dependances_a_evaluer_separement'):
        notes.append('IMPORTANT : terrasse et/ou dépendances d’appartement peuvent faire l’objet d’une évaluation fiscale distincte ; leur valeur n’entre pas dans les montants ci-dessus.')
    if not d.get('taux_complets'):notes.append('Une ou plusieurs composantes fiscales ne sont pas documentées. Aucun total complet n’est affiché.')
    notes.append('* Cotisations hors frais de gestion, exonérations/dégrèvements personnels et autres taxes annexes spécifiques. Valeurs arrondies ; taux antérieurs éventuels.')
    notes.append('Surface habitable renseignée par l’utilisateur ; elle peut différer de la surface cadastrale mesurée au sol.')
    for n in notes:story.append(Paragraph('• '+ph(n),st['AxTinyH']))
    story.append(Spacer(1,12))
    story.append(Paragraph('Sources : '+ph(d.get('source_tarifs','DGFiP open data 2024')),st['AxTinyH']))
    story.append(Paragraph('Actualisation : '+ph(fac.get('source_departement',''))+' ; revalorisation : '+ph(fac.get('source_revalorisation','')),st['AxTinyH']))
    doc.build(story)
    data=out.getvalue()
    if not data.startswith(b'%PDF'):raise RuntimeError('Export PDF habitation invalide')
    return data
