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

Tests de non-régression V13.1 inclus ; test additionnel du contrat du nouveau parcours. Les appels réels IGN/DGFiP et le rendu Streamlit ne sont pas testés dans cet environnement : valider sur le Mac avant publication générale.
