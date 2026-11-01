"""Pages 11 à la fin (FR) : fin du 2.2, 2.3, 2.4, 3. Actions ; le ch. 4 vient de content_fr."""
from xml.sax.saxutils import escape as e
import content_fr
R = lambda t: ("role", "Rôle. " + e(t))
P = lambda t: ("p", e(t))
NEW = " (Hydra 0.17.0+)"

SPEC = [
P("Voir ci-dessus. Rôle : identifie une ligne pour l'upsert."),
("h3", "batch_size : lignes par écriture (10 à 100000, défaut 10000)"),
("code", "load: { batch_size: 20000 }"),
R("règle le compromis mémoire / vitesse."),
("h3", "atomic : tout ou rien"),
("code", "load: { atomic: true }   # annule l'écriture entière en cas d'erreur"),
R("évite une destination à moitié chargée."),

("h2", "2.3 Pipeline (pipeline.yaml)"),
("h3", "pipeline, from, to"),
("code", '''version: "1.0"
pipeline:
  from: orders        # id déclaré dans sources.yaml
  to: dwh_orders      # id déclaré dans destinations.yaml'''),
R("relie une source à une destination ; les transformations s'appliquent entre les deux."),

("h2", "2.4 Transformations (transformations.yaml)"),
("h3", "transformations : liste ordonnée d'opérations"),
("code", '''version: "1.0"
engine: auto           # auto | pandas | duckdb (voir plus bas)
transformations:
  - select: { columns: [id, country, amount] }
  - filter: { expr: "amount > 0" }'''),
R("décrit ce qui arrive aux données ; les opérations s'exécutent dans l'ordre."),
("h3", "Colonnes"),
("code", '''select : garde des colonnes.
- select:
    columns: [id, country, amount]   # les autres sont supprimées
rename : renomme.
- rename:
    mapping: { cust_id: customer_id }   # ancien: nouveau
cast : change le type (int, float, str, bool, datetime).
- cast:
    mapping: { amount: float, created: datetime }'''),
("h3", "Lignes"),
("code", '''filter : garde les lignes vraies.
- filter: { expr: "country == 'BE' and amount >= {{ param:min_amount }}" }
sort : trie (stable).
- sort: { by: [country, amount], ascending: [true, false] }
deduplicate : supprime les doublons.
- deduplicate: { columns: [customer_id], keep: last }   # first | last
fill_null : remplace les valeurs vides.
- fill_null: { columns: { country: "N/A", amount: 0 } }   # ou value: 0 pour toutes
trim : retire les espaces.
- trim: { columns: [name] }   # défaut : toutes les colonnes texte
clean : nettoie le texte.
- clean: { columns: [status], case: upper }   # none | lower | upper'''),
("h3", "text_to_rows : une ligne par valeur" + NEW),
("code", '''- text_to_rows:
    column: tags            # "a;b;c" -> 3 lignes, les autres colonnes recopiées
    sep: ";"                # défaut ","
    regex: false            # true : sep est une expression régulière, ex. "[,;]"
    trim: true              # défaut true : espaces retirés autour de chaque valeur
    keep_empty: false       # défaut false : valeurs vides ignorées
    index_column: tag_pos   # optionnel : position 1, 2, 3...'''),
R("découpe une liste rangée dans une cellule. Une valeur nulle, ou sans aucune partie non vide, garde une ligne avec une valeur nulle : aucune ligne d'entrée n'est perdue."),
("h3", "Calcul"),
("code", '''calculate : crée une colonne.
- calculate: { column: total_ttc, expr: "amount * 1.2" }
script : Python restreint.
- script:
    inputs: [amount]
    outputs: { amount_x2: float }
    mode: vectorized         # vectorized | row
    code: |
      amount_x2 = amount * params["factor"]   # colonnes = variables ; params = paramètres du run'''),
("h3", "Agrégation"),
("code", '''aggregate : regroupe et calcule.
- aggregate:
    by: [country]
    agg:
      total: { func: sum, col: amount }   # sum | count | mean | avg | min | max | first | last
      n:     { func: count, col: id }'''),
R("une ligne par groupe ; les colonnes absentes de by et agg disparaissent."),
("h3", "Fonctions de fenêtre : window" + NEW),
("code", '''- window:
    partition_by: [customer_id]                  # optionnel : toute la table sans lui
    order_by: [order_date, {col: amount, desc: true}]
    columns:
      order_rank:  { func: row_number }
      prev_amount: { func: lag, col: amount, offset: 1, default: 0 }
      running:     { func: cumsum, col: amount }
      cust_total:  { func: sum, col: amount }'''),
R("ajoute des colonnes et garde toutes les lignes, dans leur ordre d'entrée (contrairement à aggregate)."),
("table", ([["Famille", "Fonctions", "Options"],
  ["Rang", "row_number, rank, dense_rank", "aucune"],
  ["Décalage", "lag, lead", "col, offset (défaut 1), default (nul)"],
  ["Cumul", "cumsum, cumcount, cummin, cummax", "col (facultatif pour cumcount)"],
  ["Partition entière", "sum, mean, min, max, count, first, last", "col"]],
  [10, 110, 330])),
P("Les fonctions de rang, de décalage et de cumul exigent order_by. Les valeurs nulles sont triées en dernier, même en desc ; les égalités gardent l'ordre d'entrée. Un cumul saute les valeurs nulles (la ligne garde le cumul atteint). Les fonctions de partition ignorent les nulls, comme aggregate ; first et last rendent la première et la dernière valeur non nulle dans l'ordre order_by. cumsum, cummin, cummax, sum et mean exigent une colonne numérique."),
("h3", "Combinaison (une seconde source déclarée dans sources.yaml)"),
("code", '''join : jointure.
- join:
    right: customers
    key: customer_id          # ou left_key / right_key
    how: left                 # inner | left | right | outer | cross
merge : fusion/mise à jour.
- merge: { right: corrections, key: id, delete_unmatched: false }
union : empilement.
- union: { right: orders_archive, distinct: true }'''),
("h3", "Jointure croisée : chaque ligne × chaque ligne" + NEW),
("code", '''- join:
    right: calendar
    how: cross                # ni key, ni left_key, ni right_key
    max_rows: 5000000         # défaut 10 000 000 lignes produites'''),
R("associe chaque ligne à chaque ligne de right (ordre de gauche, puis de droite). Le run s'arrête avant de produire le lot qui dépasserait max_rows."),
("h3", "Restructuration"),
("code", '''pivot : lignes en colonnes.
- pivot: { index: [country], column: month, values: amount, aggfunc: sum }
unpivot : colonnes en lignes.
- unpivot: { id_vars: [id], value_vars: [jan, feb], var_name: month, value_name: amount }
transpose : inverse lignes et colonnes.
- transpose: { index_col: id, header_name: column }
engine : moteur de calcul (racine de transformations.yaml)
engine: duckdb   # auto (défaut) | pandas | duckdb'''),
R("auto choisit DuckDB au-delà de 2 000 000 de lignes pour les opérations globales (aggregate, sort, join right/outer, window). HYDRA_ENGINE l'emporte sur le fichier."),
("h3", "Expressions (expr, when)"),
P("Opérateurs de comparaison, logiques (and, or, not) et arithmétiques ; évaluation sûre, sans code arbitraire."),

("h1", "3. Actions"),
("h3", "Une action est une étape type: action. Structure commune :"),
("code", '''- name: mon_etape
  type: action
  action: <nom>
  params: { ... }
  undo: { ... }      # requis pour webhook, email, bash, powershell, ssh, python'''),
("h3", "log : écrit un message"),
("code", '''action: log
params: { message: "Chargement terminé" }   # défaut : "Step '<name>' executed"'''),
R("tracer la progression."),
("h3", "delay : attend"),
("code", '''action: delay
params: { seconds: 30 }   # ou duration'''),
R("laisser un système se stabiliser entre deux étapes."),
("h3", "condition : évalue une condition et stocke le résultat"),
("code", '''action: condition
params:
  name: is_big                      # paramètre qui reçoit le résultat
  mode: expr                        # expr | structured
  expr: "{{ param:rows }} > 1000"
  # structured : left / op / right'''),
R("alimenter les when des étapes suivantes."),
("h3", "webhook : appel HTTP"),
("code", '''action: webhook
params:
  url: https://hooks.example.com/notify
  method: POST                      # défaut POST
  headers: { Authorization: "Bearer ${SECRET:api.token}" }
  body: { status: done }            # mapping (JSON) ou texte
undo:
  action: webhook
  params: { url: https://hooks.example.com/cancel }'''),
R("notifier ou déclencher un système externe."),
("h3", "email : envoie un e-mail"),
("code", '''action: email
params:
  to: ops@example.com
  subject: "Rapport prêt"
  body: "Voir pièce jointe"
  from_addr: hydra@example.com      # défaut hydra@localhost
  smtp_host: smtp.example.com       # défaut localhost
  smtp_port: 587                    # défaut 1025
  username: etl
  password: ${SECRET:smtp.password}
  use_tls: true                     # STARTTLS
undo: none'''),
R("alerter les personnes concernées."),
("h3", "bash : commande shell"),
("code", '''action: bash
params:
  command: "./scripts/archive.sh"
  working_dir: ./scripts            # défaut dossier courant
  timeout: 60                       # secondes, défaut 60
undo: { action: bash, params: { command: "./scripts/restore.sh" } }'''),
R("exécuter un traitement système (Linux/macOS)."),
("h3", "powershell : commande PowerShell"),
("code", '''action: powershell
params: { command: "Copy-Item a.csv b.csv", timeout: 60 }
undo: { action: powershell, params: { command: "Remove-Item b.csv" } }'''),
R("équivalent de bash sous Windows."),
("h3", "ssh : commande distante"),
("code", '''action: ssh
params:
  host: srv1.example.com
  username: etl
  command: "systemctl restart app"
  port: 22                          # défaut 22
  key_path: ~/.ssh/id_ed25519       # utilisé en premier
  password: ${SECRET:ssh.password}  # si pas de clé
  timeout: 30
undo: none'''),
R("piloter un serveur distant."),
("h3", "python : code Python"),
("code", '''action: python
params:
  script: |                         # code en ligne, ou file_path: job.py
    print("bonjour")
  working_dir: .
  timeout: 60
undo: none'''),
R("logique spécifique que le DSL ne couvre pas."),
("h3", "set_param : crée un paramètre pour la suite du run"),
("code", '''action: set_param
params: { name: batch_label, value: "nightly", type: str }   # échoue si déjà défini'''),
R("partager une valeur entre étapes ({{ param:batch_label }})."),
("h3", "assign_param : modifie un paramètre existant"),
("code", '''action: assign_param
params: { name: batch_label, value: "partial" }   # échoue s'il n'existe pas'''),
R("mettre à jour une valeur en cours de run."),
("pagebreak", None),
] + content_fr.SPEC

HEADER, FOOTER = content_fr.HEADER, content_fr.FOOTER
