[English](README.md) · **Français**

# opportunity-scout

**Chaque matin, un agent Claude Code cherche du travail payé sur le web ; un simple script recontrôle chaque piste avant qu'elle n'arrive dans votre liste.**

[![Le juge garde 4 pistes sur 8, les pistes sont triées dans l'app, puis le récapitulatif du lundi (données de démonstration, cliquer pour la vidéo complète)](docs/demo.gif)](https://drive.google.com/file/d/1JvPLCW5v554LGiX6XDvAgMzJfXQjS-YM/view)

*L'app de ce dépôt sur des données de démonstration : le juge garde 4 pistes sur 8, deux sont triées, puis le récapitulatif du lundi. [Vidéo complète (1:18)](https://drive.google.com/file/d/1JvPLCW5v554LGiX6XDvAgMzJfXQjS-YM/view)*

## Ce qu'on fait avec

- **Passage quotidien.** À 7 h, `lancer.sh` (cron) lance `claude -p`. Il cherche des contrats (missions freelance, marchés publics), des concours et du red-teaming, et des emplois, selon la répartition de l'effort que vous fixez (60 / 20 / 20 par défaut).
- **Chaque piste recontrôlée.** `verifier-pistes.py` écarte une piste à laquelle il manque un champ, dont la date limite est passée, dont le montant est sous votre seuil, un emploi ni dans vos villes ni en télétravail complet, ou un lien en erreur ou qui dit l'offre close.
- **Trier dans l'app.** Les pistes par catégorie, chacune marquée *à voir*, *intéressé* ou *écarté* d'un clic. L'agent lit ce tri le lendemain matin et ne repropose plus ce que vous avez écarté.
- **Vos réglages.** Onglet Sources pour ajouter des sites ; onglet Profil pour les seuils, les villes, la répartition et le texte qui vous décrit. Ce texte n'entre jamais dans une recherche web ; l'agent ne crée aucun compte et ne candidate à rien.
- **Récapitulatif du lundi.** Les pistes de la semaine, recontrôlées le matin même, en newsletter HTML lisible dans les messageries. Rien ne part tant que le fichier `.envoi-actif` n'existe pas.

## Architecture

![Architecture d'opportunity-scout : le cron lance l'agent, qui cherche sur les sites publics et écrit les pistes du jour ; un script juge les contrôle ; l'app web les importe ; vous les triez et l'app écrit votre profil et votre tri, lus au passage suivant ; le lundi, le lanceur envoie le récapitulatif](docs/architecture.svg)

## Démarrage

```bash
git clone https://github.com/anthohunt/opportunity-scout && cd opportunity-scout
cp docker-compose.example.yml docker-compose.yml
mkdir data && sudo chown 1000:1000 data            # le conteneur tourne en uid 1000
cp agent/contexte.exemple.md data/contexte.md      # puis décrivez-vous, ou passez par l'onglet Profil
docker compose up -d --build
docker compose exec scout python manage.py masterpw   # affiche le mot de passe maître une seule fois
```

Ouvrez http://localhost:8000. Pour l'agent : `cp .env.example .env`, réglez-le, chargez-le (`set -a; . ./.env; set +a`), puis `FORCE=1 agent/lancer.sh` fait un passage tout de suite et `FORCE=1 HEBDO=1 agent/lancer.sh` rend le récapitulatif du lundi sans l'envoyer.

<details><summary>Prérequis, tests, sources</summary>

- **Prérequis.** Docker avec l'extension compose, ou Python 3.10 ou plus (`pip install -r requirements.txt`). Pour la recherche quotidienne, [Claude Code](https://code.claude.com/docs/fr/overview) connecté sur la machine qui lance `lancer.sh` ; sans lui, l'app, le juge et le récapitulatif fonctionnent quand même.
- **Tests.** `docker compose run --rm scout python -m pytest -q tests` : 13 tests sur une vraie base SQLite et un vrai serveur HTTP local.
- **Sources.** Pages et API publiques (BOAMP, TED, Devpost…). Respectez les conditions de chaque site et gardez un faible volume ; les sites qui bloquent les robots (Malt, Upwork, Indeed) passent par la recherche web.

</details>

## État

- **En usage depuis octobre 2026.** La copie de l'auteur tourne chaque matin. Elle a dépassé ce dépôt (subventions, mail quotidien, compteur d'effort, règle de distance) et n'est pas publiée.
- **Ce dépôt** est la première version publique (26 octobre 2026), dépendances mises à jour le 10 novembre.
- **Licences.** Code sous Apache 2.0 (`LICENSE`, `NOTICE`) ; documentation et consignes de l'agent sous CC BY 4.0 (`LICENSE-docs`). Le profil d'exemple est inventé.

---

**Anthony Hunt** · [ingevision.cloud](https://ingevision.cloud/?p=opportunity-scout) · [LinkedIn](https://www.linkedin.com/in/anthony-hunt-3948a9196) · [GitHub](https://github.com/anthohunt)
