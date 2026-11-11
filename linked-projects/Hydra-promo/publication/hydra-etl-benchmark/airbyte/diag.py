"""Diagnostic Airbyte : teste chaque source et la destination, puis lance la
découverte du schéma, et affiche la vraie erreur du connecteur.

  cd ~/comparatif-orchestration/airbyte && ~/bench-envs/airbyte/bin/python diag.py
"""
import json
from pathlib import Path

import requests

BASE = "http://localhost:8000"
import re
import subprocess

_cp = Path(__file__).parent / ".credentials.json"
if _cp.exists():
    cred = json.loads(_cp.read_text())
else:   # relire les identifiants auprès d'abctl
    out = subprocess.run("sudo abctl local credentials || sudo ~/.local/bin/abctl local credentials",
                         shell=True, capture_output=True, text=True).stdout
    out = re.sub(r"\x1b\[[0-9;]*m", "", out)
    cred = {"client_id": re.search(r"Client-Id\s*:\s*(\S+)", out).group(1),
            "client_secret": re.search(r"Client-Secret\s*:\s*(\S+)", out).group(1)}
    _cp.write_text(json.dumps(cred))


def token() -> str:
    body = {**cred, "grant-type": "client_credentials"}
    for url in (f"{BASE}/api/public/v1/applications/token", f"{BASE}/api/v1/applications/token"):
        r = requests.post(url, json=body, timeout=30)
        if r.ok and "access_token" in r.json():
            return r.json()["access_token"]
    raise SystemExit(f"token refusé : {r.status_code} {r.text[:300]}")


def h():
    return {"Authorization": f"Bearer {token()}"}


def show(title, r):
    print(f"\n===== {title} → HTTP {r.status_code}")
    try:
        d = r.json()
    except Exception:  # noqa: BLE001
        print(r.text[:2000]); return
    job = d.get("jobInfo") or {}
    print("status:", d.get("status"), "| message:", (d.get("message") or "")[:1500])
    fr = job.get("failureReason") or {}
    if fr:
        print("failure:", json.dumps(fr)[:2500])
    lines = (job.get("logs") or {}).get("logLines") or []
    for ln in lines[-40:]:
        print("  |", ln[:300])


srcs = requests.get(f"{BASE}/api/public/v1/sources", headers=h(), params={"limit": 100}, timeout=60).json()["data"]
dsts = requests.get(f"{BASE}/api/public/v1/destinations", headers=h(), params={"limit": 100}, timeout=60).json()["data"]
for s in srcs:
    print(f"\n### source {s['name']} : {json.dumps(s.get('configuration'))[:400]}")
    show(f"check {s['name']}", requests.post(f"{BASE}/api/v1/sources/check_connection", headers=h(),
                                               json={"sourceId": s["sourceId"]}, timeout=900))
for d in dsts:
    show(f"check {d['name']}", requests.post(f"{BASE}/api/v1/destinations/check_connection", headers=h(),
                                               json={"destinationId": d["destinationId"]}, timeout=900))
for s in srcs[:1]:
    show(f"discover {s['name']}", requests.post(f"{BASE}/api/v1/sources/discover_schema", headers=h(),
                                                  json={"sourceId": s["sourceId"], "disable_cache": True},
                                                  timeout=900))
