# Hydra container — build and run Hydra in Docker

This directory builds Hydra Core, the CLI, the REST API and the compiled Studio
into a single container image, **on your own machine**. Nothing is downloaded
from a registry and nothing is published.

Everything runs the same way on the three systems; only the shell syntax
differs. Pick yours:

- **[Linux](#linux)**
- **[Windows](#windows)**
- **[macOS](#macos)**

Then, whichever system you are on: [use the CLI](#use-the-cli) ·
[check persistence](#check-persistence) · [stop it](#stop-the-local-environment) ·
[what is in the image](#image-contents).

## What you get

One container, one port. Once it is up, `http://localhost:5678` serves:

| Path | What it is |
|---|---|
| `/` | Hydra Studio, the visual editor |
| `/api/health` | health endpoint, reports the version and that Studio is bundled |
| `/docs` | the OpenAPI interface for the REST API |

The service runs as the unprivileged `hydra` user and keeps everything mutable
under `/workspace`, which Compose stores in a named volume so your projects
survive a restart.

---

## Linux

### Prerequisites

- **Docker Engine 24 or newer** with the Compose plugin
  (`docker compose version` must answer; the old `docker-compose` binary is not
  used here).
- Your user in the `docker` group, so you do not need `sudo`:
  `sudo usermod -aG docker "$USER"`, then log out and back in. If you skip this,
  prefix every `docker` command below with `sudo`.
- About 3 GB of free disk for the build layers.

### 1. Build the image

From the repository root:

```bash
bash GHCR/build-local.sh
```

That is a thin wrapper; the command it runs is:

```bash
docker build --file GHCR/Dockerfile --tag hydra:local .
```

The resulting image is named `hydra:local`. Add `--no-cache` to the script to
force a clean rebuild.

### 2. Run the smoke tests

```bash
bash GHCR/test-local.sh
```

It checks the CLI, waits for the container to report healthy, calls the API
health endpoint, loads the Studio page and runs a complete CSV job end to end.
It uses a throwaway container, so it never touches the Compose workspace.

### 3. Start Hydra

```bash
docker compose -f GHCR/compose.yaml up -d
docker compose -f GHCR/compose.yaml ps
```

Open <http://localhost:5678>. To use a different port:
`HYDRA_PORT=8080 docker compose -f GHCR/compose.yaml up -d`.

---

## Windows

### Prerequisites

- **Docker Desktop**, with the **Linux container engine** selected (right-click
  the whale icon: it must not say "Switch to Linux containers").
- **PowerShell 7** or Windows PowerShell 5.1.
- WSL 2 enabled, which Docker Desktop sets up for you.

### 1. Build the image

From the repository root:

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\GHCR\build-local.ps1
```

The `-ExecutionPolicy Bypass` is there so the script runs even on a machine
whose policy blocks local scripts. The command it wraps is:

```powershell
docker build --file .\GHCR\Dockerfile --tag hydra:local .
```

### 2. Run the smoke tests

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\GHCR\test-local.ps1
```

### 3. Start Hydra

```powershell
docker compose -f .\GHCR\compose.yaml up -d
docker compose -f .\GHCR\compose.yaml ps
```

Open <http://localhost:5678>.

---

## macOS

### Prerequisites

- **Docker Desktop for Mac**, or Colima / OrbStack if you prefer them — any of
  them provides `docker` and `docker compose`.
- Docker Desktop must be running before you build: on macOS the Docker daemon
  is a virtual machine, so `docker build` fails with "Cannot connect to the
  Docker daemon" if the app is closed.
- In Docker Desktop, give the VM at least 4 GB of memory
  (Settings → Resources); the Studio build step is the hungry one.

### 1. Build the image

The shell is bash or zsh, so the Linux commands apply unchanged. From the
repository root:

```bash
bash GHCR/build-local.sh
```

**On Apple Silicon (M1 to M4):** you are building the image here rather than
pulling one, so Docker builds it natively for `arm64` and no `--platform` flag
or emulation is involved. If a Python dependency has no arm64 wheel, the build
fails during that step with a compiler error rather than silently producing a
broken image — report it as an issue with the failing package name.

### 2. Run the smoke tests

```bash
bash GHCR/test-local.sh
```

### 3. Start Hydra

```bash
docker compose -f GHCR/compose.yaml up -d
docker compose -f GHCR/compose.yaml ps
```

Open <http://localhost:5678>.

---

## Use the CLI

Against the container's own persistent workspace — identical on every system
apart from the path separator:

```bash
docker compose -f GHCR/compose.yaml run --rm hydra hdrctl --help
docker compose -f GHCR/compose.yaml run --rm hydra hdrctl list /workspace
```

On Windows, write the path as `.\GHCR\compose.yaml`.

To run Hydra against a project in the directory you are standing in, the
current directory is spelled differently by each shell. This is the one line
that genuinely differs, so copy the row for your shell:

| Shell | Command |
|---|---|
| bash / zsh (Linux, macOS) | `docker run --rm -v "$PWD:/project" -w /project hydra:local hdrctl validate .` |
| PowerShell (Windows) | `docker run --rm -v "${PWD}:/project" -w /project hydra:local hdrctl validate .` |
| CMD (Windows) | `docker run --rm -v "%cd%:/project" -w /project hydra:local hdrctl validate .` |

Swap `validate` for `run` to execute the job. A path with spaces is why the
quotes are there; keep them.

## Check persistence

Create a project in the Studio, then restart the service:

```bash
docker compose -f GHCR/compose.yaml restart hydra
```

The project must still be there afterwards. Compose keeps the workspace in the
`hydra-local-workspace` named volume, which outlives the container.

## Stop the local environment

```bash
docker compose -f GHCR/compose.yaml down
```

That keeps your workspace volume. To throw the test data away as well, ask for
it explicitly:

```bash
docker compose -f GHCR/compose.yaml down --volumes
```

## Image contents

- Python 3.12 runtime
- Hydra Core and `hdrctl`
- FastAPI and Uvicorn
- The compiled Hydra Studio
- Connector dependencies: DuckDB, Parquet, MySQL, PostgreSQL, MongoDB and HTTP
