# Journal du projet Hydra-promo

> **Ce fichier est la mémoire du projet.** Il permet de reprendre le travail avec n'importe quel assistant (Claude, GPT, Grok, un modèle local…) sans repartir de zéro.
> **Règle : à la fin de chaque session, ajouter une entrée datée** — ce qui a été fait, ce qui a été décidé, ce qui a été appris, ce qui reste ouvert.
> Ordre : le plus récent en haut.

---

## Comment reprendre le travail (à lire en premier)

1. Lire `CLAUDE.md` — produit, positionnement, règles, feuille de route, objectifs chiffrés.
2. Lire ce journal, au moins les deux dernières entrées.
3. Lire `suivi/actions-bechir.md` — ce que Bechir doit faire maintenant.
4. Vérifier l'état réel avant d'agir (rien n'est supposé) :
   - GitHub : `https://api.github.com/repos/bejaouibechir/Hydra` (étoiles, forks), PR ouvertes, Actions
   - PyPI : `https://pypi.org/pypi/hydra-etl/json` (version publiée)
   - Site : https://hydraetl.com et https://hydraetl.com/blog
5. Ne jamais publier, pousser ou soumettre à la place de Bechir. Produire le texte, il agit.

### Carte des fichiers

| Dossier | Contenu |
|---|---|
| `CLAUDE.md` | Contexte, règles, positionnement, feuille de route, objectifs |
| `suivi/journal.md` | Ce fichier : l'historique daté |
| `suivi/actions-bechir.md` | La file d'actions de Bechir, mise à jour en continu |
| `contenus/articles/` | Articles (version site + version dev.to + captures) |
| `contenus/posts/` | Posts LinkedIn |
| `contenus/annuaires/` | Listes awesome (PR) et fiches annuaires |
| `contenus/mcp/` | Définitions anglaises des tools du serveur MCP (référence Glama) |
| `contenus/github/` | Tickets « good first issue », traitement des PR externes |
| `contenus/pages/` | Textes des pages du site (licence, validation) |
| `contenus/pilotes/` | Kit de recrutement des utilisateurs pilotes |
| `contenus/lancement/` | Brouillon Show HN |
| `ressources/` | Protocole de benchmark, patchs |
| `divers/` | Avis externes (ChatGPT) |

### Dépôts et accès

| Quoi | Où |
|---|---|
| Produit | `C:\Users\DELL\Desktop\Hydra` → github.com/bejaouibechir/Hydra |
| Site (Astro) | `C:\Users\DELL\Desktop\hydra-site` → github.com/bejaouibechir/bejaouibechir.github.io |
| Promo | `C:\Users\DELL\Desktop\Hydra-promo` |
| Paquet | pypi.org/project/hydra-etl/ |
| Audience | cloud.umami.is (site id `32e25563-c8f5-439f-9503-324694899add`) |

---

## 27 septembre 2026 (suite) — hydra-demo en ligne, valide dans un vrai Codespace

### Resultat

Le depot `hydra-demo` est publie et **le parcours complet a ete joue dans un Codespace** : workflow 5 steps sur 5,
Studio qui ouvre le projet, le workflow visible, et l'editeur qui affiche le graphe (`src_csv -> dst_mysql`,
2 nodes, 1 edge, Valid) avec les deux jobs en onglets.

### Trois corrections qu'il a fallu trouver en testant

1. **`docker-in-docker` echouait a s'installer.** Remplace par un devcontainer **service d'un docker-compose** : le
   conteneur de travail et MySQL sont deux services d'un meme reseau, plus aucun moteur de conteneur a installer.
   Au passage, une voie intermediaire a ete ecartee : `docker-outside-of-docker` aurait laisse les conteneurs sur
   l'hote, injoignables en `127.0.0.1` depuis le devcontainer.
2. **`onAutoForward: openPreview`** ouvrait Studio dans le Simple Browser de VS Code — une iframe que GitHub refuse
   d'afficher. Passe a `openBrowser`.
3. **`Import workflow` ouvre l'explorateur de la machine locale**, pas celui du Codespace : inutilisable la-bas.
   Le workflow est donc declare dans `.hydra/workflows/nightly-report.json`.

### Verifie avant livraison (et pas suppose)

Le fichier de metadonnees a ete teste contre l'API reelle avant d'etre livre : `GET /api/workflows?project_id=...`
le liste, et `GET /api/workflows/<id>?project_id=...` lit bien le YAML (926 caracteres). **Le `path` relatif
fonctionne** — contrairement a l'exemple du depot qui stocke un chemin absolu Windows. Et `layout: null` suffit :
Studio dispose le graphe tout seul.

### Ce que la demo a revele sur le produit

Quatre remontees, toutes trouvees en **utilisant** Hydra comme le ferait un inconnu :

| Trouve | Etat |
|---|---|
| `${SECRET:}` ne resolvait jamais, alors que le README l'annonce | corrige, publie en 0.11.3 |
| Regenerer les schemas DSL est une etape obligatoire apres chaque bump | identifie, CI verte |
| Un projet dont le dossier ne porte pas le nom de son id est visible mais inouvrable | contourne, a corriger |
| Studio ne decouvre pas les workflows YAML poses a plat | contourne, a corriger |

**Les deux derniers ont la meme racine** : la CLI lit le systeme de fichiers, Studio lit ses propres metadonnees.
Des qu'un projet circule — un clone, un tutoriel, le projet d'un collegue — les deux divergent : la CLI marche et
Studio parait casse. Pour un produit qui cherche ses premiers adoptants, c'est la dette la plus couteuse des quatre,
parce qu'elle frappe au premier contact.

### Lecon de methode

La demo a servi deux fois : comme vitrine, et comme **premier utilisateur reel**. Aucune de ces quatre remontees
n'etait visible en relisant le code ; toutes sont apparues en parcourant le produit de bout en bout.

---

## 27 septembre 2026 (suite) — depot de demo Codespaces construit et teste

### Decide

Le devcontainer vit dans un **depot `hydra-demo` separe**, pas dans Hydra. Raison : le badge ouvre ce que l'essayeur
verra, et 200 fichiers de code Python ne sont pas une demo. Le badge reste dans le README de Hydra, la ou le trafic
arrive, mais pointe vers le depot lisible. J'avais d'abord propose l'inverse ; l'arbitrage a ete revu.

### Fait

`contenus/codespaces/hydra-demo/` — 22 fichiers, tout verifie en executant :

- workflow `nightly-report` : **5 steps sur 5 OK** — action bash, job CSV→MySQL, job MySQL→CSV, action python
  appelant `scripts/summarise.py`, action bash finale en `on_failure: continue` ;
- deux jobs parametres : dev (170 lignes) et prod (104 lignes) depuis le meme manifeste ;
- Studio : `hdrctl serve` repond `{"status":"ok","studio":"bundled"}` et sert le HTML ;
- secrets via `${SECRET:mysql.user}` — ce qui **revalide le correctif 0.11.3 dans un vrai projet**.

### Appris sur le produit (verifie en executant, pas suppose)

- Le manifeste workflow attend `version` + `workflow:` au premier niveau ; le modele `WorkflowDef` est la structure
  interne, pas le format du fichier.
- `sort` prend `by:`, pas `columns:`.
- **Trois regles de chemin differentes dans un meme workflow** : `job:` et `file_path:` sont relatifs au dossier du
  workflow, alors que le cwd d'execution des actions est la racine du projet. Deroutant — dette a noter.
- `working_dir: ..` remonte depuis le cwd du processus, pas depuis le fichier.
- Le connecteur MySQL **ne cree pas la table** : il faut un `init.sql` monte dans le conteneur.

### Reste ouvert

Creer le depot et ouvrir un Codespace : le `postCreateCommand` est le seul element non testable ici (pas de daemon
Docker dans le conteneur cloud).

---

## 27 septembre 2026 (suite) — dette `${SECRET:}` corrigee

### Le probleme, plus grave qu'annonce

La note prise pendant le labo disait « `${SECRET:x}` est inerte ». Verification faite dans le code : il n'est pas
inerte, il **leve une erreur explicite**, et l'erreur n'est pas avalee. Mais surtout, ce que la note ne disait pas :
**le README annonce `${SECRET:}` en page d'accueil** (lignes 53 et 217) et `docs/6.DSL Hydra.md` le montre en exemple
(`password: ${SECRET:DB_PASSWORD}`). C'etait donc une promesse publique qu'aucun utilisateur ne pouvait tenir.

Un seul point d'instanciation en cause : `executor.py:106`, `SecretResolver(secrets={})`.

### Le correctif

Une seule fonction touchee, `_get_secret` dans `hydra_etl/internal/config/secrets.py`. Ordre de recherche :

1. le mapping `secrets` injecte — inchange, et c'est la porte laissee ouverte pour Vault/AWS/Azure ;
2. la variable d'environnement normalisee (`db.password` -> `DB_PASSWORD`) ;
3. la variable portant exactement le nom de la cle.

Choix assume : **aucun nouveau format de fichier**. Les secrets viennent de l'environnement du processus, ce qui est
la pratique reelle en CI et ce que le labo n°6 enseigne deja. Aucune modification de l'executor, donc surface de
regression minimale.

### Verification

- 10 cas sur 10, dont les **5 de non-regression** qui verrouillent le comportement existant (le test
  `test_missing_secret_raises` continue de passer : `not.found` n'existe ni dans le dict ni dans l'environnement).
- **Preuve de bout en bout** : un vrai job avec `${SECRET:mysql.user}` / `${SECRET:mysql.password}` execute par
  l'executor — echec avant le correctif (`Secret manquant: mysql.user`), succes apres (3 lignes en dev, 5 en prod).
- Le message d'erreur nomme maintenant la variable a definir.

Reste a faire par Bechir : la suite pytest complete, le bump 0.11.3, le tag et la publication PyPI.

### Appris

La note initiale (« inerte ») etait imprecise sur deux points : la severite reelle du comportement, et le fait que la
fonctionnalite etait documentee publiquement. **Une dette se requalifie en lisant le code au moment de la traiter,
pas en relisant la note qui la decrit.**

---

## 27 septembre 2026 — Labo Killercoda n°6 : paramètres et secrets

### Fait

Nouveau labo `contenus/killercoda/07-parameters-and-secrets/` (4 étapes, ~15 min), **testé de bout en bout** avant livraison.

Scénario : deux bases MySQL en Docker sur deux ports (3307 dev / 3308 prod), identifiants et données différents. L'apprenant reçoit un job **volontairement écrit en dur** (port, base, user, mot de passe), le corrige, puis le lance deux fois sans plus y toucher → `destination_dev.csv` (3 lignes) et `destination_prod.csv` (5 lignes).

Étapes : 1. explorer `parameters.yaml`, `environments/`, `secrets/`, `.gitignore` — 2. remplacer les valeurs en dur par `{{ param: }}` et `${ENV:}` — 3. exécuter en dev — 4. exécuter en prod, comparer, et révéler le DSN par un échec volontaire.

Numéroté **06** : c'est le sixième labo publié. Le crontab en attente est passé à `07-replace-crontab`.

### Incident — première version livrée défectueuse

`/root/lab` n'existait pas sur Killercoda : le `setup/background.sh` n'a **jamais été exécuté**. Le script commence par
`set +e`, donc même un échec de Docker, d'apt et de pip aurait laissé `mkdir -p /root/lab` s'exécuter. Cause la plus
probable : le bit exécutable perdu au passage par Windows (`100644` au lieu de `100755` dans git) — un risque qui avait
été signalé à Bechir mais traité comme secondaire (« peu probable, les 5 précédents sont passés ») au lieu d'être
vérifié avant la publication.

**Leçon retenue** : une dépendance que l'on sait fragile se vérifie avant la livraison, elle ne se mentionne pas en note
de bas de page. Le contrôle coûte une commande : `git ls-files -s <dossier> | grep '\.sh$'` doit afficher `100755`.

Durcissements apportés ensuite : fichiers du projet créés **avant** Docker et pip (les étapes 1 et 2 fonctionnent même si
l'installation échoue), `docker run` en arrière-plan, repli sur pip système si le venv échoue, et journalisation
complète dans `/tmp/setup.log`. Parcours rejoué après correction : 4 étapes sur 4 vertes.

### Décidé

**Deux syntaxes, deux rôles, distinction visuelle assumée** — c'est l'axe pédagogique du labo :

| | Paramètres | Secrets |
|---|---|---|
| Syntaxe | `{{ param:x }}` | `${ENV:X}` |
| Source | `environments/<env>.yaml` | variables d'environnement |
| Sélection | `hdrctl run . --env dev` | `set -a; . secrets/dev.env; set +a` |
| Versionné | oui | jamais (`secrets/` dans `.gitignore`) |

Les secrets sont injectés par le shell, pas par un fichier que Hydra lit : c'est ce que font réellement un runner CI ou un gestionnaire de secrets, et cela contourne la dette `SecretResolver(secrets={})` sans la masquer.

### Appris (vérifié sur le moteur, pas supposé)

- `--env` charge **uniquement** `environments/<nom>.yaml`, donc les paramètres. Il ne touche pas aux secrets.
- Un seul `.env` est auto-chargé (racine projet et dossier job) — **il n'existe pas de `.env.dev`** côté CLI. Et les vraies variables d'environnement l'emportent sur lui (`override_os=False`).
- `HYDRA_ENV` est équivalent à `--env`.
- La racine projet est trouvée en remontant l'arborescence (6 niveaux max, arrêt sur `.hydra/` ou `workflows/`) : un job dans `jobs/<nom>/` trouve bien `parameters.yaml` à la racine.
- Le port accepte une chaîne : `int(cfg.get("port", 3306))`.
- **Le driver MySQL requis est `mysql-connector-python`**, pas PyMySQL. Oubli = échec du labo.
- Un run réussi **n'affiche pas le DSN** ; seul un échec le montre — d'où l'échec volontaire en étape 4. Le mot de passe y est masqué (`***`).
- Avec des secrets exportés, `-vv` affiche « No .env file found ». C'est normal et c'est même le but : le labo en fait une leçon plutôt qu'une confusion.

### Dettes relevées (à traiter plus tard)

- `hdrctl test` n'accepte pas `--env` alors que `hdrctl run` oui — incohérence CLI.
- Les exemples officiels `examples/mysql_demos/*` utilisent `batch_size: 100`, qui déclenche désormais un avertissement de performance du moteur (« mettez au moins 1000 »). Les exemples livrés contredisent l'avertissement du produit.
- Rappel : `${SECRET:x}` reste inerte (`SecretResolver(secrets={})`) — dette déjà consignée dans `CLAUDE.md`.

### Reste ouvert

Publication du labo sur Killercoda par Bechir, puis intégration des liens labos dans hydraetl.com (point 4 de la feuille de route).

---

## 26 septembre 2026 (suite) — Killercoda : le lab crontab retiré, 5 scénarios de découverte CLI publiés

- Décision de Bechir : abandonner l'arc « cas d'usage » (crontab, etc.) pour prioriser des scénarios qui couvrent
  la découverte de `hdrctl` lui-même — cohérent avec l'audience Killercoda (devops/terminal) et l'ICP « consultants
  qui utilisent `hdrctl` au quotidien ».
- Bechir a fourni la spécification des 5 scénarios (verbatim dans le fil de discussion) : installation + flags +
  `init` (job & workflow) + `list` ; `validate` vs `run` sur un job invalide ; `test` vs `validate` ; `serve` + `curl` ;
  namespace `workflow` vs namespace racine.
- `hdrctl clear` : vérifié dans le code (`hydra_etl/cli/hdrctl.py`) — se contente d'effacer le terminal. Trop trivial
  pour un scénario dédié, écarté d'un commun accord.
- **Chaque scénario a été vérifié contre le code source de `Hydra`** (pas d'affirmation non vérifiée) : lecture de
  `hdrctl.py` (`cmd_run`, `cmd_validate`, `cmd_test`, `cmd_list`/`find_jobs`, `cmd_workflow_*`, `cmd_serve`), de
  `internal/runner/executor.py` (résolution `pipeline.from`/`to`, résolution `${ENV:...}`, gestion des exceptions),
  de `internal/config/secrets.py` (`SecretResolutionError`), de `api/routers/jobs.py` et `api/routers/health.py`
  (les endpoints `/api/jobs/*` encapsulent `hdrctl` en sous-processus et renvoient son stdout/stderr/returncode tels quels),
  et des fichiers de traduction `cli/locales/en.json` pour citer les messages exacts affichés à l'écran.
- **Décision confirmée par Bechir** (question posée) : retirer complètement le lab crontab plutôt que le garder à côté
  des 5 nouveaux. Déplacé (pas supprimé) vers `contenus/killercoda-archive/01-replace-crontab/`.
- **5 scénarios écrits** dans `contenus/killercoda/`, structure identique au lab crontab (`index.json`, `intro.md`,
  `setup/background.sh` + `foreground.sh`, `stepN/text.md` + `verify.sh`, `finish.md`) :
  1. `01-meet-hdrctl` — `--version`/`--help`/`--lang`, `hdrctl init`, `hdrctl workflow init`, pourquoi `hdrctl list`
     ne voit que le job simple (non récursif).
  2. `02-validate-before-you-run` — référence `pipeline.from` cassée : `hdrctl run` laisse fuir une exception Python
     brute et non traduite (`ValueError: JobExecutor: source inconnue: '...'`) ; `hdrctl validate` nomme l'erreur
     proprement (`pipeline.from='...' not found in sources.yaml`) sans jamais exécuter quoi que ce soit.
  3. `03-test-is-not-validate` — job MySQL sans `.env` : `hdrctl test` et `hdrctl validate` passent tous les deux
     (« All tests pass », « DSL valid ») alors que `test` annonce lui-même « connection not tested » et
     « .env not found » ; seul `hdrctl run` tente réellement de résoudre `${ENV:...}` et échoue
     (`SecretResolutionError`).
  4. `04-hdrctl-over-http` — `hdrctl serve --no-studio` + `curl` sur `/api/health` et `/api/jobs/validate` (cas
     valide puis cassé) : le corps JSON renvoyé contient le `stdout` exact de la commande CLI équivalente, preuve
     vérifiée que l'API encapsule le binaire en sous-processus.
  5. `05-jobs-vs-workflows` — `hdrctl init` vs `hdrctl workflow init` côte à côte : `hdrctl list` (un niveau, non
     récursif) ne voit que le job simple ; `hdrctl workflow list` (récursif sur `workflow.yaml`) ne voit que le
     workflow ; `hdrctl workflow run` exécute réellement `job_a` → `job_b` → `notify`.
- **Suite du 26/09 :** titres numérotés « 1. » à « 5. » (Killercoda trie par titre) ; `verify.sh` corrigés (ils
  ne faisaient pas `cd /root/lab`, d'où un blocage à l'étape 1) ; scénario 2 réordonné (validate → corriger →
  validate → run) ; scénario 3 refait autour de `hdrctl test` (casser → test → corriger → test).
  **Les 5 scénarios ont été rejoués pour de vrai avec `hydra-etl` 0.11.2** : 2 bugs produit trouvés (voir actions).
- Labo n°6 crontab préparé dans `contenus/killercoda-pending/`, à publier après 1 à 2 semaines de mesures.
- iximiuz Labs étudié : auteur payant (Tinkerer 43,20 $/an), apprenant gratuit (1 h/jour). Plan B si Killercoda échoue.
- **Compte Killercoda bloqué** (« VPN or proxy »). Cause probable : l'extension Firefox « Mobile simulator »
  (falsifie le user-agent, injecte `spoofer.js`). Désactivée ; e-mail de demande de réactivation envoyé à
  security@killercoda.com. **En attente de leur réponse — tout le travail Killercoda est suspendu jusque-là.**
- Article 18456 vérifié en ligne sur `hydraetl.com/blog`. Reste l'indexation Google + Bing.
- Reste à faire par Bechir : pousser le nouvel état du dépôt `hydra-killercoda` (contenu de `contenus/killercoda/`
  remplace l'ancien), puis sur killercoda.com dépublier/supprimer le lab crontab et publier les 5 nouveaux. Commandes
  git données dans `suivi/actions-bechir.md`.


## 26 septembre 2026 (suite) — skill GEO adopté

- Bechir a fourni un skill `seo-geo-content-framework` (`D:\framework geo`). Analysé : adopté.
- Ajouts : code publié = code exécuté ; expériences datées ; langue du public ; registre `<slug>.evidence.md` ;
  « le GEO vise la citation, pas le clic » ; indexation = prérequis ; point de départ de mesure GEO ;
  exigences d'article technique ; **fiche Hydra ETL remplie** (vérifiée sur le commit `ed53916`).
- Chiffres retenus (sourcés) : 84 % des développeurs utilisent l'IA, 46 % s'en méfient (Stack Overflow 2025) ;
  les assistants IA = 0,29 % des référents de recherche contre ~88 % pour Google (Cloudflare Radar, mai 2026).
- Copie consolidée dans `ressources/seo-geo-content-framework.SKILL.md` ; proposé à l'installation.
- **Article 18456 retravaillé** avec le skill : `contenus/articles/sql-server-error-18456.md` + `.evidence.md`.
  Le contrôle a trouvé 1 citation FreeTDS **fausse** (la doc dit l'inverse), 4 lignes du tableau des états
  non conformes à Microsoft, 1 affirmation sans source (images sans sqlcmd). Tout corrigé ou retiré ;
  8 sources Microsoft Learn/FreeTDS ajoutées, réponse en tête, dates, auteur, métadonnées.
- Suite : retravailler l'article 18456 avec ce skill, puis publication sur hydraetl.com + indexation Google et Bing,
  puis point de départ GEO (10 questions × 4 assistants).

---

## 26 septembre 2026 — action inconnue : confirmée, corrigée

### Constat

Confirmé dans le code, pas seulement dans la doc : `workflow/runner.py` renvoyait `success=True`
pour une action absente de `action_handlers`, et `workflow validate` ne contrôlait pas le nom.
Un test (`test_unknown_action_is_noop`) verrouillait même ce comportement.

### Corrigé dans `Hydra` (non commité — diff à relire par Bechir)

- `workflow/models.py` : `WORKFLOW_ACTIONS` + refus au chargement, avec suggestion
  (`unknown action 'powersheII' … did you mean 'powershell'?`). `validate` échoue, `run` ne démarre pas.
- `workflow/runner.py` : une action inconnue qui arriverait malgré tout est **en échec**, plus en succès.
- Description MCP `hydra_list_actions`, `tools/spec_export.py` et les deux `DSL_REFERENCE.md` alignés.
- Tests : l'ancien test remplacé par 6 (chargement, suggestion, contournement, parité avec
  `action_handlers`, CLI validate, CLI run). 79 tests workflow verts ; `spec_export --check` OK.
- `CHANGELOG.md` : entrée `[Unreleased] / Fixed`.

### Suite — scénario Killercoda n°1 « Replace a fragile crontab » (angle choisi par Bechir)

- Construit dans `contenus/killercoda/01-replace-crontab/` : `index.json`, intro, 5 étapes avec
  vérification, fin, installation en arrière-plan (venv `/opt/hydra`), 4 scripts shell réalistes.
- Histoire : la livraison amont manque, cron produit « 3 orders » (ceux d'hier) en ayant l'air normal ;
  Hydra ETL saute les dépendants et sort en code 1. Puis retry sur coupure réseau, faute de frappe
  refusée, et une seule ligne cron conservée pour le *quand*.
- **Message honnête retenu : Hydra ne remplace pas cron comme ordonnanceur** en CLI (le déclencheur
  `schedule` ne tourne que sous `hdrctl serve`). Il remplace l'enchaînement deviné. Pas de « reprise
  après panne » affirmée : elle n'existe pas.
- Jouer le lab a révélé trois défauts de sortie de `workflow run`, corrigés et commités dans `Hydra` :
  trace Python sur manifeste invalide ; steps non atteints absents de l'affichage ; bruit Pydantic et
  messages français dans une sortie anglaise. 4 commits au total, **non poussés**.
- Tous les `{{exec}}` joués par un harnais sous Linux : étapes 1 à 4 vertes ; l'étape 5 (`crontab`)
  exige root, non testable dans la VM.

### Suite — clés et paramètres inconnus (demande de Bechir)

Même défaut que l'action inconnue, un niveau plus bas : `depend_on:` (au lieu de `depends_on`)
passait `validate` et l'étape tournait **sans sa dépendance** ; `mesage:` disparaissait.

- Refus, avec suggestion, de toute clé inconnue : premier niveau, `workflow`, étape, `trigger`,
  `retry` ; `action`/`params` sur une étape job et `job` sur une étape action.
- Table `ACTION_PARAMS` (requis / facultatifs par action) : paramètre inconnu refusé, paramètre
  requis absent ou vide refusé dès `validate` au lieu d'échouer à 2 h du matin.
- Deux tests de parité empêchent la dérive : la table = ce que le runner lit réellement, et
  ⊇ ce que Studio propose.
- Trouvé au passage : le `webhook` **ignorait les `headers`** que Studio propose (un
  `Authorization` ne partait jamais) et ré-encodait un body texte. Corrigé, testé avec un vrai
  serveur HTTP local.
- Vérifié sans régression : 27 workflows du dépôt, 4 modèles `workflow init`, 3 modèles de l'API,
  le workflow du lab Killercoda, 126 tests (workflow, API Studio, MCP), `spec_export --check`.
- 2 commits de plus (6 au total), non poussés. Changement cassant assumé : un workflow qui
  comptait sur une clé ignorée échoue désormais à la validation, avec la clé nommée.

### Conséquence

Le scénario Killercoda n°4 et l'angle « remplacer crontab » sont désormais démontrables honnêtement.
Il faut publier une 0.11.2 pour que Killercoda (qui fera `pip install hydra-etl`) en bénéficie.

---

## 25 septembre 2026 — la stratégie d'acquisition, et un point à vérifier

Session sans production de code : uniquement de la stratégie. Trois choses en sont sorties.

### 1. L'ordre de la feuille de route a changé — et c'est Bechir qui avait raison

Les articles passent **en dernier**, après les conversations avec les prospects. Motif : écrire
avant d'avoir parlé à des utilisateurs, c'est deviner ce qui intéresse. Après vingt conversations,
on connaîtra les problèmes qui reviennent et les mots pour les décrire. Les pages de comparaison
suivent la même logique, encore plus fortement.

Nouvel ordre : **Killercoda (+ liens dans le site) → les six canaux → articles et comparaisons**,
avec l'article `18456` publié hors séquence puisqu'il est prêt et qu'il sert de carte de visite.

### 2. La cible prioritaire n'est pas celle qu'on croyait

**Ni les startups, ni les grandes entreprises : les consultants et freelances data.**

- Une startup n'a **aucune licence ETL à économiser** — elle n'en a jamais acheté. L'argument du
  prix ne mord pas. Ce qui est vrai chez elle, c'est la vitesse de décision, pas le budget.
- Un consultant **déploie chez plusieurs clients** : un utilisateur devient trois à cinq
  installations. Il a le problème tous les jours, décide seul, et parle publiquement de ses outils
  parce que c'est son marketing.
- L'argument qui le concerne **lui** et pas ses clients : un pipeline déclaratif se relit, se
  transmet et s'audite. C'est la maintenabilité qu'il vend.

Les six canaux et la méthode d'approche sont consignés dans
`contenus/prospection/trouver-les-consultants-data.md`, avec la manière de prouver l'usage le jour
du Show HN.

### 3. Une piste écartée, et pourquoi

Le cold email de masse à partir des 11 millions d'entreprises de data.gouv/Sirene. Écarté pour
quatre raisons, dont la première est rédhibitoire :

- **Sirene ne contient pas d'adresses email** — c'est un registre d'identification.
- Le ciblage y est impossible : le code NAF ne dit pas qui fait de l'ETL.
- Un domaine de deux mois qui envoie en masse **détruit sa réputation d'expéditeur**, y compris
  pour la newsletter et les échanges avec les pilotes.
- Dans les communautés techniques, l'étiquette de spammeur ne part plus — et le lancement vise
  Hacker News.

À noter : le **serveur MCP officiel de data.gouv.fr existe** (`https://mcp.data.gouv.fr/mcp`, sans
authentification, lecture seule). Il donne accès au catalogue de jeux de données ; rien ne dit que
le registre Sirene y soit interrogeable directement.

### 4. Ce qui a été découvert sur le produit

En vérifiant sur GitHub si les actions de workflow sont exploitables en CLI :

- **Oui.** `hdrctl` expose `workflow run`, `workflow validate`, `workflow list` et
  `workflow init` (qui scaffolde un projet complet).
- **Conséquence de positionnement non exploitée :** les onze actions du DSL (`bash`, `powershell`,
  `python`, `ssh`, `webhook`…) s'exécutent hors Studio. Hydra devient un **remplaçant de « cron +
  une pile de scripts »**, ce qui élargit l'audience aux devops — le public exact de Killercoda.
- **Un point à vérifier d'urgence**, lu dans `DSL_REFERENCE.md` : *une action inconnue serait
  ignorée en silence et l'étape comptée comme réussie*. Si c'est exact, cela contredit frontalement
  la promesse « validé avant de s'exécuter » et complique le scénario Killercoda n°4. Détaillé dans
  `CLAUDE.md` §5.

### Aussi, en passant

- « Recherche d'entreprise » dans l'aide de Claude est la traduction d'**Enterprise Search** — la
  recherche *en* entreprise (Slack, SharePoint, Drive), réservée aux forfaits Team et Enterprise.
  Rien à voir avec des données sur les entreprises.
- Il n'existe ni skill ni connecteur Claude pour les entreprises françaises. La source de référence
  reste l'API Sirene de l'INSEE.

---

## 23 septembre 2026 — publication de la 0.11.0 : connecteur SQL Server

### Ce qui a été publié

`hydra-etl 0.11.0` est sur PyPI, avec l'extra `mssql`. Trois commits :

- `21fe2d8` correction de la résolution des instances nommées
- `4282ff3` bump de version, CHANGELOG, README, spécification DSL régénérée
- `0913106` résolution par SQL Browser

Le connecteur : extraction par table ou par requête, chargement en `append`,
`replace` ou `upsert`, création automatique de la table.

### Les deux décisions techniques qui comptent

**pymssql plutôt que pyodbc.** pyodbc est plus capable mais exige le pilote
système `msodbcsql`, ce qui contredit la promesse « une commande, rien à
déployer ». pymssql embarque FreeTDS dans ses wheels.

**Pas de MERGE pour l'upsert.** `UPDATE` puis `INSERT ... WHERE NOT EXISTS`
dans une transaction. Les problèmes de concurrence de MERGE sont documentés et
beaucoup d'équipes SQL Server l'interdisent. Un test vérifie que le mot MERGE
n'apparaît nulle part.

### La limitation levée le jour même

FreeTDS n'interroge pas SQL Browser : `MACHINE\SQLEXPRESS` visait le port 1433
et échouait — exactement la configuration par défaut de SQL Express, donc du
public visé. Plutôt que d'ajouter pyodbc, Hydra fait la résolution elle-même :
un datagramme UDP vers le port 1434 (protocole SSRP), une quarantaine de lignes,
aucune dépendance nouvelle.

Un bug attrapé par les tests, et il valait cher : le `;;` qui sépare les blocs
d'instances décalait les paires clé/valeur dès la deuxième instance. Sur un
serveur en hébergeant plusieurs, on aurait pu rendre le port d'une autre
instance et connecter l'utilisateur, en silence, à la mauvaise base.

### Preuves

90 tests unitaires, 11 tests bout en bout contre de vrais serveurs, dans les
deux modes :

| Mode | Plateforme | Résultat |
|---|---|---|
| SQL Browser, sans port | Windows, `DESKTOP-463V422\SERVER2024` | port 14330 trouvé seul, 11/11 |
| Port explicite | `mcr.microsoft.com/mssql/server:2022-latest`, Linux | 11/11 |

`test_accented_text_survives_the_round_trip` passe des deux côtés malgré des
classements par défaut différents : le choix `NVARCHAR` + UTF-8 est mesuré, pas
seulement raisonné.

### Quatre obstacles de terrain — la matière de l'article SSIS

Aucun ne vient du code, tous attendent le lecteur :

1. Instance nommée non résolue par FreeTDS -> `20009`, sans citer l'instance.
2. Port dynamique instable -> il faut le fixer, ou compter sur SQL Browser.
3. Login serveur sans utilisateur dans la base -> `18456`, qui oriente à tort
   vers le mot de passe.
4. Base inexistante -> `18456 State 38`, le plus sournois : identique au
   précédent à l'œil nu. C'est le champ `State` du log serveur qui tranche.

À quoi s'ajoute, côté conteneur Linux, que `sqlcmd` n'est plus livré dans
l'image SQL Server 2022 : un `CREATE DATABASE` par `docker exec` échoue en
silence.

### Ce qui a été corrigé au passage

- **Identité git.** Le dépôt était configuré sur `Bbejaoui@andaluzlab.com`,
  l'adresse d'un client. Réglé sur `bejaouibechir / vadimaentreprise@gmail.com`,
  et les trois commits non poussés réécrits. Quatre commits déjà publics gardent
  l'ancienne adresse : les réécrire imposerait un force-push sur un dépôt public
  pour un bénéfice symbolique — décision de ne pas le faire.
- **Résidus git.** Les opérations git menées depuis le shell Linux laissaient
  des verrous et 132 objets temporaires que Windows ne pouvait pas effacer
  (propriétaire différent). Résolu en accordant le droit de suppression au
  shell. `git fsck` : aucune anomalie.

### Dette constatée, non traitée

- **Deux générateurs de schémas** écrivent dans le même dossier :
  `tools/spec_export.py` (celui de la CI, qui estampille `generatedBy`) et
  `scripts/generate_hydra_dsl_schemas.py`, plus ancien et plus pauvre. D'où
  l'échec permanent de `test_committed_schemas_are_synchronised`. Vérifié
  contre HEAD : antérieur au bump.
- `eval-dataset.json` porte `productVersion 0.9.6`.
- Les messages du connecteur Parquet ont perdu leurs accents depuis `a223580`,
  alors que ses tests les attendent encore.
- Les tests Parquet échouent sous Windows sur un verrou de fichier lors du
  `os.replace` atomique (`WinError 5` / `32`). Piste : exclure
  `%TEMP%\pytest-of-DELL` de Windows Defender.
- Pas d'icône SQL Server dans `assets/connectors/`, donc absent du tableau du
  README.

### 0.11.1 — SQL Server dans Studio

Le connecteur existait dans le moteur, mais l'éditeur visuel ne l'offrait pas :
un utilisateur de Studio ne pouvait pas construire un pipeline SQL Server. Deux
nœuds ajoutés, source et destination, entre PostgreSQL et MongoDB.

Le formulaire porte `host`, `instance`, `port`, `database`, `schema`, `user`,
`password`, puis table/requête en source et table/mode en destination.

**Le piège évité, et il valait cher.** MySQL et PostgreSQL écrivent 3306 et 5432
par défaut quand le champ port est vide. Faire pareil avec 1433 aurait rendu les
instances nommées inatteignables depuis Studio — donc SQL Express, donc le
public visé — alors que le moteur les gère. Le port est omis du manifeste quand
le champ est vide, et le libellé le dit.

**Deux trous trouvés en vérifiant, pas en écrivant.** La première passe ne
traitait que deux des quatre blocs `connection` (`flowToJobModel` a les siens).
Et `_sourceToParams` / `_destToParams` ne relisaient ni `instance` ni `schema` :
ouvrir un manifeste SQL Server puis l'enregistrer les aurait effacés en silence.

**Icône.** Celles de MySQL et PostgreSQL sont des redessins de leurs logos. Le
logo SQL Server est une marque Microsoft et n'est pas reproduit : les nœuds
utilisent l'icône générique `Database` de Lucide. Une icône originale reste à
faire si on veut l'équilibre visuel.

Preuve de bout en bout : un job SQL Server → CSV construit dans Studio et
exécuté, avec instance nommée et sans port. Ce succès prouve à lui seul que le
manifeste ne contient pas de port — l'instance écoute sur 14330, un `port: 1433`
parasite aurait échoué en `20009` au lieu de se connecter.

Tests Studio : 57, dont 14 dans le sérialiseur.

### Reste ouvert

Devcontainer et badge Codespaces, arc de scénarios Killercoda, article sur le
garde-fou, article SSIS, pages `/migrate/*`, page de benchmark, storyboard de
la démo.

---

## 22 septembre 2026 — revision de la strategie et de la feuille de route

Journee sans production de code : uniquement des arbitrages, tous reportes dans `CLAUDE.md`
(sections 2, 2 bis, 5 et 9, reecrites).

### Le declencheur

Bechir a fait relire le projet par ChatGPT (`divers/avis chatbgt.md`) et a tenu avec lui une seance
sur les canaux de promotion (`divers/pv chatbgt.md`). Diagnostic de ChatGPT, que je partage :
**le probleme de Hydra ETL n'est plus technique, il est probatoire** — 7,5/10 sur le produit,
2/10 sur l'adoption. Deux corrections factuelles : l'avis parle de 0.10.1 et d'« une etoile, aucun
fork », on est a 0.10.3, 2 etoiles, un fork avec PR externe et Glama a 83 %.

### Desaccords assumes avec ChatGPT

- **Sa priorite n°5 se contredit** : « une seule promesse », puis il en enonce trois dont
  « pilotable par prompts IA ». L'IA sort de la promesse principale. Glama indexe **90 380 serveurs
  MCP** : ce n'est plus un differenciateur.
- **L'angle MCP defendable n'est pas celui qu'il propose.** Ce n'est pas « ETL + MCP », c'est
  **le garde-fou** : l'incident reel documente dans `hydra_etl/mcp/server.py`, ou un modele a execute
  un job sans qu'on le lui demande. Verifie dans le code et les tests. Personne ne raconte cette
  histoire du point de vue de l'outil qui subit l'agent.
- **Pas de porte-parole anglophone**, contrairement a la piste envisagee dans le PV.

### Decisions

- **Canaux retenus** : Show HN, The New Stack (article invite, editable donc sans frein de langue),
  Data Engineering Podcast, C# Corner. **Ecartes** : TechCrunch, VentureBeat, G2, chaine YouTube,
  comparatifs generes par des tiers, liens retro-ajoutes dans les anciens articles.
- **Essai sans installation** : Codespaces d'abord (le bouton se place dans le README ou le trafic
  arrive deja), Killercoda ensuite avec un arc de 6 scenarios publie par etapes, Colab plus tard.
  Killercoda seul ne genere pas d'audience — c'est nous qui poussons le lien.
- **Pages comparatives** : investir sur nos propres `/migrate/*`, pas sur les annuaires. Preuve :
  LibHunt a fabrique seul une page `hydra-vs-pinball`, Pinball etant un projet Pinterest abandonne.
- **C# Corner** : actif le plus sous-evalue du projet, mais exploitable **uniquement par le pont
  SSIS** — voir `CLAUDE.md` §2 bis.
- **Connecteur SQL Server** : exception consciente au « arreter d'ajouter des fonctionnalites »,
  parce que c'est le seul connecteur qui ouvre une audience deja acquise. Pilote `pymssql` et non
  `pyodbc` (qui casserait la promesse « une commande, rien a deployer »). Roues verifiees sur PyPI :
  Windows x64, Linux glibc et musl x86_64/ARM64, macOS Intel et Apple Silicon, Python 3.9 a 3.15.
  UPSERT par UPDATE + INSERT WHERE NOT EXISTS, pas `MERGE`.

### Audit SEO du site — defauts trouves en lisant le code

Requete « hydra etl » sur Google : hydraetl.com n'est pas dans les trois premiers, et l'Apercu IA
cite **Glama et le depot homonyme `jsogarro/hydra-etl`**, pas le site officiel.

- `favicon.svg` est **un eclair violet reste du gabarit Astro** (couleurs #863bff/#7e14ff). Google
  affiche fidelement ce que le site declare. La vraie marque existe dans `public/` mais n'est
  declaree qu'en `alternate icon`. Seul `hydra-mark.png` (96×96) est carre ; les deux autres logos
  sont a quelques pixels pres du carre, ce que Google rejette.
- Le `<title>` de l'accueil place « Hydra ETL » en 48e position ; le `<h1>` ne contient pas la marque.
  Google fait d'ailleurs remonter `hydraetl.com/dsl/sources` **plutot que l'accueil**.
- `sameAs` ne liste que GitHub et PyPI — d'ou l'absence de consolidation de l'entite.
- Trois pages emettent trois `SoftwareApplication` concurrents sans `@id`.
- La cause dominante reste l'anciennete du domaine et les liens entrants : cela se gagne par les
  liens, pas par les balises. A noter : les deux resultats qui devancent le site sont SourceForge et
  Glama, c'est-a-dire nos propres fiches.

### Verification d'outillage

Pas de demon Docker dans le conteneur cloud, pas de Docker dans la VM de la machine. Les tests E2E
du connecteur SQL Server devront tourner sur Docker Desktop cote Bechir, sur **deux** configurations
pour pouvoir annoncer la portabilite honnetement.

---

## 21 septembre 2026 — soir : note Glama de 25 % a 83 %

### Ce qui a ete fait

**La note qualite Glama est passee de 25 % a 83 % dans la journee.** C'etait le verrou de la
PR `awesome-mcp-servers` #14699 (liste a 95 000 etoiles), qui exige un badge de note.

Enchainement, dans l'ordre :

1. **Decouverte de l'onglet Admin de Glama** (il faut etre connecte). Il contient : Listing,
   Analytics, Boost, Repository, Releases, Dockerfile, Score, GitHub Badge. Le reglage qui
   debloque tout est dans `Dockerfile`, pas un fichier a poser dans le depot.
2. **`glama.json` ajoute a la racine du depot Hydra** (commit `9d872a0`) :
   `{"$schema": "https://glama.ai/mcp/schemas/server.json", "maintainers": ["bejaouibechir"]}`
   C'est un critere de note a lui seul. 25 % -> 33 %.
3. **Diagnostic des deux builds Glama en echec du 19/09.** La configuration par defaut
   (`uv sync`, Python 3.14) ne pouvait pas marcher : pas de `uv.lock` dans le depot,
   `uv sync` installe dans `/app/.venv` donc `hydra-mcp` n'est pas dans le PATH, et l'extra
   `mcp` n'est pas installe. Python 3.14 n'a pas de wheels pour pandas/pydantic.
4. **Configuration de build qui marche** (verifiee d'abord en local : venv propre + PyPI) :
   - `Python version` : `3.12`
   - `Build steps` : `["uv venv /opt/hydra", "uv pip install --python /opt/hydra/bin/python --no-cache-dir 'hydra-etl[mcp]==0.10.3'"]`
   - `CMD arguments` : `["mcp-proxy", "--", "/opt/hydra/bin/hydra-mcp"]`
   - `Environment variables JSON schema` : laisse vide (`properties` et `required` vides)
   - `Placeholder parameters` : `{}`
   On installe **le wheel PyPI**, pas les sources. Build reussi en 14 s. 33 % -> 50 %.
5. **Anomalie trouvee en interrogeant le serveur MCP** : les instructions du serveur et les
   **17 descriptions de tools etaient en francais**, et `serverInfo.version` etait vide. Or
   Glama note `Tool Definition Quality` et `Server Coherence` en faisant lire ces descriptions
   par un LLM, **au moment de la release**, et publie le detail. Release retardee
   volontairement : traduction d'abord.
6. **Traduction en anglais, version 0.10.3 publiee sur PyPI** (detail ci-dessous).
7. **`Sync Server`** sur l'onglet Repository — Glama n'avait pas relu le depot depuis le
   19/09 18:26 et ignorait les nouveaux commits — puis **`Build & Release`**.

### Resultat : 8 criteres sur 10

| Critere | Etat |
|---|---|
| Has a Glama release | OK |
| **Server Coherence** | OK, note **A** |
| **Tool Definition Quality** | OK, note **A** |
| Maintenance | OK, note A |
| Has a permissive license (AGPL 3.0) | OK, note A |
| Has README | OK |
| Has valid glama.json | OK |
| Author verified | OK |
| No recent usage | ECHEC : aucun appel de tool en 30 jours |
| No related servers | ECHEC : calcule par Glama |

### Version 0.10.3 : le serveur MCP passe en anglais

Commits `b991839` (traduction) et `08a4bd4` (version, CHANGELOG, spec DSL regeneree).
Publie sur PyPI le 21/09 a 16:01 UTC.

- 27 remplacements de chaines dans `hydra_etl/mcp/server.py` : instructions du serveur, les
  17 `description=`, les 3 titres d'annotations, l'aide de `hydra-mcp --help`.
- `serverInfo` avant : `{"name": "hydra", "version": ""}`
- `serverInfo` apres : `{"name": "hydra-etl", "title": "Hydra ETL", "version": "0.10.3", "websiteUrl": "https://hydraetl.com"}`
  Les trois champs ajoutes ne sont passes que si le SDK les accepte (`inspect.signature`),
  pour ne pas casser le repli SDK 1.x present dans le module.
- Le texte anglais complet, capture depuis le serveur en fonctionnement, est archive dans
  `contenus/mcp/tool-definitions-en.md`.
- **Non-regression** : 1158 tests avant / 1158 apres, 21 echecs pre-existants dans les deux
  cas, **0 `pass -> fail`**, 0 test disparu ou ajoute (comparaison `--junitxml` test par
  test). Verification finale faite depuis le paquet PyPI publie : venv neuf, install
  `hydra-etl[mcp]==0.10.3`, poignee de main MCP, 17 tools, aucun accent francais.
- La regeneration de la spec DSL est **obligatoire** apres un bump : `release.yml` ligne 63
  lance `spec_export.py --check` et les fichiers de spec embarquent le numero de version.
  C'est ce qui avait fait echouer la release 0.10.2. Verifie : seuls les numeros ont change.

### Decisions et choses apprises

- **Hors perimetre volontairement** : les messages de retour a l'execution du serveur MCP
  (`REFUSE`, `VALIDE`, `ECRIT`, `ALERTES`...) restent en francais. `tests/test_mcp_server.py`
  fait ses assertions dessus (12 occurrences du type `startswith("REFUSE")`). Les traduire
  impose de modifier les tests et le code qu'ils surveillent dans le meme commit. Glama ne
  les note pas. **Ticket a creer**, a traiter avec le mecanisme `locales/*.json` du CLI.
- La release Glama porte le numero **`0.1.0`**, attribue automatiquement par `Build & Release`
  (doc Glama : « choosing the version for you »). Incoherent avec PyPI et `serverInfo` qui
  disent `0.10.3`. Correction possible : `Build` seul, puis `Make Release` en saisissant
  `0.10.3` a la main. Cosmetique.
- **`Auto-Release` est active** sur Glama : « Builds and publishes a new version on every
  GitHub release ». Piege : `release.yml` se declenche sur un **tag** `v*`, et un tag n'est
  pas une *GitHub Release*. Tant qu'aucune Release n'est creee dans l'interface GitHub,
  l'auto-release Glama ne partira pas.
- La page Overview de Glama affiche **`Responsiveness: Unresponsive`**. C'est mesure sur le
  temps de reponse aux issues et PR du depot Hydra ; la PR #9 sans reponse depuis le 20/09 y
  contribue. Independant de la note qualite.
- Le jeton GitHub est dans `C:\Users\DELL\.hydra\gh_token`, **hors des dossiers connectes
  a la session**. Claude ne peut donc ni pousser ni ecrire sur GitHub : il commite en local,
  Bechir pousse. Pour deleguer les ecritures GitHub, il faudrait connecter ce dossier.
- Methode confirmee : ne rien affirmer sans preuve. Chaque etape a ete verifiee contre la
  source vive (API PyPI, serveur MCP reellement lance, `--junitxml` compare), jamais deduite.

### Fin de session : tout ce qui etait bloquant est fait

- **PR `awesome-mcp-servers` #14699 : plus aucun blocage.** Badge `score.svg` pose apres le lien
  du depot (pas en fin de ligne : c'est la pratique de la liste, contre ce que dit le bot).
  Les 3 labels sont verts — `has-emoji`, **`has-glama`**, `valid-name` — et les controles passent
  2/2. Le bot a fait basculer `missing-glama` en `has-glama` tout seul au commit suivant.
  Reste la revue humaine de `punkpeye`. Detail et pieges dans
  `contenus/github/pr-14699-reponse-badge.md`.
- **Badges Glama dans le README de Hydra** (commit `b007de9`, pousse et verifie sur
  `origin/main`) : petit badge de note dans la rangee du haut apres `status: beta`, carte
  complete dans la section MCP, introduite par une phrase factuelle sur ce que Glama mesure.
- **Branche `patch-1` du fork awesome-mcp-servers supprimee** (commit egare, aucune PR associee —
  verifie par `is:pr author:bejaouibechir` sur le depot amont : `Open 1 · Closed 0`).
  Piege a retenir : la colonne « Pull request » de la page des branches d'un fork **n'affiche pas**
  les PR vers le depot amont. Elle etait vide pour `patch-2` aussi, qui porte pourtant la PR.

### Ce qui reste ouvert

- « No recent usage » : remede suggere par Glama lui-meme, « Try in Browser » sur la fiche.
- Post LinkedIn n°2, PR #9, jeton fine-grained, Umami + Search Console, tache planifiee
  Windows, benchmark A3, pilotes, article n°2.

---

## 21 septembre 2026 — mise en place de deux agents hebdomadaires

**Décision :** trois agents étaient envisagés ; le troisième (génération d'un ou deux articles par jour) a été **écarté**. Publier du contenu non vérifié à ce rythme détruirait la crédibilité que l'on construit — notre différenciateur est que chaque commande publiée a été exécutée. Remplacé par une **recommandation d'article** produite par le rapport hebdomadaire, fondée sur les faits observés dans la semaine.

**Créé (voir `suivi/agents.md`) :**
- Rapport hebdomadaire — samedi 10 h : chiffres réels, mouvements, blocages, recommandation d'article, 3 priorités. Met à jour le journal et la liste d'actions.
- Veille forums — samedi 10 h 30 : 3 à 5 discussions pertinentes maximum, avec brouillons de réponses en anglais dans `suivi/veille-forums.md`.

**Limites connues et assumées :**
- Les deux tâches exigent l'ordinateur allumé avec Claude ouvert ; une tâche manquée ne se rattrape pas automatiquement. Parades : une tâche du Planificateur Windows qui ouvre Claude à 9 h 50 (procédure dans `suivi/agents.md`), et une règle de rattrapage inscrite dans `CLAUDE.md`.
- Aucun canal entrant n'existe vers l'assistant : un service Windows ne peut pas le notifier.
- Umami et Search Console restent inaccessibles faute de jeton ou d'export : les rapports diront ce qui manque plutôt que d'inventer des chiffres.

**Règle réaffirmée :** aucun agent ne publie quoi que ce soit. Ils préparent, Bechir publie.

### Jeton GitHub confié à Claude (21/09)

Bechir a déposé un jeton GitHub dans `C:\Users\DELL\.hydra\gh_token` (hors dépôt git). Claude le lit au moment de s'en servir.
- Jeton **classique** (`ghp_`) : portée large sur tous ses dépôts. À remplacer à terme par un jeton *fine-grained* limité à `Hydra` et aux 4 forks awesome, avec expiration.
- Règle : Claude exécute les modifications mécaniques (ligne d'un fork, description) ; tout **texte public en son nom** lui est montré avant publication.
- Les deux agents du samedi restent en **lecture seule** : ils ne publient rien.

### Réponses aux mainteneurs (21/09)

- **awesome-duckdb #353** : le mainteneur (szarnyasg, DuckDB) a relevé que la description opposait DuckDB à pandas alors que Hydra ETL choisit le moteur **par opération**. Ligne corrigée (« can run each transformation step on DuckDB or pandas ») et réponse postée. Leçon : ne pas écrire « instead of » quand l'outil fait coexister deux moteurs.
- **awesome-mcp-servers #14699** : le mainteneur (punkpeye) confirme que la fiche Glama existe et est revendiquée, mais **la note qualité est `?`** et il en faut une, quelle qu'elle soit. La page Glama affiche « This server cannot be deployed » : il manque la configuration de déploiement. Le badge devra être au format `[![MCP](https://glama.ai/mcp/servers/bejaouibechir/Hydra/badge)](...)`, différent de celui annoncé par le bot le 19/09.

---

## 20 septembre 2026 — publication de la 0.10.2 et du premier article

### Produit : deux correctifs, une version publiée

**Anomalies trouvées en lisant le code** (`hydra_etl/cli/hdrctl.py`) :

1. `validate --strict` lisait `steps` à la racine, alors que les exemples du dépôt utilisent `transformations: steps:` → affichait « aucune » opération. Corrigé en passant par `TransformParser`, la source de vérité du DSL.
2. `validate --strict` affichait les expressions `filter`/`calculate` sans les analyser → une expression invalide passait la validation. Corrigé avec le pré-analyseur de pandas (même grammaire que `df.query`/`df.eval`), sans évaluation. Sortie en code 1 si erreur.
3. `workflow run` n'affichait pas la sortie des actions python/bash/powershell. Corrigé : nouveau champ `StepResult.output`, affiché sous l'étape, plafonné à 20 lignes.

**Méthode de non-régression appliquée** (à reproduire pour toute modification future) :
mesure de référence sur la suite complète → modification → nouvelle mesure → comparaison test par test (aucun `pass → fail`) → tests dédiés ajoutés → jeu de tests de la CI relancé.
Résultat : 1 211 tests, 21 échecs préexistants hors CI, **0 régression**, 26 tests ajoutés.

**Publication 0.10.2 :** le tag `vX.Y.Z` déclenche le workflow `release` (Trusted Publishing PyPI, aucun jeton).
⚠️ **Piège rencontré :** la spécification DSL exportée contient le numéro de version ; après un bump de `__version__`, il faut lancer `python tools/spec_export.py` et committer, sinon l'étape « La spécification du DSL est-elle à jour ? » échoue. C'est arrivé, le tag a dû être déplacé.

### Site

- Page `/license` créée (AGPL expliquée, obligation unique, licence commerciale, contact `admin@hydraetl.com`).
- **Blog créé** : `src/layouts/BlogPost.astro`, `src/pages/blog/index.astro`, lien « Blog » dans la navigation et le pied de page. Ajouter un `.md` dans `src/pages/blog/` suffit pour publier un article.
- Correction : `install.astro` pointait vers un dépôt inexistant (`andaluzlab/hydra`).
- ⚠️ La build du site ne peut pas se faire depuis l'environnement de Claude (`node_modules` installé pour Windows) : c'est Bechir qui lance `pnpm dev` pour valider.

### Article n°1 — publié

« Clean a million rows with Hydra ETL — no database, no Docker »

- https://hydraetl.com/blog/one-million-rows
- https://dev.to/bejaouibechir/clean-a-million-rows-with-hydra-etl-no-database-no-docker-nm1 (canonical vers le site, vérifié)

**Décisions éditoriales prises :** pas de Docker ni de base (dépendances minimales), données générées par un script à copier-coller (l'utilisateur ne cherche pas un CSV sur son disque), dossier de travail explicite avant chaque commande, mesures réelles sur deux machines.

**Mesures (1 M lignes, ~25 Mo) :**

| Machine | Python | Rust | Gain |
|---|---|---|---|
| Windows 11 25H2, Python 3.13.7 | 6,4 · 6,5 · 6,7 s | 3,5 · 3,7 · 3,8 s | ~42 % |
| VM Linux, Python 3.10.12 | 8,5 · 8,7 · 9,2 s | 6,4 · 6,8 · 7,6 s | ~22 % |

Sorties identiques au bit près (même md5) entre les deux moteurs.
Un run Rust à 7,7 s (parasite) est mentionné dans l'article plutôt que masqué.
**Position assumée :** le « ~4× » du README concerne la lecture CSV seule ; l'article le dit explicitement.

### Communauté

- **PR externe #9** (`Voyagerroc-Lab`, doc `validate`) : CI approuvée, commentaire de relecture posté demandant de préciser la partie `--strict` avec ce que fait la 0.10.2. Marche à suivre dans `contenus/github/pr-9-traitement.md`.
  ⚠️ Compte créé le 11/09 avec 512 dépôts : contribution probablement automatisée. Contenu correct, mais son étoile et son fork ne comptent pas comme adoption réelle.
- 6 tickets « good first issue » ouverts (#3 à #8).

### Conventions adoptées ce jour

- **Langue :** discussion en français, **tout contenu public en anglais**.
- **Ne jamais mentionner Andaluz Lab** dans le contexte Hydra ETL (c'est un client, sans lien avec le produit).
- **Marquage des commandes :** ▶️ À EXÉCUTER (par Bechir) · ℹ️ DÉJÀ FAIT (par Claude) · 📋 POUR INFO.
- **Calendrier :** les « mois » de la feuille de route donnent un ordre de priorité, pas des dates. Seule dépendance dure : pas de Show HN avant 3 pilotes + GIF de démo + page benchmark.

---

## 19 septembre 2026 — fondations et premiers liens entrants

### Fait

- Dépôt GitHub : description, site, 10 topics, release v0.10.1.
- **4 PR sur des listes awesome** préparées et ouvertes par Bechir :
  - awesome-pipeline #246 → **FUSIONNÉE le 19/09** ✅ (premier lien entrant depuis une source reconnue)
  - awesome-mcp-servers #14699 → ouverte, bloquée par l'exigence d'une fiche Glama
  - awesome-data-engineering #371 → ouverte
  - awesome-duckdb #353 → ouverte
- **Listes écartées après lecture de leurs règles :** awesome-etl (exige une traction tierce quand l'auteur se propose), awesome-python (refuse les projets en bêta), awesome-workflow-engines (affiche le nombre d'étoiles de chaque entrée : attendre ~50 ⭐).
- Fiches soumises : Glama, AlternativeTo, SaaSHub, LibHunt, SourceForge.
- Post LinkedIn n°1 publié.

### Appris

- AlternativeTo bride l'ajout d'applications pour les comptes trop récents.
- SaaSHub a automatiquement ajouté Hydra ETL comme concurrent d'AWS Glue, Fivetran, Talend, Matillion, Mule ESB.
- Sur GitHub, la CI d'une PR venant d'un contributeur externe demande une approbation manuelle du mainteneur.

### Avis externe (ChatGPT, `divers/avis chatbgt.md`)

Produit 7,5/10, adoption 2/10. Le frein n'est pas technique mais l'absence de **preuves d'usage réel**.
Décisions prises à la suite : recruter 3 pilotes, publier un benchmark reproductible, page licence, nommage « Hydra ETL » systématique, gel des grosses fonctionnalités.

---

## Avant le 19 septembre — état de départ

Site en ligne avec SEO technique, Umami, Search Console et Bing configurés, dépôt nettoyé (README, CONTRIBUTING, SECURITY, CI verte sur 5 environnements), PyPI 0.10.1 publiée, 1 post + 1 article LinkedIn en français.
Aucune adoption : 1 étoile, 0 fork, 0 contributeur.
