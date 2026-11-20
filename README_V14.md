# Simulateur de taxe foncière — V14, parcours express

## Ce qui change

La page principale ne demande plus que : adresse du local, catégorie fiscale, ventilation des surfaces P1/P2/P3/PK1/PK2 et année d'imposition. Le programme tente d'identifier la parcelle (confirmation seulement lorsqu'il existe une ambiguïté), d'actualiser les publications DGFiP et de récupérer les taux. Il restitue le détail par composante fiscale lorsqu'il dispose des paramètres.

**Le calcul fiscal reste le moteur V13.1 (`moteur.py`)** : la V14 ne réimplémente pas les formules de taxe foncière. Le parcours est dans `parcours_express.py` et reste indépendant de `page_calcul_v9.py`, conservée comme référence technique mais non appelée par le portail.

## Lancer sur Mac

Copiez et décompressez le ZIP, puis utilisez `bash lancer_mac_linux.sh` ou `demarrer_mac.command` (si vous avez déjà Python et les dépendances). Rendez-vous sur http://localhost:8501. En local, le script de lancement renseigne `TF_LOCAL_MODE=1`. Le lancement cloud conserve la protection par `TF_SHARED_PASSWORD_HASH` dans les Secrets de Streamlit.

## Mettre à jour GitHub / Streamlit

Dans votre dépôt GitHub existant, chargez les nouveaux fichiers à la racine (`app.py`, `parcours_express.py`, les modules `.py`, `requirements.txt`, et `data/referentiel_initial.json`). Le point d'entrée Streamlit reste `app.py`. Conservez votre secret `TF_SHARED_PASSWORD_HASH` : il reste inchangé et n'est pas présent dans le dépôt.

Ne déposez jamais `data/referentiel_local.json`, les dossiers `data/historique`, `data/en_attente`, les données de clients ou les fichiers `.streamlit/secrets.toml` sur GitHub. Le `.gitignore` est livré mais les fichiers déposés via l'interface web doivent toujours être vérifiés.

## Limites fiscales importantes

- L'adresse et la déclaration 6660-REV **ne contiennent pas** les anciennes valeurs locatives nécessaires au planchonnement des locaux existant avant 2017, ni toutes les exonérations. Le résultat visible est une **estimation de base** sans correctifs historiques, exonérations particulières et sans frais de gestion. Il ne remplace pas un avis fiscal.
- La TEOM peut relever d'un zonage local et ses taux doivent être rapprochés du bien.
- Lorsque les fichiers officiels ou une composante indispensable manquent, **aucun montant global n'est inventé** : l'interface fournit la valeur locative calculable et indique ce qu'il manque.
- Le moteur actuellement embarqué est limité aux années 2017–2026. Les règles transitoires 2027 doivent être intégrées avant de proposer cette année.
- La synchronisation est déclenchée au premier calcul pour la commune / le département / l'année dans une session. Elle peut prendre du temps, surtout lors du premier usage, et elle nécessite un accès aux services DGFiP et aux sources de taux.
- Les taux et barèmes récupérés sont réutilisés depuis le référentiel local. Le fichier national des tarifs habitation 2024 est également conservé sur disque après une première récupération réussie. Les taux de millésimes antérieurs restent signalés et aucune donnée manquante n’est remplacée par zéro.
- Sur un serveur, configurez `TF_DATA_DIR` vers un dossier accessible en écriture sur un volume persistant. Ce dossier conserve `referentiel_local.json`, les tarifs habitation et l’historique après redémarrage. Pour conserver un référentiel local déjà constitué, copiez-le dans ce dossier avant de démarrer le simulateur. Par défaut, les fichiers restent sous `data/`. Streamlit Community Cloud peut réinitialiser les fichiers du conteneur. Une première recherche cadastrale ou une donnée fiscale jamais enregistrée peut toujours nécessiter qu’un service externe soit disponible.

## Tests

### Saisie guidée professionnel et habitation

Le parcours professionnel explique les rubriques P1/P2/P3/PK1/PK2 et les champs
d’historique. La catégorie fiscale doit être choisie explicitement. Les champs
conditionnels apparaissent dès le changement de choix ; modifier une saisie
invalide le résultat précédent. Le périmètre d’imposition est limité à 2017–2026.

Le parcours habitation comporte trois étapes : recherche et confirmation de
l’adresse, surfaces et équipements, vérification puis estimation. Les saisies
sont conservées lors du retour à une étape précédente. La catégorie est visible et obligatoire avant de calculer. Une aide qualitative
présente les huit catégories et les critères de classement (CGI, annexe III,
article 324 H). Le choix est identifié comme indicatif ou issu de la fiche cadastrale.
Aucune fourchette entre catégories différentes n’est calculée. Le détail du calcul,
les taux manquants ou antérieurs et le zonage TEOM non confirmé sont affichés ;
le PDF reprend la catégorie du scénario sélectionné. Les dépendances distinctes
d’appartement restent hors du chiffrage de la partie principale.

Validation locale : `python -m unittest discover -s tests -v`. Les tests de
navigation Streamlit simulent les API publiques et ne valident pas leur accès réel.

Les tests de non-régression du moteur sont inclus. Les appels réels IGN/DGFiP
doivent être vérifiés sur un environnement disposant des autorisations réseau
nécessaires avant publication générale.

### Appartement : rubriques H2

Le cadre 41 recueille les nombres de pièces par type, la surface totale affectée
à l’habitation, les terrasses et l’existence d’une partie professionnelle. Le
cadre 42 recueille les équipements, dont une case chauffage, l’ascenseur et
l’escalier de service. La rubrique sanitaire compte uniquement les lavabos ; les éviers sont exclus.
Les correctifs et le classement réservés à l’administration sont regroupés
dans un volet facultatif.

Lorsque le chauffage est coché, le simulateur retient les pièces du cadre 41 A,
y compris les cuisines et les salles d’eau, sauf les autres annexes intérieures.
Il applique 2 m² d’équivalence par pièce retenue. L’escalier de service est
conservé sans correctif automatique.
La partie professionnelle demeure hors du calcul habitation.

Le résultat habitation reprend les cartes du parcours professionnel : montant
annuel sur le périmètre simulé, trois indicateurs de synthèse et répartition par
taxe avec base, taux et millésime. Le calcul détaillé et les sources restent dans
des volets dépliables. Si des taux manquent, la carte principale affiche la valeur
locative et précise qu’il ne s’agit pas d’une cotisation.

### Catégorie et fourchette des séries

La catégorie doit être sélectionnée dans le parcours principal. Les repères
simplifiés couvrent architecture, construction, distribution et confort ; ils
ne remplacent pas le classement par comparaison avec les locaux de référence
communaux. Les catégories intermédiaires restent disponibles.

Lorsque plusieurs séries existent dans la catégorie choisie, la fourchette
concerne uniquement ces séries pour le même décompte de pièces. Le PDF conserve ce même périmètre. Sans taux
complets, la fourchette porte sur les bases TFPB, sans inventer de cotisations.

Le résultat et le PDF explicitent la majoration chauffage : nombre de pièces
retenues × 2 m². Ces m² sont des équivalences, pas de la surface réelle.

### Ascenseur de l’immeuble — article 324 S

La desserte par l’ascenseur de l’immeuble et le niveau du logement sont saisis
explicitement (entresol compté pour un étage). Le barème 324 S est ajouté au
correctif d’ensemble avant calcul de la surface nette ; il ne correspond ni à
un ascenseur intérieur privatif ni à une équivalence de surface supplémentaire.
Le niveau, la présence d’ascenseur et le coefficient retenu sont tracés à l’écran
et dans le PDF. Le barème numérique existant est conservé et testé à chaque niveau.

### Recherche par référence cadastrale, sans adresse

Les parcours professionnel et habitation proposent « Adresse » ou « Parcelle
cadastrale ». Dans ce second mode, saisir commune, code INSEE cadastral, section
et numéro ; le préfixe est facultatif. Le code INSEE n’est pas le code postal.
Les sections à une lettre et les numéros courts sont normalisés (A → 0A,
242 → 0242). Si le préfixe est inconnu, les références distinctes restent
proposées pour confirmation : aucune parcelle n’est choisie automatiquement.

La recherche utilise directement l’API Cadastre IGN, sans appeler le géocodage.
La référence confirmée est conservée dans le dossier et le PDF habitation ;
le parcours professionnel utilise cette parcelle pour identifier les paramètres
cadastraux. Une parcelle peut contenir plusieurs locaux : le type, la catégorie
et les surfaces du local doivent toujours être renseignés par l’utilisateur.

Validation : tests des identifiants, préfixes ambigus, codes Corse/DOM, réponses
incohérentes, absence de résultat, navigation et confirmation dans les deux
parcours. Un appel réel IGN a retrouvé 42005 / 000 / BI / 0242 pendant le développement.

### Retrouver le code INSEE par le nom de commune

En mode parcelle, « Rechercher par nom » interroge l’API officielle
geo.api.gouv.fr. La sélection indique le nom, le département et le code INSEE ;
un filtre facultatif par département permet de réduire les homonymes. Aucun
résultat n’est choisi automatiquement. Les 30 premiers résultats sont affichés ;
préciser le nom ou le département si nécessaire. Pour Paris, Lyon et Marseille,
l’arrondissement est obligatoire et fournit le code cadastral correspondant.
Le code INSEE n’est plus à saisir dans ce mode.

« Saisir le code INSEE » reste disponible en solution de repli. Changer le
nom ou le département invalide les anciens résultats. La recherche est exécutée
uniquement sur clic, avant la saisie de la section et du numéro de parcelle.
La résolution réelle a été vérifiée pour Andrézieux-Bouthéon, Lyon et des
communes portant le nom Saint-Sauveur pendant le développement.

### Accueil et nouveau calcul

L’entrée app.py affiche deux boutons : « Local professionnel » et « Local
d’habitation ». Le bouton « Retour à l’accueil » reste visible en haut de chaque parcours.
Chaque parcours possède un bouton « Nouveau calcul » qui efface les recherches,
saisies, résultats et choix de cette session tout en conservant l’authentification.
L’identité des widgets est renouvelée pour éviter le retour d’anciennes valeurs.
Les adresses démarrent vides, sans l’exemple Gambetta ; les cases de confort
sont décochées et les quantités d’équipements à zéro.

### Millésime habitation sans plafond de saisie

L’année d’imposition est saisie numériquement, sans liste limitée à 2024–2026.
La collecte tente les fichiers DGCL du millésime demandé et du précédent selon
le modèle d’URL existant, sous réserve de publication et de format compatible.
Un taux antérieur conserve son année source. Les coefficients habitation
restent documentés dans data/habitation_facteurs.json : aucune revalorisation
future n’est extrapolée si elle manque. Le schéma extensible
« coefficients_amalgames » et « sources_revalorisation », indexés par année,
permet d’ajouter des millésimes après 2026 sans changer les fonctions de calcul.
La récupération automatique d’un nouveau coefficient de revalorisation n’est
pas implémentée : son intégration documentée au référentiel reste nécessaire.

### Suggestions d’adresses pendant la frappe

Les deux parcours utilisent streamlit-searchbox : à partir de cinq caractères,
une pause de 450 ms déclenche la recherche IGN existante. L’utilisateur choisit
une proposition ; son libellé, son code INSEE et ses coordonnées sont conservés
pour la recherche de parcelle, sans géocodage supplémentaire. Une nouvelle
frappe invalide le choix précédent. La saisie manuelle reste accessible, avec
le bouton de recherche existant, notamment en cas d’indisponibilité des suggestions.
Le premier écran habitation utilise des champs réactifs hors formulaire pour
permettre les suggestions. « Nouveau calcul » réinitialise aussi le composant.

Validation : tests des seuils, de la sélection, du repli manuel et de
l’invalidation des coordonnées ; vérification réelle sous Chromium de la frappe,
des propositions IGN, de la sélection et de la remise à zéro dans les deux parcours.

### Dépendances H2 : saisie ligne par ligne

Le bouton « ＋ Ajouter une dépendance » crée une ligne du cadre 5 : type,
désignation, lot, situation dans la propriété, surface et confort propre. Chaque
ligne possède un choix obligatoire : rattachée au logement (même tarif) ou
évaluation distincte. Des lignes peuvent être ajoutées/supprimées sans perdre
les autres saisies ; « Nouveau calcul » efface aussi ces lignes.

Pour une dépendance rattachée, sa surface est pondérée par le coefficient
renseigné (0,4 proposé comme hypothèse à confirmer), ajoutée avant le correctif
d’ensemble du logement et chiffrée au tarif sélectionné. Seuls les équipements
propres non déjà comptés doivent être déclarés. Ne pas reporter sa surface dans
la surface principale.

Une évaluation distincte ne reçoit pas le tarif du logement. Elle reste hors
du chiffrage tant que sa base imposable annuelle n’est pas documentée et que
l’applicabilité des mêmes taux et du même zonage TEOM n’est pas confirmée.
Le cas échéant, ses cotisations sont calculées séparément puis ajoutées à un
total du bien explicitement identifié. Changer d’année efface la base annuelle
et la confirmation des taux. Le détail et les réserves figurent dans le PDF.
Une dépendance sans base/taux connus reste signalée comme non chiffrée : le
sous-total du logement ne vaut pas total du bien.

### Terrasse du cadre 4 B H2

La terrasse accessible est incorporée au calcul du logement, y compris pour
un appartement. La pondération est visible et modifiable de 0,2 à 0,6 ; 0,4
est proposé comme hypothèse à confirmer sur la fiche cadastrale, et non comme
une valeur universelle. La surface réelle est arrondie au m² inférieur, puis
la surface pondérée est arrondie au m² inférieur avant le correctif d’ensemble.
Exemple : 12 m² × 0,4 → 4 m² pondérés retenus. Le calcul utilise Decimal pour
éviter qu’un produit exact comme 50 × 0,58 = 29 soit arrondi à 28 à cause
de la représentation binaire des nombres. Le détail apparaît à l’écran et au PDF.
Référence vérifiée : brochure DGFiP IDL 2025, page 23, articles 324 M et 324 N.
Les dépendances du cadre 5 conservent leur propre choix rattaché/distinct.

### Arrondis H2 des parties principale et secondaire

La partie principale reçoit les correctifs d’entretien/situation et d’ascenseur.
Les éléments secondaires rattachés reçoivent les correctifs d’entretien/situation
sans ascenseur. Chaque groupe est arrondi au m² inférieur séparément avant
addition ; les équivalences de confort sont ajoutées ensuite. Le calcul des
correctifs utilise Decimal. Régression : 49 × 1,35 → 66 ; (3 + 4) × 1,30 → 9 ;
66 + 9 + 25 = 100 m². Les mêmes étapes figurent à l’écran et au PDF.

### Présentation H1/H2 alignée sur les formulaires fournis (page 2)

Le H1 suit désormais les rubriques de H1.pdf : 41 A (nombre de pièces et surface
habitation), 41 B (garages, caves/celliers/bûchers/buanderies, greniers, terrasses
incorporés avec leur pondération propre), 41 C (partie professionnelle), 42
(confort), 43 (murs, toitures, entretien, construction, niveaux), puis classement
et correctifs toujours visibles. Les niveaux comprennent le RDC et excluent
les greniers ; ils ne créent pas de correctif d’ascenseur pour une maison.
Les éviers restent exclus ; les équipements non présents au H1 (vide-ordures,
ascenseur collectif, escalier de service) ne sont pas demandés dans ce parcours.
Les matériaux des murs et des toitures (43 A et B) sont saisis dans la fenêtre
de préparation du H1. Le calcul du chauffage H1 suit le même décompte que le H2.

Le cadre 5 H1 dispose du même bouton d’ajout que le H2, avec une décomposition
par dépendance des surfaces garages, caves, greniers, terrasses et agrément,
puis équipement (eau/électricité) et caractéristiques (murs, toit, entretien).
Le mode de traitement rattaché/distinct reste un choix explicite. Les éléments
de pur agrément requièrent une évaluation distincte ; aucune piscine n’est
valorisée automatiquement avec le tarif d’habitation. Le cadre 6 recueille les
emprises au sol à titre descriptif, sans les ajouter aux surfaces fiscales.
Les caractéristiques de construction n’attribuent pas automatiquement de
catégorie et n’ajoutent aucun coefficient non documenté.

La page 2 du H2 (6652_4004.pdf) a également été revue : les dépendances conservent
leur lot, leur désignation et leur surface, avec des précisions de bâtiment et
d’étage. Les parcours H1/H2 gardent des listes de dépendances distinctes en
session. Les données de la maison et des dépendances sont reprises dans le
récapitulatif et le PDF. La première page administrative des formulaires n’est
pas reproduite. Aucune identité, signature ou coordonnées de déclarant n’est demandée.
