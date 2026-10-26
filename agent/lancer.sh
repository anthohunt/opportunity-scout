#!/bin/bash
# Agent de recherche d'opportunités : lanceur (cron).
#
# Passage QUOTIDIEN, sans mail : l'agent écrit rapports/<date>.json, verifier-pistes.py refait les contrôles et teste
# les liens, puis la commande SCOUT_IMPORT_CMD importe ce qui reste dans l'app (onglet Pistes).
# Récapitulatif du LUNDI (HEBDO=1) : assembler-semaine.py prépare les candidats, un agent écrit hebdo/<date>.json,
# rendre-mail.py en fait la newsletter, envoyer-mail.py l'envoie — et SEULEMENT si le fichier .envoi-actif existe
# dans le dossier de données (l'opérateur voit d'abord le mail rendu dans hebdo/<date>.html, puis active l'envoi :
# touch "$SCOUT_DIR/.envoi-actif").
#
# Exemple de crontab (l'heure du serveur peut être UTC : le garde-fou d'heure suit SCOUT_TZ, été comme hiver) :
#   5 5,6 * * *   /chemin/agent/lancer.sh            -> ne travaille qu'à SCOUT_HEURE_QUOTIDIEN (7 h par défaut)
#   0 6,7 * * 1   HEBDO=1 /chemin/agent/lancer.sh    -> ne travaille qu'à SCOUT_HEURE_HEBDO (8 h par défaut)
# À la main : FORCE=1 lancer.sh [AAAA-MM-JJ] ; FORCE=1 HEBDO=1 lancer.sh [AAAA-MM-JJ].
# Un seul passage à la fois (verrou) : le lundi, le mail attend le passage quotidien.
#
# Réglages (variables d'environnement, voir .env.example) :
#   SCOUT_DIR            dossier de données de l'app (rapports/, hebdo/, logs/, contexte.md, seuils.json…) — obligatoire
#   SCOUT_TZ             fuseau des heures de passage (Europe/Paris par défaut)
#   SCOUT_CLAUDE_CMD     commande de l'agent (claude par défaut) ; SCOUT_MODEL son modèle ; SCOUT_WRAPPER un préfixe facultatif
#                        (limiteur de CPU, nice…) ; SCOUT_ENV_FILE un fichier d'environnement à charger avant l'agent
#   SCOUT_IMPORT_CMD     commande d'import dans l'app (ex. « docker compose exec -T scout python manage.py import »)
#   SCOUT_MAIL_A / SCOUT_MAIL_DE / SMTP_*   envoi du mail (voir envoyer-mail.py) ; SCOUT_ENVOI_DES  date AAAA-MM-JJ avant laquelle rien n'est envoyé
set -u
D="${SCOUT_DIR:?SCOUT_DIR doit désigner le dossier de données}"
SCRIPTS="$(cd "$(dirname "$0")" && pwd)"
export TZ="${SCOUT_TZ:-Europe/Paris}"
J="${1:-$(date +%F)}"
H=$(date +%H)
if [ "${FORCE:-0}" != 1 ]; then
  if [ "${HEBDO:-0}" = 1 ]; then [ "$H" = "${SCOUT_HEURE_HEBDO:-08}" ] || exit 0; else [ "$H" = "${SCOUT_HEURE_QUOTIDIEN:-07}" ] || exit 0; fi
fi
mkdir -p "$D/rapports" "$D/hebdo" "$D/logs"
exec 9>"$D/.lancer.lock"
flock -w 5400 9 || exit 1
touch "$D/deja-vus.md" "$D/sources.md" "$D/etats.md"
# les scripts et les règles sont lus depuis le dossier de données (c'est là que l'agent travaille)
cp "$SCRIPTS"/*.py "$SCRIPTS"/*.md "$D"/ 2>/dev/null; cp "$SCRIPTS/../app/regles.py" "$D/regles.py"
[ -e "$D/contexte.md" ] || { echo "contexte.md manquant : copiez agent/contexte.exemple.md et adaptez-le" >&2; exit 1; }
export DATE="$J"
ENVOI_DES="${SCOUT_ENVOI_DES:-1970-01-01}"
DEST="${SCOUT_MAIL_A:-}"
CLAUDE="${SCOUT_CLAUDE_CMD:-claude}"
MODELE="${SCOUT_MODEL:-claude-opus-5-5}"

agent() {  # agent <consigne> <journal> ; remplace les {{VAR}} par les variables d'environnement exportées
  perl -pe 's/\{\{(\w+)\}\}/$ENV{$1}/g' "$D/$1" > "$D/logs/$J.$1"
  echo "début $1 : $(date -u +%FT%TZ)" >> "$D/logs/$2"
  ( cd "$D" && { [ -z "${SCOUT_ENV_FILE:-}" ] || { set -a; . "$SCOUT_ENV_FILE"; set +a; }; } \
    && ${SCOUT_WRAPPER:-} timeout 70m "$CLAUDE" -p "$(cat "$D/logs/$J.$1")" --model "$MODELE" --effort medium \
         --dangerously-skip-permissions --add-dir "$D" < /dev/null ) >> "$D/logs/$2" 2>&1
  echo "fin $1 : code $? $(date -u +%FT%TZ)" >> "$D/logs/$2"
}

envoi_permis() { [ -e "$D/.envoi-actif" ] && [ -n "$DEST" ] && [ ! "$J" \< "$ENVOI_DES" ]; }

envoyer() {  # envoyer <objet> <fichier html>
  python3 "$SCRIPTS/envoyer-mail.py" --sujet "$1" --html "$2"
}

alerter() {  # alerter <objet> : prévient l'opérateur, et seulement une fois l'envoi activé
  envoi_permis || { echo "alerte non envoyée (envoi désactivé) : $1" >> "$D/logs/$J.log"; return; }
  local f; f=$(mktemp); printf '<p>Journal : %s/logs/%s.log</p>' "$D" "$J" > "$f"
  envoyer "$1" "$f" >> "$D/logs/$J.log" 2>&1; rm -f "$f"
}

if [ "${HEBDO:-0}" != 1 ]; then
  # 1. Passage quotidien, sans mail
  agent consigne.md "$J.log"
  R="$D/rapports/$J.json"
  if [ -s "$R" ] && (cd "$D" && python3 verifier-pistes.py "rapports/$J.json") >> "$D/logs/$J.log" 2>&1; then
    ${SCOUT_IMPORT_CMD:-python3 "$SCRIPTS/../manage.py" import} >> "$D/logs/$J.log" 2>&1
  else
    alerter "Opportunités $J : le passage quotidien n'a produit aucun fichier de pistes"
  fi
else
  # 2. Récapitulatif du lundi
  W="$D/hebdo/$J"
  export DU=$(date -d "$J -6 days" +%F) AU="$J"
  (cd "$D" && python3 assembler-semaine.py "$J") >> "$D/logs/$J.hebdo.log" 2>&1
  agent consigne-hebdo.md "$J.hebdo.log"
  if [ -s "$W.json" ] \
     && (cd "$D" && python3 verifier-pistes.py --hebdo "hebdo/$J.json") >> "$D/logs/$J.hebdo.log" 2>&1 \
     && python3 "$D/rendre-mail.py" "$W.json" > "$W.html.tmp" 2>> "$D/logs/$J.hebdo.log"; then
    mv "$W.html.tmp" "$W.html"
    S=$(head -1 "$W.sujet" 2>/dev/null); S="${S:-Opportunités, semaine du $(date -d "$J" +%d/%m)}"
    if envoi_permis && [ ! -e "$W.envoye" ]; then
      envoyer "$S" "$W.html" >> "$D/logs/$J.hebdo.log" 2>&1 && date -u +%FT%TZ > "$W.envoye"
    else
      echo "mail rendu dans $W.html, NON envoyé (envoi désactivé, destinataire absent ou avant le $ENVOI_DES)" >> "$D/logs/$J.hebdo.log"
    fi
  else
    rm -f "$W.html.tmp"
    alerter "Opportunités, semaine du $J : le récapitulatif n'a pas été produit"
  fi
fi
