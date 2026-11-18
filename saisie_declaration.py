"""Complément déclaratif saisi après l’estimation, en mémoire de session."""
from datetime import date
from hashlib import sha256

import streamlit as st

from export_cerfa import champs_habitation, champs_professionnel, creer_cerfa
from session_calcul import cle_calcul


def textes(premier, libelles, prefixe='a'):
    return [(f'{prefixe}{i}', libelle) for i, libelle in enumerate(libelles, premier)]


PROPRIETAIRE = (
    'Nom de naissance ou dénomination sociale', 'Date et lieu de naissance',
    'Prénoms', 'Adresse du propriétaire', 'Adresse du propriétaire · suite',
    'Nom d’usage et prénom', 'Date d’acquisition (JJMMAAAA)',
    'Nu-propriétaire · nom, prénoms et adresse', 'Nu-propriétaire · suite',
)
LOGEMENT = (
    'Date d’achèvement des travaux (JJMMAAAA)', 'Nature de l’occupation', 'Nom et prénom de l’occupant',
    'Nature du prêt', 'Date de demande du prêt (JJMMAAAA)', 'Date de décision du prêt (JJMMAAAA)',
    'Nom et adresse du prêteur', 'Adresse du prêteur · suite', 'Montant du prêt (€)',
    'Prix de revient ou d’acquisition (€)', 'Date d’ouverture du chantier (JJMMAAAA)',
)
COORDONNEES = ('Lieu de signature', 'Date de signature', 'Téléphone', 'Adresse électronique',
               'Nom, qualité et adresse du signataire mandaté')
SITUATION = textes(1, ('Département', 'Commune', 'Rue ou lieu-dit', 'Numéro de voirie'))
HABITATION = {
    'h1': (
        ('Situation du local', SITUATION + textes(5, ('Numéro de lot', 'Quote-part'))),
        ('Propriétaire ou usufruitier', textes(7, PROPRIETAIRE)),
        ('Achèvement, occupation et financement', textes(16, LOGEMENT)),
        ('Coordonnées et signature', textes(43, COORDONNEES, 'b')),
    ),
    'h2': (
        ('Situation du local', SITUATION + textes(5, ('Bâtiment', 'Entrée', 'Étage', 'Porte'))
         + textes(1, tuple(f'Lot de l’appartement {i}' for i in range(1, 5)), 'b')),
        ('Propriétaire ou usufruitier', textes(9, PROPRIETAIRE)),
        ('Achèvement, occupation et financement', textes(18, LOGEMENT)),
        ('Coordonnées et signature', list(zip(('b93', 'b94', 'b95', 'b100', 'signature'), COORDONNEES))),
    ),
}
PROFESSIONNEL = (
    ('Situation du local', textes(1, ('Département', 'Commune', 'Numéro de voirie',
     'Voie', 'Bâtiment', 'Entrée', 'Étage', 'Porte', 'Parcelle d’assise'))
     + textes(10, tuple(f'{libelle} {i}' for i in range(1, 5) for libelle in ('Numéro de lot', 'Quote-part')))
     + [('a18', 'Date d’achèvement des travaux (JJMMAAAA)')]),
    ('Origine de la déclaration', [
        ('construction_neuve', 'Construction neuve ou addition', '/1'),
        ('a22', 'Références des autorisations de construire'),
        ('modification_local', 'Modification d’un local existant', '/Oui'),
        ('cac1', 'Réunion ou division de locaux', '/Oui'), ('a23', 'Locaux réunis ou divisés'),
        ('cac2', 'Modification de la répartition des surfaces', '/Oui'),
        ('cac3', 'Modification de la catégorie du local', '/Oui'),
        ('cac4', 'Modification de la méthode d’évaluation', '/Oui'),
        ('cac5', 'Autre modification', '/Oui'), ('a25', 'Précisions sur la modification'),
    ]),
    ('Propriétaire', textes(26, ('Nom', 'Dénomination sociale', 'Prénom', 'Sigle',
                                 'Identifiant fiscal ou SIREN', 'Adresse du propriétaire'))),
    ('Occupation et loyer', list(zip(('cac5b', 'cac7', 'cac8', 'cac9', 'cac10'),
      ('Occupé par le propriétaire', 'Occupé à titre gratuit', 'Loué', 'En partie vacant', 'Vacant'),
      ('/Oui',) * 5)) + textes(33, tuple(f'{libelle} {i}' for i in range(1, 5)
                                         for libelle in ('SIREN de l’occupant', 'Nom ou dénomination de l’occupant')))
     + [('a43', 'Activité principale'), ('a44', 'Loyer annuel (€)')]),
    ('Coordonnées et signature', textes(11, ('Téléphone', 'Lieu de signature', 'Date de signature (JJMMAAAA)',
     'Adresse électronique · avant @', 'Adresse électronique · après @',
     'Nom, qualité et adresse du signataire mandaté'), 'd')),
)


def afficher_declaration(modele, dossier):
    professionnel = modele == '6660-rev'
    adresse = dossier['adresse'] if professionnel else dossier['adresse']['libelle']
    bien = dossier.get('bien') or dossier.get('parcelle') or {}
    identite = (modele, adresse, *(bien.get(cle) for cle in ('prefixe', 'section', 'numero')))
    cle = cle_calcul('cerfa_' + sha256(repr(identite).encode()).hexdigest()[:20])
    initial = champs_professionnel(dossier) if professionnel else champs_habitation(dossier, modele)
    enregistre = st.session_state.get(cle, {})
    groupes = list(PROFESSIONNEL if professionnel else HABITATION[modele])
    if professionnel:
        if dossier['categorie'] == 'EXC1':
            groupes.insert(4, ('Acquisition et travaux · catégorie EXC1', textes(1, tuple(
                f'{poste} · {libelle}' for poste in ('Terrain', 'Aménagements', 'Construction',
                 'Addition de construction', 'Travaux importants') for libelle in ('date (JJMMAAAA)', 'prix (€)')), 'c')))
        groupes.append(('Observations', textes(17, tuple(f'Observations · ligne {i}' for i in range(1, 13)), 'd')))

    champs_visibles = {champ[0] for _, champs in groupes for champ in champs}
    if professionnel:
        champs_visibles.add('cac11')
    enregistre = {nom: valeur for nom, valeur in enregistre.items() if nom in champs_visibles}

    st.subheader(f'Déclaration {modele.upper()}')
    with st.expander('Compléter les informations du formulaire'):
        st.caption('Les champs sont facultatifs dans le simulateur. Enregistrez vos compléments avant de télécharger le formulaire.')
        with st.form(cle + '_saisie'):
            valeurs = {}
            for titre, champs in groupes:
                st.markdown(f'**{titre}**')
                for nom, libelle, *case in champs:
                    valeur = enregistre.get(nom, initial.get(nom))
                    if case:
                        valeurs[nom] = case[0] if st.checkbox(libelle, value=valeur == case[0], key=f'{cle}_{nom}') else '/Off'
                    elif '(JJMMAAAA)' in libelle:
                        date_initiale = date(int(valeur[4:]), int(valeur[2:4]), int(valeur[:2])) if valeur and valeur.isdigit() else None
                        saisie = st.date_input(libelle.removesuffix(' (JJMMAAAA)'), value=date_initiale,
                                              min_value=date(1800, 1, 1), max_value=date(2200, 12, 31),
                                              format='DD/MM/YYYY', key=f'{cle}_{nom}')
                        valeurs[nom] = saisie.strftime('%d%m%Y') if saisie else (initial.get(nom) or '')
                    elif (modele, nom) in {('h1', 'a17'), ('h2', 'a19')}:
                        options = {'': 'À compléter', 'V': 'Vacant', 'P': 'Propriétaire ou usufruitier',
                                   'A': 'Autre occupant'}
                        valeurs[nom] = st.selectbox(libelle, list(options), index=list(options).index(valeur or ''),
                                                    format_func=options.get, key=f'{cle}_{nom}')
                    else:
                        saisir = st.text_area if 'signataire mandaté' in libelle else st.text_input
                        valeurs[nom] = saisir(libelle, value=str(valeur or '').strip(), key=f'{cle}_{nom}').strip()
            if professionnel:
                options = {'': 'À compléter ou sans objet', '/1': 'Oui', '/2': 'Non'}
                choix = enregistre.get('cac11', '')
                valeurs['cac11'] = st.selectbox('Surfaces à usage de bureaux en Île-de-France',
                                                 list(options), index=list(options).index(choix),
                                                 format_func=options.get, key=f'{cle}_cac11')
            if st.form_submit_button('Enregistrer les compléments'):
                st.session_state[cle] = enregistre = {
                    nom: valeur for nom, valeur in valeurs.items()
                    if valeur != str(initial.get(nom) or '')
                    and (valeur != '/Off' or initial.get(nom))
                }
        if enregistre:
            st.success('Les compléments enregistrés sont inclus dans le PDF.')

    st.download_button(
        f'Télécharger le {modele.upper()} prérempli',
        data=creer_cerfa(modele, dossier, enregistre),
        file_name=f'declaration-{modele}.pdf', mime='application/pdf', on_click='ignore',
    )
    st.caption('Le PDF reste modifiable dans un lecteur compatible. Relisez le formulaire et signez-le avant de le transmettre.')
