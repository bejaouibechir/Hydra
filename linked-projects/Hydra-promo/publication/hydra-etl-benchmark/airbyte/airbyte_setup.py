"""Configure Airbyte par son API (équivalent des clics dans l'interface) :
sources CSV lues par SFTP (conteneur bench-sftp), destination PostgreSQL,
trois connexions.

Note : la source « File » d'Airbyte force https:// pour une URL web ; un
simple serveur HTTP ne convient donc pas, d'où SFTP.
Idempotent : réutilise ce qui existe déjà sous le même nom.

  python airbyte_setup.py <client_id> <client_secret> <ip de la machine>
Écrit airbyte.json (identifiants des connexions).
"""
import json
import sys
from pathlib import Path

import requests

API = "http://localhost:8000/api/public/v1"
CID, SECRET, HOST = sys.argv[1], sys.argv[2], sys.argv[3]
SFTP = {"storage": "SFTP", "host": HOST, "port": "2222", "user": "bench", "password": "bench"}


def token() -> str:
    """Jeton d'accès (courte durée). Deux chemins selon la version d'Airbyte."""
    body = {"client_id": CID, "client_secret": SECRET, "grant-type": "client_credentials"}
    for url in (f"{API}/applications/token", "http://localhost:8000/api/v1/applications/token"):
        r = requests.post(url, json=body, timeout=30)
        if r.ok and "access_token" in r.json():
            return r.json()["access_token"]
    raise SystemExit(f"jeton Airbyte refusé : {r.status_code} {r.text[:300]}")


def call(method: str, path: str, **kw):
    r = requests.request(method, f"{API}{path}", headers={"Authorization": f"Bearer {token()}"},
                         timeout=120, **kw)
    if r.status_code >= 400:
        raise SystemExit(f"{method} {path} → {r.status_code} {r.text[:800]}")
    return r.json()


ws = call("GET", "/workspaces")["data"][0]["workspaceId"]
print("workspace", ws)


def find_or_create(kind: str, name: str, body: dict) -> str:
    """Réutilise l'élément du même nom (configuration mise à jour) ou le crée."""
    key = {"sources": "sourceId", "destinations": "destinationId", "connections": "connectionId"}[kind]
    for item in call("GET", f"/{kind}", params={"workspaceIds": ws, "limit": 100}).get("data", []):
        if item.get("name") == name:
            if kind != "connections" and "configuration" in body:
                call("PATCH", f"/{kind}/{item[key]}", json={"name": name, "configuration": body["configuration"]})
                print("updated", kind, name)
            else:
                print("exists", kind, name)
            return item[key]
    out = call("POST", f"/{kind}", json={"name": name, **body})
    print("created", kind, name)
    return out[key]


def csv_source(name: str, dataset: str, path: str) -> str:
    return find_or_create("sources", name, {"workspaceId": ws, "configuration": {
        "sourceType": "file", "dataset_name": dataset, "format": "csv", "url": f"/data/{path}",
        "provider": SFTP,
        "reader_options": json.dumps({"dtype": "str"})}})


src_main = csv_source("orders_main", "orders", "orders.csv")
src_backup = csv_source("orders_backup", "orders", "backup/orders.csv")
src_cust = csv_source("customers", "customers", "customers.csv")
dst = find_or_create("destinations", "bench_postgres", {"workspaceId": ws, "configuration": {
    "destinationType": "postgres", "host": HOST, "port": 5433, "database": "bench", "schema": "raw",
    "username": "postgres", "password": "bench", "ssl_mode": {"mode": "disable"},
    "tunnel_method": {"tunnel_method": "NO_TUNNEL"}}})


def connection(name: str, src: str, stream: str) -> str:
    return find_or_create("connections", name, {
        "sourceId": src, "destinationId": dst, "schedule": {"scheduleType": "manual"},
        "namespaceDefinition": "destination",
        "configurations": {"streams": [{"name": stream, "syncMode": "full_refresh_overwrite"}]}})


cfg = {"client_id": CID, "client_secret": SECRET, "connections": {
    "orders_main": connection("orders_main", src_main, "orders"),
    "orders_backup": connection("orders_backup", src_backup, "orders"),
    "customers": connection("customers", src_cust, "customers")}}
(Path(__file__).parent / "airbyte.json").write_text(json.dumps(cfg, indent=1))
print("ok", cfg["connections"])
