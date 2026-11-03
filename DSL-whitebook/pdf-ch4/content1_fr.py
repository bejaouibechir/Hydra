"""Pages 3 à la fin (FR) : 1. Workflows (dont 1.4 Sous-projets, 0.19), 2.1, 2.2 ;
la suite vient de content2_fr (fin 2.2 → 3) puis content_fr (4)."""
from xml.sax.saxutils import escape as e
import content2_fr
R = lambda t: ("role", "Rôle. " + e(t))
P = lambda t: ("p", e(t))
NEW = " (Hydra 0.19.0+)"

CH1 = [
("h1", "1. Workflows"),
P("Fichiers : workflows/<nom>.yaml et workflows/thread.yaml."),
("h2", "1.1 Le workflow"),
("h3", "version : version du format DSL"),
("code", 'version: "1.0"      # toujours "1.0" aujourd\'hui'),
R("permet au moteur de valider le fichier avec la bonne grammaire."),
("h3", "workflow : racine d'un workflow"),
("code", '''workflow:           # tout le contenu du workflow est sous cette clé
  name: daily_sales'''),
R("déclare un enchaînement d'étapes (jobs, actions et projets)."),
("h3", "name : nom du workflow (obligatoire)"),
("code", '''workflow:
  name: daily_sales     # identifiant affiché dans les logs et le fichier undo'''),
R("identifie le workflow ; sert aussi de nom pour hdrctl workflow undo."),
("h3", "description : texte libre"),
("code", 'description: "Charge les ventes du jour"'),
R("documentation uniquement, sans effet à l'exécution."),
("h3", "trigger : déclencheur (défaut manual)"),
("code", "trigger: manual        # manual | schedule | webhook"),
R("indique quand le workflow démarre."),
("h3", "cron : planification (obligatoire avec trigger: schedule)"),
("code", '''trigger: schedule
cron: "0 6 * * *"      # tous les jours à 06:00'''),
R("expression cron à 5 champs donnant l'heure de démarrage."),
("h3", "rollback : annulation en cas d'échec (défaut false)"),
("code", "rollback: true        # si une étape échoue, les étapes déjà faites sont annulées"),
R("déclenche les undo des étapes terminées, dans l'ordre inverse."),
("h3", "steps : liste des étapes (obligatoire)"),
("code", '''steps:
  - name: load
    type: job
    job: ../jobs/orders'''),
R("contient les étapes exécutées par le workflow."),

("h2", "1.2 L'étape (step)"),
("h3", "name : nom unique de l'étape (obligatoire)"),
("code", "- name: load_orders     # sert de référence dans depends_on"),
R("identifie l'étape et permet aux autres de dépendre d'elle."),
("h3", "type : nature de l'étape (obligatoire)"),
("code", "type: job             # job | action | project"),
R("indique si l'étape exécute un job, une action ou un autre projet (section 1.4)."),
("h3", "job : chemin du job (avec type: job)"),
("code", '''type: job
job: ../jobs/orders     # dossier contenant sources/destinations/pipeline'''),
R("désigne le dossier du job à lancer."),
("h3", "action : nom de l'action (avec type: action)"),
("code", '''type: action
action: log             # une des 11 actions (voir section 3)'''),
R("choisit l'action à exécuter."),
("h3", "params : paramètres de l'action"),
("code", '''action: log
params:
  message: "Début du chargement"'''),
R("fournit les entrées de l'action ; accepte {{ param: }} et ${SECRET:}. Avec type: project : les paramètres passés au projet appelé."),
("h3", "depends_on : étapes à attendre (défaut [])"),
("code", '''- name: publish
  depends_on: [load, clean]     # démarre quand load ET clean sont finies'''),
R("construit le graphe d'exécution ; les étapes sans dépendance commune tournent en parallèle."),
("h3", "on_failure : comportement en cas d'échec (défaut fail)"),
("code", "on_failure: continue     # fail | skip | continue"),
R("fail arrête le workflow ; skip ignore les étapes dépendantes ; continue les exécute quand même."),
("h3", "enabled : active ou désactive l'étape (défaut true)"),
("code", "enabled: false    # l'étape est sautée sans être supprimée"),
R("désactiver temporairement une étape."),
("h3", "when : condition d'exécution"),
("code", 'when: "{{ param:publish_enabled }} == True"     # exécutée seulement si vrai'),
R("exécute l'étape selon une expression sûre (paramètres, résultat d'une étape)."),
("h3", "retry : politique de nouvelle tentative"),
("code", '''retry:
  max: 3               # tentatives après le premier échec
  delay: 10            # secondes d'attente
  backoff: exponential     # fixed | exponential (délai doublé)'''),
R("absorbe les pannes passagères (réseau, base indisponible)."),
("h3", "undo : comment annuler l'action"),
("code", '''type: action
action: bash
params: { command: "touch /tmp/flag" }
undo:
  action: bash
  params: { command: "rm /tmp/flag" }      # exécuté si rollback: true'''),
R("obligatoire pour webhook, email, bash, powershell, ssh, python (ou undo: none). Un job s'annule tout seul ; une étape project ne s'annule pas : rollback: true la refuse."),

("h2", "1.3 Le thread"),
("h3", "thread : racine de thread.yaml"),
("code", '''thread:              # liste d'étapes (stages)
  - mode: sequential
    workflows:
      - name: load_referentials'''),
R("fixe l'ordre d'exécution de tous les workflows du projet (hdrctl run .)."),
("h3", "mode : exécution d'un stage (défaut sequential)"),
("code", "mode: parallel       # sequential | parallel"),
R("les workflows du stage tournent l'un après l'autre ou en même temps."),
("h3", "delay_after : pause après le stage"),
("code", "delay_after: 5m      # attente avant le stage suivant"),
R("laisse le temps à un système externe de se stabiliser."),
("h3", "workflows : workflows du stage (au moins un)"),
("code", '''workflows:
  - name: load_sales
  - name: load_stock'''),
R("liste ce que le stage exécute (workflows/<name>.yaml)."),
("h3", "active : active ou saute un workflow (défaut true)"),
("code", '''- name: load_stock
  active: false'''),
R("mise de côté sans modifier le fichier du workflow."),
("h3", "delay_before : attente avant le démarrage"),
("code", '''- name: build_reports
  delay_before: 30s'''),
R("décaler le démarrage d'un workflow."),
("h3", "timeout : durée maximale"),
("code", '''- name: load_sales
  timeout: 20m          # dépassé = échec'''),
R("empêche un workflow de bloquer le thread."),
("h3", "fallback : workflow de remplacement"),
("code", '''- name: load_sales
  fallback:
    use: [load_sales_backup]           # workflows essayés dans l'ordre
    when: "not source_available('crm')"
    on_failure: true                   # remplace aussi après un échec
    on_probe_error: keep               # keep | replace si la condition est invérifiable'''),
R("bascule vers un plan B quand la condition est vraie."),
("h3", "use / when / on_failure / on_probe_error : clés de fallback"),
P("Voir ci-dessus. Rôle : use liste les remplaçants, when décide de la bascule avant le démarrage, on_failure l'étend aux échecs, on_probe_error gère le cas où la condition ne peut pas être évaluée."),
("h3", "loops : rejouer une partie du thread"),
("code", '''loops:
  - from: load_stock         # dernier workflow de la partie
    to: load_sales           # premier workflow de la partie
    times: 3                 # nombre total d'exécutions (1 à 1000)
    delay: 10m               # pause avant chaque rejeu'''),
R("répète une séquence (polling, traitements par vagues)."),
("h3", "Fonctions des conditions de when (fallback)"),
("table", ([["Fonction", "Rôle"],
            ["source_available('id')", "la source répond"],
            ["destination_available('id')", "la destination répond"],
            ["file_exists('path')", "le fichier existe"],
            ["file_size('path')", "taille, comparée à 10KB, 5MB, 1GB"],
            ["file_age('path')", "ancienneté, comparée à 30s, 5m, 24h, 7d"],
            ["url_ok('url')", "réponse HTTP 2xx/3xx"],
            ["secret_defined('NAME')", "le secret existe"],
            ["db.load('id')", "requêtes actives sur la base"],
            ["previous.status", "success · failed · skipped · inactive · none"],
            ["previous.rows", "lignes écrites par le workflow précédent"]], [10, 200])),
("h3", "Exemple"),
("code", '''fallback:
  use: [load_sales_light]
  when: "db.load('dwh') > 50 or file_size('in/orders.csv') > 1GB"'''),

("h2", "1.4 Sous-projets : type: project" + NEW),
P("Une étape de type project lance un autre projet Hydra : son thread.yaml, ou seulement les workflows listés. Le projet appelant est le maître ; les projets appelés sont ses sous-projets. Rien n'est transmis implicitement, sauf l'environnement."),
("h3", "project : le projet appelé (obligatoire avec type: project)"),
("code", '''- name: crm_sync
  type: project
  project: ../crm_sync      # dossier, relatif à la racine du maître'''),
R("désigne le projet à lancer. Dans Hydra Studio, glisser un projet depuis la section Projects de la palette : l'étape est créée après contrôle des cycles."),
("h3", "ref : lecture de project (défaut path)"),
("code", '''ref: path      # path : dossier, portable avec git (défaut)
ref: name      # name : nom du projet dans le workspace Studio'''),
R("choisit entre un chemin versionné dans le dépôt et un nom du workspace."),
("h3", "env : environnement du projet appelé (défaut inherit)"),
("code", "env: inherit   # inherit | none | <nom d'environnement>, ex. prod"),
R("inherit applique le nom d'environnement du maître avec les propres environments/<env>.yaml, variables env.<env> et secrets.<env> du projet appelé ; none lance sans environnement."),
("h3", "params : paramètres passés au projet appelé"),
("code", '''params:
  batch_date: "{{ param:run_date }}"   # même rang que -P batch_date=...'''),
R("donne une valeur aux paramètres du projet appelé. Un paramètre required sans valeur arrête l'étape avant tout lancement."),
("h3", "variables : variables d'environnement prêtées pour ce run"),
("code", '''variables:
  EXPORT_DIR: out/crm       # visible seulement dans le projet appelé'''),
R("prête des variables le temps du run ; les variables du maître, son .env et --env-file ne sont pas transmis."),
("h3", "Les secrets ne se transmettent pas"),
("code", '''variables:
  DB_PASSWORD: "${SECRET:crm_db}"   # refusé : chaque projet garde ses secrets'''),
R("un ${SECRET:...} dans params ou variables est refusé à la validation : le projet appelé lit son propre .hydra/secrets."),
("h3", "workflows : workflows à lancer (défaut : le thread.yaml)"),
("code", "workflows: [ingest, report]     # lancés l'un après l'autre"),
R("lance une partie du projet appelé au lieu de tout son thread."),
("h3", "outputs : paramètres relus par le maître"),
("code", '''outputs: [last_batch]
# étapes suivantes : {{ project:crm_sync.param.last_batch }}'''),
R("liste des paramètres du projet appelé (set_param, assign_param ou déclarés) à relire à la fin de son run. Un output listé mais non publié fait échouer l'étape."),
("h3", "isolation : où tourne le projet (défaut inprocess)"),
("code", "isolation: inprocess    # inprocess | subprocess"),
R("inprocess tourne dans le même processus avec un environnement isolé puis restauré ; subprocess lance un hdrctl séparé. Les étapes en parallèle passent toujours en subprocess."),
("h3", "timeout : durée maximale"),
("code", "timeout: 10m        # 30s, 5m, 1h ou un nombre de secondes"),
R("arrête le projet appelé au dépassement ; l'étape échoue."),
("h3", "overlap : projet déjà en cours (défaut wait)"),
("code", "overlap: wait      # wait | skip | fail"),
R("un projet tourne une seule fois à la fois (.hydra/run.lock) : wait attend la fin (jusqu'au timeout), skip saute l'étape, fail la fait échouer."),
("h3", "Résultats du projet appelé"),
("table", ([["Référence", "Valeur"],
            ["{{ project:STEP.status }}", "success · failed · skipped"],
            ["{{ project:STEP.rows }}", "lignes écrites par le projet appelé"],
            ["{{ project:STEP.duration }}", "durée en secondes"],
            ["{{ project:STEP.param.NAME }}", "un paramètre listé dans outputs"]], [10, 200])),
("code", '''- name: report
  type: action
  action: log
  when: "{{ project:crm_sync.status }} == 'success'"
  params: { message: "{{ project:crm_sync.rows }} lignes synchronisées" }
  depends_on: [crm_sync]'''),
R("permet aux étapes suivantes du maître de réagir au projet appelé."),
("h3", "Cycles et profondeur"),
("code", '''hdrctl workflow validate main     # affiche l'arbre des projets appelés
#   ↳ crm_sync [ingest, report]
#      ↳ billing
# cycle: master → crm_sync → master   -> refusé'''),
R("un projet ne peut pas s'appeler lui-même, directement ou via d'autres ; plus de 5 niveaux est refusé. Contrôlé par hdrctl run, workflow validate, Studio et l'outil MCP hydra_project_calls ; un projet calculé avec {{ }} est contrôlé à l'exécution."),
("h3", "hdrctl run -w : lancer seulement certains workflows"),
("code", "hdrctl run ../crm_sync -w ingest -w report --env prod"),
R("lance les workflows listés d'un projet, dans l'ordre, depuis la ligne de commande."),

("h2", "1.5 Déclencheurs de projet : triggers.yaml" + NEW),
P("triggers.yaml, à la racine d'un projet, lance le projet entier (son thread.yaml, ou les workflows listés) quand un événement survient. Le trigger: d'un workflow lance un workflow ; un déclencheur de projet lance le projet. Ils tournent dans hdrctl watch et hdrctl serve."),
("h3", "triggers, name, type"),
("code", '''version: "1.0"
triggers:
  - name: nightly         # nom unique
    type: cron            # cron | interval | file | marker | source_change | webhook | after_project'''),
R("liste les déclencheurs ; type choisit l'événement et ses clés (une clé d'un autre type est refusée)."),
("h3", "cron, timezone : à heure fixe"),
("code", '''type: cron
cron: "0 2 * * *"         # minute heure jour mois jour-semaine ; */15, mon-fri, jan…
timezone: Europe/Paris    # défaut : l'heure de la machine'''),
R("lance le projet quand l'heure correspond. Les échéances manquées pendant un arrêt ne sont pas rejouées."),
("h3", "every : intervalle"),
("code", '''type: interval
every: 15m                # 30s, 5m, 1h ou secondes'''),
R("lance le projet à intervalle régulier."),
("h3", "path, events, debounce : un fichier arrive"),
("code", '''type: file
path: inbox/*.csv         # dans le projet ; ** pour les sous-dossiers
events: [added, modified] # défaut [added]
debounce: 2s              # inchangé ce temps avant d'être pris (défaut 2s)
every: 5s                 # fréquence de lecture du dossier (défaut 5s)'''),
R("lance le projet pour les fichiers nouveaux ou modifiés ; des fichiers arrivés ensemble donnent un seul run, qui reçoit {{ param:trigger.file }} et {{ param:trigger.files }}."),
("h3", "marker, consume : un fichier témoin apparaît"),
("code", '''type: marker
path: inbox/READY
consume: true             # retiré avant le run (défaut) ; false le garde'''),
R("lance le projet quand un autre système signale que les données sont prêtes."),
("h3", "source : une source change"),
("code", '''type: source_change
source: {job: jobs/ingest, id: orders, check: count}   # count | max (+ column) | checksum
every: 1m                 # défaut 1m'''),
R("mesure une source d'un job (construite comme au run) ; la première mesure sert de référence, une mesure différente lance le projet avec {{ param:trigger.value }} et {{ param:trigger.previous }}."),
("h3", "token : webhook"),
("code", '''type: webhook
token: ${SECRET:trigger.on_push.token}   # une référence de secret uniquement
# hdrctl trigger token on_push  → crée la valeur, affichée une fois
# POST /api/projects/<id>/triggers/on_push/webhook   X-Hydra-Token: <jeton>'''),
R("permet à un autre système de lancer le projet via hdrctl serve ; un mauvais jeton reçoit 401 et rien de la requête n'atteint le projet."),
("h3", "project, on : après un autre projet"),
("code", '''type: after_project
project: ../crm           # ref: path (défaut) ou ref: name
on: success               # success | failure | any'''),
R("lance le projet quand un autre se termine, quel que soit son lanceur ; le run reçoit {{ param:trigger.project }} et {{ param:trigger.status }}. Une boucle a → b → a est refusée."),
("h3", "env, workflows, params, overlap, timeout, retry, enabled"),
("code", '''env: prod                 # défaut : --env / HYDRA_ENV de watch ou serve
workflows: [ingest]       # défaut : thread.yaml
params: {mode: full}      # comme -P ; pas de secret
overlap: skip             # skip (défaut) | wait | fail
timeout: 1h
retry: {max: 2, delay: 5m}
enabled: false'''),
R("règlent ce qui est lancé et comment ; le projet tourne toujours dans son propre processus, sous .hydra/run.lock, et chaque run est noté dans .hydra/triggers/history.jsonl."),
("h3", "hdrctl trigger, hdrctl watch"),
("code", '''hdrctl trigger validate        # clés, cron, workflows, sources, secrets, boucles
hdrctl trigger list            # déclencheurs et dernier run
hdrctl trigger fire nightly    # en lancer un maintenant
hdrctl trigger history
hdrctl watch --env prod        # faire tourner les déclencheurs jusqu'à Ctrl+C'''),
R("hdrctl watch fait tourner les déclencheurs sans Studio ; hdrctl serve fait tourner le même moteur pour les projets de la liste Studio."),
]

CH2 = [
("pagebreak", None),
("h1", "2. Jobs"),
P("Dossier : jobs/<nom>/ avec sources.yaml, destinations.yaml, pipeline.yaml, transformations.yaml (optionnel)."),
("h2", "2.1 Sources (sources.yaml)"),
("h3", "sources : racine"),
("code", '''version: "1.0"
sources:
  orders:               # "orders" est l'id de la source
    type: csv'''),
R("déclare au moins une source, référencée ensuite par son id."),
("h3", "type : connecteur (obligatoire)"),
("code", "type: postgresql   # csv, json, parquet, mysql/mariadb, postgresql/postgres, sqlserver/mssql, mongodb"),
R("choisit le connecteur de lecture ; insensible à la casse."),
("h3", "connection : paramètres de connexion"),
("code", '''connection:
  host: db.local
  port: 5432
  user: etl
  password: ${SECRET:db.password}         # jamais en clair
  database: sales'''),
R("indique comment joindre la source ({} pour un fichier local). Clés SQL : host, port, user, password, database, schema ; SQL Server : instance, tds_version, login_timeout, timeout."),
("h3", "extract : quoi lire (obligatoire)"),
("code", '''extract:
  table: orders.csv           # fichier, table, ou...
  batch_size: 5000            # lignes par lot (défaut 10000, minimum 10)'''),
R("définit la lecture ; doit contenir table, query ou collection."),
("h3", "table / query / collection"),
("code", '''extract: { table: public.orders }                          # table ou fichier
extract: { query: "SELECT * FROM orders WHERE total>0" }   # SQL uniquement
extract: { collection: orders }                            # MongoDB'''),
R("désigne l'objet lu."),
("h3", "filter et limit : MongoDB"),
("code", '''extract:
  collection: orders
  filter: { status: "paid" }        # filtre de requête
  limit: 1000                       # nombre maximal de documents'''),
R("restreint la lecture côté base."),
("h3", "Options CSV (dans connection)"),
("code", '''connection:
  base_path: ./data      # dossier de résolution de table (défaut : dossier du job)
  delimiter: ";"         # défaut ,
  quotechar: '"'
  encoding: utf-8
  lineterminator: "\\n"
  strict_schema: false'''),
R("adapter la lecture à la forme du fichier."),
("h3", "schema : structure attendue (MongoDB)"),
("code", '''schema:
  mode: infer_strict             # auto | manual | infer_strict | hybrid
  drift_policy: warn             # fail | warn | ignore | adapt
  validation_policy: strict      # strict | best_effort | permissive
  sample_size: 100               # documents échantillonnés
  fields:
    - name: total
      type: float                # string, integer, float, decimal, boolean, date,
                                 # datetime, array, object, json
      path: amount.total
      required: true
      default: 0
      array_handling: flatten    # keep | flatten | explode | json
      description: "Montant"'''),
R("fixe la forme des documents et la réaction face à un champ nouveau (dérive)."),
("h2", "2.2 Destinations (destinations.yaml)"),
("h3", "destinations : racine"),
("code", '''destinations:
  dwh_orders:            # id de la destination
    type: postgresql'''),
R("déclare où écrire."),
("h3", "table / collection : cible"),
("code", "load: { table: dwh.orders }      # collection est un alias pour MongoDB"),
R("table ou fichier de destination (obligatoire)."),
("h3", "mode : mode d'écriture (défaut append)"),
("code", '''load:
  mode: upsert        # append | replace | upsert
  key: [order_id]     # obligatoire avec upsert'''),
R("append ajoute, replace vide puis écrit, upsert met à jour ou insère selon la clé."),
("h3", "key : colonnes clés"),
]

SPEC = CH1 + CH2 + list(content2_fr.SPEC)
HEADER = content2_fr.HEADER
def _breaks(spec):
    """Chaque chapitre (h1) commence sur une nouvelle page."""
    out = []
    for item in spec:
        if item[0] == "h1" and out and out[-1][0] != "pagebreak":
            out.append(("pagebreak", None))
        out.append(item)
    return out


SPEC = _breaks(SPEC)
FOOTER = "hydraetl.com  ·  Hydra DSL v1.0  ·  Hydra 0.19.0"
