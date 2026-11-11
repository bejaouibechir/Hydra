"""Lance une synchronisation Airbyte et attend sa fin (utilisé par les DAG).

  python airbyte_sync.py <nom de la connexion>     ex. orders_main
Code de sortie 0 si la synchronisation réussit, 1 sinon.
"""
import json
import sys
import time
from pathlib import Path

import requests

CFG = json.loads((Path(__file__).parent / "airbyte.json").read_text())
API = "http://localhost:8000/api/public/v1"


def token() -> str:
    """Jeton d'accès (courte durée). Deux chemins selon la version d'Airbyte."""
    body = {"client_id": CFG["client_id"], "client_secret": CFG["client_secret"], "grant-type": "client_credentials"}
    for url in (f"{API}/applications/token", "http://localhost:8000/api/v1/applications/token"):
        r = requests.post(url, json=body, timeout=30)
        if r.ok and "access_token" in r.json():
            return r.json()["access_token"]
    raise SystemExit(f"jeton Airbyte refusé : {r.status_code} {r.text[:300]}")


def sync(name: str) -> int:
    conn = CFG["connections"][name]
    h = {"Authorization": f"Bearer {token()}"}
    job = requests.post(f"{API}/jobs", headers=h, timeout=60,
                        json={"connectionId": conn, "jobType": "sync"}).json()
    print("job", job.get("jobId"), job.get("status"), flush=True)
    if "jobId" not in job:
        print("sync refused:", job)
        return 1
    while True:
        time.sleep(5)
        h = {"Authorization": f"Bearer {token()}"}      # jeton de courte durée
        st = requests.get(f"{API}/jobs/{job['jobId']}", headers=h, timeout=60).json().get("status")
        print("status", st, flush=True)
        if st == "succeeded":
            return 0
        if st in ("failed", "cancelled", "incomplete"):
            why(job["jobId"])
            return 1


def why(job_id) -> None:
    """Raison de l'échec (API de configuration d'Airbyte), pour le journal."""
    try:
        r = requests.post("http://localhost:8000/api/v1/jobs/get", timeout=60, json={"id": job_id},
                          headers={"Authorization": f"Bearer {token()}"}).json()
        for a in (r.get("attempts") or [])[-1:]:
            for f in ((a.get("attempt") or {}).get("failureSummary") or {}).get("failures", [])[:3]:
                print("FAILURE", f.get("failureOrigin"), "|", f.get("externalMessage"), "|",
                      (f.get("internalMessage") or "")[:800], flush=True)
    except Exception as e:  # noqa: BLE001
        print("failure reason unavailable:", e)


if __name__ == "__main__":
    sys.exit(sync(sys.argv[1]))
