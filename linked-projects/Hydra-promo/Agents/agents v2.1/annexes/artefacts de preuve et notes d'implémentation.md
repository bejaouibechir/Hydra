# ANNEXE A : artefacts de preuve et notes d'implémentation (Agents v2.1)

Cette annexe accompagne les prompts `00` à `07`. Elle regroupe les artefacts du Benchmark and Proof Agent, les notes pour les mettre en service et les points encore ouverts. Les fichiers du dossier `benchmark_assets/` restent la source de vérité : le code ci-dessous en est la copie exacte au moment de la génération.

## Sommaire

1. Arborescence cible
2. Prérequis et configuration
3. Spécification du `content_hash`
4. Cycle d'une preuve (n8n, agent, GitHub Actions)
5. Format de `claims.json`
6. Sémantique des verdicts et des causes
7. Sécurité
8. Checklist avant le premier run
9. Points ouverts et limites connues
10. Hors périmètre de cette annexe
11. Historique des versions
12. Artefacts (code complet)

## 1. Arborescence cible

Dans le repo de Hydra ETL :

```
.github/workflows/proof.yml
benchmarks/
├── tools/
│   ├── verdict.py
│   └── content_hash.py          # copié avec verdict.py (import)
└── <proof_id>/                  # un dossier par preuve, branche proof/<proof_id>
    ├── contenu.md               # écrit par n8n, jamais modifié ensuite
    ├── pipelines/               # exemples YAML, écrits par n8n
    ├── claims.json              # produit par le Benchmark and Proof Agent
    ├── baseline/                # configurations des outils concurrents (comparatifs)
    ├── scripts/                 # scripts de vérification référencés par claims.json
    └── requirements.txt         # optionnel
```

Côté n8n, hors repo : `n8n_code_content_hash.js` (Code node) et `test_content_hash_equivalence.py` (test à rejouer à chaque changement de l'algorithme).

## 2. Prérequis et configuration

| Où                            | Élément                                        | Valeur / remarque                                                                                                                                 |
| ----------------------------- | ---------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------- |
| GitHub (Settings > Variables) | `PYPI_PACKAGE`                                 | nom exact du paquet, à confirmer avant tout run                                                                                                   |
| GitHub (Settings > Variables) | `HYDRA_VERSION`                                | version figée par défaut (le champ `hydra_version` du dispatch la remplace)                                                                       |
| GitHub                        | token pour n8n                                 | permissions minimales : Actions (écriture), Contents (écriture sur les branches `proof/*`), Metadata (lecture). Jamais de droit d'administration. |
| Runner auto-hébergé           | label `bench-fixed`                            | `runs-on` utilise la valeur du champ `runner` ; le runner doit porter ce label. Concurrence 1.                                                    |
| Runner auto-hébergé           | description (`runner_spec`)                    | CPU, RAM, OS, responsable, coût : à documenter, sans quoi les benchmarks ne sont pas comparables dans le temps                                    |
| n8n                           | `NODE_FUNCTION_ALLOW_BUILTIN=crypto`           | sans cette variable le Code node ne peut pas charger `crypto`                                                                                     |
| n8n                           | `PYPI_PACKAGE`, `repo_url`, `lab_redirect_url` | injectés dans le bloc commun ; valeur absente ou invalide = `config_manquante`                                                                    |

`BENCH_RUNNER` est positionné automatiquement par le workflow (`true` si `runner == bench-fixed`). Ne le définissez pas à la main.

## 3. Spécification du `content_hash`

Définition complète dans `00_bloc_commun.md`. Résumé opérationnel :

- Fichiers pris en compte : `contenu.md` et tous les fichiers sous `pipelines/`. Rien d'autre (ni `claims.json`, ni scripts).
- Tri lexicographique des chemins relatifs POSIX. Chemins limités à `[A-Za-z0-9._/-]`.
- Pour chaque fichier : l'en-tête `\n--FILE:<chemin>--\n`, puis le contenu normalisé.
- Normalisation : BOM initial retiré, fins de ligne en LF, espaces et tabulations de fin de ligne retirés (U+0020 et U+0009 uniquement), un seul saut de ligne final. Aucune normalisation Unicode (NFC/NFD) : le contenu est haché tel qu'écrit.
- Le placeholder `{{lien_lab}}` fait partie du contenu haché. La substitution par Distribution se fait sur le texte de publication, pas sur le contenu prouvé.
- Deux implémentations de référence, équivalentes : `content_hash.py` (utilisée par `verdict.py`) et `n8n_code_content_hash.js`. Toute modification de l'une impose de modifier l'autre et de rejouer le test d'équivalence.

## 4. Cycle d'une preuve

1. n8n reçoit le JSON du Technical Content Agent, calcule `content_hash` (Code node) et valide la structure.
2. n8n crée la branche `proof/<proof_id>` à partir de la branche principale (elle doit contenir `proof.yml`), écrit `contenu.md` et `pipelines/*` sans les modifier.
3. Le Benchmark and Proof Agent produit `claims.json`, les scripts et la baseline, qui sont ajoutés à la branche (voir point ouvert n° 1).
4. n8n déclenche `proof.yml` sur la branche (`proof_id`, `hydra_version`, `runner`, `content_hash`).
5. `proof-watcher` interroge le run, avec un délai global de 1 h ; dépassement = `A_REVOIR`, cause `infra`.
6. `verdict.py` recalcule le hash avant toute exécution. Hash différent : FAIL immédiat, aucune commande exécutée.
7. n8n télécharge l'artefact `verdict.json` (même si le job est en échec : le script retourne un code non nul sauf PASS, l'upload est en `always()`).
8. PASS : n8n vérifie `manifest_sha256` et transmet à Distribution avec `integrite_verifiee = true`. FAIL ou A_REVOIR : retour à Technical Content avec `retour_contenu`.
9. Les compteurs d'échecs (`compteurs_echecs`) sont tenus par n8n : 3 échecs cumulés sur un `contenu_ref` déclenchent l'escalade à Béchir.

## 5. Format de `claims.json`

Champs communs : `id` (`aff_<contenu_ref>_nn`), `type`, `text`, `check` (commande shell, exécutée depuis le dossier de preuve), `timeout_s` (défaut 300, max 1 800), `expected_stdout_contains`, `expected_files[]`, `allow_http_errors` (défaut `false`).

| Type                     | Champs supplémentaires                                                                  | Remarque                                                                                                                              |
| ------------------------ | --------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------- |
| `code`, `fonctionnalite` | aucun                                                                                   | PASS si code de sortie 0 et sortie attendue présente                                                                                  |
| `performance`            | `claimed` (secondes), `tolerance_pct` (défaut 15)                                       | durée médiane de la commande `check` sur 5 runs, démarrage du processus inclus : le script ne doit contenir que l'exécution à mesurer |
| `comparatif`             | `baseline_check`, `baseline_expected_stdout_contains`, `claimed_ratio`, `tolerance_pct` | ratio = médiane Hydra / médiane baseline ; `claimed_ratio` < 1 signifie que Hydra est annoncé plus rapide                             |
| `opinion`                | aucun (pas de `check`)                                                                  | toujours A_REVOIR : à reformuler ou supprimer                                                                                         |

En tête de fichier : `proof_id` et `content_hash`.

Exemple :

```json
{
  "proof_id": "proof_cont_camp_2026-W46_01_01_v1",
  "content_hash": "<sha256 calculé par n8n>",
  "claims": [
    {"id": "aff_cont_camp_2026-W46_01_01_01", "type": "code",
     "text": "Le pipeline du tutoriel se valide et s'exécute",
     "check": "bash scripts/run_c1.sh",
     "expected_stdout_contains": "OK", "expected_files": ["out/result.csv"], "timeout_s": 300},
    {"id": "aff_cont_camp_2026-W46_01_01_02", "type": "performance",
     "text": "1 M de lignes traitées en 12 s",
     "check": "bash scripts/run_c2.sh", "claimed": 12.0, "tolerance_pct": 15, "timeout_s": 900},
    {"id": "aff_cont_camp_2026-W46_01_01_03", "type": "comparatif",
     "text": "Hydra ETL plus rapide à exécuter que l'alternative sur la même tâche",
     "check": "bash scripts/run_c3_hydra.sh", "baseline_check": "bash baseline/run_c3_other.sh",
     "claimed_ratio": 0.8, "tolerance_pct": 15},
    {"id": "aff_cont_camp_2026-W46_01_01_04", "type": "opinion", "text": "Plus simple que dbt"}
  ]
}
```

## 6. Sémantique des verdicts et des causes

- Verdict global : FAIL l'emporte sur A_REVOIR, qui l'emporte sur PASS. Si toutes les affirmations sont A_REVOIR : `motif_global` renseigné.
- Causes : `produit` (la commande échoue ou dépasse la tolérance), `contenu` (sortie attendue absente, affirmation non vérifiable, chiffre trop prudent), `config_concurrent` (la baseline échoue seule), `timeout`, `infra` (une relance automatique, puis A_REVOIR), `bruit` (écart-type/médiane > 0,15 : A_REVOIR, jamais PASS ni FAIL).
- Les mesures de performance et de comparatif ne comptent que sur `bench-fixed` ; ailleurs : A_REVOIR (cause `infra`).
- Borne basse : médiane inférieure à 50 % du chiffre annoncé, ou ratio inférieur à 50 % du ratio annoncé : A_REVOIR ("non représentatif"). Un chiffre annoncé trop prudent n'est pas validé en silence.
- Mesure partielle : sur échec d'un comparatif, `verdict.json` contient le nombre de runs réussis et les médianes disponibles de chaque côté.

## 7. Sécurité

- Les commandes de `claims.json` sont exécutées avec `shell=True`. Elles proviennent d'un agent IA : traitez-les comme du code non fiable.
- Sur les runners hébergés par GitHub, l'environnement est éphémère. Sur le runner auto-hébergé `bench-fixed`, il ne l'est pas : réservez-le au déclenchement manuel (`workflow_dispatch`) depuis des branches créées par n8n, et n'y faites jamais tourner des pull requests de tiers. Le workflow exclut déjà les PR issues de forks, mais cette protection ne remplace pas le cloisonnement du runner.
- Aucun secret dans les jobs de preuve. `persist-credentials: false` est positionné sur les `checkout`.
- Le token GitHub de n8n est à permissions minimales (section 2).

## 8. Checklist avant le premier run

- [ ] `repo_url` et `pypi_package` confirmés ; `vars.PYPI_PACKAGE` et `vars.HYDRA_VERSION` créées.
- [ ] Commandes `hdrctl` utilisées dans les exemples vérifiées sur la documentation.
- [ ] `verdict.py` et `content_hash.py` copiés dans `benchmarks/tools/`.
- [ ] `python test_content_hash_equivalence.py` affiche `ÉQUIVALENT` sur votre machine.
- [ ] `NODE_FUNCTION_ALLOW_BUILTIN=crypto` actif ; Code node collé et testé sur un contenu d'exemple, hash comparé à celui de `content_hash.py`.
- [ ] Runner `bench-fixed` enregistré, labellisé, décrit (`runner_spec`).
- [ ] Un run de preuve de bout en bout sur un contenu factice (`cont_test_01`) : PASS attendu ; puis une modification d'un caractère dans `contenu.md` : FAIL attendu avant toute exécution.

## 9. Points ouverts et limites connues

1. **Sortie de l'agent Benchmark.** Le prompt `04` demande à l'agent de produire `claims.json`, les scripts et la baseline, mais son schéma de sortie ne décrit que le verdict. Il faut trancher : soit deux appels (un en mode "plan" qui renvoie `claims.json` et les scripts, un en mode "verdict" après exécution), soit un champ de sortie dédié. À décider avant l'implémentation n8n.
2. **Non testé dans les conditions réelles** : `proof.yml` (jamais exécuté sur GitHub), `n8n_code_content_hash.js` dans n8n (testé sous Node 22 seulement), `verdict.py` sur `bench-fixed`, les chemins performance et comparatif de `verdict.py` (seuls les cas `code` et `opinion`, le rejet par hash et le test d'équivalence ont été exécutés).
3. Les noms de paquet, commandes `hdrctl` et options YAML ne sont pas vérifiés : seule la documentation du projet fait foi.
4. Pas d'isolation par conteneur des commandes de preuve (section 7).
5. La détection d'infra repose sur des sous-chaînes (`429`, `503`, `rate limit`, etc.) : `allow_http_errors` en désactive l'effet pour un claim donné, mais d'autres messages d'erreur réseau ne sont pas reconnus.
6. `runner_spec` non défini.

## 10. Hors périmètre de cette annexe

Restent à concevoir côté n8n : `config-check`, pipeline principal, `proof-watcher`, `publish-confirm`, `init-baseline`, les tables de données (`opportunites`, `campagnes`, `contenus`, `preuves`, `publications`, `elements_communaute`, `metriques_hebdo`, `baseline`, `compteurs_echecs`, `journal_audit`), le générateur d'identifiants, la boucle de correction Technical Content / Benchmark et les tests de non-régression des prompts.

## 11. Historique des versions

- **v2.0** : bloc commun, contrats contenu/preuve, campagne/tracking et état persistant, premier `verdict.py`.
- **v2.1** : `run_id`, `dry_run`, liste blanche de versions de schéma, mode dégradé, plafond de volume, compteurs d'échecs centralisés dans n8n, UTM `community` documenté, anti-doublon Distribution sur la cible exacte, placeholder `{{lien_lab}}`, `verdict.py` (recalcul du hash, cause `bruit`, `BENCH_RUNNER`, `allow_http_errors`, mesures partielles, `manifest_sha256`), `content_hash` spécifié exactement et implémenté en Python et en JavaScript avec test d'équivalence (correction de la définition "espaces de fin de ligne").

## 12. Artefacts (code complet)

### 12.1 `.github/workflows/proof.yml`

```yaml
name: proof

on:
  workflow_dispatch:
    inputs:
      proof_id:
        description: "Dossier benchmarks/<proof_id>"
        required: true
      hydra_version:
        description: "Version figée du paquet (ex. 0.11.4)"
        required: true
      runner:
        description: "ubuntu-24.04 (code) ou bench-fixed (performance)"
        required: true
        default: "ubuntu-24.04"
      content_hash:
        description: "SHA-256 du contenu soumis (calculé par n8n)"
        required: true
  pull_request:
    paths:
      - "benchmarks/**"

permissions:
  contents: read

concurrency:
  group: proof-${{ github.event.inputs.proof_id || github.ref }}
  cancel-in-progress: false

jobs:
  validate-structure:
    runs-on: ubuntu-24.04
    outputs:
      proof_id: ${{ steps.p.outputs.proof_id }}
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0
          persist-credentials: false
      - id: p
        run: |
          PID="${{ github.event.inputs.proof_id }}"
          if [ -z "$PID" ]; then
            PID=$(git diff --name-only origin/${{ github.base_ref }}...HEAD | grep '^benchmarks/' | grep -v '^benchmarks/tools' | cut -d/ -f2 | sort -u | head -1)
          fi
          test -n "$PID" || { echo "Aucun proof_id"; exit 1; }
          test -f "benchmarks/$PID/claims.json" || { echo "claims.json manquant"; exit 1; }
          test -f "benchmarks/$PID/contenu.md" || { echo "contenu.md manquant"; exit 1; }
          python3 -c "import json; json.load(open('benchmarks/$PID/claims.json'))"
          echo "proof_id=$PID" >> "$GITHUB_OUTPUT"

  run-proof:
    needs: validate-structure
    if: github.event_name != 'pull_request' || github.event.pull_request.head.repo.full_name == github.repository
    runs-on: ${{ github.event.inputs.runner || 'ubuntu-24.04' }}
    timeout-minutes: 45
    env:
      HYDRA_VERSION: ${{ github.event.inputs.hydra_version || vars.HYDRA_VERSION }}
      PYPI_PACKAGE: ${{ vars.PYPI_PACKAGE }}
      CONTENT_HASH: ${{ github.event.inputs.content_hash }}
      BENCH_RUNNER: ${{ github.event.inputs.runner == 'bench-fixed' && 'true' || 'false' }}
      RUN_URL: ${{ github.server_url }}/${{ github.repository }}/actions/runs/${{ github.run_id }}
      PROOF_ID: ${{ needs.validate-structure.outputs.proof_id }}
    steps:
      - uses: actions/checkout@v4
        with:
          persist-credentials: false

      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"

      - name: Installer Hydra ETL (version figée)
        run: |
          test -n "$PYPI_PACKAGE" || { echo "vars.PYPI_PACKAGE non défini"; exit 1; }
          test -n "$HYDRA_VERSION" || { echo "hydra_version non défini"; exit 1; }
          python -m venv .venv
          . .venv/bin/activate
          pip install "${PYPI_PACKAGE}==${HYDRA_VERSION}"
          hdrctl --version || true

      - name: Installer les dépendances de la preuve
        run: |
          . .venv/bin/activate
          if [ -f "benchmarks/${PROOF_ID}/requirements.txt" ]; then
            pip install -r "benchmarks/${PROOF_ID}/requirements.txt"
          fi

      - name: Exécuter les affirmations et produire le verdict
        run: |
          . .venv/bin/activate
          python benchmarks/tools/verdict.py "benchmarks/${PROOF_ID}"

      - name: Publier le dossier de preuve
        if: always()
        uses: actions/upload-artifact@v4
        with:
          name: proof-${{ env.PROOF_ID }}
          path: benchmarks/${{ env.PROOF_ID }}/
          retention-days: 90
```

### 12.2 `benchmarks/tools/verdict.py`

```python
#!/usr/bin/env python3
"""Benchmark and Proof : verdict.py v2.1
Usage : python verdict.py benchmarks/<proof_id>
Variables d'environnement : CONTENT_HASH, HYDRA_VERSION, RUN_URL, RUNNER_NAME, BENCH_RUNNER, GITHUB_STEP_SUMMARY
"""
import hashlib, json, os, platform, statistics, subprocess, sys, time
from pathlib import Path

from content_hash import compute_content_hash  # même dossier benchmarks/tools/

proof_dir = Path(sys.argv[1])
cfg = json.loads((proof_dir / "claims.json").read_text(encoding="utf-8"))
claims = cfg["claims"]
DEFAULT_TIMEOUT, RUNS_PERF, LOW, MAX_CV = 300, 5, 0.5, 0.15
INFRA = ("Temporary failure", "Connection reset", "429", "503", "rate limit")


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def execute(cmd, timeout, exp_out=None, exp_files=(), allow_http_errors=False):
    for attempt in (1, 2):
        t0 = time.perf_counter()
        try:
            p = subprocess.run(cmd, shell=True, cwd=proof_dir, capture_output=True,
                               text=True, timeout=timeout)
        except subprocess.TimeoutExpired:
            return {"ok": False, "type": "timeout", "detail": f"timeout {timeout}s"}
        dt = time.perf_counter() - t0
        if p.returncode == 0:
            if exp_out and exp_out not in p.stdout:
                return {"ok": False, "type": "contenu", "detail": f"sortie attendue absente: {exp_out!r}"}
            for f in exp_files:
                if not (proof_dir / f).exists():
                    return {"ok": False, "type": "contenu", "detail": f"fichier attendu absent: {f}"}
            return {"ok": True, "dt": dt}
        infra = (not allow_http_errors) and any(s in p.stderr for s in INFRA)
        if infra and attempt == 1:
            continue
        return {"ok": False, "type": "infra" if infra else "produit",
                "detail": f"rc={p.returncode} {p.stderr[-1500:]}"}


def series(cmd, n, timeout, exp_out=None, exp_files=(), allow_http_errors=False):
    times = []
    for _ in range(n):
        r = execute(cmd, timeout, exp_out, exp_files, allow_http_errors)
        if not r["ok"]:
            return times, r
        times.append(r["dt"])
    return times, None


def stats(t):
    return {"runs": len(t), "mediane_s": round(statistics.median(t), 3),
            "ecart_type_s": round(statistics.stdev(t), 3) if len(t) > 1 else 0.0,
            "min_s": round(min(t), 3), "max_s": round(max(t), 3)}


def too_noisy(t):
    if len(t) < 2:
        return False
    med = statistics.median(t)
    return med > 0 and statistics.stdev(t) / med > MAX_CV


def fail(r, err):
    r["verdict"] = "A_REVOIR" if err["type"] == "infra" else "FAIL"
    r["cause_type"], r["cause_detail"] = err["type"], err["detail"]


def write_outputs(overall, motif, results, manifest, computed):
    manifest_sha = hashlib.sha256(json.dumps(manifest, sort_keys=True).encode()).hexdigest()
    out = {"schema_version": "2.1", "proof_id": cfg["proof_id"], "verdict_global": overall,
           "motif_global": motif,
           "content_hash_attendu": os.environ.get("CONTENT_HASH") or cfg.get("content_hash"),
           "content_hash_calcule": computed,
           "environnement": {"runner": os.environ.get("RUNNER_NAME", "local"),
                             "bench_runner": os.environ.get("BENCH_RUNNER") == "true",
                             "os": platform.platform(), "cpu": os.cpu_count(),
                             "python": platform.python_version(),
                             "hydra_version": os.environ.get("HYDRA_VERSION", "inconnue"),
                             "workflow_run": os.environ.get("RUN_URL", "")},
           "affirmations": results, "manifest": manifest, "manifest_sha256": manifest_sha}
    (proof_dir / "verdict.json").write_text(json.dumps(out, indent=2, ensure_ascii=False), encoding="utf-8")
    summ = os.environ.get("GITHUB_STEP_SUMMARY")
    if summ:
        with open(summ, "a", encoding="utf-8") as f:
            f.write(f"## Verdict : {overall}\n\n")
            if motif:
                f.write(f"Motif : {motif}\n\n")
            f.write("| id | type | verdict | cause |\n|---|---|---|---|\n")
            for r in results:
                f.write(f"| {r['id']} | {r['type']} | {r['verdict']} | {r['cause_detail'] or r['mesure']} |\n")
    sys.exit(0 if overall == "PASS" else 1)


def build_manifest():
    return {p.relative_to(proof_dir).as_posix(): sha256(p)
            for p in sorted(proof_dir.rglob("*")) if p.is_file() and p.name != "verdict.json"}


computed = compute_content_hash(proof_dir)
expected = os.environ.get("CONTENT_HASH") or cfg.get("content_hash")
if expected and expected != computed:
    write_outputs("FAIL", "contenu modifié après soumission (content_hash recalculé différent)", [],
                  build_manifest(), computed)

on_bench = os.environ.get("BENCH_RUNNER") == "true"
results = []
for c in claims:
    r = {"id": c["id"], "type": c["type"], "verdict": "A_REVOIR",
         "mesure": {}, "cause_type": None, "cause_detail": None}
    to = c.get("timeout_s", DEFAULT_TIMEOUT)
    exp, files = c.get("expected_stdout_contains"), c.get("expected_files", [])
    ahe = c.get("allow_http_errors", False)
    t = c["type"]
    if t == "opinion" or "check" not in c:
        r["cause_type"], r["cause_detail"] = "contenu", "Non vérifiable : reformuler ou supprimer"
    elif t in ("code", "fonctionnalite"):
        res = execute(c["check"], to, exp, files, ahe)
        if res["ok"]:
            r["verdict"] = "PASS"
        else:
            fail(r, res)
    elif t == "performance":
        times, err = series(c["check"], RUNS_PERF, to, exp, files, ahe)
        if err:
            if times:
                r["mesure"] = stats(times)
            fail(r, err)
        else:
            s = stats(times)
            s["valeur_annoncee"] = c["claimed"]
            r["mesure"] = s
            tol = 1 + c.get("tolerance_pct", 15) / 100
            if not on_bench:
                r["cause_type"], r["cause_detail"] = "infra", "performance mesurée hors runner bench-fixed"
            elif too_noisy(times):
                r["cause_type"], r["cause_detail"] = "bruit", f"écart-type/médiane > {MAX_CV}"
            elif s["mediane_s"] > c["claimed"] * tol:
                r["verdict"], r["cause_type"] = "FAIL", "produit"
                r["cause_detail"] = f"médiane {s['mediane_s']}s > {c['claimed'] * tol:.2f}s"
            elif s["mediane_s"] < c["claimed"] * LOW:
                r["cause_type"], r["cause_detail"] = "contenu", "chiffre annoncé non représentatif (trop prudent)"
            else:
                r["verdict"] = "PASS"
    elif t == "comparatif":
        h, eh = series(c["check"], RUNS_PERF, to, exp, files, ahe)
        b, eb = series(c["baseline_check"], RUNS_PERF, to,
                       c.get("baseline_expected_stdout_contains"), (), ahe)
        if eh or eb:
            fail(r, eh or eb)
            if eb and not eh and eb["type"] != "infra":
                r["cause_type"] = "config_concurrent"
            r["mesure"] = {"hydra_runs_ok": len(h), "baseline_runs_ok": len(b),
                           "hydra_mediane_s": round(statistics.median(h), 3) if h else None,
                           "baseline_mediane_s": round(statistics.median(b), 3) if b else None}
        else:
            ratio = statistics.median(h) / statistics.median(b)
            r["mesure"] = {**stats(h), "baseline_mediane_s": round(statistics.median(b), 3),
                           "baseline_ecart_type_s": stats(b)["ecart_type_s"],
                           "ratio": round(ratio, 3), "valeur_annoncee": c["claimed_ratio"]}
            tol = 1 + c.get("tolerance_pct", 15) / 100
            if not on_bench:
                r["cause_type"], r["cause_detail"] = "infra", "comparatif mesuré hors runner bench-fixed"
            elif too_noisy(h) or too_noisy(b):
                r["cause_type"], r["cause_detail"] = "bruit", f"écart-type/médiane > {MAX_CV}"
            elif ratio > c["claimed_ratio"] * tol:
                r["verdict"], r["cause_type"] = "FAIL", "produit"
                r["cause_detail"] = f"ratio {ratio:.2f} > {c['claimed_ratio'] * tol:.2f}"
            elif ratio < c["claimed_ratio"] * LOW:
                r["cause_type"], r["cause_detail"] = "contenu", "ratio annoncé non représentatif"
            else:
                r["verdict"] = "PASS"
    results.append(r)

vs = {r["verdict"] for r in results}
overall = "FAIL" if "FAIL" in vs else ("A_REVOIR" if "A_REVOIR" in vs else "PASS")
motif = "toutes les affirmations sont A_REVOIR" if vs == {"A_REVOIR"} else None
write_outputs(overall, motif, results, build_manifest(), computed)
```

### 12.3 `benchmarks/tools/content_hash.py`

```python
"""content_hash : implémentation de référence (Python). À copier dans benchmarks/tools/.
Spécification : voir 00_bloc_commun.md. Doit rester strictement équivalente à n8n_code_content_hash.js."""
import hashlib
import re
from pathlib import Path

PATH_RE = re.compile(r"^[A-Za-z0-9._/-]+$")


def normalize_text(raw: bytes) -> bytes:
    s = raw.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    s = "\n".join(line.rstrip(" \t") for line in s.split("\n")).rstrip("\n") + "\n"
    return s.encode("utf-8")


def compute_content_hash(root: Path) -> str:
    files = []
    md = root / "contenu.md"
    if md.is_file():
        files.append(md)
    pip = root / "pipelines"
    if pip.is_dir():
        files += [p for p in pip.rglob("*") if p.is_file()]
    h = hashlib.sha256()
    for p in sorted(files, key=lambda x: x.relative_to(root).as_posix()):
        rel = p.relative_to(root).as_posix()
        if not PATH_RE.match(rel):
            raise ValueError(f"chemin non autorisé (ASCII [A-Za-z0-9._/-] uniquement) : {rel}")
        h.update(f"\n--FILE:{rel}--\n".encode("utf-8"))
        h.update(normalize_text(p.read_bytes()))
    return h.hexdigest()
```

### 12.4 `n8n_code_content_hash.js` (Code node n8n)

```javascript
// n8n Code node : "Run Once for All Items", langage JavaScript.
// Prérequis : variable d'environnement n8n NODE_FUNCTION_ALLOW_BUILTIN=crypto
// Entrée : un item = sortie du Technical Content Agent (contenu_markdown, exemples_code[{fichier, contenu}]).
// Sortie : le même item + content_hash + content_hash_fichiers[].
// Doit rester strictement équivalent à content_hash.py.
const crypto = require('crypto');

const PATH_RE = /^[A-Za-z0-9._\/-]+$/;

function normalizeText(s) {
  s = s.replace(/^\uFEFF/, '').replace(/\r\n/g, '\n').replace(/\r/g, '\n');
  s = s.split('\n').map((l) => l.replace(/[ \t]+$/, '')).join('\n');
  s = s.replace(/\n+$/, '') + '\n';
  return s;
}

function computeContentHash(files) {
  // files : [{ path: 'contenu.md' | 'pipelines/x.yaml', content: string }]
  const seen = new Set();
  for (const f of files) {
    if (!PATH_RE.test(f.path) || f.path.startsWith('/') || f.path.split('/').includes('..')) {
      throw new Error('chemin non autorisé : ' + f.path);
    }
    if (f.path !== 'contenu.md' && !f.path.startsWith('pipelines/')) {
      throw new Error('fichier hors périmètre du hash : ' + f.path);
    }
    if (seen.has(f.path)) throw new Error('chemin en double : ' + f.path);
    seen.add(f.path);
  }
  const sorted = [...files].sort((a, b) => (a.path < b.path ? -1 : a.path > b.path ? 1 : 0));
  const h = crypto.createHash('sha256');
  for (const f of sorted) {
    h.update('\n--FILE:' + f.path + '--\n', 'utf8');
    h.update(normalizeText(f.content), 'utf8');
  }
  return { hash: h.digest('hex'), paths: sorted.map((f) => f.path) };
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { normalizeText, computeContentHash };
}

if (typeof $input !== 'undefined') {
  const item = $input.first().json;
  const files = [{ path: 'contenu.md', content: item.contenu_markdown }];
  for (const ex of item.exemples_code || []) {
    files.push({ path: ex.fichier, content: ex.contenu });
  }
  const { hash, paths } = computeContentHash(files);
  return [{ json: { ...item, content_hash: hash, content_hash_fichiers: paths } }];
}
```

### 12.5 `test_content_hash_equivalence.py`

```python
#!/usr/bin/env python3
"""Vérifie que content_hash.py et n8n_code_content_hash.js produisent le même hash.
Usage : python test_content_hash_equivalence.py   (nécessite node)"""
import json, subprocess, sys, tempfile
from pathlib import Path

HERE = Path(__file__).parent
sys.path.insert(0, str(HERE))
from content_hash import compute_content_hash  # noqa: E402

CASES = {
    "simple": {"contenu.md": "# Titre\nTexte\n", "pipelines/a.yaml": "a: 1\n"},
    "crlf": {"contenu.md": "Bonjour\r\n{{lien_lab}}\r\n", "pipelines/a.yaml": "a: 1\r\nb: 2\r\n"},
    "cr_seul": {"contenu.md": "l1\rl2\r", "pipelines/a.yaml": "x: 1"},
    "bom": {"contenu.md": "\ufeff# Titre\n", "pipelines/a.yaml": "\ufeffa: 1\n"},
    "espaces_fin": {"contenu.md": "ligne   \n\ttab\t\t\n  \nfin  \n", "pipelines/a.yaml": "a: 1   \n"},
    "sans_saut_final": {"contenu.md": "fin sans saut", "pipelines/a.yaml": "a: 1"},
    "sauts_multiples": {"contenu.md": "texte\n\n\n\n", "pipelines/a.yaml": "a: 1\n\n\n"},
    "fichier_vide": {"contenu.md": "", "pipelines/vide.yaml": ""},
    "unicode": {"contenu.md": "Éléphant, données, 日本語, 🙂\n", "pipelines/é.yaml".replace("é", "e"): "n: «x»\n"},
    "nbsp_fin_conserve": {"contenu.md": "ligne\u00a0\n", "pipelines/a.yaml": "a: 1\u00a0\n"},
    "separateurs_exotiques": {"contenu.md": "a\x85\nb\u2028\nc\x1c\n", "pipelines/a.yaml": "k: v\x0c\n"},
    "ordre_fichiers": {"contenu.md": "x\n", "pipelines/b.yaml": "b: 2\n", "pipelines/a.yaml": "a: 1\n",
                       "pipelines/sub/c.yaml": "c: 3\n", "pipelines/B.yaml": "B: 0\n", "pipelines/_z.yaml": "z: 0\n"},
    "placeholder": {"contenu.md": "Essayez : {{lien_lab}}\n", "pipelines/a.yaml": "a: 1\n"},
}


def py_hash(files):
    with tempfile.TemporaryDirectory() as d:
        root = Path(d)
        for rel, txt in files.items():
            p = root / rel
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(txt.encode("utf-8"))
        return compute_content_hash(root)


def js_hash(files):
    payload = json.dumps([{"path": k, "content": v} for k, v in files.items()])
    code = ("const m=require(%r);let s='';process.stdin.on('data',d=>s+=d).on('end',()=>{"
            "console.log(m.computeContentHash(JSON.parse(s)).hash)})" % str(HERE / "n8n_code_content_hash.js"))
    r = subprocess.run(["node", "-e", code], input=payload, capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(r.stderr)
    return r.stdout.strip()


ko = 0
for name, files in CASES.items():
    p, j = py_hash(files), js_hash(files)
    ok = p == j
    ko += not ok
    print(f"{'OK ' if ok else 'KO '} {name:24} {p[:16]} {j[:16]}")

# invariance voulue : CRLF == LF, BOM ignoré, espaces de fin ignorés
inv = [("simple", "crlf_equiv", {"contenu.md": "Bonjour\n{{lien_lab}}\n", "pipelines/a.yaml": "a: 1\nb: 2\n"}, "crlf")]
a, b = py_hash(inv[0][2]), py_hash(CASES["crlf"])
print("OK " if a == b else "KO ", "invariance CRLF/LF")
ko += a != b
# sensibilité voulue : un caractère modifié change le hash
c = dict(CASES["simple"]); c["contenu.md"] = "# Titre\nTexte.\n"
print("OK " if py_hash(c) != py_hash(CASES["simple"]) else "KO ", "sensibilité au contenu")
ko += py_hash(c) == py_hash(CASES["simple"])
# garde-fous : chemin non ASCII et hors périmètre rejetés des deux côtés
for bad in ({"contenu.md": "x\n", "pipelines/é.yaml": "a\n"}, {"contenu.md": "x\n", "autre/a.yaml": "a\n"}):
    try:
        js_hash([bad][0] if False else bad)
        jsrej = False
    except RuntimeError:
        jsrej = True
    try:
        py_hash(bad)
        pyrej = False
    except ValueError:
        pyrej = True
    print("OK " if (jsrej and (pyrej or "autre/" in str(bad))) else "KO ", "rejet chemin :", list(bad)[1])
    ko += not jsrej
print("\nRésultat :", "ÉQUIVALENT" if ko == 0 else f"{ko} divergence(s)")
sys.exit(1 if ko else 0)
```
