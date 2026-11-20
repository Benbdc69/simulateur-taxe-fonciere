"""Rapport PDF de simulation : utilise uniquement le résultat déjà calculé.
Aucune requête réseau, aucune réévaluation des paramètres fiscaux.
"""
from io import BytesIO
from xml.sax.saxutils import escape
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, PageBreak

from presentation_pdf import pied_rapport, synthese_pdf
from moteur import TAXES_AVANT_2021


# Palette éditoriale inspirée d'Axens, indépendante du thème Streamlit
BLEU_FONCE = colors.HexColor('#164C79')
BLEU_PALE = colors.HexColor('#EAF2F8')
BORDURE = colors.HexColor('#DFE8F2')
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
    frais = dossier.get('frais')
    reforme = analyse.get('reforme_2017')
    planch = analyse.get('planchonnement', {})
    partial = analyse['partial']
    bien = dossier['bien']
    styles = getSampleStyleSheet()
    styles.add(ParagraphStyle(name='TitreTF', parent=styles['Title'], fontName='Helvetica-Bold',
                              fontSize=19, leading=24, textColor=BLEU_FONCE, spaceAfter=12))
    styles.add(ParagraphStyle(name='PetitTF', parent=styles['Normal'], fontSize=8.5,
                              leading=12, textColor=SECONDAIRE, spaceAfter=7))
    styles.add(ParagraphStyle(name='CorpsTF', parent=styles['Normal'], fontSize=10, leading=15, spaceAfter=7))
    buffer = BytesIO()
    pdf = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=1.7*cm, rightMargin=1.7*cm,
                            topMargin=1.7*cm, bottomMargin=1.6*cm,
                            title='Estimation de taxe foncière - local professionnel')
    lignes = [(ligne['taxe'], ligne['base_taxable'], ligne['taux_pct'], ligne['montant'])
              for ligne in (result or {}).get('lignes', ())]
    parcelle = ' '.join(str(bien.get(cle) or '') for cle in ('prefixe', 'section', 'numero')).strip()
    reserve = planch.get('reserve') or 'Estimation sous réserve des paramètres cadastraux et des régimes particuliers.'
    story = synthese_pdf(
        dossier['annee'], 'Local professionnel', dossier.get('adresse'),
        f"Parcelle {parcelle} · INSEE {bien.get('code_insee', '—')}",
        f"Catégorie {dossier['categorie']} · Déclaration 6660-REV",
        lignes, result.get('total_hors_frais') if result else None, frais,
        partial.get('valeur_locative_brute'),
        'Cotisations indisponibles : les paramètres fiscaux requis sont détaillés en annexe.'
        if not result else reserve,
    )
    story.extend([PageBreak(), Paragraph('Annexe — détail du calcul', styles['TitreTF'])])
    exo = analyse.get('exoneration_neuf', {})
    if dossier.get('construction_nouvelle'):
        story.append(Paragraph('<b>Construction nouvelle :</b> oui ; année d’achèvement : '+_texte(dossier.get('annee_achevement')), styles['CorpsTF']))
        story.append(Paragraph('Exonération de 40 % sur la part communale et les taxes additionnelles éligibles (GEMAPI, TSE et syndicats sans fiscalité propre) : '+('appliquée' if exo.get('active') else 'non appliquée ('+_texte(exo.get('raison'))+')'), styles['PetitTF']))
    if not result and analyse.get('missing'):
        story.append(Paragraph('<b>Données manquantes :</b> '+_texte(', '.join(analyse['missing'])),
                               styles['PetitTF']))
    story.extend([Spacer(1, 12), Paragraph('<b>Paramètres de calcul</b>',styles['Heading3']),
                  Paragraph('Secteur : '+_texte(partial.get('secteur'))+' ; tarif : '+_nombre(partial.get('tarif'))+
                            ' EUR/m² ; coefficient de localisation : '+_nombre(partial.get('localisation'),4), styles['PetitTF']),
                  Paragraph('Valeur locative brute : '+_nombre(partial.get('valeur_locative_brute'))+' EUR',styles['PetitTF'])])
    if reforme:
        story.append(Paragraph('Calcul du planchonnement', styles['Heading3']))
        story.append(Paragraph(
            f"Base TFPB 2016 de {_nombre(reforme['base_2016'])} EUR x 1,004 = "
            f"<b>ancienne base 2017 de {_nombre(reforme['base_ancienne_2017'])} EUR</b>.",
            styles['PetitTF']))
        if reforme['vl_revisee_2017'] is not None:
            story.append(Paragraph(
                f"Tarif 2017 de {_nombre(reforme['tarif_2017'])} EUR/m² et coefficient de localisation "
                f"de {_nombre(reforme['localisation_2017'], 2)} appliqués à la surface pondérée, soit une "
                f"<b>valeur locative révisée 2017 de {_nombre(reforme['vl_revisee_2017'])} EUR</b>.",
                styles['PetitTF']))
        story.append(Paragraph(
            'Le calcul suppose que les surfaces et le classement saisis correspondent à 2017. '
            '<link href="https://www.impots.gouv.fr/revision-des-valeurs-locatives">Barèmes départementaux de la DGFiP</link>.',
            styles['PetitTF']))
    if planch.get('applique'):
        story.append(Paragraph('<b>Planchonnement pris en compte</b>', styles['Heading3']))
        bases = (reforme or {}).get('bases_neutralisees', {})
        for cle, val in planch.get('corrections', {}).items():
            bases_2017 = (f" · ({_nombre(reforme['base_ancienne_2017'])} EUR − {_nombre(bases[cle])} EUR) ÷ 2"
                          if cle in bases else '')
            story.append(Paragraph(_texte(TAXES_AVANT_2021[cle])+bases_2017
                                   +' · correction de base '+_nombre(val)+' EUR', styles['PetitTF']))
    if planch.get('reserve'):
        story.append(Paragraph('<b>Réserve relative au planchonnement :</b> '+_texte(planch['reserve']), styles['PetitTF']))
    out_of_date=[f"{key} ({rate['annee_source']})" for key,rate in analyse.get('taux',{}).items()
                 if rate and rate.get('decalage',0)>0]
    if out_of_date:
        story.append(Paragraph('Taux repris de millésimes antérieurs : '+_texte(', '.join(out_of_date)),styles['PetitTF']))
    if analyse.get('neutral_warnings'):
        story.append(Paragraph('Certaines neutralisations historiques ont été reprises à titre provisoire.',styles['PetitTF']))
    story.append(Spacer(1, 12))
    story.append(Paragraph('<b>Réserves importantes</b>',styles['Heading3']))
    story.append(Paragraph('Estimation hors exonérations particulières. '
                           'Les taux repris d’années antérieures et les zones TEOM doivent être vérifiés. Pour une construction nouvelle, l’exonération de l’article 1383 II du CGI suppose le respect des formalités déclaratives (90 jours).',styles['PetitTF']))
    story.append(Paragraph('1. Pondération des surfaces', styles['Heading3']))
    coefficients = {'P1': 1.0, 'P2': 0.5, 'P3': 0.2, 'PK1': 0.5, 'PK2': 0.2}
    pond = (result or {}).get('surfaces_ponderees', {})
    lignes_surface = [[_texte('Surface'), _texte('Déclarée (m²)'), _texte('Coefficient'), _texte('Pondérée (m²)')]]
    for cle, coeff in coefficients.items():
        brut = float(dossier.get('surfaces', {}).get(cle, 0) or 0)
        valeur = pond.get(cle, brut * coeff)
        lignes_surface.append([cle, _nombre(brut), _nombre(coeff, 2), _nombre(valeur)])
    lignes_surface.append(['TOTAL', '', '', _nombre((result or {}).get('surface_ponderee_totale', partial.get('surface_ponderee')))])
    t = Table(lignes_surface, colWidths=[4.0*cm, 4.0*cm, 4.0*cm, 4.0*cm], repeatRows=1)
    t.setStyle(TableStyle([('BACKGROUND', (0,0), (-1,0), BLEU_PALE),
                           ('GRID',(0,0),(-1,-1),.35,BORDURE),
                           ('ALIGN',(1,1),(-1,-1),'RIGHT'),
                           ('FONTSIZE',(0,0),(-1,-1),8),
                           ('TOPPADDING',(0,0),(-1,-1),7),
                           ('BOTTOMPADDING',(0,0),(-1,-1),7),
                           ('FONTNAME',(0,-1),(-1,-1),'Helvetica-Bold')]))
    story.append(t)
    story.append(Spacer(1,10))
    story.append(Paragraph('2. Valeur locative et assiette initiale', styles['Heading3']))
    surface_total = (result or {}).get('surface_ponderee_totale', partial.get('surface_ponderee'))
    tarif = (result or {}).get('tarif_m2', partial.get('tarif'))
    localisation = (result or {}).get('coefficient_localisation', partial.get('localisation'))
    vl = (result or {}).get('valeur_locative_brute',partial.get('valeur_locative_brute'))
    assiette = (result or {}).get('assiette_tf_avant_neutralisation')
    story.append(Paragraph('Secteur fiscal : <b>'+_texte(partial.get('secteur'))+'</b> ; catégorie : <b>'+_texte(dossier.get('categorie'))+'</b>.', styles['CorpsTF']))
    story.append(Paragraph('Surface pondérée <b>'+_nombre(surface_total)+' m²</b> x tarif <b>'+_nombre(tarif)+' EUR/m²</b> x coefficient de localisation <b>'+_nombre(localisation,4)+'</b> = valeur locative brute <b>'+_nombre(vl)+' EUR</b>.', styles['CorpsTF']))
    if assiette is not None:
        story.append(Paragraph('Valeur locative brute '+_nombre(vl)+' EUR x 50 % = assiette avant neutralisation <b>'+_nombre(assiette)+' EUR</b>.', styles['CorpsTF']))
    else:
        story.append(Paragraph('Assiette avant neutralisation : non calculable (paramètres manquants).', styles['PetitTF']))
    for cle in ('secteur','localisation','neutralisation'):
        m = (analyse.get('messages') or {}).get(cle)
        if m:
            story.append(Paragraph(_texte(cle.title())+' : '+_texte(m),styles['PetitTF']))
    story.append(Paragraph('3. Base et cotisation par composante fiscale', styles['Heading3']))
    if result:
        for line in result.get('lignes', []):
            source_taux = (analyse.get('taux') or {}).get(line.get('cle')) or {}
            millesime = source_taux.get('annee_source', dossier.get('annee'))
            cb = [Paragraph('<b>'+_texte(line.get('taxe',''))+'</b>  (taux millésime '+_texte(millesime)+')',styles['CorpsTF'])]
            cb.append(Paragraph('Assiette '+_nombre(assiette)+' EUR x neutralisation '+_nombre(line.get('coefficient_neutralisation'),6)+' = base neutralisée <b>'+_nombre(line.get('base_neutralisee'))+' EUR</b>.',styles['PetitTF']))
            cb.append(Paragraph('Base neutralisée '+_nombre(line.get('base_neutralisee'))+' EUR + correction de planchonnement signée '+_nombre(line.get('correction_planchonnement'))+' EUR = base avant exonération <b>'+_nombre(line.get('base_avant_abattement'))+' EUR</b>.',styles['PetitTF']))
            cb.append(Paragraph('Base avant exonération '+_nombre(line.get('base_avant_abattement'))+' EUR x (1 - '+_nombre(line.get('abattement_pct'))+' %) = base taxable <b>'+_nombre(line.get('base_taxable'))+' EUR</b>.',styles['PetitTF']))
            cb.append(Paragraph('Base taxable '+_nombre(line.get('base_taxable'))+' EUR x taux '+_nombre(line.get('taux_pct'))+' % = cotisation <b>'+_nombre(line.get('montant'))+' EUR</b>.',styles['PetitTF']))
            story.append(KeepTogether(cb+[Spacer(1,5)]))
        story.append(Paragraph('<b>Total des composantes avant frais : '+_nombre(result.get('total_hors_frais'))+' EUR</b>.', styles['CorpsTF']))
        story.append(Paragraph('Les opérations sont effectuées par le moteur avec les valeurs numériques non arrondies ; le présent rapport arrondit leur affichage à deux décimales. Une correction de planchonnement affichée à zéro ne démontre pas qu’aucun planchonnement n’est applicable.',styles['PetitTF']))
    else:
        story.append(Paragraph('Aucune cotisation détaillée ne peut être affichée : les taux, tarifs, neutralisations ou autres paramètres requis sont incomplets.',styles['PetitTF']))
    if frais:
        story.append(Paragraph('4. Frais de gestion — CGI, article 1641', styles['Heading3']))
        for ligne in (result or {}).get('lignes', []):
            calcul = frais.get('lignes', {}).get(ligne['cle'])
            if calcul:
                story.append(Paragraph(
                    f"{_texte(ligne['taxe'])} : {_nombre(ligne['montant'])} EUR x {calcul['taux']} %"
                    f" = <b>{_nombre(calcul['montant'])} EUR</b>.", styles['PetitTF']))
        story.append(Paragraph('Frais calculables : '+_nombre(frais['frais'])+' EUR.', styles['CorpsTF']))
    story.append(Paragraph('Ce document sert au contrôle des étapes de simulation ; il ne remplace pas l’avis fiscal, la fiche d’évaluation cadastrale ni la vérification des régimes particuliers.',styles['PetitTF']))
    pdf.build(story, onFirstPage=pied_rapport, onLaterPages=pied_rapport)
    sortie = buffer.getvalue()
    if not sortie.startswith(b'%PDF'):
        raise RuntimeError('Le rapport professionnel ne contient pas de PDF valide')
    return sortie
