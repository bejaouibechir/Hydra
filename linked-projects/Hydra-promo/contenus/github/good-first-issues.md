# Tickets GitHub « good first issue » — mode d'emploi pas à pas

> Objectif : montrer que le projet est vivant et accueillir des contributeurs. 6 tickets à créer, ~5 min chacun.
> Tout le texte à coller est en anglais (public). Les consignes sont en français.

## Avant de commencer (à lire une fois)

1. Ouvre https://github.com/bejaouibechir/Hydra/issues/new/choose
2. GitHub affiche **2 formulaires** (les tickets libres sont désactivés sur ton dépôt) :
   - **Feature request** → pour une amélioration (tickets 2 à 6) — 3 champs : *What problem…*, *What would you like Hydra to do?*, *Alternatives you considered*
   - **Bug report** → pour un défaut (ticket 7) — 4 champs obligatoires : *Hydra version*, *Environment*, *Steps to reproduce*, *Expected vs actual behaviour*
3. Clique sur **Get started** à côté du bon formulaire (indiqué en tête de chaque ticket ci-dessous).
4. Remplis **Title**, puis colle chaque bloc dans le champ **du même nom**.
5. Clique **Submit new issue**.
6. Sur la page du ticket créé, panneau de droite : **Labels** → ⚙️ → coche les labels indiqués. Ils existent déjà par défaut sur GitHub (`good first issue`, `enhancement`, `documentation`, `bug`). S'il en manque un : *Issues → Labels → New label*, même nom.
7. Coche la case « Créé » ici.

> ❌ Ticket 1 (analyse des expressions dans `validate --strict`) : **ne pas créer**, Claude l'a déjà corrigé (patch dans `ressources/`, voir `suivi/actions-bechir.md` A1+A2).

---

## Ticket 2 — formulaire **Feature request**

- [ ] Créé

**Title** (1er champ, en haut) :

```
Cross-platform scripts for the examples (bash + Python)
```

**Labels** (panneau de droite, après création) : `good first issue`, `documentation`

**What problem are you trying to solve?**

```
Several helper scripts exist only as Windows .bat files:
- examples/generate_minimal_csv_demo.bat
- examples/mysql_demos/*.bat
- tests/fixtures/csv/generate_mocks.bat

Linux and macOS users cannot run them as-is, so they cannot reproduce the examples.
```

**What would you like Hydra to do?**

```
Add an equivalent next to each .bat file — ideally a small Python script that works on every OS
(or a .sh file) — and mention the command in the example's README.

Acceptance: each example can be generated on Linux/macOS with one documented command.
```

**Alternatives you considered**

```
Keeping .bat only and documenting WSL for Linux/macOS users — rejected, too much friction for a first try.
```

---

## Ticket 3 — formulaire **Feature request**

- [ ] Créé

**Title** (1er champ, en haut) :

```
Add a runnable examples/csv_to_postgres/ with docker compose
```

**Labels** (panneau de droite, après création) : `good first issue`, `enhancement`

**What problem are you trying to solve?**

```
There is no end-to-end example for the most common job: loading a CSV file into PostgreSQL.
```

**What would you like Hydra to do?**

```
- examples/csv_to_postgres/ with the four YAML files (csv source, `type: postgresql` destination, a few steps)
- a docker-compose.yml starting PostgreSQL
- a README: `docker compose up -d`, `hdrctl validate .`, `hdrctl run .`, then a psql query to check the rows
- credentials passed through ${ENV:...}, never in clear

Acceptance: a new user runs the example in under 10 minutes on Linux, macOS or Windows.
```

**Alternatives you considered**

```
Using SQLite to avoid Docker — rejected, Hydra ETL has no SQLite connector and PostgreSQL is the realistic target.
```

---

## Ticket 4 — formulaire **Feature request**

- [ ] Créé

**Title** (1er champ, en haut) :

```
Publish the manifest JSON Schemas to SchemaStore
```

**Labels** (panneau de droite, après création) : `good first issue`, `enhancement`

**What problem are you trying to solve?**

```
Editor completion for Hydra manifests currently requires the Hydra VS Code extension.
JSON Schemas already exist in documentations/chatbot-hydra-dsl/schemas/manifests/*.schema.json.
```

**What would you like Hydra to do?**

```
1. Expose the schemas at stable URLs (e.g. https://hydraetl.com/schemas/...).
2. Open a PR on SchemaStore/schemastore mapping Hydra file patterns to them.

Then VS Code (YAML extension), JetBrains IDEs and others offer completion automatically.
Acceptance: schemas reachable at stable URLs and listed in SchemaStore's catalog.json.
```

**Alternatives you considered**

```
A `# yaml-language-server: $schema=...` comment in each file — works, but every user must add it by hand.
```

---

## Ticket 5 — formulaire **Feature request**

- [ ] Créé

**Title** (1er champ, en haut) :

```
hdrctl validate --format json for CI
```

**Labels** (panneau de droite, après création) : `good first issue`, `enhancement`

**What problem are you trying to solve?**

```
`hdrctl validate` prints human-readable output only. CI jobs and bots cannot parse the result reliably.
```

**What would you like Hydra to do?**

```
Add `--format json` returning {"ok": bool, "errors": [{"file": ..., "message": ...}]}, keeping the exit codes.

Acceptance: documented flag, one test, default output unchanged.
```

**Alternatives you considered**

```
Relying on the exit code only — enough to fail a build, not to show which file is wrong.
```

---

## Ticket 6 — formulaire **Feature request**

- [ ] Créé

**Title** (1er champ, en haut) :

```
Document what validate checks — and what it cannot
```

**Labels** (panneau de droite, après création) : `good first issue`, `documentation`

**What problem are you trying to solve?**

```
Users need to know exactly what `hdrctl validate` guarantees before a run, and what can only fail at run time.
```

**What would you like Hydra to do?**

```
A docs/VALIDATION.md page with two lists:
- checked before run: YAML syntax, schema of each manifest, pipeline from/to references,
  expression syntax in --strict mode
- only detectable at run time: connections/credentials (see `hdrctl test`), data values,
  missing columns, file encodings, database constraints

The maintainer has a draft to start from.
```

**Alternatives you considered**

```
A section in the README — too long for the README, better as a linked page.
```

---

## Ticket 7 — formulaire **Bug report**

- [ ] Créé

> ⚠️ Créer ce ticket **seulement après avoir fusionné le patch** (A1+A2) : c'est le patch qui rend le défaut visible.

**Title** (1er champ, en haut) :

```
Some DSL test fixtures contain expressions pandas rejects
```

**Labels** (panneau de droite, après création) : `good first issue`, `bug`

**Hydra version**

```
0.10.1
```

**Environment**

```
Any OS, Python 3.10, pandas 2.3
```

**Steps to reproduce**

```
1. Use Hydra ETL with the validate --strict expression check (merged on main).
2. hdrctl validate --strict tests/fixtures/dsl_cases/ok_calculate_complex_expr_01
```

**Expected vs actual behaviour**

```
Expected: a fixture named "ok_..." passes strict validation.
Actual: it contains `discount ?? 0`, which pandas rejects at run time (SyntaxError).

Several other fixtures contain `^>` / `^>=`: Windows .bat escape characters that leaked into the YAML
(generated by tests/fixtures/dsl_cases/generate_dsl_cases_series*.bat).

Fix: correct the generator scripts and regenerate the fixtures.
```

---

## Quand les 6 tickets sont créés

- Dis « vérifiez » à Claude : il contrôle titres, labels et contenus sur GitHub.
- Si quelqu'un commente « I'd like to work on this » : réponds `Thanks! It's yours — feel free to ask questions here.` et assigne-le (*Assignees* à droite).

## Historique : les 2 bugs de `validate --strict` (corrigés)

1. Le mode strict lisait `steps` à la racine alors que les exemples utilisent `transformations: steps:` → affichait « aucune » opération.
2. Les expressions `filter` / `calculate` étaient affichées sans être analysées → une expression invalide passait.

Corrigés et testés par Claude le 19/09 (1 136 tests, 0 régression). Patch : `ressources/0001-fix-cli-validate-strict-reads-nested-steps-and-check.patch`.

---

## Ticket 8 — formulaire **Feature request**

- [ ] Créé

**Title** (1er champ, en haut) :
```
Show action output in `hdrctl workflow run`
```
**Labels** (panneau de droite, après création) : `good first issue`, `enhancement`

**What problem are you trying to solve?**
```
When a workflow runs a `python`, `bash` or `powershell` action, whatever the script prints does not appear
in the console. `hdrctl workflow run` only reports the step name, its status and its duration, so a script
that reports a result has to write it to a file for the user to see it.
```
**What would you like Hydra to do?**
```
Print the action's stdout/stderr under the step line (indented), at least with a -v flag.
The runner already captures it (`_action_shell` and `_action_python` in hydra_etl/workflow/runner.py).

Acceptance: `hdrctl workflow run` shows what an action printed, and the default output stays readable.
```
**Alternatives you considered**
```
Writing results to a file and reading it afterwards — works, but it makes a two-line demo need three steps.
```
