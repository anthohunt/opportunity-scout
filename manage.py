"""Gestion (dans le conteneur) : docker compose exec scout python manage.py <commande>

  masterpw        nouveau mot de passe maître, affiché UNE fois ; toutes les sessions sont fermées
  import          importe tout de suite les passages quotidiens (rapports/*.json)
  etats           réécrit etats.md depuis la base
"""
import secrets
import string
import sys

from app.main import db, import_reports, set_master_password, write_etats_md

ALPHABET = string.ascii_letters + string.digits + "-_.!?#%+="


def new_password(n: int = 22) -> str:
    while True:
        pw = "".join(secrets.choice(ALPHABET) for _ in range(n))
        if any(c.islower() for c in pw) and any(c.isupper() for c in pw) and any(c.isdigit() for c in pw) \
                and any(not c.isalnum() for c in pw):
            return pw


def main(argv):
    cmd = argv[0] if argv else ""
    if cmd == "masterpw":
        pw = new_password()
        with db() as con:
            set_master_password(con, pw)
        print(pw)
    elif cmd == "import":
        import_reports()
        with db() as con:
            print(con.execute("SELECT COUNT(*) FROM pistes").fetchone()[0], "pistes en base")
    elif cmd == "etats":
        with db() as con:
            write_etats_md(con)
    else:
        print(__doc__)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
