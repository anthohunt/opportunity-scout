"""Opportunités — app web de l'agent de recherche d'opportunités.

Un mot de passe maître unique ouvre l'app. L'agent quotidien écrit rapports/<date>.json (pistes vérifiées
par verifier-pistes.py) ; l'app les importe en base, un état par piste (à voir / intéressé / écarté) donné par
l'opérateur. L'app écrit les fichiers que l'agent lit : sources.md (sources ajoutées), contexte.md et seuils.json
(onglet Profil), etats.md (ce que l'opérateur a trié).
"""
import datetime as dt
import hashlib
import json
import os
import re
import secrets
import sqlite3
from pathlib import Path

from argon2 import PasswordHasher
from argon2.exceptions import VerificationError
from fastapi import FastAPI, Form, Request
from fastapi.responses import HTMLResponse, JSONResponse, PlainTextResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app import regles

DATA = Path(os.environ.get("DATA_DIR", "/data"))
APP_DIR = DATA / "app"
DB_PATH = APP_DIR / "app.db"
REPORTS = DATA / "rapports"
SOURCES_MD = DATA / "sources.md"
CONTEXTE = DATA / "contexte.md"
SEUILS = DATA / "seuils.json"
ETATS_MD = DATA / "etats.md"
SECURE_COOKIE = os.environ.get("SECURE_COOKIE", "1") == "1"

SESSION_DAYS = 30
MAX_FAILS, FAIL_WINDOW = 5, 15 * 60   # par adresse IP
MAX_FAILS_ALL = 30                     # toutes adresses confondues, même fenêtre (mot de passe unique)
ETATS = {"a_voir": "À voir", "interesse": "Intéressé", "ecarte": "Écarté"}

# Sources de base, fouillées à chaque passage par le protocole de l'agent (agent/consigne.md, étape 2).
CORE_SOURCES = [
    ("contrats", "Free-Work et Freelance-info, missions freelance", "https://www.free-work.com/fr/tech-it/jobs?contracts=contractor", "Missions IA et XR avec TJM, télétravail"),
    ("contrats", "Malt", "https://www.malt.fr/", "Missions IA (bloque les robots : par la recherche web)"),
    ("contrats", "Comet", "https://www.comet.co/", "Missions freelance tech haut de gamme"),
    ("contrats", "Crème de la Crème", "https://www.cremedelacreme.io/", "Missions freelance tech haut de gamme"),
    ("contrats", "Upwork, Toptal", "https://www.upwork.com/", "Missions haut de gamme (bloquent les robots : par la recherche web)"),
    ("contrats", "BOAMP (API)", "https://www.boamp.fr/", "Marchés publics français IA, XR, développement"),
    ("contrats", "PLACE, marchés de l'État", "https://www.marches-publics.gouv.fr/", "Consultations de l'État"),
    ("contrats", "Marchés sécurisés", "https://www.marches-securises.fr/", "Marchés des collectivités"),
    ("contrats", "TED (API)", "https://ted.europa.eu/", "Appels d'offres européens"),
    ("contrats", "Réseaux d'experts et évaluateurs", "https://ec.europa.eu/info/funding-tenders/opportunities/portal/screen/work-as-an-expert", "Appels à experts datés ; plateformes de consultation : appels reçus par mail"),
    ("contrats", "Mercor, Alignerr, micro1", "https://work.mercor.com/", "Missions d'experts IA à l'heure ; tâches à l'unité hors quota"),
    ("concours", "Devpost (API)", "https://devpost.com/hackathons", "Hackathons IA ouverts avec dotation"),
    ("concours", "Kaggle", "https://www.kaggle.com/competitions", "Compétitions IA dotées"),
    ("concours", "AIcrowd", "https://www.aicrowd.com/challenges", "Challenges IA dotés"),
    ("concours", "lablab.ai", "https://lablab.ai/event", "Hackathons IA agentique"),
    ("concours", "ML Contests", "https://mlcontests.com/", "Annuaire des compétitions ML"),
    ("concours", "Gray Swan Arena", "https://app.grayswan.ai/arena", "Red-teaming d'agents doté"),
    ("concours", "HackerOne IA, huntr, 0Din", "https://0din.ai/", "Bug bounties sur l'IA générative"),
    ("emplois", "LinkedIn (offres publiques)", "https://www.linkedin.com/jobs/", "villes de votre choix, et télétravail complet"),
    ("emplois", "Welcome to the Jungle", "https://www.welcometothejungle.com/fr/jobs", "Offres IA et XR, villes de votre choix et télétravail"),
    ("emplois", "Remotive, RemoteOK, Himalayas, We Work Remotely", "https://remotive.com/", "Emplois 100 % à distance, salaire souvent affiché"),
    ("emplois", "Indeed, APEC (par la recherche web)", "https://fr.indeed.com/", "Bloquent les robots : passés par la recherche web"),
]

ph = PasswordHasher()
DUMMY_HASH = ph.hash(secrets.token_urlsafe(16))
BASE = Path(__file__).parent
templates = Jinja2Templates(directory=BASE / "templates")
app = FastAPI(docs_url=None, redoc_url=None, openapi_url=None)
app.mount("/static", StaticFiles(directory=BASE / "static"), name="static")

SCHEMA = """
CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS sessions (token_hash TEXT PRIMARY KEY, expires REAL NOT NULL);
CREATE TABLE IF NOT EXISTS login_attempts (key TEXT NOT NULL, ts REAL NOT NULL);
CREATE TABLE IF NOT EXISTS sources (id INTEGER PRIMARY KEY, name TEXT NOT NULL, url TEXT NOT NULL, note TEXT,
  added_at TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS reports (date TEXT PRIMARY KEY, mtime REAL NOT NULL, n INTEGER NOT NULL DEFAULT 0);
CREATE TABLE IF NOT EXISTS pistes (id TEXT PRIMARY KEY, data TEXT NOT NULL, categorie TEXT NOT NULL,
  date_limite TEXT, premiere_vue TEXT NOT NULL, derniere_vue TEXT NOT NULL,
  etat TEXT NOT NULL DEFAULT 'a_voir', etat_le TEXT);
CREATE TABLE IF NOT EXISTS report_pistes (date TEXT NOT NULL, id TEXT NOT NULL, PRIMARY KEY (date, id));
"""


def db() -> sqlite3.Connection:
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    return con


def init():
    for d in (APP_DIR, REPORTS):
        d.mkdir(parents=True, exist_ok=True)
    with db() as con:
        con.executescript(SCHEMA)


def now_iso() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M")


def today() -> dt.date:
    return regles.date_iso(os.environ.get("AUJOURDHUI")) or dt.date.today()


# ---------- fichiers lus par l'agent ----------

def write_sources_md(con):
    rows = con.execute("SELECT * FROM sources ORDER BY id").fetchall()
    lines = ["# Sources ajoutées par l'opérateur dans l'app (nom | lien | quoi chercher | date)", ""]
    lines += [f"- {r['name']} | {r['url']} | {r['note'] or ''} | {r['added_at'][:10]}" for r in rows]
    SOURCES_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def write_etats_md(con):
    rows = con.execute("SELECT data, etat, etat_le FROM pistes WHERE etat!='a_voir' ORDER BY etat_le DESC").fetchall()
    lines = ["# Tri fait par l'opérateur dans l'app (état | date | type | titre | lien)",
             "# « ecarte » = ne plus proposer cette piste ni ses pareilles ; « interesse » = chercher davantage dans cette veine.", ""]
    for r in rows:
        p = json.loads(r["data"])
        lines.append(f"- {r['etat']} | {(r['etat_le'] or '')[:10]} | {p.get('type')} | {p.get('titre')} | {p.get('lien')}")
    ETATS_MD.write_text("\n".join(lines) + "\n", encoding="utf-8")


def read_seuils() -> dict:
    try:
        s = {**regles.SEUILS_DEFAUT, **json.loads(SEUILS.read_text(encoding="utf-8"))}
    except Exception:
        return dict(regles.SEUILS_DEFAUT)
    if set(s.get("repartition", {})) != {k for k, _ in regles.CATEGORIES}:  # ancienne répartition à 4 catégories
        s["repartition"] = dict(regles.SEUILS_DEFAUT["repartition"])
    return s


# ---------- import des passages quotidiens ----------

def import_reports():
    with db() as con:
        known = {r["date"]: r["mtime"] for r in con.execute("SELECT date, mtime FROM reports")}
        for f in sorted(REPORTS.glob("*.json")):
            date = f.stem
            if not re.fullmatch(r"\d{4}-\d{2}-\d{2}(-\d{4})?", date):  # .brut.json, .tmp : ignorés
                continue
            mtime = f.stat().st_mtime
            if known.get(date) == mtime:
                continue
            try:
                data = json.loads(f.read_text(encoding="utf-8"))
            except Exception:
                continue
            if "verifie_le" not in data:  # pas encore passé par verifier-pistes.py
                continue
            n, ids = 0, set()
            for p in data.get("pistes", []):
                if p.get("type") not in regles.TYPES or not p.get("lien"):
                    continue
                pid = p.get("id") or regles.piste_id(p)
                cat = regles.TYPES[p["type"]][0]
                row = con.execute("SELECT premiere_vue FROM pistes WHERE id=?", (pid,)).fetchone()
                first = min(row["premiere_vue"], date[:10]) if row else date[:10]
                con.execute(
                    "INSERT INTO pistes(id, data, categorie, date_limite, premiere_vue, derniere_vue) VALUES (?,?,?,?,?,?) "
                    "ON CONFLICT(id) DO UPDATE SET data=excluded.data, categorie=excluded.categorie, "
                    "date_limite=excluded.date_limite, premiere_vue=?, "
                    "derniere_vue=MAX(derniere_vue, excluded.derniere_vue)",
                    (pid, json.dumps(p, ensure_ascii=False), cat, p.get("date_limite") or None, first, date[:10], first))
                ids.add(pid)
                n += 1
            # Une piste retirée de ce passage (nouveau contrôle) et vue nulle part ailleurs disparaît, sauf si
            # L'opérateur l'a déjà triée.
            avant = {r["id"] for r in con.execute("SELECT id FROM report_pistes WHERE date=?", (date,))}
            con.execute("DELETE FROM report_pistes WHERE date=?", (date,))
            con.executemany("INSERT INTO report_pistes(date, id) VALUES (?,?)", [(date, i) for i in ids])
            for pid in avant - ids:
                if not con.execute("SELECT 1 FROM report_pistes WHERE id=?", (pid,)).fetchone():
                    con.execute("DELETE FROM pistes WHERE id=? AND etat='a_voir'", (pid,))
            con.execute("INSERT OR REPLACE INTO reports(date, mtime, n) VALUES (?,?,?)", (date, mtime, n))


# ---------- sessions ----------

class LoginRequired(Exception):
    pass


@app.exception_handler(LoginRequired)
async def _login_required(request, exc):
    if request.headers.get("accept", "").startswith("application/json"):
        return JSONResponse({"error": "login"}, status_code=401)
    return RedirectResponse("/login", status_code=303)


def client_ip(request: Request) -> str:
    return request.headers.get("x-real-ip") or (request.client.host if request.client else "?")


def logged_in(request: Request) -> bool:
    token = request.cookies.get("sid")
    if not token:
        return False
    th = hashlib.sha256(token.encode()).hexdigest()
    with db() as con:
        return con.execute("SELECT 1 FROM sessions WHERE token_hash=? AND expires>?",
                           (th, dt.datetime.now().timestamp())).fetchone() is not None


def need_login(request: Request):
    if not logged_in(request):
        raise LoginRequired()


def master_hash(con):
    row = con.execute("SELECT value FROM settings WHERE key='master_hash'").fetchone()
    return row["value"] if row else None


def set_master_password(con, pw: str):
    con.execute("INSERT OR REPLACE INTO settings(key, value) VALUES ('master_hash', ?)", (ph.hash(pw),))
    con.execute("DELETE FROM sessions")


def page(request, name, **ctx):
    return templates.TemplateResponse(request, name, {"tab": name.split(".")[0], "logged": name != "login.html", **ctx})


@app.middleware("http")
async def headers(request, call_next):
    resp = await call_next(request)
    resp.headers["X-Robots-Tag"] = "noindex, nofollow"
    resp.headers["X-Frame-Options"] = "DENY"
    resp.headers["X-Content-Type-Options"] = "nosniff"
    resp.headers["Referrer-Policy"] = "no-referrer"
    resp.headers["Content-Security-Policy"] = ("default-src 'self'; style-src 'self' 'unsafe-inline'; "
                                               "img-src 'self' data:; frame-ancestors 'none'")
    return resp


@app.get("/robots.txt", response_class=PlainTextResponse)
def robots():
    return "User-agent: *\nDisallow: /\n"


@app.get("/login", response_class=HTMLResponse)
def login_form(request: Request):
    if logged_in(request):
        return RedirectResponse("/", status_code=303)
    return page(request, "login.html", error=None)


@app.post("/login")
def login(request: Request, password: str = Form(...)):
    ip_key = "ip:" + client_ip(request)
    t = dt.datetime.now().timestamp()
    with db() as con:
        con.execute("DELETE FROM login_attempts WHERE ts<?", (t - FAIL_WINDOW,))
        fails_ip = con.execute("SELECT COUNT(*) FROM login_attempts WHERE key=?", (ip_key,)).fetchone()[0]
        fails_all = con.execute("SELECT COUNT(*) FROM login_attempts").fetchone()[0]
        if fails_ip >= MAX_FAILS or fails_all >= MAX_FAILS_ALL:
            return page(request, "login.html", error="Trop d'essais. Réessaie dans 15 minutes.")
        h = master_hash(con)
        try:
            ph.verify(h or DUMMY_HASH, password)
            ok = h is not None
        except VerificationError:
            ok = False
        if not ok:
            con.execute("INSERT INTO login_attempts(key, ts) VALUES (?,?)", (ip_key, t))
            return page(request, "login.html", error="Mot de passe incorrect.")
        token = secrets.token_urlsafe(32)
        con.execute("INSERT INTO sessions VALUES (?,?)",
                    (hashlib.sha256(token.encode()).hexdigest(), t + SESSION_DAYS * 86400))
    resp = RedirectResponse("/", status_code=303)
    resp.set_cookie("sid", token, max_age=SESSION_DAYS * 86400, httponly=True, secure=SECURE_COOKIE, samesite="lax")
    return resp


@app.post("/logout")
def logout(request: Request):
    token = request.cookies.get("sid")
    if token:
        with db() as con:
            con.execute("DELETE FROM sessions WHERE token_hash=?", (hashlib.sha256(token.encode()).hexdigest(),))
    resp = RedirectResponse("/login", status_code=303)
    resp.delete_cookie("sid")
    return resp


@app.get("/")
def home(request: Request):
    need_login(request)
    return RedirectResponse("/pistes", status_code=303)


# ---------- 1. Pistes ----------

MOIS = ["janv.", "févr.", "mars", "avr.", "mai", "juin", "juil.", "août", "sept.", "oct.", "nov.", "déc."]


def date_courte(d: dt.date) -> str:
    return f"{'1er' if d.day == 1 else d.day} {MOIS[d.month - 1]} {d.year}"


def vue_piste(row, t: dt.date) -> dict:
    p = json.loads(row["data"])
    d = regles.date_iso(row["date_limite"])
    if d:
        n = (d - t).days
        reste = "passée" if n < 0 else ("aujourd'hui" if n == 0 else ("demain" if n == 1 else f"dans {n} j"))
        echeance = {"date": date_courte(d), "reste": reste, "urgent": 0 <= n <= 7, "passee": n < 0}
    else:
        pub = regles.date_iso(p.get("publiee_le"))
        echeance = {"date": f"Publiée le {pub.strftime('%d/%m')}" if pub else "Non publiée", "reste": "pas de date limite",
                    "urgent": False, "passee": False}
    lieu = ""
    if p.get("type") == "emploi":
        lieu = "Télétravail complet" if p.get("teletravail_complet") else (p.get("lieu") or "")
    return {"id": row["id"], "p": p, "cat": regles.TYPES[p["type"]][0], "etat": row["etat"], "echeance": echeance,
            "type_label": regles.TYPES[p["type"]][1], "hors_quota": p["type"] in regles.HORS_QUOTA, "lieu": lieu, "nouveau": row["premiere_vue"] >= (t - dt.timedelta(days=1)).isoformat(),
            "domaine": re.sub(r"^https?://(www\.)?", "", p.get("lien", "")).split("/")[0]}


@app.get("/pistes", response_class=HTMLResponse)
def pistes(request: Request, cat: str = "", etat: str = "actives", passees: int = 0):
    need_login(request)
    import_reports()
    t = today()
    with db() as con:
        rows = con.execute("SELECT * FROM pistes").fetchall()
        n_reports = con.execute("SELECT COUNT(*), MAX(date) FROM reports").fetchone()
    toutes = [vue_piste(r, t) for r in rows if json.loads(r["data"]).get("type") in regles.TYPES]
    visibles = [v for v in toutes if passees or not v["echeance"]["passee"]]

    def garde_etat(v):
        return v["etat"] != "ecarte" if etat == "actives" else (v["etat"] == etat if etat in ETATS else True)

    par_etat = [v for v in visibles if garde_etat(v)]
    counts = {k: sum(1 for v in par_etat if v["cat"] == k) for k, _ in regles.CATEGORIES}
    liste = [v for v in par_etat if not cat or v["cat"] == cat]
    ordre = {k: n for n, (k, _) in enumerate(regles.CATEGORIES)}
    # contrats en tête ; dans une catégorie, la date limite la plus proche ; les tâches à l'unité (hors quota) à la fin
    liste.sort(key=lambda v: (ordre[v["cat"]] if not cat else 0, v["p"]["type"] in regles.HORS_QUOTA,
                              v["p"].get("date_limite") or "9999-12-31", v["p"].get("titre", "")))
    etat_counts = {k: sum(1 for v in visibles if v["etat"] == k) for k in ETATS}
    n_passees = sum(1 for v in toutes if v["echeance"]["passee"])
    return page(request, "pistes.html", liste=liste, counts=counts, cat=cat, etat=etat, passees=passees,
                categories=regles.CATEGORIES, etats=ETATS, etat_counts=etat_counts, n_passees=n_passees,
                total=len(par_etat), n_reports=n_reports[0], dernier=n_reports[1])


@app.post("/pistes/{pid}/etat")
def set_etat(request: Request, pid: str, etat: str = Form(...)):
    need_login(request)
    if etat not in ETATS:
        return JSONResponse({"error": "état inconnu"}, status_code=400)
    with db() as con:
        cur = con.execute("UPDATE pistes SET etat=?, etat_le=? WHERE id=?", (etat, now_iso(), pid))
        if cur.rowcount == 0:
            return JSONResponse({"error": "piste inconnue"}, status_code=404)
        write_etats_md(con)
    if request.headers.get("accept", "").startswith("application/json"):
        return JSONResponse({"ok": True, "etat": etat})
    return RedirectResponse(request.headers.get("referer") or "/pistes", status_code=303)


# ---------- 2. Sources ----------

@app.get("/sources", response_class=HTMLResponse)
def sources(request: Request, msg: str = "", err: str = ""):
    need_login(request)
    with db() as con:
        rows = con.execute("SELECT * FROM sources ORDER BY id DESC").fetchall()
    core = {k: [s for s in CORE_SOURCES if s[0] == k] for k, _ in regles.CATEGORIES}
    return page(request, "sources.html", rows=rows, core=core, categories=regles.CATEGORIES, msg=msg, err=err)


@app.post("/sources")
def add_source(request: Request, name: str = Form(""), url: str = Form(...), note: str = Form("")):
    need_login(request)
    url = url.strip()
    if not re.match(r"^https?://[^\s/$.?#].[^\s]*$", url):
        return RedirectResponse("/sources?err=Le+lien+doit+commencer+par+http%3A%2F%2F+ou+https%3A%2F%2F", status_code=303)
    name = name.strip() or re.sub(r"^https?://(www\.)?", "", url).split("/")[0]
    with db() as con:
        con.execute("INSERT INTO sources(name, url, note, added_at) VALUES (?,?,?,?)",
                    (name[:120], url[:500], note.strip()[:300], now_iso()))
        write_sources_md(con)
    return RedirectResponse("/sources?msg=Source+ajout%C3%A9e.+L%27agent+la+fouille+d%C3%A8s+le+prochain+passage.", status_code=303)


@app.post("/sources/{src_id}/delete")
def source_delete(request: Request, src_id: int):
    need_login(request)
    with db() as con:
        con.execute("DELETE FROM sources WHERE id=?", (src_id,))
        write_sources_md(con)
    return RedirectResponse("/sources?msg=Source+retir%C3%A9e.", status_code=303)


# ---------- 3. Profil ----------

@app.get("/profil", response_class=HTMLResponse)
def profil(request: Request, msg: str = "", err: str = ""):
    need_login(request)
    contexte = CONTEXTE.read_text(encoding="utf-8") if CONTEXTE.exists() else ""
    modifie = dt.datetime.fromtimestamp(CONTEXTE.stat().st_mtime).strftime("%d/%m/%Y") if CONTEXTE.exists() else None
    return page(request, "profil.html", s=read_seuils(), contexte=contexte, modifie=modifie,
                categories=regles.CATEGORIES, msg=msg, err=err)


@app.post("/profil")
async def save_profil(request: Request):
    need_login(request)
    form = await request.form()
    s = read_seuils()
    try:
        for k in ("mission_eur_h", "concours_eur", "marche_eur", "emploi_net_mois", "emploi_brut_an", "sans_date_jours"):
            v = float(str(form.get(k, s[k])).replace(",", ".").replace(" ", "").replace(" ", ""))
            if v < 0 or v > 10_000_000:
                raise ValueError(k)
            s[k] = int(v) if v == int(v) else v
        rep = {k: int(form.get(f"rep_{k}", s["repartition"].get(k, 0))) for k, _ in regles.CATEGORIES}
        if sum(rep.values()) != 100 or min(rep.values()) < 0:
            return RedirectResponse("/profil?err=La+r%C3%A9partition+doit+faire+100+%25", status_code=303)
        s["repartition"] = rep
    except (ValueError, TypeError):
        return RedirectResponse("/profil?err=Un+seuil+n%27est+pas+un+nombre+valable", status_code=303)
    lieux = [l.strip() for l in str(form.get("lieux_emploi", "")).split(",") if l.strip()]
    s["lieux_emploi"] = lieux[:10] or s["lieux_emploi"]
    SEUILS.write_text(json.dumps(s, ensure_ascii=False, indent=1) + "\n", encoding="utf-8")
    texte = str(form.get("contexte", "")).replace("\r\n", "\n").strip()
    if texte:
        CONTEXTE.write_text(texte[:30000] + "\n", encoding="utf-8")
    return RedirectResponse("/profil?msg=Profil+enregistr%C3%A9.+L%27agent+l%27applique+d%C3%A8s+le+prochain+passage.", status_code=303)


init()
