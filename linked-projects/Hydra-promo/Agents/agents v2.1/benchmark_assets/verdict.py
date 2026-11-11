#!/usr/bin/env python3
"""Benchmark and Proof : verdict.py v2.1
Usage : python verdict.py benchmarks/<proof_id>
Variables d'environnement : CONTENT_HASH, HYDRA_VERSION, RUN_URL, RUNNER_NAME, BENCH_RUNNER, GITHUB_STEP_SUMMARY
"""
import hashlib, json, os, platform, statistics, subprocess, sys, time
from pathlib import Path

proof_dir = Path(sys.argv[1])
cfg = json.loads((proof_dir / "claims.json").read_text(encoding="utf-8"))
claims = cfg["claims"]
DEFAULT_TIMEOUT, RUNS_PERF, LOW, MAX_CV = 300, 5, 0.5, 0.15
INFRA = ("Temporary failure", "Connection reset", "429", "503", "rate limit")


def normalize_text(raw: bytes) -> bytes:
    s = raw.decode("utf-8-sig").replace("\r\n", "\n").replace("\r", "\n")
    s = "\n".join(line.rstrip() for line in s.split("\n")).rstrip("\n") + "\n"
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
        h.update(f"\n--FILE:{p.relative_to(root).as_posix()}--\n".encode("utf-8"))
        h.update(normalize_text(p.read_bytes()))
    return h.hexdigest()


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
