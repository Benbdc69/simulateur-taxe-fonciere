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
- **Streamlit Community Cloud n'est pas une base de données durable**. Une mise à jour automatique dans le conteneur peut disparaître après redémarrage. Pour offrir des mises à jour réellement persistantes à tous les utilisateurs, il faudra ajouter un stockage persistant (par exemple une base SQL sécurisée) ou un référentiel statique mis à jour par une automatisation externe. Ne pas saisir d'informations confidentielles sur un hébergement non validé.

## Tests

### Saisie guidée professionnel et habitation

Le parcours professionnel explique les rubriques P1/P2/P3/PK1/PK2 et les champs
d’historique. La catégorie fiscale doit être choisie explicitement. Les champs
conditionnels apparaissent dès le changement de choix ; modifier une saisie
invalide le résultat précédent. Le périmètre d’imposition est limité à 2017–2026.

Le parcours habitation comporte trois étapes : recherche et confirmation de
l’adresse, surfaces et équipements, vérification puis estimation. Les saisies
sont conservées lors du retour à une étape précédente. Une catégorie inconnue
ouvre les scénarios publiés disponibles, sans attribuer de classement au bien.
Chaque catégorie conserve sa propre surface pondérée. Le détail du calcul,
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
l’escalier de service. La rubrique sanitaire regroupe les lavabos et les éviers.
Les correctifs et le classement réservés à l’administration sont regroupés
dans un volet facultatif.

Le H2 ne détaille pas la desserte du chauffage : lorsque la case est cochée,
deux hypothèses de sensibilité sont conservées (aucune équivalence chauffage,
ou toutes les pièces et annexes déclarées desservies), selon le moteur existant.
Ces hypothèses sont identifiées à l’écran et dans le PDF ; elles ne constituent
pas une évaluation cadastrale confirmée. L’escalier de service est conservé sans
correctif automatique. La partie professionnelle demeure hors du calcul habitation.

Le résultat habitation reprend les cartes du parcours professionnel : montant
annuel sur le périmètre simulé, trois indicateurs de synthèse et répartition par
taxe avec base, taux et millésime. Le calcul détaillé et les sources restent dans
des volets dépliables. Si des taux manquent, la carte principale affiche la valeur
locative et précise qu’il ne s’agit pas d’une cotisation.
