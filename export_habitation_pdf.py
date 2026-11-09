"""Export PDF Axens - Habitation H1/H2 (ne modifie pas export_pdf professionnel)."""
from io import BytesIO
from dependances_habitation import MODES
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet,ParagraphStyle
from reportlab.lib.enums import TA_CENTER
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate,Paragraph,Spacer,Table,TableStyle,KeepTogether,PageBreak

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
    if d.get('parcelle'):
        parcelle=d['parcelle']
        fields.append(('Référence cadastrale', f"{parcelle['insee']} / {parcelle['prefixe']} / {parcelle['section']} / {parcelle['numero']}"))
    for k,v in fields:
        story.append(Paragraph(f'<b>{ph(k)} :</b> {ph(v)}',st['AxNormalH']))
        story.append(Spacer(1,3))
    if d.get('h2'):
        from dossier_habitation import H2_PIECES
        story.append(Paragraph('Consistance et confort déclarés au H2',st['AxHeadH']))
        for key,value in d['h2']['pieces'].items():
            story.append(Paragraph(ph(H2_PIECES[key])+ ' : '+ph(value),st['AxNormalH']))
        for key,label in [('chauffage','Chauffage'),('escalier_service','Escalier de service'),('partie_professionnelle','Partie professionnelle'),('declaration_6660','Déclaration 6660-REV souscrite')]:
            story.append(Paragraph(ph(label)+' : '+('oui' if d['h2'].get(key) else 'non'),st['AxNormalH']))
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
          [[Paragraph(ph(x['serie'])+' / '+ph(x.get('origine') or '—') + (f"<br/>Chauffage : {x['pieces_chauffage_scenario']} pièces déclarées" if 'pieces_chauffage_scenario' in x else ''),st['AxTinyH']),eur(x['tarif_1970']),eur(x['vl_1970']),
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
        detail.append(['TOTAL LOGEMENT ET RATTACHÉES',eur(chosen['total']),'*'])
        t=Table(detail,colWidths=[8.0*cm,4.5*cm,4.0*cm],repeatRows=1)
        t.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),PALE),('GRID',(0,0),(-1,-1),0.3,LINE),
                              ('FONTNAME',(0,-1),(-1,-1),'Helvetica-Bold'),('TEXTCOLOR',(0,-1),(-1,-1),BLUE),
                              ('FONTSIZE',(0,0),(-1,-1),9),('BOTTOMPADDING',(0,0),(-1,-1),6)]))
        story.append(t)
    comparables = [x for x in d['tarifs'] if x.get('categorie', d['categorie']) == chosen.get('categorie', d['categorie'])
                   and x.get('pieces_chauffage_scenario') == chosen.get('pieces_chauffage_scenario')]
    if len({(x['serie'], x.get('origine')) for x in comparables}) > 1:
        cle = 'total' if all('total' in x for x in comparables) else 'base_tf'
        label = 'cotisations hors frais et exonérations' if cle == 'total' else 'bases TFPB, cotisations indisponibles'
        valeurs = [x[cle] for x in comparables]
        story.append(Paragraph('Fourchette des séries de la catégorie '+ph(d['categorie'])+' : '+eur(min(valeurs))+' à '+eur(max(valeurs))+' ('+ph(label)+', pour le nombre de pièces chauffées déclaré).',st['AxNormalH']))
    if d.get('dependances'):
        story.append(Paragraph('Dépendances déclarées — cadre 5 H2',st['AxHeadH']))
        for dependance in d['dependances']:
            description = (ph(dependance['designation'])+' ; lot : '+ph(dependance.get('lot') or 'non précisé')
                +' ; situation : '+ph(dependance.get('situation') or 'non précisée')
                +' ; surface : '+ph(dependance['surface'])+' m² ; '+ph(MODES[dependance['mode']]))
            if dependance['mode']=='incorporee':
                description += (' ; pondération : '+ph(dependance['coefficient'])+' ; surface rattachée avant correctifs : '
                    +ph(dependance['surface_ponderee'])+' m² ; équivalences de confort : '+ph(dependance['equivalence_confort'])+' m². Tarif du logement appliqué après le correctif d’ensemble.')
            story.append(Paragraph(description,st['AxNormalH']))
        for dependance in d.get('dependances_distinctes', []):
            texte = ph(dependance['designation'])+' : '
            if 'total' in dependance:
                texte += 'base imposable distincte '+eur(dependance['base_tf'])+' ; cotisations '+eur(dependance['total'])+' ; mêmes taux que le logement confirmés pour la dépendance.'
            else:
                if dependance.get('base_tf') is not None:
                    texte += 'base déclarée '+eur(dependance['base_tf'])+' ; '
                texte += 'évaluation distincte non chiffrée : base de l’année et taux/zonage à documenter. Non incluse dans les montants du logement.'
            story.append(Paragraph(texte,st['AxNormalH']))
        if d.get('dependances_distinctes') and 'total_bien' in chosen:
            story.append(Paragraph('<b>Total estimé du bien, dépendances distinctes comprises : '+eur(chosen['total_bien'])+'</b> (hors frais et exonérations).',st['AxNormalH']))
    if d.get('terrasse_reelle',0) and d['surfaces'].get('detail_terrasse'):
        terrasse=d['surfaces']['detail_terrasse']
        story.append(Paragraph('Terrasse intégrée au logement : '+ph(terrasse['surface_declaree'])+' m² déclarés ; '+ph(terrasse['surface_reelle_retenue'])+' m² réels retenus x '+ph(terrasse['coefficient'])+' = '+ph(terrasse['surface_ponderee'])+' m² pondérés après arrondi inférieur, avant correctif d’ensemble. Coefficient à confirmer sur la fiche cadastrale. Référence : articles 324 M/N, brochure DGFiP IDL 2025 p. 23.',st['AxNormalH']))
    story.append(Paragraph('Périmètre et réserves',st['AxHeadH']))
    notes=list(d.get('reserves_h2', []))
    if any('total' not in x for x in d.get('dependances_distinctes', [])):
        notes.append('Estimation partielle : les dépendances évaluées distinctement non chiffrées ne sont pas incluses. Le montant du logement n’est pas le total du bien.')
    if any(x['mode']=='incorporee' for x in d.get('dependances', [])):
        notes.append('Les dépendances rattachées sont pondérées avec les coefficients renseignés, avant le correctif d’ensemble du logement et le même tarif. Rattachement et pondération à confirmer sur la fiche cadastrale.')
    if 'pieces_chauffage_scenario' in chosen:
        notes.append(f"Chauffage : {chosen['pieces_chauffage_scenario']} pièces et annexes déclarées chauffées x 2 m² = +{2*chosen['pieces_chauffage_scenario']} m² d’équivalence, ajoutés à la surface nette avant application du tarif. Le nombre est saisi par l’utilisateur ; aucun comptage automatique n’est effectué.")
    if not d.get('categorie_confirmee'):
        notes.append('Catégorie choisie à titre indicatif avec l’aide au classement : elle ne constitue pas un classement confirmé par l’administration. À vérifier sur la fiche cadastrale.')
    if d.get('categorie_inconnue'):
        notes.append('Catégorie cadastrale inconnue : ce rapport détaille un scénario exploratoire sélectionné, et ne confirme pas le classement du logement. D’autres catégories peuvent être disponibles dans le simulateur.')
    if len({(x['serie'],x.get('origine')) for x in d['tarifs']})>1:notes.append('Plusieurs séries de tarifs : la série exacte du local doit être confirmée dans la fiche cadastrale.')
    if d['surfaces'].get('dependances_a_evaluer_separement'):
        notes.append('Des surfaces de dépendances anciennement regroupées restent hors calcul : préciser leur rattachement ou leur évaluation distincte au cadre 5.')
    if not d.get('taux_complets'):notes.append('Une ou plusieurs composantes fiscales ne sont pas documentées. Aucun total complet n’est affiché.')
    anciens=[f"{k} ({v['annee_source']})" for k,v in rates.items() if v and int(v.get('annee_source',d['annee']))<d['annee']]
    if anciens:notes.append('Taux antérieurs repris à titre indicatif : '+', '.join(anciens)+'.')
    if rates.get('teom') and not rates['teom'].get('zonage_confirme'):
        notes.append('Le zonage TEOM n’est pas confirmé pour cette adresse ; la cotisation correspondante reste à vérifier.')
    notes.append('* Cotisations hors frais de gestion, exonérations/dégrèvements personnels et autres taxes annexes spécifiques. Valeurs arrondies ; taux antérieurs éventuels.')
    notes.append('Surface réelle déclarée par l’utilisateur ; une surface habitable ou Carrez peut différer de la surface cadastrale mesurée au sol.')
    for n in notes:story.append(Paragraph('• '+ph(n),st['AxTinyH']))
    # Les références documentaires sont regroupées à la fin de l'annexe de contrôle.
    # Cela évite une page supplémentaire contenant seulement les sources.
    # Annexe explicative conservée dans le PDF uniquement.
    # Toutes les valeurs fiscales chiffrées proviennent du scénario d'origine.
    story.append(PageBreak())
    story.append(Paragraph('Annexe de contrôle - détail du calcul',st['AxTitleH']))
    story.append(Paragraph('Habitation H1/H2 - décomposition des surfaces, de la valeur locative et de la cotisation.',st['AxTinyH']))
    sp=d['surfaces']
    story.append(Paragraph('1. Surface pondérée cadastrale',st['AxHeadH']))
    tr=sp.get('detail_comparative') or {}
    if tr:
        formula=(f"{float(tr['tranche_haute_m2']):g} m² x {float(tr['importance']):.3f}"
                 f" + {float(tr['tranche_moyenne_m2']):g} m² x {float(tr['coeff_moyen']):.2f}"
                 f" + {float(tr['tranche_basse_m2']):g} m² x {float(tr['coeff_bas']):.2f}"
                 f" = {float(tr['total_non_arrondi']):.2f} m² avant arrondi.")
        story.append(Paragraph('Surface comparative (catégorie '+ph(d['categorie'])+', '+ph(d['nature'])+') : '+ph(formula),st['AxNormalH']))
    story.append(Paragraph('Surface comparative retenue : <b>'+ph(sp.get('comparative','?'))+' m²</b>.',st['AxNormalH']))
    if sp.get('nature')=='M':
        story.append(Paragraph('Dépendances rattachées (pondérées) : '+ph(sp.get('annexes_ponderees',0))+' m² ; terrasse (pondérée) : '+ph(sp.get('terrasse_ponderee',0))+' m².',st['AxNormalH']))
    else:
        story.append(Paragraph('Terrasse déclarée : '+ph(d.get('terrasse_reelle',0))+' m² ; autres dépendances : '+ph(d.get('autres_dependances',0))+' m². Terrasse intégrée après pondération ; seules les dépendances évaluées distinctement restent hors de la surface du logement.',st['AxNormalH']))
    corr=sp.get('detail_correctifs') or {}
    if corr:
        story.append(Paragraph('Correctifs : entretien '+ph(corr.get('entretien'))+' (x '+ph(corr.get('coef_entretien'))+'), situation générale '+ph(corr.get('situation_generale'))+' ('+ph(corr.get('correctif_situation_generale'))+'), situation particulière '+ph(corr.get('situation_particuliere'))+' ('+ph(corr.get('correctif_situation_particuliere'))+'), étage/ascenseur ('+ph(corr.get('correctif_ascenseur'))+').',st['AxNormalH']))
    if sp.get('nature') == 'A' and corr.get('niveau_local') is not None:
        story.append(Paragraph('Article 324 S : niveau retenu '+ph(corr['niveau_local'])+' (entresol compté pour un étage) ; ascenseur de l’immeuble desservant l’étage : '+('oui' if corr.get('ascenseur_immeuble') else 'non')+' ; correctif '+f"{float(sp['correctif_ascenseur']):+.2f}"+' appliqué à la partie principale uniquement. Ce correctif ne correspond pas à un ascenseur privatif intérieur ni à des m² d’équipement.',st['AxNormalH']))
    if sp.get('dependances_ponderees'):
        story.append(Paragraph('Dépendances rattachées détaillées : +'+ph(sp['dependances_ponderees'])+' m² pondérés avant correctif d’ensemble (sans double comptage dans les surfaces principales).',st['AxNormalH']))
    net=sp.get('detail_surface_nette') or {}
    if net.get('mode')=='separe':
        story.append(Paragraph('Partie principale : '+ph(sp['comparative'])+' x '+ph(sp['correctif'])+' = '+ph(net['principal_brut'])+' → '+ph(net['principal_net'])+' m² nets. Éléments secondaires : '+ph(net['secondaires_ponderes'])+' x '+ph(net['coefficient_secondaires'])+' = '+ph(net['secondaires_brut'])+' → '+ph(net['secondaires_net'])+' m² nets, sans correctif d’ascenseur. Somme des deux groupes arrondis séparément : <b>'+ph(sp['surface_nette'])+' m²</b>.',st['AxNormalH']))
    else:
        story.append(Paragraph('Coefficient global appliqué : <b>'+ph(sp.get('correctif','?'))+'</b> ; surface nette : <b>'+ph(sp.get('surface_nette','?'))+' m²</b>.',st['AxNormalH']))

    eq=sp.get('detail_confort') or {}
    if eq:
        story.append(Paragraph('Équivalences superficielles des équipements',st['AxHeadH']))
        eq_rows=[[Paragraph('<b>Équipement</b>',st['AxTinyH']),Paragraph('<b>Équivalence (m²)</b>',st['AxTinyH'])]]
        for libelle,val in eq.items():
            if val:
                eq_rows.append([ph(libelle),str(val)])
        eq_rows.append(['TOTAL ÉQUIPEMENTS',str(sp.get('equivalence_confort',0))])
        eq_table=Table(eq_rows,colWidths=[12*cm,4*cm],repeatRows=1)
        eq_table.setStyle(TableStyle([('BACKGROUND',(0,0),(-1,0),PALE),
                                      ('GRID',(0,0),(-1,-1),.3,LINE),
                                      ('ALIGN',(1,1),(1,-1),'RIGHT'),
                                      ('FONTNAME',(0,-1),(-1,-1),'Helvetica-Bold'),
                                      ('FONTSIZE',(0,0),(-1,-1),8),
                                      ('TOPPADDING',(0,0),(-1,-1),5),
                                      ('BOTTOMPADDING',(0,0),(-1,-1),5)]))
        story.append(eq_table)
    else:
        story.append(Paragraph('Équivalences d’équipements retenues : '+ph(sp.get('equivalence_confort',0))+' m² (détail indisponible dans le dossier).',st['AxNormalH']))
    story.append(Spacer(1,8))
    story.append(Paragraph('<b>Surface pondérée totale = surface nette '+ph(sp.get('surface_nette','?'))+' m² + équipements '+ph(sp.get('equivalence_confort','?'))+' m² = '+ph(sp.get('surface_ponderee','?'))+' m².</b>',st['AxNormalH']))
    story.append(Paragraph('2. Tarif cadastral et valeur locative',st['AxHeadH']))
    story.append(Paragraph('Série tarifaire sélectionnée : <b>'+ph(chosen.get('serie','?'))+'</b> ; origine : '+ph(chosen.get('origine') or 'non précisée')+' ; catégorie : '+ph(d['categorie'])+'.',st['AxNormalH']))
    story.append(Paragraph('VL 1970 = surface pondérée '+ph(sp['surface_ponderee'])+' m² x tarif DGFiP '+eur(chosen['tarif_1970'])+'/m² = <b>'+eur(chosen['vl_1970'])+'</b>.',st['AxNormalH']))
    story.append(Paragraph('Actualisation 1980 : x '+ph(fac['actualisation_1980'])+' ; coefficient national amalgamé jusqu’en '+ph(d['annee'])+' : x '+ph(fac['revalorisation_nationale'])+' ; facteur global : x '+ph(fac['coefficient_cumule'])+'.',st['AxNormalH']))
    story.append(Paragraph('VL revalorisée '+ph(d['annee'])+' = VL 1970 x facteur global = <b>'+eur(chosen.get('vl_annee',0))+'</b>.',st['AxNormalH']))
    story.append(Paragraph('Base foncière de la partie principale = 50 % de la VL revalorisée = <b>'+eur(chosen.get('base_tf',0))+'</b>.',st['AxNormalH']))
    story.append(Paragraph('3. Cotisations par taxe',st['AxHeadH']))
    if chosen.get('montants'):
        for k,montant in chosen['montants'].items():
            objet=rates.get(k) or {}
            taux=objet.get('taux')
            taux_str=f'{float(taux):.4f} %'.replace('.',',') if taux is not None else 'non documenté'
            story.append(Paragraph('<b>'+ph(LIBELLES.get(k,k))+'</b> (millésime '+ph(objet.get('annee_source','?'))+') : base '+eur(chosen['base_tf'])+' x '+ph(taux_str)+' = <b>'+eur(montant)+'</b>.',st['AxNormalH']))
        story.append(Spacer(1,6))
        story.append(Paragraph('<b>Sous-total de la partie principale : '+eur(chosen['total'])+'</b> (hors exonérations et frais).',st['AxNormalH']))
    else:
        story.append(Paragraph('Cotisations indisponibles : au moins un taux requis n’a pas été retrouvé ; aucune hypothèse de taux nul n’est retenue.',st['AxNormalH']))
    story.append(Spacer(1,6))
    story.append(Paragraph('<b>Contrôles :</b> classement et série à confirmer sur la fiche cadastrale ; dépendances éventuellement évaluées à part ; frais, exonérations et dégrèvements particuliers exclus. Montants arrondis pour la lecture.',st['AxTinyH']))
    story.append(Paragraph('Tarifs : '+ph(d.get('source_tarifs','DGFiP open data 2024')),st['AxTinyH']))
    story.append(Paragraph('Coefficients : '+ph(fac.get('source_departement',''))+' ; '+ph(fac.get('source_revalorisation','')),st['AxTinyH']))
    doc.build(story)
    data=out.getvalue()
    if not data.startswith(b'%PDF'):raise RuntimeError('Export PDF habitation invalide')
    return data
