"""Aide au classement des locaux professionnels d’après la notice 6660-NOT."""

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

DESCRIPTIONS = {
    'MAG1': (
        'Locaux utilisables pour la vente ou une activité commerciale ou de service, disposant d’une vitrine '
        'ou d’un accès sur la rue. La surface principale est inférieure à 400 m². Sont notamment visés '
        'les commerces, bars, restaurants, primeurs, magasins de vêtements, agences bancaires et immobilières.'
    ),
    'MAG2': (
        'Locaux de même affectation que les MAG1, sans accès direct sur la voie publique, '
        'comme les commerces situés en étage ou sur cour. Leur surface principale est inférieure à 400 m².'
    ),
    'MAG3': (
        'Locaux de même affectation que les MAG1 et intégrés à un ensemble organisé d’établissements '
        'commerciaux. Il peut s’agir d’un centre ou d’une zone commerciale en centre-ville ou en périphérie, '
        'd’un aéroport, d’une gare ou d’une galerie marchande. Leur surface principale est inférieure à 400 m².'
    ),
    'MAG4': (
        'Magasins de grande surface, intégrés ou non dans un ensemble commercial. Cette catégorie comprend '
        'notamment les supermarchés, les magasins dédiés à l’alimentation et les magasins de meubles, d’électroménager, '
        'd’habillement, de luminaires, de décoration, de jardinerie ou de bricolage.'
    ),
    'MAG5': (
        'Magasins de très grande surface, intégrés ou non dans un ensemble commercial. Cette catégorie comprend '
        'notamment les hypermarchés, les magasins dédiés à l’alimentation, les magasins de meubles, d’électroménager, '
        'd’habillement, de luminaires, de décoration, de jardinerie ou de bricolage, ainsi que les grands magasins.'
    ),
    'MAG6': 'Ce classement s’applique aussi quand la station-service ou la station de lavage comporte une boutique ou un espace de vente.',
    'MAG7': 'Marchés publics, marchés d’intérêt national, halles de marché et marchés aux bestiaux.',
    'BUR1': (
        'Bureaux situés dans un immeuble de conception ancienne, sans équipements particuliers. Ils accueillent '
        'des activités de services, y compris des professions libérales, médicales ou paramédicales, '
        'comme les cabinets de médecins ou de dentistes.'
    ),
    'BUR2': (
        'Bureaux situés dans un immeuble de conception récente ou rénové de manière importante. '
        'Leur agencement est modulable, par exemple avec des cloisons mobiles, et ils disposent d’équipements '
        'informatiques comme le câblage. Ils accueillent aussi les activités de services et les professions libérales, '
        'y compris les cabinets médicaux et paramédicaux.'
    ),
    'BUR3': 'Cabinets de vétérinaires, laboratoires d’analyses médicales et centres de radiologie.',
    'DEP1': (
        'Terrains exploités commercialement comme dépôts à ciel ouvert, tels que les déchetteries, '
        'les casses automobiles et les dépôts de matériaux. La catégorie comprend aussi les terrains '
        'exploités pour la publicité au moyen de panneaux d’affichage ou d’écrans dédiés.'
    ),
    'DEP2': (
        'Entrepôts ou hangars destinés au stockage de marchandises, notamment pour le commerce de gros, '
        'la vente par Internet ou la vente sur catalogue.'
    ),
    'DEP3': (
        'Parcs ou aires de stationnement non couverts. Leur surface se renseigne en PK2 au cadre 4 '
        'lorsque le parc constitue la totalité du local. Pour un commerce, les aires de stationnement non couvertes '
        'rattachées au local se renseignent aussi en PK2.'
    ),
    'DEP4': (
        'Parcs ou aires de stationnement couverts. Leur surface se renseigne en PK1 au cadre 4 '
        'lorsque le parc constitue la totalité du local. Pour un commerce, les aires de stationnement couvertes '
        'rattachées au local se renseignent aussi en PK1.'
    ),
    'DEP5': 'Installations spécifiques de stockage, telles que les réservoirs, silos et cuves.',
    'ATE1': (
        'Locaux exploités par des artisans pour transformer ou manipuler des matières ou des matériaux '
        'avec un outillage courant. La notice cite la réparation mécanique, la menuiserie et l’ébénisterie.'
    ),
    'ATE2': (
        'Locaux spécialement équipés pour la transformation, la manutention ou la maintenance. Ils peuvent '
        'accueillir des activités commerciales, de service après-vente ou de petit stockage, avec peu de '
        'services administratifs. On les trouve souvent en zone d’activité ou en zone industrielle. '
        'La notice cite l’entretien automobile.'
    ),
    'ATE3': (
        'Chenils, viviers, pensions pour animaux et locaux aménagés pour permettre la conservation '
        'de certaines espèces animales.'
    ),
    'HOT4': 'Foyers d’hébergement, centres d’accueil et auberges de jeunesse, généralement d’un confort limité.',
    'HOT5': (
        'Hôtels-clubs, villages de vacances et résidences hôtelières composés d’appartements, de maisonnettes '
        'ou de bungalows. Ils sont intégrés à un ensemble proposant des équipements sportifs ou de loisirs, '
        'comme un complexe aquatique ou des courts de tennis.'
    ),
    'SPE1': (
        'Locaux consacrés à des activités culturelles ou artistiques, tels que les théâtres, cinémas, '
        'salles de concert, de spectacle, de conférence ou d’exposition et les musées.'
    ),
    'SPE2': (
        'Patinoires, piscines, gymnases, courts de tennis, salles de gymnastique ou de musculation '
        'et centres de remise en forme.'
    ),
    'SPE3': 'Discothèques, casinos, salles de jeux, cabarets et cafés-théâtres.',
    'SPE6': 'Établissements de relaxation, hammams, saunas, établissements de massage et spas.',
    'SPE7': (
        'Centres de loisirs ou de colonies de vacances, maisons de jeunes, foyers socioculturels '
        'et locaux culturels dédiés utilisés par des communautés spirituelles.'
    ),
    'ENS1': (
        'Établissements d’enseignement et institutions privées gérés par des associations sans but lucratif '
        'régies par la loi du 1er juillet 1901. Ils peuvent comporter un internat.'
    ),
    'ENS2': 'Les autres établissements d’enseignement relèvent d’ENS2. Ils peuvent comporter un internat.',
    'CLI1': (
        'Cliniques et établissements hospitaliers qui dispensent des soins, pratiquent des actes médicaux '
        'importants et assurent l’hébergement des malades. L’outillage médical y est important.'
    ),
    'CLI2': (
        'Centres de soins ou de consultations médicales, dont les centres de médecine préventive, '
        'instituts médico-pédagogiques ou médico-psycho-pédagogiques et établissements de garde des enfants, '
        'comme les crèches et les haltes-garderies. La notice rattache généralement les cabinets médicaux à BUR1 ou BUR2.'
    ),
    'CLI3': 'Maisons de repos, maisons de retraite médicalisées ou non et locaux assimilés.',
    'CLI4': 'Centres de rééducation, centres de thalassothérapie et établissements thermaux.',
    'IND1': (
        'La notice regroupe ici les établissements suivants.\n\n'
        '- Usines ou ateliers utilisant un outillage important pour transformer des matières premières, fabriquer ou réparer des objets.\n'
        '- Locaux de manipulation ou de prestations de services où l’outillage et la force motrice jouent un rôle prépondérant.\n'
        '- Installations de stockage d’un certain volume qui utilisent un outillage très important, tel que des ponts roulants ou des grues.\n'
        '- Locaux occupés par des artisans relevant de l’article 1499-00 A du CGI.'
    ),
    'IND2': 'Carrières et établissements assimilés où l’outillage et la force motrice jouent un rôle prépondérant dans les opérations d’extraction.',
    'EXC1': (
        'Locaux dont les caractéristiques exceptionnelles empêchent un classement dans une autre catégorie, '
        'tels que certains parcs de loisirs, centres aquatiques ou aquariums. La rubrique couvre aussi '
        'les locaux qui ne relèvent d’aucune des 38 autres catégories. L’évaluation suit le III de l’article 1498 '
        'du CGI. Le cadre 3.10 demande les dates et les prix de revient ou d’acquisition.'
    ),
}

PRECISIONS_PAR_FAMILLE = {
    'MAG': (
        'Pour MAG1 à MAG5, reportez-vous à la surface principale P1. Le cadre 4 y inclut les espaces '
        'de vente, y compris en sous-sol, et les espaces accessibles à la clientèle.'
    ),
    'HOT': (
        'HOT1 à HOT3 regroupent les établissements de tourisme assimilables à des hôtels. Le classement '
        'suit l’arrêté du 23 décembre 2009, en fonction des étoiles ou du niveau de confort équivalent.'
    ),
    'SPE': 'Le classement des campings en SPE4 ou SPE5 suit la classification définie dans l’arrêté du 6 juillet 2010.',
}


def libelle_categorie(code, categories):
    return LIBELLES_MAGASINS.get(code, categories[code]['description']).rstrip('.')


@st.dialog('Guide des catégories de locaux professionnels', width='large')
def afficher_guide_categories(categories, categorie):
    st.markdown(
        'Retenez **une seule catégorie**. La nature et la destination principale du local déterminent sa famille. '
        'Son utilisation et ses caractéristiques physiques déterminent ensuite la catégorie. '
        'Si plusieurs activités sont exercées dans le local, retenez celle qui occupe la plus grande surface.'
    )
    st.caption('Pour un garage qui vend et répare des véhicules, la notice indique MAG1, MAG4 ou MAG5 '
               'si la vente occupe la plus grande surface, et ATE2 si la réparation occupe la plus grande surface.')
    familles = {}
    for code in categories:
        familles.setdefault(code[:3], []).append(code)
    famille_selectionnee = categorie[:3] if categorie else 'MAG'
    for famille, codes in familles.items():
        with st.expander(FAMILLES.get(famille, famille), expanded=famille == famille_selectionnee):
            if famille in PRECISIONS_PAR_FAMILLE:
                st.markdown(PRECISIONS_PAR_FAMILLE[famille])
            for code in codes:
                st.markdown(f'**{code} · {libelle_categorie(code, categories)}**')
                if code in DESCRIPTIONS:
                    st.markdown(DESCRIPTIONS[code])
    st.caption('Source · notice de la déclaration 6660-REV (6660-NOT), cadres 3 et 4.')
