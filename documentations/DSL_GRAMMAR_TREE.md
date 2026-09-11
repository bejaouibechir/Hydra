# Hydra DSL — arborescence complète de la grammaire

Périmètre de la page `/dsl` : **la langue, rien que la langue**. Tout élément ci-dessous
est extrait du code, pas de la documentation. Sources de vérité :
`internal/parser/{source,transform,destination}.py`, `workflow/models.py`,
`internal/connector/registry.py`, `internal/config/{parameters,secrets}.py`,
`internal/engines/pandas_engine.py`, `cli/hdrctl.py` (templates `init`).

Marques : `✱` dépendance optionnelle · `⌁` valeur par défaut

---

```
hydra-dsl/
│
├── 1-manifest/                          Les fichiers et leur rôle
│   ├── version                          "1.0" — en tête de chaque fichier
│   ├── sources.yaml                     déclaration des entrées
│   ├── transformations.yaml             suite ordonnée d'opérations
│   ├── destinations.yaml                déclaration des sorties
│   ├── pipeline.yaml                    câblage from → to
│   └── workflow.yaml                    orchestration de jobs
│
├── 2-sources/
│   └── sources.<id>/
│       ├── type                         csv · json · mysql · mariadb · postgresql
│       │                                postgres · parquet✱ · mongodb✱ · web_api✱
│       ├── connection/
│       │   ├── csv                      base_path · delimiter · encoding · quotechar
│       │   │                            lineterminator · newline · strict_schema
│       │   ├── json                     file · table
│       │   ├── parquet✱                 file · table
│       │   ├── mysql · mariadb          host · port · user · password · database
│       │   ├── postgresql · postgres    host · port · user · password · database · schema
│       │   ├── mongodb✱                 host · port · database · collection
│       │   └── web_api✱/
│       │       ├── base_url
│       │       ├── auth/                type: bearer · api_key · oauth2
│       │       │                        token · key
│       │       └── pagination/          strategy: cursor · offset · next_link
│       │                                cursor_field · page_size
│       ├── extract/
│       │   ├── table                    fichier, table SQL ou endpoint
│       │   ├── query                    SQL brut
│       │   ├── collection               MongoDB
│       │   ├── filter                   mapping, MongoDB
│       │   ├── limit
│       │   └── batch_size               ⌁ 10000, minimum 1
│       └── schema/                      bloc optionnel
│           ├── mode                     ⌁ auto
│           ├── fields[]/                name · type · path · required · default
│           │                            array_handling · description
│           ├── drift_policy             ⌁ warn
│           ├── validation_policy        ⌁ best_effort
│           └── sample_size              ⌁ 100
│
├── 3-destinations/
│   └── destinations.<id>/
│       ├── type                         mêmes types que les sources
│       ├── connection                   mêmes clés que les sources
│       └── load/
│           ├── table
│           ├── collection
│           ├── mode                     ⌁ append · replace · upsert
│           ├── key[]                    requis pour upsert
│           └── batch_size               ⌁ 10000, entre 10 et 100000
│
├── 4-pipeline/
│   └── pipeline/
│       ├── from                         identifiant d'une source déclarée
│       └── to                           identifiant d'une destination déclarée
│
├── 5-transformations/
│   ├── steps[]                          liste ordonnée, au moins un élément
│   ├── <step>.name                      libellé optionnel
│   └── operations/                      18 opérations, aucune autre n'existe
│       │
│       ├── colonnes/
│       │   ├── select                   columns[]
│       │   ├── rename                   mapping{ancien: nouveau}
│       │   └── cast                     mapping{colonne: type}
│       │                                types : int·integer · float · str·string
│       │                                        bool·boolean · datetime
│       │
│       ├── lignes/
│       │   ├── filter                   expr
│       │   ├── sort                     by[] · ascending ⌁ true
│       │   ├── deduplicate              columns[] · keep ⌁ first
│       │   ├── fill_null                value · columns{}
│       │   ├── trim                     columns[]
│       │   └── clean                    columns[] · case ⌁ none
│       │
│       ├── calcul/
│       │   ├── calculate                column · expr
│       │   └── script                   inputs[] · outputs{} · code
│       │                                mode ⌁ vectorized · row
│       │
│       ├── agrégation/
│       │   └── aggregate                by[] · agg{colonne: fonction}
│       │
│       ├── combinaison/
│       │   ├── join                     right · key · left_key · right_key
│       │   │                            how ⌁ inner
│       │   ├── merge                    right · key · delete_unmatched ⌁ false
│       │   └── union                    right · distinct ⌁ false
│       │
│       └── remodelage/
│           ├── pivot                    index[] · column · values · aggfunc ⌁ first
│           ├── unpivot                  id_vars[] · value_vars[]
│           │                            var_name ⌁ variable · value_name ⌁ value
│           └── transpose                index_col · header_name ⌁ column
│
├── 6-workflow/
│   └── workflow/
│       ├── version                      ⌁ "1.0"
│       ├── name
│       ├── description
│       ├── trigger/
│       │   ├── type                     ⌁ manual · schedule · webhook
│       │   └── cron                     si type: schedule
│       └── steps[]/
│           ├── name
│           ├── type                     job · action
│           ├── job                      chemin du job, si type: job
│           ├── action                   nom de l'action, si type: action
│           ├── params{}
│           ├── depends_on[]             toujours une liste, même à un élément
│           ├── on_failure               ⌁ fail · skip · continue
│           ├── enabled                  ⌁ true
│           ├── when                     expression conditionnelle
│           └── retry/
│               ├── max                  ⌁ 0
│               ├── delay                ⌁ 0.0
│               └── backoff              ⌁ fixed · exponential
│
├── 7-expressions/                       la sous-langue des expressions
│   ├── filter.expr                      évalué par pandas query, moteur python
│   ├── calculate.expr                   évalué par pandas eval, moteur python
│   ├── step.when                        condition d'exécution d'un step
│   └── script.code                      Python restreint — liste blanche de builtins
│                                        abs round min max sum len int float str bool
│                                        list dict tuple set sorted reversed zip range
│                                        enumerate map filter any all divmod pow
│                                        isinstance print format repr ord chr hex bin
│
└── 8-interpolation/                     substitué avant lecture du manifeste
    ├── ${ENV:NOM}                       variable d'environnement
    ├── ${SECRET:NOM}                    secret
    ├── {{ param:NOM }}                  paramètre de job
    └── {{ env:NOM }}                    variable d'environnement
```

---

## Ce qui est hors périmètre de `/dsl`

Ces sujets touchent au YAML mais ne sont pas la langue. Ils vont dans `/guide`.

| Sujet | Pourquoi | Où |
|---|---|---|
| Se connecter à un vrai MySQL | valeurs, réseau, droits | `/guide/connections` |
| Fournir un secret, remplir un `.env` | exploitation | `/guide/secrets` |
| Faire tourner le scheduler, backfill | plateforme | `/guide/operations/scheduling` |
| Lire une erreur d'exécution du runner | sortie de terminal | `/guide/cli` |
| `hdrctl validate` | outil | `/guide/cli` |

**La frontière** : `/dsl` enseigne la **forme** d'un bloc `connection`, `/guide` enseigne
comment le **remplir** pour une base réelle.

---

## Les six points, tranchés depuis le code

Lot 2. Chaque réponse cite sa ligne. La colonne **nature** distingue ce qui est un choix
de Hydra de ce qui n'est qu'une propriété de pandas remontée à la surface — documenter
une fuite comme si c'était la langue, c'est la figer.

### 1 · `right` de `join`, `merge`, `union` — **voulu**

`internal/runner/executor.py:441-487`, `_prepare_join_steps`. Le runner précharge le
second flux **avant** d'appeler le moteur, et `right` accepte **deux formes** :

```yaml
# a) un id de source déclarée dans sources.yaml — recommandé
- join:
    right: src_customers
    key: customer_id

# b) une source inline, pour un usage ponctuel
- join:
    right:
      type: csv
      connection: {}
      extract: { table: data/customers.csv }
    key: customer_id
```

Toute autre valeur lève : *`{op}.right doit etre un id de source declaree ou une source
inline (dict avec 'type')`*. Les trois opérations partagent le même mécanisme
(`executor.py:451`). Le moteur seul ne peut pas les exécuter : `_right_rows` est injecté
par le runner, et son absence lève une erreur explicite (`pandas_engine.py:733-736`).

**La forme inline n'est documentée nulle part.** C'est une vraie fonctionnalité, à décider :
publique ou trappe d'échappement.

### 2 · `aggregate.agg` — **fuite de l'implémentation**

`pandas_engine.py:_op_aggregate`. Deux écritures acceptées :

```yaml
agg:
  total: { func: sum, col: revenue }   # forme longue
  revenue: sum                          # forme courte, col = clé de sortie
```

La docstring annonce `sum, count, mean, avg, min, max, first, last`. **Le code ne
contrôle rien** : `func` est passé tel quel à `df.groupby().agg()`. Donc `median`, `std`,
`var`, `nunique` fonctionnent aussi, sans être documentés ni voulus.

Un seul alias est bien de Hydra : `avg` → `mean` (`_FUNC_ALIASES`).

### 3 · `join.how` — **voulu**

`pandas_engine.py:739-740`. Contrairement à ce que laissait croire le type `str`, la
valeur **est** validée : `inner` (défaut), `left`, `right`, `outer`. Toute autre valeur
lève *`join.how invalide`*. Ce n'est pas une fuite de pandas.

### 4 · `web_api_connector_v2.py` — **confirmé hors périmètre**

Présent dans le dépôt, absent du registre (`internal/connector/registry.py`). Ne rien
en documenter.

### 5 · `clean.case` — **voulu, mais silencieux**

`pandas_engine.py:_op_clean`. Trois valeurs : `none` (défaut), `lower`, `upper`.
`clean` réduit aussi les espaces multiples et supprime les espaces de bord, toujours,
indépendamment de `case`.

**Problème** : une valeur inconnue — `case: capitalize` — ne fait rien et ne dit rien.
Le silence est un bug bloquant selon la charte. À trancher.

### 6 · DuckDB — **n'existe pas**

`internal/engines/duckdb_engine.py` fait 8 lignes et lève `NotImplementedError`.
`internal/engines/registry.py:63` n'enregistre que `pandas`. Et le runner n'utilise même
pas le registre : `executor.py:104` instancie `PandasEngine()` en dur.

Il n'y a donc **qu'un seul moteur**, et aucune divergence possible sur les expressions.
La section 7 de cette arborescence est universelle par défaut.

En revanche `CLAUDE.md` annonce « Engines de transformation : Pandas, DuckDB » et le
`README` du site en dit autant. **C'est faux en l'état.** Je n'ai pas modifié ces fichiers.

---

## Ce qui remonte à Bechir

Le code ne tranche pas ces quatre points — ce sont des décisions de produit, pas des
lectures de source.

| # | Décision | Enjeu |
|---|---|---|
| A | `clean.case: capitalize` doit-il lever une erreur, ou continuer d'être ignoré ? | La charte interdit le silence. Corriger le moteur, ou documenter le silence comme voulu |
| B | `aggregate.agg` : fermer la liste des fonctions et la valider, ou assumer d'exposer pandas ? | Fermer, c'est une langue stable ; ouvrir, c'est se lier à pandas pour toujours |
| C | DuckDB : retirer la promesse, ou l'afficher comme prévu et non livré ? | Un lecteur qui écrit `engine: duckdb` aujourd'hui n'a aucun retour |
| D | `right` inline : documenter publiquement, ou garder comme trappe d'échappement ? | Publier, c'est s'engager à le maintenir |
| E | `connection.base_path` est résolu depuis le **répertoire courant**, pas depuis le dossier du job. Voulu ? | Constaté au lot 3 en exécutant un vrai job : le même manifeste marche ou non selon l'endroit d'où on lance `hdrctl`. Sans `base_path`, le repli se fait bien sur `job_dir` (`csv_connector.py:92`) |

Tant que A, B et D ne sont pas tranchés, les fiches `clean`, `aggregate`, `join`, `merge`
et `union` ne peuvent pas être rédigées sans inventer.

---

## Compte

| Branche | Éléments terminaux |
|---|---|
| Manifeste | 6 |
| Sources | 9 types · 6 blocs `connection` · 6 clés `extract` · 5 clés `schema` |
| Destinations | 5 clés `load` |
| Pipeline | 2 |
| Transformations | 18 opérations · 45 paramètres |
| Workflow | 2 clés `trigger` · 10 clés de step · 3 clés `retry` |
| Expressions | 4 points d'usage |
| Interpolation | 4 formes |
