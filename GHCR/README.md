# Hydra container — local test image

This directory builds Hydra Core, the CLI, the API, and the compiled Studio as
one local container image. It does not publish anything to GitHub.

## Prerequisites

- Docker Desktop with the Linux container engine running
- PowerShell 7 or Windows PowerShell 5.1

## 1. Build the image

From the repository root:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\GHCR\build-local.ps1
```

The resulting local image is named `hydra:local`.

## 2. Run automated smoke tests

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\GHCR\test-local.ps1
```

The script verifies the CLI, API health endpoint, and bundled Studio without
publishing the image or modifying the persistent Compose workspace.

## 3. Start Hydra for manual testing

```powershell
docker compose -f .\GHCR\compose.yaml up -d
docker compose -f .\GHCR\compose.yaml ps
```

Open <http://localhost:5678>.

The API health endpoint is available at
<http://localhost:5678/api/health>, and the OpenAPI interface is available at
<http://localhost:5678/docs>.

## 4. Use the CLI

Run the CLI against the same persistent workspace:

```powershell
docker compose -f .\GHCR\compose.yaml run --rm hydra hdrctl --help
docker compose -f .\GHCR\compose.yaml run --rm hydra hdrctl list /workspace
```

To run Hydra against a project in the current host directory:

```powershell
docker run --rm -v "${PWD}:/project" -w /project hydra:local hdrctl validate .
docker run --rm -v "${PWD}:/project" -w /project hydra:local hdrctl run .
```

## 5. Verify persistence

Create a project in the Studio, then restart the service:

```powershell
docker compose -f .\GHCR\compose.yaml restart hydra
```

The project must still be visible after the restart. Compose stores the
workspace in the `hydra-local-workspace` named volume.

## Stop the local environment

```powershell
docker compose -f .\GHCR\compose.yaml down
```

This keeps the workspace volume. To remove the test data as well, explicitly
run `docker compose -f .\GHCR\compose.yaml down --volumes`.

## Image contents

- Python 3.12 runtime
- Hydra Core and `hdrctl`
- FastAPI and Uvicorn
- Compiled Hydra Studio
- DuckDB, Parquet, MySQL, PostgreSQL, MongoDB, and HTTP connector dependencies

The service runs as the unprivileged `hydra` user and stores mutable content
under `/workspace`.
