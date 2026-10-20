# Budget perso

Suivi de dépenses personnelles : récurrents détectés, catégorisation corrigeable, et calcul de ce
qu'on peut dépenser en loisirs / épargner / investir. Local, sans cloud : les données restent dans
`data/` (ignoré par Git).

## Lancer (le plus simple)

1. Installer Python 3.11+ (https://www.python.org/downloads/ ; sous Windows, cocher « Add python.exe to PATH »).
2. Double-cliquer sur **`lancer.bat`** (Windows) ou **`lancer.command`** (Mac). La première fois, l'installation prend 1 à 2 minutes ; le navigateur s'ouvre ensuite sur http://localhost:8000.

## Lancer (avancé)

```bash
docker compose up --build        # http://localhost:8000
# ou sans Docker :
pip install -r requirements.txt
BUDGET_DB=data/budget.db uvicorn app.main:app --port 8000
```

Puis **Réglages & import** (ou glisser les fichiers dans la barre latérale) : export CSV Banque Populaire
(compte courant) et export PayPal « Activité / Transactions ». Le type de fichier est détecté tout seul ;
réimporter un fichier qui chevauche le précédent est sans risque (doublons ignorés). Les prélèvements
« PayPal » de la banque sont rattachés à leur commerçant (même montant, 0 à 12 jours plus tôt), et les
paiements en 4 fois apparaissent comme engagements à venir.
En ligne de commande : `python -m app.cli import data/export.csv`.

## Comment c'est calculé

| Notion | Définition |
|---|---|
| Virements Livret A, PEA, crypto | Jamais des dépenses (mouvement ou investissement) |
| Charges fixes | Paiements présents dans ≥ la moitié des mois, montant stable ou prélèvement |
| Exceptionnelles | Dépense isolée ≥ 400 € non récurrente |
| Primes | Part d'un salaire au-delà de 1,25 × le salaire médian |
| Capacité de base | Salaire + remboursements − fixes − variables − compte joint |
| Capacité lissée | Capacité de base + primes + autres rentrées − exceptionnelles (moyenne 12 mois complets) |
| Loisirs possibles | Loisirs actuels + capacité lissée − objectif d'épargne |

Catégories : `app/rules.yaml` (ordre = priorité). Les corrections faites dans l'interface passent
avant les règles.

## Tests

```bash
pip install -r requirements-dev.txt && pytest
```

## Suite prévue

- Connexion Enable Banking (API) pour remplacer l'import CSV — Banque Populaire puis compte joint.
- Import Boursorama (compte joint), PayPal (export CSV pour détailler les prélèvements).
- Hébergement : un petit serveur domestique + accès privé (Tailscale) pour les futurs services.
