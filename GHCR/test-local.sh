#!/usr/bin/env bash
# Smoke-test the local Hydra image. The bash twin of test-local.ps1.
#
#   bash GHCR/test-local.sh
#   IMAGE=hydra:test bash GHCR/test-local.sh
#
# Uses a throwaway container, so it never touches the Compose workspace.
set -euo pipefail

IMAGE="${IMAGE:-hydra:local}"
container="hydra-smoke-$$"

# Remove the container whatever happens, including on Ctrl-C.
cleanup() {
  docker rm --force "$container" >/dev/null 2>&1 || true
}
trap cleanup EXIT

echo "Checking the CLI"
docker run --rm "$IMAGE" hdrctl --version
docker run --rm "$IMAGE" hdrctl --help >/dev/null

echo "Starting an isolated Hydra container"
docker run --detach --name "$container" "$IMAGE" >/dev/null

ready=0
for _ in $(seq 1 30); do
  health="$(docker inspect --format '{{.State.Health.Status}}' "$container" 2>/dev/null || echo starting)"
  if [ "$health" = "healthy" ]; then ready=1; break; fi
  sleep 1
done
if [ "$ready" -ne 1 ]; then
  echo "Hydra did not become healthy within 30 seconds. Container logs:" >&2
  docker logs "$container" >&2
  exit 1
fi

echo "Checking the API response"
docker exec "$container" python -c "import json,urllib.request; d=json.load(urllib.request.urlopen('http://127.0.0.1:5678/api/health')); assert d['status']=='ok'; assert d['studio']=='bundled'; print(json.dumps(d, indent=2))"

echo "Checking the Studio entry page"
docker exec "$container" python -c "import urllib.request; r=urllib.request.urlopen('http://127.0.0.1:5678/'); body=r.read().lower(); assert r.status==200 and b'<html' in body; print('Studio: HTTP 200')"

echo "Checking a complete CSV job"
docker exec "$container" sh -c "hdrctl init /workspace/smoke-job --template csv && hdrctl validate /workspace/smoke-job && hdrctl run /workspace/smoke-job && test -f /workspace/smoke-job/data/output.csv"

echo "All local image smoke tests passed."
