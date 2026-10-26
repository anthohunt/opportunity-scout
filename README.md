# opportunity-scout — a daily agent that hunts paid opportunities, and the small web app that holds its leads

Every morning an AI agent (Claude Code, run headless) looks for **contracts** (freelance missions, public
tenders a solo contractor can serve), **competitions** (AI challenges, red-teaming, bug bounties) and **jobs**,
according to a profile and thresholds you set. A deterministic script then **re-checks every lead** (required
fields, deadline still ahead, amount above your threshold, location rule, and a real HTTP test of the link) and
drops what fails. What survives lands in a password-protected web app; on Mondays a short newsletter sums up the week.

> The agent instructions, the app and the code comments are in French (the default sources are French and
> European procurement and job sites). Adapt `agent/sources-base.md` and `agent/contexte.exemple.md` to your market.

## What is in the box

| Part | What it does |
| --- | --- |
| `app/` | FastAPI app: one master password (argon2), tabs **Pistes** (leads, with a state *to see / interested / dismissed*), **Sources** (sources you add), **Profil** (thresholds, effort split, the text describing you). It writes the files the agent reads. |
| `agent/consigne.md` | The daily protocol given to the agent (load context, search with an effort budget per type, filter, write `rapports/<date>.json`, trace). |
| `agent/verifier-pistes.py` | The judge: it never trusts the agent. Required fields, future deadline, thresholds, location, link really opens and is not a closed offer. |
| `agent/consigne-hebdo.md`, `assembler-semaine.py`, `rendre-mail.py`, `envoyer-mail.py` | Monday digest: candidates assembled and re-checked by script, ordered by the agent, rendered as an email-safe HTML table, sent by plain SMTP. |
| `agent/lancer.sh` | The cron entry point, configured only by environment variables. |

The agent never searches the web with your name, employer, city or salary: it searches *topics*. It creates no
account and applies to nothing. The mail is sent only once you create the file `.envoi-actif` (so you can read the
rendered mail first).

## Requirements

- Docker with the compose plugin (for the app), or Python ≥ 3.10 and `pip install -r requirements.txt`.
- For the agent: [Claude Code](https://docs.anthropic.com/en/docs/claude-code) installed and logged in on the
  machine that runs `agent/lancer.sh` (a paid Anthropic account; a separate product under Anthropic's terms).
  Without it, everything but the daily search runs: the app, the judge, the digest rendering.
- Python third-party packages (all installed from PyPI by `requirements.txt`): FastAPI, Uvicorn, Jinja2,
  python-multipart, argon2-cffi, httpx (MIT / BSD / Apache-2.0), pytest (MIT).

## Install and try it

```bash
git clone <this repository> opportunity-scout && cd opportunity-scout
cp docker-compose.example.yml docker-compose.yml
mkdir data && sudo chown 1000:1000 data           # the container runs as uid 1000
cp agent/contexte.exemple.md data/contexte.md     # then edit: describe yourself (or use the Profil tab)
docker compose up -d --build
docker compose exec scout python manage.py masterpw   # prints the master password ONCE
# open http://localhost:8000, log in with that password
docker compose run --rm scout python -m pytest -q tests   # the test suite
```

### Run the agent every day

```bash
cp .env.example .env     # edit SCOUT_DIR (the folder mounted on /data), the schedule, the mail settings
set -a; . ./.env; set +a
FORCE=1 agent/lancer.sh                  # one daily pass now
FORCE=1 HEBDO=1 agent/lancer.sh          # the Monday digest now (rendered to hebdo/<date>.html, not sent)
touch "$SCOUT_DIR/.envoi-actif"          # only when you want the mail to really leave
```

Cron: `5 5,6 * * * /path/agent/lancer.sh` and `0 6,7 * * 1 HEBDO=1 /path/agent/lancer.sh` (the script only works at
the configured local hour, so summer/winter time changes are harmless).

## Respect the sources

The agent reads public pages and APIs (procurement notices, job boards, hackathon listings). Respect each site's
terms of use and robots rules, keep the volume low, and do not redistribute what you collect. Several sites
(Malt, Upwork, Indeed…) block robots on purpose: the protocol goes through web search for them.

## Licenses

- Code: Apache License 2.0 (`LICENSE`, `NOTICE`).
- Documentation and agent instruction files (`README.md`, `agent/*.md`): CC BY 4.0 (`LICENSE-docs`).
- The example profile in `agent/contexte.exemple.md` is fictional.
