# Mettre l'application en ligne (Render)

Une fois fait, tu ouvres une adresse web et tu rafraîchis la page pour voir les nouveautés.
Le coût attendu est d'environ 7 $/mois pour l'offre « Starter », plus quelques centimes pour le disque (à vérifier sur https://render.com/pricing).

1. Crée un compte sur https://render.com avec « Sign in with GitHub » et autorise l'accès au dépôt `JPWZ/JPWZ`.
2. Dans Render : **New + → Blueprint**, choisis le dépôt `JPWZ/JPWZ` et la branche `claude/determined-edison-ul7dwq`.
3. Render lit `render.yaml` et te demande **APP_PASSWORD** : choisis un mot de passe long et unique (au moins 16 caractères, gestionnaire de mots de passe conseillé).
4. Clique sur **Apply**. Le premier déploiement prend 5 à 10 minutes.
5. Ouvre l'adresse `https://budget-xxxx.onrender.com` affichée dans Render. Le navigateur demande un identifiant et un mot de passe : mets ce que tu veux comme identifiant, et ton `APP_PASSWORD` comme mot de passe.
6. Va dans **Réglages & import** et envoie ton CSV.

## Ensuite
- Chaque modification poussée sur la branche est déployée automatiquement (2 à 3 minutes). Tu rafraîchis la page.
- **Sauvegarde** : Réglages & import → « Télécharger une sauvegarde ». Fais-le de temps en temps.
- Pour arrêter et tout supprimer : supprime le service dans Render (le disque et les données partent avec).

## Sécurité
- L'application refuse de démarrer en ligne si `APP_PASSWORD` est absent (`APP_PUBLIC=1`).
- Ne partage jamais l'adresse avec le mot de passe, et ne mets jamais le mot de passe dans GitHub.
