"""Tests sur l'app réelle : vraie base SQLite, vrais fichiers, vrais scripts de l'agent, vrai serveur HTTP local
pour le test des liens (aucune simulation). DATA_DIR est un dossier jetable créé par chaque test.
Lancer : docker compose run --rm scout python -m pytest -q tests
"""
import datetime as dt
import http.server
import importlib
import importlib.util
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

ROOT = Path(__file__).resolve().parents[1]
TODAY = dt.date.today()


def jour(n):
    return (TODAY + dt.timedelta(days=n)).isoformat()


def piste(**kw):
    p = {"titre": "Mission agents LLM", "type": "mission", "organisme": "Acme", "montant": "600 €/jour",
         "montant_eur": 600, "unite": "jour", "date_limite": jour(10), "lien": "https://example.org/a",
         "pourquoi": "Orchestration multi-agents, ton cœur de métier.", "effort": "3 j par mois", "domaine": "IA"}
    p.update(kw)
    return p


@pytest.fixture()
def env():
    tmp = Path(tempfile.mkdtemp(prefix="scout-test-"))
    os.environ.update(DATA_DIR=str(tmp), SECURE_COOKIE="0", SCOUT_TEST="1")
    for f in (ROOT / "agent").glob("*.py"):
        shutil.copy(f, tmp / f.name)
    shutil.copy(ROOT / "app" / "regles.py", tmp / "regles.py")
    sys.path.insert(0, str(ROOT))
    for m in [m for m in sys.modules if m == "manage" or m.startswith("app")]:
        del sys.modules[m]
    main = importlib.import_module("app.main")
    manage = importlib.import_module("manage")
    pw = manage.new_password()
    with main.db() as con:
        main.set_master_password(con, pw)
    yield main, pw, tmp
    shutil.rmtree(tmp, ignore_errors=True)


@pytest.fixture()
def site():
    """Vrai serveur HTTP local : /ok (200), /close (offre close), /absent (404)."""
    class H(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            if self.path.startswith("/absent"):
                self.send_response(404); self.end_headers(); return
            body = b"<h1>Offre</h1>" + (b"No longer accepting applications" if self.path.startswith("/close") else b"Postuler")
            self.send_response(200); self.send_header("Content-Type", "text/html"); self.end_headers(); self.wfile.write(body)

        def log_message(self, *a):
            pass
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_port}"
    srv.shutdown()


def login(main, password):
    c = TestClient(main.app)
    r = c.post("/login", data={"password": password}, follow_redirects=False)
    return c, r


def ecrire_rapport(tmp, date, pistes, verifie=True):
    d = {"date": date, "pistes": pistes}
    if verifie:
        d["verifie_le"] = "2026-10-25T06:30Z"
    (tmp / "rapports").mkdir(exist_ok=True)
    (tmp / "rapports" / f"{date}.json").write_text(json.dumps(d, ensure_ascii=False), encoding="utf-8")


def module(tmp, name):
    spec = importlib.util.spec_from_file_location(name.replace("-", "_"), tmp / f"{name}.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


# ---------- accès ----------

def test_pages_need_login(env):
    main, _, _ = env
    c = TestClient(main.app)
    for path in ["/", "/pistes", "/sources", "/profil"]:
        r = c.get(path, follow_redirects=False)
        assert r.status_code == 303 and r.headers["location"] == "/login", path
    r = c.post("/pistes/abc/etat", data={"etat": "ecarte"}, headers={"Accept": "application/json"})
    assert r.status_code == 401
    assert "noindex" in c.get("/login").headers["x-robots-tag"]
    assert "Disallow: /" in c.get("/robots.txt").text


def test_login_ok_wrong_and_lockout(env):
    main, pw, _ = env
    c, r = login(main, pw)
    assert r.status_code == 303 and "sid" in r.cookies
    assert c.get("/pistes").status_code == 200
    for _ in range(5):
        _, r = login(main, "faux")
    assert "Mot de passe incorrect" in r.text
    _, r = login(main, pw)
    assert "Réessaie dans 15 minutes" in r.text and "sid" not in r.cookies


def test_new_master_password_closes_sessions(env):
    main, pw, _ = env
    c, _ = login(main, pw)
    with main.db() as con:
        main.set_master_password(con, "Autre-Mot-2026!")
    assert c.get("/pistes", follow_redirects=False).status_code == 303


# ---------- règles d'entrée ----------

def test_seuils(env):
    from app import regles as R
    ok = lambda **kw: R.controle(piste(**kw), today=TODAY) == []
    assert ok(montant_eur=50, unite="heure") and not ok(montant_eur=49, unite="heure")
    assert ok(montant_eur=400, unite="jour") and not ok(montant_eur=390, unite="jour")
    assert not ok(montant_eur=3000, unite="total")  # forfait sans heures : refusé
    assert ok(montant_eur=3000, unite="total", effort_heures=40) and not ok(montant_eur=1000, unite="total", effort_heures=40)
    assert ok(type="concours", montant_eur=1000, unite="total") and not ok(type="concours", montant_eur=999, unite="total")
    assert ok(type="appel_offres", montant_eur=5000, unite="total") and not ok(type="appel_offres", montant_eur=500, unite="total")
    assert ok(type="tache", montant_eur=1000, unite="total", effort_heures=10)
    assert R.controle(piste(type="financement"), today=TODAY) != []          # catégorie non gérée
    emploi = dict(type="emploi", montant_eur=3000, unite="mois_net", lieu="Lyon")
    assert ok(**emploi) and not ok(**{**emploi, "montant_eur": 2999})
    assert ok(**{**emploi, "unite": "an_brut", "montant_eur": 48000}) and not ok(**{**emploi, "unite": "an_brut", "montant_eur": 45000})
    assert not ok(**{**emploi, "lieu": "Paris"}) and ok(**{**emploi, "lieu": "Paris", "teletravail_complet": True})
    assert ok(**{**emploi, "lieu": "Lyon (Rhône)"})
    assert ok(montant_eur=None, montant_publie=False, montant_probable="Grille publique des évaluateurs : 450 €/jour")
    assert not ok(montant_eur=None)


def test_dates(env):
    from app import regles as R
    ok = lambda **kw: R.controle(piste(**kw), today=TODAY) == []
    assert ok(date_limite=jour(0)) and not ok(date_limite=jour(-1))
    assert not ok(date_limite="31/12/2026")
    emploi = dict(type="emploi", montant_eur=3500, unite="mois_net", lieu="Lyon", date_limite=None)
    assert ok(**emploi, publiee_le=jour(-29)) and not ok(**emploi, publiee_le=jour(-30))   # moins de 30 jours
    assert not ok(type="concours", montant_eur=5000, unite="total", date_limite=None, publiee_le=jour(-1))
    strict = lambda **kw: R.controle(piste(**kw), seuils={"sans_date_jours": 0}, today=TODAY) == []
    assert not strict(**emploi, publiee_le=jour(-5))


def test_lien_canonique_dedoublonne(env):
    from app import regles as R
    a = R.piste_id({"lien": "https://www.Example.org/job/12/?utm_source=x&trk=y#top"})
    b = R.piste_id({"lien": "https://example.org/job/12"})
    assert a == b and R.piste_id({"lien": "https://example.org/job/13"}) != a


# ---------- vérificateur et liens (vrai serveur HTTP) ----------

def test_verifier_teste_les_liens(env, site):
    main, _, tmp = env
    v = module(tmp, "verifier-pistes")
    assert v.tester_lien(site + "/ok", "emploi") == (200, None)
    assert v.tester_lien(site + "/close", "emploi")[1] == "la page dit que l'offre est close"
    assert v.tester_lien(site + "/absent", "concours")[0] == 404
    ecrire_rapport(tmp, TODAY.isoformat(), [
        piste(titre="Bonne", lien=site + "/ok"),
        piste(titre="Lien mort", lien=site + "/absent"),
        piste(titre="Close", lien=site + "/close"),
        piste(titre="Trop basse", lien=site + "/ok?b", montant_eur=200),
        piste(titre="Doublon", lien=site + "/ok"),
    ], verifie=False)
    f = tmp / "rapports" / f"{TODAY.isoformat()}.json"
    out = subprocess.run([sys.executable, str(tmp / "verifier-pistes.py"), str(f)], capture_output=True, text=True,
                         env={**os.environ})
    assert out.returncode == 0, out.stderr
    d = json.loads(f.read_text(encoding="utf-8"))
    assert [p["titre"] for p in d["pistes"]] == ["Bonne"] and d["pistes"][0]["verif"]["http"] == 200
    assert {p["titre"] for p in d["rejetees"]} == {"Lien mort", "Close", "Trop basse", "Doublon"}
    assert (tmp / "rapports" / f"{TODAY.isoformat()}.brut.json").exists() and "verifie_le" in d


# ---------- onglet Pistes ----------

def test_import_tri_filtres_et_etats(env):
    main, pw, tmp = env
    ecrire_rapport(tmp, jour(-1), [
        piste(titre="Concours tardif", type="concours", montant="5 000 $", montant_eur=4600, unite="total",
              date_limite=jour(30), lien="https://example.org/c"),
        piste(titre="Mission urgente", date_limite=jour(3), lien="https://example.org/m"),
    ])
    ecrire_rapport(tmp, TODAY.isoformat(), [
        piste(titre="Mission urgente (mise à jour)", date_limite=jour(3), lien="https://example.org/m?utm_source=x"),
        piste(titre="Emploi Lyon", type="emploi", montant_eur=3500, unite="mois_net", lieu="Lyon",
              date_limite=None, publiee_le=jour(-2), lien="https://example.org/e"),
    ])
    ecrire_rapport(tmp, jour(-2), [piste(titre="Non vérifiée", lien="https://example.org/x")], verifie=False)
    c, _ = login(main, pw)
    html = c.get("/pistes").text
    assert "Non vérifiée" not in html                       # pas passée par verifier-pistes.py
    assert html.count('class="card ') == 3                   # dédoublonnée par lien
    assert "Mission urgente (mise à jour)" in html           # la version la plus récente
    assert html.index("Mission urgente") < html.index("Concours tardif") < html.index("Emploi Lyon")  # contrats en tête
    assert "dans 3 j" in html and "pas de date limite" in html and f"Publiée le {(TODAY - dt.timedelta(days=2)).strftime('%d/%m')}" in html
    html = c.get("/pistes?cat=concours").text
    assert "Concours tardif" in html and "Mission urgente" not in html

    with main.db() as con:
        pid = con.execute("SELECT id FROM pistes WHERE categorie='concours'").fetchone()[0]
    r = c.post(f"/pistes/{pid}/etat", data={"etat": "ecarte"}, headers={"Accept": "application/json"})
    assert r.json() == {"ok": True, "etat": "ecarte"}
    assert "Concours tardif" not in c.get("/pistes").text
    assert "Concours tardif" in c.get("/pistes?etat=ecarte").text
    assert "ecarte |" in (tmp / "etats.md").read_text(encoding="utf-8")
    assert c.post(f"/pistes/{pid}/etat", data={"etat": "n_importe"}, headers={"Accept": "application/json"}).status_code == 400
    # un nouveau passage qui revoit la piste ne remet pas son état à zéro
    ecrire_rapport(tmp, jour(-1), [piste(titre="Concours tardif", type="concours", montant_eur=4600, unite="total",
                                         date_limite=jour(30), lien="https://example.org/c")])
    os.utime(tmp / "rapports" / f"{jour(-1)}.json", (1, 1))
    assert "Concours tardif" not in c.get("/pistes").text


def test_piste_retiree_au_nouveau_controle(env):
    main, pw, tmp = env
    ecrire_rapport(tmp, TODAY.isoformat(), [piste(titre="Gardée", lien="https://example.org/g"),
                                            piste(titre="Retirée", lien="https://example.org/r")])
    c, _ = login(main, pw)
    assert "Retirée" in c.get("/pistes").text
    ecrire_rapport(tmp, TODAY.isoformat(), [piste(titre="Gardée", lien="https://example.org/g")])
    os.utime(tmp / "rapports" / f"{TODAY.isoformat()}.json", (2, 2))
    html = c.get("/pistes").text
    assert "Gardée" in html and "Retirée" not in html


def test_date_limite_passee_masquee(env):
    main, pw, tmp = env
    ecrire_rapport(tmp, jour(-20), [piste(titre="Ancienne", date_limite=jour(-5), lien="https://example.org/old")])
    c, _ = login(main, pw)
    assert "Ancienne" not in c.get("/pistes").text
    assert "Ancienne" in c.get("/pistes?passees=1").text


# ---------- Sources et Profil ----------

def test_sources(env):
    main, pw, tmp = env
    c, _ = login(main, pw)
    assert "Devpost" in c.get("/sources").text
    r = c.post("/sources", data={"url": "pas-un-lien"}, follow_redirects=True)
    assert "Le lien doit commencer" in r.text
    c.post("/sources", data={"url": "https://www.xrmust.eu/open-calls", "note": "open calls XR"})
    md = (tmp / "sources.md").read_text(encoding="utf-8")
    assert "xrmust.eu" in md and "open calls XR" in md


def test_profil(env):
    main, pw, tmp = env
    c, _ = login(main, pw)
    assert 'value="50"' in c.get("/profil").text
    form = {"mission_eur_h": "60", "concours_eur": "1 500", "marche_eur": "1000", "emploi_net_mois": "3200",
            "emploi_brut_an": "50000", "sans_date_jours": "21", "lieux_emploi": "Lyon, Nantes, Brest",
            "rep_contrats": "60", "rep_concours": "20", "rep_emplois": "20",
            "contexte": "# Profil\nIA agentique et XR."}
    r = c.post("/profil", data=form, follow_redirects=True)
    assert "Profil enregistré" in r.text
    s = json.loads((tmp / "seuils.json").read_text(encoding="utf-8"))
    assert s["mission_eur_h"] == 60 and s["concours_eur"] == 1500 and s["lieux_emploi"][-1] == "Brest"
    assert "IA agentique et XR" in (tmp / "contexte.md").read_text(encoding="utf-8")
    r = c.post("/profil", data={**form, "rep_emplois": "40"}, follow_redirects=True)
    assert "doit faire 100" in r.text
    # le vérificateur applique les seuils du profil
    v = module(tmp, "verifier-pistes")
    assert v.seuils()["mission_eur_h"] == 60


# ---------- mail du lundi ----------

def test_semaine_et_mail(env, site):
    main, pw, tmp = env
    lundi = TODAY
    ecrire_rapport(tmp, jour(-3), [
        piste(titre="Mission A", lien=site + "/ok?a"),
        piste(titre="Concours B", type="concours", montant="2 000 €", montant_eur=2000, unite="total", lien=site + "/ok?b"),
        piste(titre="Emploi fermé", type="emploi", montant_eur=3500, unite="mois_net", teletravail_complet=True,
              lieu="Monde", date_limite=jour(20), lien=site + "/close"),
    ])
    ecrire_rapport(tmp, jour(-10), [piste(titre="Hors semaine", lien=site + "/ok?old")])
    c, _ = login(main, pw)
    c.get("/pistes")
    with main.db() as con:
        pid = [r[0] for r in con.execute("SELECT id, data FROM pistes") if "Concours B" in r[1]][0]
    c.post(f"/pistes/{pid}/etat", data={"etat": "ecarte"}, headers={"Accept": "application/json"})
    out = subprocess.run([sys.executable, str(tmp / "assembler-semaine.py"), lundi.isoformat()], capture_output=True, text=True)
    assert out.returncode == 0, out.stderr
    cand = json.loads((tmp / "hebdo" / f"{lundi.isoformat()}.candidats.json").read_text(encoding="utf-8"))
    assert [p["titre"] for p in cand["pistes"]] == ["Mission A"]
    assert cand["ecartees_par_operateur"] == 1 and [p["titre"] for p in cand["sorties"]] == ["Emploi fermé"]

    mail = {"date": lundi.isoformat(), "du": cand["du"], "au": cand["au"],
            "lead": "<b>1 piste cette semaine.</b> La principale : Mission A.", "pistes": cand["pistes"],
            "footer": "7 passages quotidiens, 1 piste retenue"}
    f = tmp / "hebdo" / f"{lundi.isoformat()}.json"
    f.write_text(json.dumps(mail, ensure_ascii=False), encoding="utf-8")
    ok = subprocess.run([sys.executable, str(tmp / "verifier-pistes.py"), "--hebdo", str(f)], capture_output=True, text=True)
    assert ok.returncode == 0, ok.stdout
    html = subprocess.run([sys.executable, str(tmp / "rendre-mail.py"), str(f)], capture_output=True, text=True).stdout
    assert "Mission A" in html and site + "/ok?a" in html and "Récapitulatif de la semaine" in html
    assert "None" not in html and "Contrats &middot; 1" in html
    # une piste inventée par l'agent du lundi est refusée
    mail["pistes"].append(piste(titre="Inventée", id="zzz"))
    f.write_text(json.dumps(mail, ensure_ascii=False), encoding="utf-8")
    ko = subprocess.run([sys.executable, str(tmp / "verifier-pistes.py"), "--hebdo", str(f)], capture_output=True, text=True)
    assert ko.returncode == 1 and "Inventée" in ko.stdout
