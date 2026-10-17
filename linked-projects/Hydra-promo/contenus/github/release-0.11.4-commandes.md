# Release 0.11.4 — commandes à exécuter

> **Tout est déjà préparé dans `C:\Users\DELL\Desktop\Hydra`, rien n'est committé.**
> Les commandes git sont à lancer depuis une **invite Windows normale** (PowerShell ou Git Bash) :
> depuis la session Claude, la suppression de fichiers est interdite dans un dossier connecté, donc
> les fichiers `.lock` de git subsistent et bloquent les commandes suivantes.

## État du dépôt préparé

| Fichier | Changement |
|---|---|
| `hydra_etl/internal/connector/postgresql_connector.py` | correctif upsert (3 lignes) + message driver → extra |
| `hydra_etl/internal/connector/mysql_mariadb_connector.py` | message driver → `hydra-etl[mysql]` |
| `hydra_etl/plugins/connectors/mongodb/connector.py` | message driver → `hydra-etl[mongodb]` |
| `hydra_etl/__init__.py` | `__version__` 0.11.3 → **0.11.4** |
| `CHANGELOG.md` | entrée `[0.11.4] — 2026-10-17` (Fixed / Changed / Added) |
| `tests/test_postgresql_upsert_key_validation.py` | **nouveau fichier**, non suivi par git |
| `.github/workflows/ci.yml` | le nouveau test ajoute a `TEST_SET` — **sans ca il ne tourne jamais en CI** |

Fins de ligne LF préservées partout. Aucune autre modification : les 8 fichiers déjà modifiés sur
`main` avant cette session n'ont pas été touchés.

---

## 1. Relire (fais-le vraiment, c'est le seul point non automatisable)

```powershell
cd C:\Users\DELL\Desktop\Hydra
git diff -- hydra_etl/ CHANGELOG.md
type tests\test_postgresall_upsert_key_validation.py
```

> ⚠️ la ligne ci-dessus a une coquille volontaire pour que tu ne la copies pas sans lire :
> le vrai nom est `tests\test_postgresql_upsert_key_validation.py`.

## 2. Verifier les tests localement

### 2a. Le nouveau test

```powershell
python -m pytest tests/test_postgresql_upsert_key_validation.py -v
```

Attendu : **5 passed**.

### 2b. La suite que la CI execute reellement

`ci.yml` ne lance pas `tests/` : il lance les 11 fichiers listes dans `TEST_SET` (12 maintenant,
avec le nouveau). C'est **cette** commande qui predit ta CI :

```powershell
python -m pytest -q tests/test_backend_switch.py tests/test_csv_rust_backend.py tests/test_frame_io_parity.py tests/test_csv_connector.py tests/test_executor.py tests/test_workflow.py tests/test_source_parser.py tests/test_cli_hdrctl.py tests/test_parameters.py tests/test_mcp_server.py tests/test_api_studio.py tests/test_postgresql_upsert_key_validation.py
```

Mesure dans la session (Linux, Python 3.10) : **193 passed, 3 skipped**, zero echec. Sur `HEAD` sans
mes changements, les memes fichiers donnent 186 passed. L'ecart de 7 : 5 tests du nouveau fichier,
plus 2 qui viennent de **ton travail en cours** sur `hdrctl init` (voir l'avertissement plus bas).

### 2c. `python -m pytest tests/` : rouge, et deja rouge avant

La suite entiere donne beaucoup d'echecs — **c'etait deja le cas avant ce correctif**. Sur Windows
il y en a davantage que sur Linux, pour deux raisons propres a la plateforme : des
`PermissionError: [WinError 32]` dans les tests Parquet (un fichier n'est pas referme avant d'etre
rouvert ou supprime — Windows verrouille, pas Linux) et des comparaisons de chemins sensibles a la
casse. Les autres (`'bool' == 'boolean'`, `'dict' object has no attribute 'model_dump'`, schemas DSL
desynchronises) sont reelles mais anterieures.

Pour t'en assurer toi-meme plutot que me croire, compare avec `HEAD` sans toucher a ton dossier :

```powershell
mkdir %TEMP%\hydra-baseline
cd C:\Users\DELL\Desktop\Hydra
git archive HEAD | tar -x -C %TEMP%\hydra-baseline
cd %TEMP%\hydra-baseline
python -m pytest tests/ --ignore=tests/e2e --ignore=tests/docker -q
```

Le nombre d'echecs doit etre le meme, aux tests Parquet pres (le dossier temporaire n'a pas les
memes verrous). **Si un echec apparait chez toi et pas dans le baseline, dis-le-moi avant de
committer.**

> Ces echecs anterieurs meritent leur propre chantier : une suite rouge sur `main` est la raison
> pour laquelle `TEST_SET` a ete reduit a 11 fichiers, et c'est aussi la raison pour laquelle le bug
> d'upsert a pu etre publie. Ce n'est pas le sujet de cette release.

## 3. Ouvrir l'issue (avant le commit, pour pouvoir la référencer)

Texte complet dans `contenus/github/issue-upsert-postgres.md`. Avec la CLI GitHub :

```powershell
cd C:\Users\DELL\Desktop\Hydra
gh issue create --repo bejaouibechir/Hydra ^
  --title "upsert mode on PostgreSQL always fails with KeyError: 0" ^
  --label bug ^
  --body-file "C:\Users\DELL\Desktop\Hydra-promo\contenus\github\issue-upsert-postgres.md"
```

⚠️ Le fichier contient un en-tête français et le message de commit. **Soit** tu colles à la main la
seule section « Corps de l'issue », **soit** tu lances `gh issue create` sans `--body-file` et tu
colles dans l'éditeur. Note le numéro obtenu, il sert à l'étape suivante.

## 4. Committer

```powershell
cd C:\Users\DELL\Desktop\Hydra
git add hydra_etl/internal/connector/postgresql_connector.py ^
        hydra_etl/internal/connector/mysql_mariadb_connector.py ^
        hydra_etl/plugins/connectors/mongodb/connector.py ^
        hydra_etl/__init__.py ^
        CHANGELOG.md ^
        .github/workflows/ci.yml ^
        tests/test_postgresql_upsert_key_validation.py
git status
```

**Verifie que seuls ces 7 fichiers sont indexes.** Ton depot contient 16 autres fichiers modifies non committes — une refonte en cours de `hdrctl init` (CLI, locales, routers API, store, Studio, et son test `tests/test_cli_hdrctl.py`), plus `pyproject.toml` et `MANIFEST.in`. **Ne lance jamais `git add -A` ici.** Ces fichiers n'ont pas ete touches et ne doivent pas partir dans cette release.
puis commite. En PowerShell, avec un fichier de message pour garder les sauts de ligne :

```powershell
git commit -F "C:\Users\DELL\Desktop\Hydra-promo\contenus\github\commit-0.11.4.txt"
```

Ajoute `Closes #<numéro>` à la fin du message si tu as ouvert l'issue à l'étape 3.

## 5. Pousser et attendre la CI

```powershell
git push origin main
gh run list --repo bejaouibechir/Hydra --workflow ci.yml --limit 3
```

**Ne passe à l'étape 6 que si `ci.yml` est verte.** Le tag déclenche la publication PyPI, qui est
irréversible : une version publiée ne peut pas être remplacée, seulement suivie d'une 0.11.5.

## 6. Taguer → publication PyPI + GHCR

```powershell
git tag -a v0.11.4 -m "0.11.4 — fix PostgreSQL upsert key validation"
git push origin v0.11.4
gh run list --repo bejaouibechir/Hydra --workflow release.yml --limit 3
```

`release.yml` vérifie d'abord que le tag correspond à `__version__` (étape « Le tag correspond-il à
__version__ ? »). Comme `__init__.py` est déjà à 0.11.4, ça passe. Il construit, contrôle le wheel,
publie sur PyPI via `pypa/gh-action-pypi-publish`, puis l'image multi-architecture sur GHCR.

## 7. Créer la GitHub Release à la main

**`release.yml` ne crée aucune GitHub Release** — il n'a pas d'étape pour ça. C'est l'explication de
l'anomalie relevée le 17/10 : le tag `v0.11.3` existe et PyPI a bien 0.11.3, mais aucune release
n'apparaît sur le dépôt, et les releases visibles s'arrêtent à 0.11.2.

```powershell
gh release create v0.11.4 --repo bejaouibechir/Hydra ^
  --title "0.11.4" ^
  --notes "PostgreSQL upsert now works. See CHANGELOG.md for details."
```

À faire aussi rétroactivement pour `v0.11.3` si tu veux une histoire de releases continue. Et à
terme : ajouter une étape `gh release create` ou `softprops/action-gh-release` dans `release.yml`,
pour ne plus y penser.

## Conflit possible avec ton travail en cours sur `hdrctl init`

`tests/test_cli_hdrctl.py` dans ton dossier attend desormais que `hdrctl init <nom>` cree un
**projet** (`.hydra/project.json`, `workflow1`, `job1`) et non plus un dossier de job avec
`sources.yaml`, `destinations.yaml`, `pipeline.yaml`, `README.md`. C'est ta refonte en cours.

Consequence directe pour la veille : le brouillon de reponse a `@lij55` et ce mode d'emploi citent
`hdrctl init <nom> --template postgres` en supposant l'ancien comportement. **Si ta refonte sort
dans la meme release, l'instruction donnee a un lecteur exterieur sera fausse.** A trancher :
sortir 0.11.4 avec le seul correctif upsert (recommande — une release de correction, courte et
lisible), et la refonte de `init` dans une 0.12.0 a part.

## 8. Vérifier depuis PyPI, pas depuis ta copie

```powershell
pip install "hydra-etl[postgres]==0.11.4" --force-reinstall
hdrctl --version
```

Puis rejouer un vrai upsert. Dis-le-moi et je refais le scénario complet (source avec fiches
golden/draft/retired/soft-deleted, destination avec PK, trois passes) contre le paquet téléchargé —
c'est cette sortie-là, et pas la nôtre, qui autorise la publication du commentaire à `@lij55`.

---

## Rappel

Ne publie rien sur `minimdm#74` avant l'étape 8 vérifiée. Le commentaire dit à son lecteur
d'installer depuis PyPI : tant que PyPI sert la 0.11.3, l'exemple échoue chez lui.
