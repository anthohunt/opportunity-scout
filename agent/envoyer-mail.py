#!/usr/bin/env python3
"""Envoie le récapitulatif du lundi par SMTP (bibliothèque standard seule).

  envoyer-mail.py --sujet "..." --html fichier.html

Réglages par variables d'environnement : SMTP_HOTE, SMTP_PORT (587 par défaut, STARTTLS ; 465 = SSL direct),
SMTP_STARTTLS (1 par défaut ; 0 pour un relais local sans chiffrement), SMTP_UTILISATEUR, SMTP_MOT_DE_PASSE, SCOUT_MAIL_DE, SCOUT_MAIL_A. Rien n'est lu ailleurs : aucun mot de passe
n'est écrit dans le dépôt.
"""
import argparse
import os
import smtplib
import ssl
import sys
from email.message import EmailMessage
from pathlib import Path


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--sujet", required=True)
    ap.add_argument("--html", required=True)
    a = ap.parse_args()
    try:
        hote = os.environ["SMTP_HOTE"]
        de, vers = os.environ["SCOUT_MAIL_DE"], os.environ["SCOUT_MAIL_A"]
    except KeyError as e:
        print(f"réglage manquant : {e.args[0]}", file=sys.stderr)
        return 2
    port = int(os.environ.get("SMTP_PORT", "587"))
    html = Path(a.html).read_text(encoding="utf-8")
    msg = EmailMessage()
    msg["From"], msg["To"], msg["Subject"] = de, vers, a.sujet
    msg.set_content("Ce message est en HTML : ouvrez-le dans un client de messagerie qui l'affiche.")
    msg.add_alternative(html, subtype="html")
    ctx = ssl.create_default_context()
    if port == 465:
        s = smtplib.SMTP_SSL(hote, port, context=ctx, timeout=30)
    else:
        s = smtplib.SMTP(hote, port, timeout=30)
        if os.environ.get("SMTP_STARTTLS", "1") != "0":   # 0 : relais local sans chiffrement uniquement
            s.starttls(context=ctx)
    with s:
        if os.environ.get("SMTP_UTILISATEUR"):
            s.login(os.environ["SMTP_UTILISATEUR"], os.environ.get("SMTP_MOT_DE_PASSE", ""))
        s.send_message(msg)
    print("mail envoyé à", vers)
    return 0


if __name__ == "__main__":
    sys.exit(main())
