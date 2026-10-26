#!/usr/bin/env python3
"""Met en page le mail du lundi de l'agent de recherche d'opportunités :
newsletter en tableaux et styles en ligne (lisible dans les clients de messagerie courants). L'agent écrit le contenu en JSON
(hebdo/<date>.json), ce script en fait le HTML, toujours avec la même mise en page.
Usage : rendre-mail.py hebdo/2026-11-02.json > hebdo/2026-11-02.html
"""
import datetime
import html
import json
import os
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import regles  # noqa: E402

APP_URL = os.environ.get("APP_URL", "http://localhost:8000")
FONT = "Arial,Helvetica,sans-serif"
SERIF = "Georgia,'Times New Roman',serif"
INK = "#1d2433"
MUTED = "#6b7280"
LINK = "#1a5fb4"
MOIS = ["janvier", "février", "mars", "avril", "mai", "juin", "juillet", "août", "septembre", "octobre",
        "novembre", "décembre"]
JOURS = ["lundi", "mardi", "mercredi", "jeudi", "vendredi", "samedi", "dimanche"]

# catégorie -> (couleur forte, fond léger)
COULEURS = {
    "contrats": ("#0f766e", "#ecf7f5"),
    "concours": ("#c2410c", "#fdf1ea"),
    "emplois": ("#1d4ed8", "#eef3fd"),
}


def inline(text):
    """Échappe le texte, en gardant seulement <b> et <i>."""
    t = html.escape(str(text or ""), quote=False)
    return re.sub(r"&lt;(/?)(b|i)&gt;", r"<\1\2>", t)


def date_fr(d, annee=True):
    d = datetime.date.fromisoformat(str(d)[:10])
    j = "1er" if d.day == 1 else str(d.day)
    return f"{j} {MOIS[d.month - 1]}" + (f" {d.year}" if annee else "")


def echeance(p, today):
    if not p.get("date_limite"):
        pub = p.get("publiee_le")
        p_ = datetime.date.fromisoformat(str(pub)[:10]) if pub else None
        return f"Publiée le {p_.strftime('%d/%m')}, pas de date limite" if p_ else "Pas de date limite publiée"
    d = datetime.date.fromisoformat(p["date_limite"][:10])
    n = (d - today).days
    reste = "aujourd'hui" if n == 0 else ("demain" if n == 1 else f"dans {n} jours")
    return f"{date_fr(d)} ({reste})"


def montant(p):
    m = inline(p.get("montant"))
    if p.get("montant_publie") is False:
        m += f'<br><span style="font-size:12px;color:{MUTED};">montant non publié</span>'
    return m


def domaine(url):
    return re.sub(r"^https?://(www\.)?", "", url or "").split("/")[0]


def fact(label, value, color):
    return (
        f'<td valign="top" style="padding:8px 10px 8px 0;">'
        f'<div style="font-family:{FONT};font-size:11px;letter-spacing:.08em;text-transform:uppercase;color:{color};'
        f'font-weight:bold;margin:0 0 2px;">{label}</div>'
        f'<div style="font-family:{FONT};font-size:14px;line-height:1.35;color:{INK};">{value}</div></td>'
    )


def card(p, color, tint, today):
    type_label = regles.TYPES.get(p.get("type"), ("", p.get("type", "")))[1]
    if p.get("type") in regles.HORS_QUOTA:
        type_label += " (hors quota)"
    lieu = ""
    if p.get("type") == "emploi":
        lieu = " &middot; " + ("Télétravail complet" if p.get("teletravail_complet") else inline(p.get("lieu")))
    head = (
        f'<div style="font-family:{FONT};font-size:12px;color:{MUTED};margin:0 0 4px;">'
        f'<span style="display:inline-block;background:#ffffff;color:{color};border:1px solid {color};border-radius:10px;'
        f'padding:1px 8px;font-size:11px;font-weight:bold;">{inline(type_label)}</span>&nbsp; {inline(p.get("organisme"))}{lieu}</div>'
    )
    title = (f'<div style="font-family:{SERIF};font-size:18px;line-height:1.3;font-weight:bold;color:{INK};margin:2px 0 6px;">'
             f'{inline(p.get("titre"))}</div>')
    facts = (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:0 0 6px;"><tr>'
        + fact("Montant", montant(p), color) + fact("Date limite", inline(echeance(p, today)), color)
        + fact("Effort", inline(p.get("effort")), color) + "</tr></table>"
    )
    why = (f'<div style="font-family:{FONT};font-size:15px;line-height:1.55;color:#374151;margin:0 0 8px;">'
           f'<b>Pourquoi pour toi.</b> {inline(p.get("pourquoi"))}</div>')
    vig = ""
    if p.get("vigilance"):
        vig = (f'<div style="font-family:{FONT};font-size:13px;line-height:1.45;color:#92400e;background:#fef6e4;'
               f'border-radius:6px;padding:6px 10px;margin:0 0 8px;"><b>À vérifier.</b> {inline(p["vigilance"])}</div>')
    lien = (f'<div style="font-family:{FONT};font-size:14px;"><a href="{html.escape(p["lien"])}" '
            f'style="color:{color};font-weight:bold;text-decoration:none;">Ouvrir l\'annonce &rarr;</a>'
            f'<span style="color:{MUTED};font-size:12px;">&nbsp; {html.escape(domaine(p["lien"]))}</span></div>')
    return (
        '<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="margin:0 0 12px;">'
        f'<tr><td width="4" style="background:{color};border-radius:4px 0 0 4px;font-size:0;line-height:0;">&nbsp;</td>'
        f'<td style="background:{tint};border-radius:0 6px 6px 0;padding:14px 18px;">{head}{title}{facts}{why}{vig}{lien}</td></tr></table>'
    )


def section(cat, pistes, today):
    color, tint = COULEURS[cat]
    n = sum(1 for p in pistes if p.get("type") not in regles.HORS_QUOTA)
    hq = len(pistes) - n
    compte = f"{n}" + (f" + {hq} tâche{'s' if hq > 1 else ''} hors quota" if hq else "")
    head = (
        f'<div style="font-family:{FONT};font-size:12px;font-weight:bold;letter-spacing:.12em;text-transform:uppercase;'
        f'color:{color};margin:22px 0 10px;padding-bottom:6px;border-bottom:1px solid #e7e3da;">'
        f'{regles.CATEGORY_LABELS[cat]} &middot; {compte}</div>'
    )
    # les tâches payées à l'unité ne sont pas des contrats : toujours en fin de section, signalées hors quota
    pistes = sorted(pistes, key=lambda p: p.get("type") in regles.HORS_QUOTA)
    return head + "".join(card(p, color, tint, today) for p in pistes)


def render(data):
    today = datetime.date.fromisoformat(data["date"])
    pistes = data.get("pistes") or []
    lead = data.get("lead") or "<b>Aucune piste nouvelle cette semaine.</b>"
    preheader = re.sub(r"<[^>]+>", "", lead)
    du, au = data.get("du"), data.get("au") or data["date"]
    periode = f"Semaine du {date_fr(du, False)} au {date_fr(au)}" if du else f"{JOURS[today.weekday()].capitalize()} {date_fr(today)}"
    sections = "".join(
        section(cat, [p for p in pistes if regles.TYPES.get(p.get("type"), ("",))[0] == cat], today)
        for cat, _ in regles.CATEGORIES
        if any(regles.TYPES.get(p.get("type"), ("",))[0] == cat for p in pistes)
    )
    return f"""<!DOCTYPE html>
<html lang="fr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="color-scheme" content="light"><meta name="supported-color-schemes" content="light"><title>Opportunités {data['date']}</title></head>
<body style="margin:0;padding:0;background:#efebe3;">
<div style="display:none;max-height:0;overflow:hidden;opacity:0;color:#efebe3;">{html.escape(preheader)}</div>
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background:#efebe3;">
<tr><td align="center" style="padding:20px 8px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:640px;background:#ffffff;border-radius:10px;">

<tr><td style="background:{INK};border-radius:10px 10px 0 0;padding:22px 22px 20px;">
<div style="font-family:{FONT};font-size:11px;letter-spacing:.18em;text-transform:uppercase;color:#a5b4cf;">Récapitulatif de la semaine</div>
<div style="font-family:{SERIF};font-size:30px;line-height:1.15;font-weight:bold;color:#ffffff;margin:4px 0 2px;">Opportunités</div>
<div style="font-family:{FONT};font-size:14px;color:#d6dcea;">{periode}</div>
</td></tr>

<tr><td style="padding:22px 18px 8px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr>
<td style="background:#f3f1ec;border-left:4px solid {INK};border-radius:6px;padding:14px 18px;font-family:{FONT};font-size:17px;line-height:1.5;color:{INK};">{inline(lead)}</td>
</tr></table>
{sections}
</td></tr>

<tr><td align="center" style="padding:18px 18px 4px;">
<table role="presentation" cellpadding="0" cellspacing="0" border="0"><tr>
<td align="center" bgcolor="{INK}" style="background:{INK};border-radius:8px;">
<a href="{APP_URL}" style="display:inline-block;padding:13px 26px;font-family:{FONT};font-size:16px;font-weight:bold;color:#ffffff;text-decoration:none;border-radius:8px;">Trier les pistes dans l'app &rarr;</a>
</td></tr></table>
<div style="font-family:{FONT};font-size:13px;color:{MUTED};margin-top:8px;">À voir, intéressé ou écarté : l'agent en tient compte dès le lendemain</div>
</td></tr>

<tr><td style="padding:18px 18px 24px;">
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"><tr><td style="border-top:1px solid #e7e3da;padding-top:14px;font-family:{FONT};font-size:12px;line-height:1.6;color:#8a8f99;">
{inline(data.get('footer', ''))}<br>
<a href="{APP_URL}" style="color:#8a8f99;text-decoration:underline;">{APP_URL.split('://', 1)[-1]}</a> &middot; chaque lien a été ouvert lundi matin avant l'envoi
</td></tr></table>
</td></tr>

</table>
</td></tr></table>
</body></html>
"""


if __name__ == "__main__":
    with open(sys.argv[1], encoding="utf-8") as f:
        sys.stdout.write(render(json.load(f)))
