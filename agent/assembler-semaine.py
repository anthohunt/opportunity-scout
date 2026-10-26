#!/usr/bin/env python3
"""Prépare le mail du lundi (agent de recherche d'opportunités) : rassemble les pistes gardées par
les passages quotidiens des 7 derniers jours (lundi exclu de la semaine précédente, lundi du jour inclus),
dédoublonne par lien, retire celles que l'opérateur a écartées dans l'app, refait les contrôles et le test des liens
(une piste close entre-temps sort), trie par catégorie puis par date limite.
  assembler-semaine.py 2026-01-19   ->  hebdo/2026-01-19.candidats.json
"""
import datetime as dt
import json
import sqlite3
import sys
from pathlib import Path

D = Path(__file__).resolve().parent
sys.path.insert(0, str(D))
import regles  # noqa: E402

def charger_verifier():
    import importlib.util
    spec = importlib.util.spec_from_file_location("verifier_pistes", D / "verifier-pistes.py")
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def etats():
    try:
        con = sqlite3.connect(f"file:{D / 'app' / 'app.db'}?mode=ro", uri=True)
        rows = dict(con.execute("SELECT id, etat FROM pistes").fetchall())
        con.close()
        return rows
    except Exception:
        return {}


def main(argv):
    jour = regles.date_iso(argv[0]) if argv else dt.date.today()
    debut = jour - dt.timedelta(days=6)
    vues = {}
    jours = []
    for f in sorted((D / "rapports").glob("*.json")):
        if f.name.endswith((".brut.json", ".tmp")):
            continue
        d = regles.date_iso(f.stem[:10])
        if d is None or not (debut <= d <= jour):
            continue
        jours.append(f.stem)
        for p in json.loads(f.read_text(encoding="utf-8")).get("pistes", []):
            p = dict(p)
            p["id"] = p.get("id") or regles.piste_id(p)
            p["vue_le"] = f.stem[:10]
            vues[p["id"]] = p  # la version la plus récente l'emporte
    e = etats()
    ecartees = [p for i, p in vues.items() if e.get(i) == "ecarte"]
    restantes = [p for i, p in vues.items() if e.get(i) != "ecarte"]
    v = charger_verifier()
    ok, rej = v.verifier(restantes, jour, v.seuils())
    for p in ok:
        p["etat"] = e.get(p["id"], "a_voir")
    ordre = {k: n for n, (k, _) in enumerate(regles.CATEGORIES)}
    ok = [p for p in ok if p.get("type") in regles.TYPES]  # types abandonnés (appels à projets, financements)
    ok.sort(key=lambda p: (ordre[regles.TYPES[p["type"]][0]], p["type"] in regles.HORS_QUOTA,
                           p.get("date_limite") or "9999", p["titre"]))
    out = {"date": jour.isoformat(), "du": debut.isoformat(), "au": jour.isoformat(), "jours": jours,
           "pistes": ok, "sorties": rej, "ecartees_par_operateur": len(ecartees)}
    (D / "hebdo").mkdir(exist_ok=True)
    f = D / "hebdo" / f"{jour.isoformat()}.candidats.json"
    f.write_text(json.dumps(out, ensure_ascii=False, indent=1), encoding="utf-8")
    print(f"{f} : {len(ok)} candidates, {len(rej)} sorties au nouveau contrôle, {len(ecartees)} écartées par l'opérateur, "
          f"{len(jours)} passages lus")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
