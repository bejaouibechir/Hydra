# Guide de test manuel — `hydra`

## Objectif

Valider manuellement la CLI Hydra ETL avec 2 modes d'usage :

1. mode simple : tout le job dans un seul dossier
2. mode compose : fichiers YAML explicites avec `-s/-d/-p/-t`

---

## Préparation

Depuis la racine du projet :

```powershell
cd C:\Users\DELL\Desktop\Hydra
pip install -e .
hydra --version
```

Attendu :

- la commande `hydra` existe
- la version affichée est `1.2.0`

---

## Test 1 — Branding de la CLI

```powershell
hydra --help
```

Attendu :

- le banner affiche `HYDRA ETL`
- les commandes visibles sont `run`, `init`, `test`, `validate`, `list`, `clear`

---

## Test 2 — Création d'un job standard

```powershell
hydra init C:\Temp\hydra_job_basic --template basic
```

Attendu :

- le dossier `C:\Temp\hydra_job_basic` est créé
- les fichiers `sources.yaml`, `destinations.yaml`, `pipeline.yaml`, `transformations.yaml`, `README.md` existent

---

## Test 3 — Validation standard

```powershell
hydra validate C:\Temp\hydra_job_basic
hydra test C:\Temp\hydra_job_basic
```

Attendu :

- la validation passe
- le test passe

---

## Test 4 — Exécution standard avec dossier unique

Préparez un vrai job CSV dans `C:\Temp\hydra_demo_job`.

### `sources.yaml`

```yaml
sources:
  src_users:
    type: csv
    extract:
      table: users.csv
      batch_size: 100
```

### `destinations.yaml`

```yaml
destinations:
  dest_output:
    type: csv
    load:
      table: output.csv
      mode: replace
```

### `pipeline.yaml`

```yaml
pipeline:
  from: src_users
  to: dest_output
```

### `transformations.yaml`

```yaml
steps:
  - filter:
      expr: "active == 'true'"
  - select:
      columns: [id, name]
```

Copiez ensuite `tests\fixtures\csv\users.csv` dans ce dossier sous le nom `users.csv`.

Exécutez :

```powershell
hydra run C:\Temp\hydra_demo_job --dry-run
hydra run C:\Temp\hydra_demo_job
```

Attendu :

- le `dry-run` valide le job sans créer `output.csv`
- le run réel crée `output.csv`
- le pipeline affiche les lignes lues et écrites

---

## Test 5 — Fichiers YAML renommés dans le même dossier

Dans `C:\Temp\hydra_demo_job_alt`, créez ces fichiers :

- `my_sources.yaml`
- `my_destinations.yaml`
- `my_pipeline.yaml`
- `my_transformations.yaml`

Le contenu peut être le même que dans le test 4.

Exécutez :

```powershell
hydra validate C:\Temp\hydra_demo_job_alt `
  -s my_sources.yaml `
  -d my_destinations.yaml `
  -p my_pipeline.yaml `
  -t my_transformations.yaml

hydra test C:\Temp\hydra_demo_job_alt `
  -s my_sources.yaml `
  -d my_destinations.yaml `
  -p my_pipeline.yaml `
  -t my_transformations.yaml

hydra run C:\Temp\hydra_demo_job_alt `
  -s my_sources.yaml `
  -d my_destinations.yaml `
  -p my_pipeline.yaml `
  -t my_transformations.yaml
```

Attendu :

- Hydra ne cherche plus obligatoirement `sources.yaml`, `destinations.yaml`, `pipeline.yaml`, `transformations.yaml`
- le job s'exécute avec les noms explicites

---

## Test 6 — Fichiers répartis dans plusieurs sous-dossiers

Structure proposée :

```text
C:\Temp\hydra_split_job\
  data\
    users.csv
  conf\
    sources_prod.yaml
    destinations_prod.yaml
    pipeline_prod.yaml
  dsl\
    transformations_prod.yaml
```

Exécutez :

```powershell
hydra validate C:\Temp\hydra_split_job `
  -s conf\sources_prod.yaml `
  -d conf\destinations_prod.yaml `
  -p conf\pipeline_prod.yaml `
  -t dsl\transformations_prod.yaml

hydra run C:\Temp\hydra_split_job `
  -s conf\sources_prod.yaml `
  -d conf\destinations_prod.yaml `
  -p conf\pipeline_prod.yaml `
  -t dsl\transformations_prod.yaml
```

Attendu :

- les chemins relatifs sont interprétés relativement à `PATH`
- Hydra exécute correctement le job même si les fichiers sont répartis

---

## Test 7 — Cas d'erreur attendus

### 7.1 fichier source YAML absent

```powershell
hydra run C:\Temp\hydra_split_job -s conf\missing_sources.yaml
```

Attendu :

- message d'erreur clair indiquant le fichier manquant

### 7.2 pipeline incohérent

Dans le fichier pipeline, remplacez `from: src_users` par `from: ghost_source`.

```powershell
hydra validate C:\Temp\hydra_demo_job
```

Attendu :

- erreur explicite sur `pipeline.from`

---

## Test 8 — Raccourcis utiles

```powershell
hydra run C:\Temp\hydra_demo_job -v
hydra run C:\Temp\hydra_demo_job -vv
hydra run C:\Temp\hydra_demo_job -vvv
hydra list C:\Temp
hydra clear
```

Attendu :

- `-v` affiche le résumé du job
- `-vv` ajoute les variables d'environnement
- `-vvv` ajoute le log détaillé
- `list` détecte les jobs standards

---

## Résultat attendu final

La campagne est validée si :

- `hydra` est la commande principale
- le banner affiche `HYDRA ETL`
- le mode standard `hydra run <dossier>` fonctionne
- le mode explicite `hydra run <dossier> -s ... -d ... -p ... -t ...` fonctionne
- `validate` et `test` comprennent les mêmes options explicites
