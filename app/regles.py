"""Règles d'entrée d'une piste. Une seule source : l'app, le vérificateur
du passage quotidien (verifier-pistes.py) et l'assemblage du lundi (assembler-semaine.py) importent ce fichier.
Copié dans le dossier de données au déploiement (voir README de l'app)."""
import datetime as dt
import hashlib
import os
import re
import unicodedata
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# Réglage par défaut : ce qui intéresse le plus l'opérateur, ce sont des CONTRATS — missions signées par sa
# micro-entreprise et marchés publics ou appels d'offres à portée d'un indépendant. Budget de recherche : contrats 60 %,
# emplois 20 %, concours 20 %. Les appels à projets, financements et interventions ne sont pas cherchés.
CATEGORIES = [
    ("contrats", "Contrats"),
    ("concours", "Concours et red-teaming"),
    ("emplois", "Emplois"),
]
CATEGORY_LABELS = dict(CATEGORIES)

TYPES = {
    "mission": ("contrats", "Mission freelance"),
    "appel_offres": ("contrats", "Marché public"),
    "reseau_experts": ("contrats", "Réseau d'experts"),
    "evaluateur": ("contrats", "Évaluateur"),
    "tache": ("contrats", "Tâche payée à l'unité"),   # hors quota : jamais un contrat, toujours en fin de section
    "concours": ("concours", "Concours IA"),
    "red_teaming": ("concours", "Red-teaming"),
    "prix": ("concours", "Prix"),
    "emploi": ("emplois", "Emploi"),
}
HORS_QUOTA = {"tache"}

UNITES = {"heure", "jour", "total", "mois_net", "an_brut"}
DOMAINES = {"IA", "XR", "IA et XR"}

SEUILS_DEFAUT = {
    "mission_eur_h": 50,        # contrats : 50 €/h ou TJM ≥ 8 × ce taux
    "heures_par_jour": 8,       # un TJM se compare à 8 × le taux horaire
    "concours_eur": 1000,       # concours et red-teaming : 1 000 € au moins
    "marche_eur": 1000,         # marchés publics et appels d'offres : budget minimum (un budget cohérent avec le travail)
    "emploi_net_mois": 3000,    # emplois : 3 000 € net par mois
    "emploi_brut_an": 48000,    # équivalent annuel brut (net ≈ 77 % du brut dans le privé en France)
    "lieux_emploi": ["Lyon", "Nantes"],  # sinon télétravail complet, n'importe quel pays
    "sans_date_jours": 30,      # offre sans date limite publiée gardée si publiée
                                # depuis moins de 30 jours (emplois, missions) ; 0 = jamais ; date passée = toujours écartée
    "repartition": {"contrats": 60, "concours": 20, "emplois": 20},
}
# Types qui publient rarement une date limite (offres d'emploi, missions) : tolérés sans date s'ils sont récents.
TYPES_SANS_DATE = {"emploi", "mission", "reseau_experts", "evaluateur", "tache"}


def sans_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s or "") if unicodedata.category(c) != "Mn").lower()


def lien_canonique(url: str) -> str:
    """Même annonce, même lien : sans fragment, sans paramètres de suivi, sans / final."""
    p = urlsplit((url or "").strip())
    q = [(k, v) for k, v in parse_qsl(p.query, keep_blank_values=True)
         if not re.match(r"^(utm_|ref$|refid$|trk|tracking|src$|source$|fbclid|gclid|position$|pagenum$)", k, re.I)]
    path = p.path.rstrip("/") or "/"
    return urlunsplit((p.scheme.lower(), p.netloc.lower().removeprefix("www."), path, urlencode(q), ""))


def piste_id(p: dict) -> str:
    return hashlib.sha1(lien_canonique(p.get("lien", "")).encode()).hexdigest()[:12]


def date_iso(s):
    try:
        return dt.date.fromisoformat(str(s)[:10]) if s else None
    except ValueError:
        return None


def controle_champs(p):
    r = []
    for k in ("titre", "type", "organisme", "montant", "lien", "pourquoi", "effort"):
        if not str(p.get(k) or "").strip():
            r.append(f"champ manquant : {k}")
    if p.get("type") and p["type"] not in TYPES:
        r.append(f"type inconnu : {p['type']}")
    local = os.environ.get("SCOUT_TEST") == "1" and str(p.get("lien", "")).startswith("http://127.0.0.1:")
    if p.get("lien") and not local and not re.match(r"^https://[^\s]+$", p["lien"]):
        r.append("le lien doit commencer par https://")
    if p.get("domaine") and p["domaine"] not in DOMAINES:
        r.append(f"domaine inconnu : {p['domaine']}")
    if len(str(p.get("titre") or "")) > 110:
        r.append("titre trop long (110 caractères au plus)")
    return r


def controle_date(p, today, seuils=SEUILS_DEFAUT):
    d = date_iso(p.get("date_limite"))
    if p.get("date_limite") and d is None:
        return ["date limite illisible (AAAA-MM-JJ attendu)"]
    if d is not None:
        return [] if d >= today else [f"date limite passée ({d})"]
    if p.get("type") not in TYPES_SANS_DATE or int(seuils.get("sans_date_jours", 0)) <= 0:
        return ["date limite manquante"]
    pub = date_iso(p.get("publiee_le"))
    if pub is None:
        return ["ni date limite ni date de publication"]
    if (today - pub).days >= int(seuils["sans_date_jours"]) or pub > today:
        return [f"offre sans date limite publiée il y a plus de {seuils['sans_date_jours']} jours"]
    return []


def controle_montant(p, seuils=SEUILS_DEFAUT):
    t = p.get("type")
    cat = TYPES.get(t, ("", ""))[0]
    v, u = p.get("montant_eur"), p.get("unite")
    if v in (None, ""):
        if p.get("montant_publie") is False and str(p.get("montant_probable") or "").strip():
            return []
        return ["montant absent : mettre montant_publie=false et justifier montant_probable"]
    try:
        v = float(v)
    except (TypeError, ValueError):
        return ["montant_eur doit être un nombre"]
    if u not in UNITES:
        return [f"unité inconnue : {u}"]
    h = float(seuils["mission_eur_h"])
    jour = h * float(seuils.get("heures_par_jour", 8))
    if u == "heure":
        ok = v >= h
    elif u == "jour":
        ok = v >= jour
    elif u == "mois_net":
        ok = v >= float(seuils["emploi_net_mois"])
    elif u == "an_brut":
        ok = v >= float(seuils["emploi_brut_an"])
    else:  # total
        if cat == "concours":
            ok = v >= float(seuils["concours_eur"])
        elif t == "appel_offres":
            ok = v >= float(seuils.get("marche_eur", seuils.get("appel_eur", 1000)))
        else:  # mission, expertise, tâche, emploi au forfait : ramené à l'heure
            try:
                eh = float(p.get("effort_heures") or 0)
            except (TypeError, ValueError):
                eh = 0
            if eh <= 0:
                return ["montant au forfait : effort_heures nécessaire pour le ramener à l'heure"]
            ok = v / eh >= h
    return [] if ok else [f"sous le seuil ({v:g} € par {u})"]


def controle_lieu(p, seuils=SEUILS_DEFAUT):
    if p.get("type") != "emploi" or p.get("teletravail_complet") is True:
        return []
    lieu = sans_accents(str(p.get("lieu") or ""))
    if any(sans_accents(l) in lieu for l in seuils.get("lieux_emploi", [])):
        return []
    return ["emploi ni dans une ville acceptée ni en télétravail complet"]


def controle(p, seuils=None, today=None):
    """Liste des raisons de refus ; vide = la piste entre."""
    seuils = {**SEUILS_DEFAUT, **(seuils or {})}
    today = today or dt.date.today()
    r = controle_champs(p)
    if r:
        return r
    return controle_date(p, today, seuils) + controle_montant(p, seuils) + controle_lieu(p, seuils)


EXPIRATION = re.compile(
    r"no longer accepting applications|this job (?:has expired|is no longer available)|position has been filled|"
    r"offre (?:a expiré|n'est plus disponible|expirée|pourvue)|cette offre n.est plus|job not found|"
    r"applications? (?:are|is) closed|competition has ended|hackathon has ended|submissions? (?:are )?closed",
    re.I,
)
