#!/usr/bin/env bash
# Build the local Hydra image. The bash twin of build-local.ps1.
#
#   bash GHCR/build-local.sh                 # builds hydra:local
#   bash GHCR/build-local.sh --no-cache      # forces a clean rebuild
#   IMAGE=hydra:test bash GHCR/build-local.sh
#
# Run it with `bash <path>` rather than `./<path>`: that works whatever the
# file's permission bits are, which is one less thing to get wrong on a fresh
# clone or on a checkout made from Windows.
set -euo pipefail

IMAGE="${IMAGE:-hydra:local}"
script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
repo_root="$(dirname -- "$script_dir")"

args=(build --file "$script_dir/Dockerfile" --tag "$IMAGE")
for a in "$@"; do
  [ "$a" = "--no-cache" ] && args+=(--no-cache)
done
args+=("$repo_root")

echo "Building $IMAGE"
docker "${args[@]}"

echo "Image ready: $IMAGE"
docker image inspect "$IMAGE" --format 'Size: {{.Size}} bytes | Created: {{.Created}}'
