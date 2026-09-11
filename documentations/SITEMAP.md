# Arborescence — hydraetl.com

Statut : `✓` maquetté et validé · `~` gabarit validé, contenu à produire · `✗` à concevoir

---

## Entrée

```
/                                   Accueil                                    ✗
/install                            Installation & quickstart                  ✗
```

`/install` est le point de convergence de tout le site : chaque tunnel de migration, le
générateur de DSL et chaque porte de sortie y renvoient. Rien ne doit être mis en ligne
avant lui.

## La règle de partage

> **Ce qui s'écrit dans un fichier YAML appartient à `/dsl`.
> Ce qui s'écrit dans un terminal ou une interface appartient à `/guide`.**

Partage par objet, pas par mode de lecture. Détail complet : `LEARNING_PATH.md`.

## Manipuler

```
/playground                         Bac à sable — job complet, données réelles ✓  (playground.html)
/build                              Le DSL se forme sous vos yeux              ✓  (dsl-builder.html)
```

## /dsl — La langue

```
/dsl/catalog                        Index A–Z cherchable                       ✓  (guide.html)
/dsl/manifest                       Anatomie d'un manifeste                    ✗
/dsl/structure                      Les 4 fichiers d'un projet                 ✗

/dsl/jobs/first-job                 lire, filtrer, écrire                      ✓  (learn.html)
/dsl/jobs/columns                   select · rename · cast                     ✗
/dsl/jobs/rows                      sort · deduplicate · fill_null · trim · clean  ✗
/dsl/jobs/compute                   calculate · script                         ✗
/dsl/jobs/aggregate                 aggregate · join                           ✗
/dsl/jobs/reshape                   pivot · unpivot · transpose · merge · union    ✗
/dsl/jobs/errors                    on_error — casser, lire, réparer           ✗

/dsl/workflows/dag                  depends_on, ordre d'exécution              ✗
/dsl/workflows/branching            fan-out, fan-in, parallélisme              ✗
/dsl/workflows/triggers             manual · schedule · webhook                ✗
/dsl/workflows/failures             on_failure, reprise                        ✗

/dsl/blocks/sources                 forme du bloc source, par type             ✗
/dsl/blocks/destinations            forme du bloc destination, modes d'écriture    ✗

/dsl/grammar/types-expressions      types, opérateurs, références              ✗
/dsl/grammar/schemas                schéma du job et du workflow               ✗
```

18 pages. Les 18 opérations du moteur sont toutes couvertes. `derive` n'existe pas
dans le moteur — l'ancienne liste de `/reference/operations` était fautive.

## /guide — La plateforme

```
/guide                              Index — par tâche                          ✗

/guide/connections/files            csv · json · parquet                       ✗
/guide/connections/databases        mysql · postgresql · mongodb               ✗
/guide/connections/webapi           pagination · retry · auth                  ✗

/guide/secrets                      ${SECRET.X}, .env, environnements          ✗

/guide/cli/commands                 init · validate · test · run · list · clear    ✗
/guide/cli/workflow                 hdrctl workflow run/validate/list/init     ✗

/guide/api/serve                    hdrctl serve                               ✗
/guide/api/endpoints                /api/run · /api/status · /api/workflows    ✗
/guide/api/monitoring               suivre une exécution                       ✗

/guide/studio/overview              ce que fait Studio                         ✗
/guide/studio/canvas                construire un workflow visuellement        ✗
/guide/studio/run                   exécuter et suivre                         ✗

/guide/operations/scheduling        cron, backfill                             ✗
/guide/operations/monitoring        journaux, états d'exécution                ✗
/guide/operations/plugins           auth · cache · retry · pagination
                                    circuit-breaker                            ✗
```

16 pages, aucune maquette. `/guide` est entièrement à concevoir.

**`/reference` est supprimé** — c'était le doublon de `/guide` dans la version
précédente de ce document. Les fiches d'éléments vivent sous `/dsl`.

## Migrer

```
/migrate                            Comparatif des 6 outils                    ✓  (migrate.html)
/migrate/airflow                    Tunnel — traducteur DAG → manifeste        ✓
/migrate/dagster                    Tunnel — assets, IO managers, checks       ✓
/migrate/prefect                    Tunnel — flows, tasks, cache               ✓
/migrate/dbt                        Cohabitation — sources.yml → ingestion     ✓
/migrate/databricks                 Tunnel — notebooks, bundles, Quartz        ✓
/migrate/airbyte                    Tunnel — connexions, streams, secrets      ✓
```

> **Studio** n'a plus de route propre : il vit sous `/guide/studio`, avec la plateforme.
> Pages de présentation, **pas** un simulateur — décision actée. Captures annotées,
> vidéos de moins de 90 s chargées au clic, et renvoi vers `/install`.

## Produit

```
/roadmap                            Les 3 engines, l'état de chacun            ✗
/changelog                          Versions                                   ✗
```

---

## Décisions de routage à figer avant le build

**URLs sans extension**, en minuscules, avec tirets. Les maquettes utilisent
`migrate-airflow.html` ; la production sert `/migrate/airflow`.

**Le noyau des tunnels est un module unique.** Les six pages partagent environ 80 % de leur
code — tokenizer, menus contextuels, lint, icônes, provenance. Ce noyau vit dans un seul
fichier ; chaque outil n'apporte que ses motifs de reconnaissance et ses verdicts, soit
environ 400 lignes. Ne jamais dupliquer six fichiers.

**Recherche côté client** dès le premier build, index statique.

**Versionnage** : à trancher maintenant. S'il y en a un, les chemins deviennent
`/v1/...` et tout ce qui précède se décale.

**Langue** : contenu du site en anglais, une seule version. L'i18n du produit
(`en`/`es`) ne concerne pas le site.

---

## Compte

| Ensemble | Pages | Faites |
|---|---|---|
| Entrée — `/` et `/install` | 2 | 0 |
| Manipuler — playground, build | 2 | 2 |
| `/dsl` — la langue | 18 | 2 |
| `/guide` — la plateforme | 16 | 0 |
| Migrer | 7 | 7 |
| Produit — roadmap, changelog | 2 | 0 |
| **Total** | **47** | **11** |

S'y ajoutent environ **30 fiches d'éléments** sous `/dsl/catalog/*` (18 opérations,
7 connecteurs, plugins). Elles sont de la duplication sur gabarit validé — `filter` ✓ —
pas de la conception.

Le travail de conception réel tient en **trois pages : `/`, `/install` et l'index
`/guide`**. Tout le reste dérive d'un gabarit existant.
