#!/usr/bin/env python3
"""Vérificateur déterministe des pistes (agent de recherche d'opportunités).

Chaque piste écrite par l'agent passe les règles de regles.py (champs, date limite à venir, seuils, lieu)
et un test réel de son lien (GET avec un User-Agent de navigateur : code 2xx exigé, page d'offre close refusée).
  verifier-pistes.py rapports/2026-01-12.json            écrit le fichier : pistes gardées + "rejetees" avec raisons
  verifier-pistes.py --essai rapports/2026-01-12.json    affiche seulement le verdict, ne touche à rien
  verifier-pistes.py --hebdo hebdo/2026-01-19.json       contrôle le mail du lundi (pistes issues des candidats)
Sortie : code 0 si au moins le fichier est lisible ; le bilan est imprimé.
"""
import datetime as dt
import json
import os
import sys
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

D = Path(__file__).resolve().parent
sys.path.insert(0, str(D))
import regles  # noqa: E402

UA = ("Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) "
      "Chrome/130.0 Safari/537.36")
HEADERS = {"User-Agent": UA, "Accept": "text/html,application/xhtml+xml,application/json;q=0.9,*/*;q=0.8",
           "Accept-Language": "fr-FR,fr;q=0.9,en;q=0.8"}
SIMPLE = {"User-Agent": "curl/8.5.0", "Accept": "*/*"}


def seuils():
    f = D / "seuils.json"
    try:
        return {**regles.SEUILS_DEFAUT, **json.loads(f.read_text(encoding="utf-8"))}
    except Exception:
        return dict(regles.SEUILS_DEFAUT)


def ouvrir(url, headers):
    req = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(req, timeout=25) as r:
        return r.status, r.read(600_000).decode("utf-8", errors="replace")


def tester_lien(url: str, type_: str):
    """(code HTTP, raison de refus ou None). Deux en-têtes essayés : navigateur, puis client simple (certains sites,
    Devpost par exemple, refusent un faux navigateur mais pas curl). Réessaie une fois en cas d'erreur réseau."""
    dernier = (0, "lien injoignable")
    for headers in (HEADERS, SIMPLE):
        for essai in range(2):
            try:
                code, corps = ouvrir(url, headers)
                if type_ in regles.TYPES_SANS_DATE and regles.EXPIRATION.search(corps):
                    return code, "la page dit que l'offre est close"
                return code, None
            except urllib.error.HTTPError as e:
                dernier = (e.code, f"lien en erreur HTTP {e.code}")
                if e.code not in (429, 500, 502, 503, 504):
                    break
            except Exception as e:  # réseau, TLS, délai
                dernier = (0, f"lien injoignable ({type(e).__name__})")
        if dernier[0] not in (401, 403, 406, 429):
            break
    return dernier


def verifier(pistes, today, s):
    gardees, rejetees = [], []
    vus = set()
    for p in pistes:
        p = dict(p)
        p.setdefault("montant_publie", True)
        p["id"] = regles.piste_id(p) if p.get("lien") else ""
        raisons = regles.controle(p, s, today)
        if p["id"] and p["id"] in vus:
            raisons.append("doublon d'une autre piste du même fichier")
        (rejetees if raisons else gardees).append((p, raisons))
        vus.add(p["id"])
    # liens : en parallèle, seulement pour les pistes qui ont passé les règles
    with ThreadPoolExecutor(max_workers=6) as ex:
        res = list(ex.map(lambda pr: tester_lien(pr[0]["lien"], pr[0].get("type", "")), gardees))
    ok = []
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
    for (p, _), (code, raison) in zip(gardees, res):
        p["verif"] = {"http": code, "le": now}
        if raison:
            rejetees.append((p, [raison]))
        else:
            ok.append(p)
    return ok, [{**p, "raisons": r} for p, r in rejetees]


def main(argv):
    essai = "--essai" in argv
    hebdo = "--hebdo" in argv
    args = [a for a in argv if not a.startswith("--")]
    if not args:
        print(__doc__)
        return 2
    f = Path(args[0])
    data = json.loads(f.read_text(encoding="utf-8"))
    today = regles.date_iso(os.environ.get("AUJOURDHUI")) or dt.date.today()
    s = seuils()
    if hebdo:
        cand = f.with_name(f.name.replace(".json", ".candidats.json"))
        connus = {p["id"] for p in json.loads(cand.read_text(encoding="utf-8")).get("pistes", [])}
        inventees = [p.get("titre") for p in data.get("pistes", []) if p.get("id") not in connus]
        for t in inventees:
            print(f"REFUS : piste absente des candidats de la semaine : {t}")
        return 1 if inventees else 0
    ok, rej = verifier(data.get("pistes", []), today, s)
    for p in ok:
        print(f"OK     {p['verif']['http']}  {p.get('date_limite') or 'sans date'}  {p['titre']}")
    for p in rej:
        print(f"REFUS  {p.get('titre')} : {'; '.join(p['raisons'])}")
    print(f"Bilan : {len(ok)} gardées, {len(rej)} refusées")
    if not essai:
        f.with_name(f.stem + ".brut.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        data["pistes"] = ok
        data["rejetees"] = data.get("rejetees", []) + rej
        data["verifie_le"] = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%MZ")
        tmp = f.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        tmp.replace(f)
        # deja-vus.md ne garde que les pistes réellement rangées : une piste refusée pourra être retrouvée plus tard
        dv = D / "deja-vus.md"
        refus = {p.get("lien") for p in rej if p.get("lien")} - {p["lien"] for p in ok}
        if dv.exists() and refus:
            jour = str(data.get("date", f.stem))[:10]
            lignes = dv.read_text(encoding="utf-8").splitlines()
            garde = [l for l in lignes if not (l.startswith(jour) and any(f"| {u} |" in l for u in refus))]
            dv.write_text("\n".join(garde) + ("\n" if garde else ""), encoding="utf-8")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
