# Sources de base (à re-tester depuis votre serveur : certaines répondent 403 aux robots selon l'hébergeur)

User-Agent de navigateur pour les sources qui répondent 403 :
`Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36`, avec `Accept-Language: fr-FR,fr;q=0.9,en;q=0.8`.

## Contrats (60 %)
### Missions signées par la micro-entreprise
- **Free-Work, missions freelance (API JSON)** : `https://www.free-work.com/api/job_postings?searchKeywords=<mots>&contracts=contractor&page=1&itemsPerPage=50` (en-tête `Accept: application/json`) ; mots : `llm`, `agents ia`, `ia generative`, `unity`, `realite virtuelle`, `chatbot`. TJM dans `minDailySalary`/`maxDailySalary` (souvent vide : lire la description), télétravail dans `remoteMode` (garder `full`), date limite = `expiredAt`, publication = `publishedAt`. Lien d'une offre (vérifié) : `https://www.free-work.com/fr/tech-it/job-mission/<job.slug>/<slug>`.
- **Freelance-info** `https://www.freelance-info.fr/missions?keywords=<mots>`.
- **Comet** `https://www.comet.co/` et **Crème de la Crème** `https://www.cremedelacreme.io/` (200 ; missions souvent visibles par la recherche web « site:comet.co mission IA »).
- **Malt** (403), **Upwork** (403), **Toptal** (403) : par la recherche web, puis ouvrir l'annonce trouvée.
- **Réseaux d'experts et évaluateurs** : appels à experts datés (Commission européenne `https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/work-as-an-expert`, Eurostars, EIC). Les plateformes où l'opérateur est déjà inscrit sont listées dans `contexte.md` : ne pas reproposer l'inscription.
- **Mercor** `https://work.mercor.com/`, **Alignerr**, **micro1** : missions d'experts à l'heure ; les tâches à l'unité y sont `tache`, hors quota.
- **Entreprises qui cherchent un prestataire** : recherche web (« recherche prestataire freelance agents IA », « freelance Unity Meta Quest mission », « consultant IA générative mission télétravail »).
### Marchés publics et appels d'offres
- **BOAMP (API Opendatasoft)** : `https://boamp-datadila.opendatasoft.com/api/explore/v2.1/catalog/datasets/boamp/records?where=search(%22intelligence%20artificielle%22)&order_by=dateparution%20desc&limit=100` ; autres mots : `agent conversationnel`, `chatbot`, `IA generative`, `realite virtuelle`, `realite augmentee`, `jumeau numerique`. Champs : `objet`, `nomacheteur`, `dateparution`, `datelimitereponse`, `url_avis` (lien direct de l'avis, `https://www.boamp.fr/pages/avis/?q=idweb:<idweb>`), `type_marche` (garder `SERVICES`). Ouvrir l'avis pour le budget, les lots et les exigences de capacité.
- **TED (API, POST)** : `curl -s -X POST https://api.ted.europa.eu/v3/notices/search -H 'Content-Type: application/json' -d '{"query":"FT=\"artificial intelligence\" AND PD>=<AAAAMMJJ>","fields":["publication-number","notice-title","deadline-receipt-tender-date-lot","buyer-country"],"limit":50}'` ; lien : `https://ted.europa.eu/fr/notice/-/detail/<publication-number>`. Garder les lots accessibles à un prestataire seul, à distance.
- **PLACE** `https://www.marches-publics.gouv.fr/` · **Marchés sécurisés** `https://www.marches-securises.fr/` (200) · Bpifrance (achats) et collectivités de votre région : par la recherche web (« marché public intelligence artificielle prestation <région> »).
- francemarches.com (403), achatpublic.com (503) : inaccessibles depuis certains serveurs.

## Concours et red-teaming
- **Devpost (API JSON)** : `https://devpost.com/api/hackathons?status[]=open&search=<mots>` (`prize_amount`, `submission_period_dates`, `url`, `open_state`) ; mots : `ai`, `agents`, `llm`, `xr`, `vr`, `unity`. Ouvrir la page du hackathon pour l'éligibilité (résidents français acceptés ?) et la date limite exacte.
- **Kaggle** `https://www.kaggle.com/competitions` (page en JavaScript : passer par la recherche web ou WebFetch) · **AIcrowd** `https://www.aicrowd.com/challenges` · **lablab.ai** `https://lablab.ai/event` · **ML Contests** `https://mlcontests.com/` · **DrivenData** `https://www.drivendata.org/competitions/` · **Zindi** `https://zindi.africa/competitions`.
- **Red-teaming** : Gray Swan Arena `https://app.grayswan.ai/arena` (429 si trop de requêtes : une seule visite), 0Din `https://0din.ai/`, huntr `https://huntr.com/`, HackerOne IA `https://www.hackerone.com/ai`.
- Devpost refuse un faux User-Agent de navigateur mais accepte un client simple (curl sans -A) : le vérificateur essaie les deux.
- Gleam répond 403 depuis certains serveurs : chercher les concours Gleam par la recherche web.

## Emplois
- **LinkedIn, API publique des offres** (sans compte) : `https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search?keywords=<mots>&location=<lieu>&start=0` ; `location=<ville>` (une par ville de `lieux_emploi`), et `location=Worldwide&f_WT=2` ou `location=European%20Union&f_WT=2` pour le télétravail ; `f_TPR=r604800` = 7 derniers jours. Liens d'offres `https://fr.linkedin.com/jobs/view/<...>` : la page de l'offre donne la date de publication et dit « No longer accepting applications » si elle est close.
- **Welcome to the Jungle** `https://www.welcometothejungle.com/fr/jobs?query=<mots>&refinementList[offices.city][]=<ville>` (WebFetch) · **Remotive (API)** `https://remotive.com/api/remote-jobs?search=<mots>` (`salary`, `publication_date`, `candidate_required_location`) · **Himalayas (API)** `https://himalayas.app/jobs/api?limit=100` (`minSalary`, `expiryDate`, `locationRestrictions`, `applicationLink`) · **RemoteOK (API)** `https://remoteok.com/api` · **We Work Remotely (RSS)** `https://weworkremotely.com/categories/remote-programming-jobs.rss`.
- Indeed (403) et APEC (403) : passer par la recherche web, puis ouvrir l'offre trouvée.
