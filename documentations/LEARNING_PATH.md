# Arborescence — la langue et la plateforme

Remplace le plan « /learn en 11 chapitres ». Complète et corrige `SITEMAP.md`.
Soumise à `CHARTE_SITE.md` : aucune page sans objet manipulable.

---

## La règle de partage

> **Ce qui s'écrit dans un fichier YAML appartient à `/dsl`.
> Ce qui s'écrit dans un terminal ou une interface appartient à `/guide`.**

Le partage est fait par **objet**, pas par mode de lecture. Une frontière par objet se
tient seule ; une frontière par mode (« apprendre » contre « consulter ») demande un
arbitrage à chaque page et dérive au bout de dix pages. C'est ce qui s'était produit.

Elle tranche le cas ambigu des connecteurs : la **forme** du bloc `sources:` est de la
langue → `/dsl/blocks`. La **connexion** à un vrai MySQL est de la configuration →
`/guide/connections`.

Chaque section contient un **chemin** et un **index**. Ce n'est pas une duplication tant
que le chemin enseigne un geste et que l'index liste des propriétés.

---

## Vue d'ensemble

```
/                   Accueil — introduction et amorce de l'environnement
/install            Préparation de l'environnement (URL propre, point de convergence)
/dsl                La langue                    18 pages
/guide              La plateforme                16 pages
/playground         Bac à sable                  ✓
/build              Le DSL se forme sous vos yeux ✓
/migrate            Comparatif + 6 tunnels        ✓
```

---

## `/` — Accueil

Porte l'introduction, qui n'est ni de la langue ni de la configuration.

- Les 3 engines : ETL (disponible), Feature Detection (à venir), Execution Intelligence (à venir)
  — les deux engines non livrés sont **affichés comme non livrés**
- Core, CLI, API, Studio : quatre entrées, un seul moteur
- Hydra face aux autres outils — une pièce manipulable, renvoi vers `/migrate`
- Amorce de la préparation de l'environnement → `/install`

## `/install` — Préparation de l'environnement

Page à URL propre : les six tunnels de migration et chaque porte de sortie y renvoient.
Sélecteur Windows / Linux / macOS. Docker affiché en « pas encore ».

---

## `/dsl` — La langue

```
/dsl
├── catalog                    Index A–Z cherchable       ✓ maquette guide.html
├── manifest                   Anatomie d'un manifeste
├── structure                  Les 4 fichiers
│
├── jobs/
│   ├── first-job              lire, filtrer, écrire      ✓ maquette learn.html
│   ├── columns                select, rename, cast
│   ├── rows                   sort, deduplicate, fill_null, trim, clean
│   ├── compute                calculate, script
│   ├── aggregate              aggregate, join
│   ├── reshape                pivot, unpivot, transpose, merge, union
│   └── errors                 on_error, lire l'erreur, réparer
│
├── workflows/
│   ├── dag                    depends_on, ordre d'exécution
│   ├── branching              fan-out, fan-in, parallélisme
│   ├── triggers               manual, schedule, webhook
│   └── failures               on_failure, reprise
│
├── blocks/
│   ├── sources                forme du bloc source, par type
│   └── destinations           forme du bloc destination, modes d'écriture
│
└── grammar/
    ├── types-expressions      types, opérateurs, références
    └── schemas                schéma du job et du workflow
```

**18 pages.** Les 18 opérations du moteur sont toutes couvertes :
`filter` (first-job) · `select, rename, cast` (columns) ·
`sort, deduplicate, fill_null, trim, clean` (rows) · `calculate, script` (compute) ·
`aggregate, join` (aggregate) · `pivot, unpivot, transpose, merge, union` (reshape).

## `/guide` — La plateforme

```
/guide
├── index                      Ce qu'on trouve ici, par tâche
│
├── connections/
│   ├── files                  csv, json, parquet
│   ├── databases              mysql, postgresql, mongodb
│   └── webapi                 pagination, retry, auth
│
├── secrets                    ${SECRET.X}, .env, environnements dev/prod
│
├── cli/
│   ├── commands               init, validate, test, run, list, clear
│   └── workflow               hdrctl workflow run / validate / list / init
│
├── api/
│   ├── serve                  hdrctl serve
│   ├── endpoints              /api/run, /api/status, /api/workflows
│   └── monitoring             suivre une exécution
│
├── studio/
│   ├── overview               ce que fait Studio
│   ├── canvas                 construire un workflow visuellement
│   └── run                    exécuter et suivre
│
└── operations/
    ├── scheduling             cron, backfill
    ├── monitoring             journaux, états d'exécution
    └── plugins                auth, cache, retry, pagination, circuit-breaker
```

**16 pages.**

---

## Conséquences à assumer

| Point | Conséquence |
|---|---|
| `guide.html` ✓ | La maquette validée est un catalogue d'éléments du DSL. Elle change de route : `/dsl/catalog`, pas `/guide` |
| `/guide` | Reste entièrement à concevoir — aucune maquette n'existe pour la configuration |
| `/reference` | Disparaît. C'était le doublon de `/guide` dans l'ancien SITEMAP. Les fiches vivent sous `/dsl` |
| `learn.html` ✓ | Devient `/dsl/jobs/first-job` |
| Navigation | `Playground · DSL · Guide · Migrate` — le libellé « Learn » décrivait un mode, pas un sujet |
| Routes | `/learn` disparaît au profit de `/dsl`. Refactor à faire en une seule opération, sur les 13 maquettes |

---

## Ordre de construction

| Lot | Contenu | Pourquoi |
|---|---|---|
| **1** | Noyau de leçon + `/dsl/jobs/first-job` | Valide le gabarit sur la maquette existante |
| **2** | `/` + `/install` | Sans eux, aucune porte de sortie ne résout |
| **3** | `/dsl` — manifest, structure, jobs (9 pages) | Le cœur pédagogique |
| **4** | `/dsl` — workflows, blocks, grammar, catalog (9 pages) | Complète la langue |
| **5** | `/guide` — connections, secrets, cli (6 pages) | |
| **6** | `/guide` — api, studio, operations (9 pages) | Dépend des captures Studio |

Chaque lot est publiable seul.

---

## Assets à fournir

| Asset | Usage |
|---|---|
| 4 à 6 captures de Studio (vue d'ensemble, nœud sélectionné, panneau de config, exécution) | `/guide/studio` |
| 1 GIF de 10 s : créer une connexion entre deux nœuds | `/guide/studio/canvas` |
| Sortie brute de `hdrctl run` (succès) et `hdrctl validate` (échec) | `/guide/cli/commands` |
| Sortie brute de `hdrctl workflow run` | `/guide/cli/workflow` |

Les schémas techniques sont produits en interne, en SVG interactif — une image générée
ne réagit pas au clic et ne s'adapte pas au thème sombre.

---

## Arbitrages ouverts

1. **Volume v1** — les 34 pages, ou les lots 1 à 3 (11 pages) publiés d'abord ?
2. **Exécution** — simulation JS déterministe partout, ou DuckDB-WASM sur
   `/dsl/jobs/aggregate` uniquement (+300 ko sur cette page seule) ?
3. **Progression** — `localStorage` sobre (coché / non coché), ou XP et streak
   comme dans la maquette actuelle ?
4. **Renommage des routes** — `/learn` → `/dsl` maintenant, ou après la validation
   du premier lot ?

---

## Checklist charte, par page

- [ ] Premier geste possible en moins de 5 secondes
- [ ] Moins de 250 mots de prose
- [ ] Les cas non supportés sont affichés, jamais omis
- [ ] Aucun appel réseau au chargement
- [ ] Parcours clavier complet, focus visible
- [ ] Aucun secret en clair, aucun formulaire d'identifiants
- [ ] Tous les liens résolvent
- [ ] Interactions déclenchées par script et comparées à l'attendu
