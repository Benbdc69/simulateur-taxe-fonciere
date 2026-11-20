"""Aide au classement des locaux professionnels d’après le cadre 3 de la 6660-REV."""

import streamlit as st

FAMILLES = {
    'MAG': 'Magasins et lieux de vente',
    'BUR': 'Bureaux et locaux assimilés',
    'DEP': 'Dépôts, stockage et parcs de stationnement',
    'ATE': 'Ateliers et locaux assimilés',
    'HOT': 'Hôtels et hébergements',
    'SPE': 'Spectacles, sports et loisirs',
    'ENS': 'Établissements d’enseignement',
    'CLI': 'Établissements sanitaires et sociaux',
    'IND': 'Établissements industriels évalués par la grille tarifaire',
    'EXC': 'Autres établissements',
}

# Le formulaire précise les seuils de surface principale pour les magasins.
LIBELLES_MAGASINS = {
    'MAG1': 'Boutiques et magasins sur rue de moins de 400 m² en surface principale',
    'MAG2': 'Commerces sans accès direct sur la rue de moins de 400 m² en surface principale',
    'MAG3': 'Magasins d’un ensemble commercial de moins de 400 m² en surface principale',
    'MAG4': 'Magasins de grande surface de 400 à moins de 2 500 m² en surface principale',
    'MAG5': 'Magasins de très grande surface à partir de 2 500 m² en surface principale',
}

REPERES = {
    'MAG1': 'Par exemple, une boutique, un café, un restaurant ou une agence bancaire avec un accès direct sur rue.',
    'MAG2': 'Par exemple, un commerce accessible par une cour ou un passage intérieur. Vérifiez s’il relève d’un ensemble commercial.',
    'MAG3': 'Par exemple, une boutique intégrée à une galerie marchande.',
    'MAG4': 'Utilisez la surface principale P1 figurant au cadre 4 pour vérifier le seuil.',
    'MAG6': 'Par exemple, une station de distribution de carburant ou un centre de lavage automobile.',
    'MAG7': 'Par exemple, une halle de marché aménagée pour accueillir plusieurs commerçants.',
    'BUR3': 'Repérez les aménagements particuliers qui distinguent le local de bureaux d’usage courant.',
    'DEP1': 'Par exemple, une aire de stockage à ciel ouvert exploitée comme lieu de dépôt.',
    'DEP2': 'Par exemple, un entrepôt fermé ou un hangar principalement affecté au stockage.',
    'DEP3': 'Parc extérieur évalué comme un local de stationnement. Le parking annexe d’un commerce se renseigne au cadre 4, en PK2.',
    'DEP4': 'Par exemple, un parc de stationnement en sous-sol évalué comme local distinct. Un parking annexe couvert se renseigne en PK1.',
    'DEP5': 'Par exemple, un silo ou une cuve aménagée pour le stockage.',
    'ATE1': 'Par exemple, un atelier artisanal de menuiserie ou de réparation.',
    'ATE2': 'Par exemple, un site de manutention ou un atelier doté d’installations pour transformer des produits ou entretenir du matériel.',
    'ATE3': 'Par exemple, un chenil ou un établissement équipé de viviers.',
    'HOT4': 'Par exemple, une auberge de jeunesse ou un foyer proposant un hébergement collectif.',
    'HOT5': 'Par exemple, une résidence de tourisme avec services hôteliers ou un village de vacances.',
    'SPE1': 'Par exemple, une salle de cinéma, de théâtre ou de concert.',
    'SPE2': 'Par exemple, un gymnase, un terrain de sport ou une enceinte sportive.',
    'SPE3': 'Par exemple, un bowling ou une salle de jeux.',
    'SPE6': 'Par exemple, un spa, un hammam ou un sauna.',
    'SPE7': 'Par exemple, un centre de vacances pour enfants ou une maison de jeunes.',
    'ENS1': 'Vérifiez que l’établissement privé est exploité dans un but non lucratif, par exemple par une association.',
    'ENS2': 'Par exemple, une école privée ou un organisme d’enseignement exploité dans un but lucratif.',
    'CLI2': 'Par exemple, un centre médico-social, une crèche ou une halte-garderie.',
    'CLI3': 'Par exemple, une maison de retraite ou un EHPAD.',
    'CLI4': 'Par exemple, un établissement thermal ou de thalassothérapie.',
    'IND1': 'Vérifiez que la fiche fiscale rattache le site à la grille des locaux professionnels et mentionne son outillage important.',
    'IND2': 'Par exemple, une carrière ou un site d’extraction assimilable évalué selon la grille des locaux professionnels.',
    'EXC1': 'Cette rubrique vise les locaux présentant des caractéristiques exceptionnelles. Le cadre 3.10 demande des données de prix de revient ou d’acquisition.',
}


def libelle_categorie(code, categories):
    return LIBELLES_MAGASINS.get(code, categories[code]['description']).rstrip('.')


@st.dialog('Guide des catégories de locaux professionnels', width='large')
def afficher_guide_categories(categories, categorie):
    st.write('Choisissez la catégorie d’après l’activité principale exercée dans le local et son aménagement. '
             'La fiche d’évaluation cadastrale indique le code retenu par la DGFiP.')
    familles = {}
    for code in categories:
        familles.setdefault(code[:3], []).append(code)
    famille_selectionnee = categorie[:3] if categorie else 'MAG'
    for famille, codes in familles.items():
        with st.expander(FAMILLES.get(famille, famille), expanded=famille == famille_selectionnee):
            if famille == 'BUR':
                st.write('Pour BUR1 et BUR2, examinez l’agencement intérieur et les équipements. '
                         'Un immeuble ancien peut abriter des bureaux réaménagés récemment.')
            for code in codes:
                st.markdown(f'**{code} · {libelle_categorie(code, categories)}**')
                if code in REPERES:
                    st.write(REPERES[code])
    st.caption('Source des catégories et des seuils · déclaration 6660-REV, cadre 3. Les exemples servent de repères pour la sélection.')
