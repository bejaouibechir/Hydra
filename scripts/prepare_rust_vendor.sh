#!/usr/bin/env bash
# Builds an offline bundle for the Rust integration work (internal tooling).
#
# Run once from WSL on a machine with internet access:
#   wsl bash /mnt/c/Users/DELL/Desktop/Hydra/scripts/prepare_rust_vendor.sh
#
# Output: <Hydra>/_vendor/hydra_rust_vendor.tgz (git-ignored), containing
#   - crates/    : vendored Rust sources (cargo vendor) + Cargo.lock
#   - wheels/    : Python wheels (maturin, pytest, pyarrow) for py3.10 and py3.11
#   - MANIFEST.txt
# The toolchain is pinned to Rust 1.95.0, the version available in the build
# sandbox, so every resolved crate compiles there.
set -euo pipefail

HYDRA_DIR="${1:-/mnt/c/Users/DELL/Desktop/Hydra}"
RUST_VERSION="1.95.0"
WORK="$HOME/hydra_vendor_build"
OUT_DIR="$HYDRA_DIR/_vendor"

step() { printf '\n==> %s\n' "$*"; }

[ -d "$HYDRA_DIR" ] || { echo "Hydra folder not found: $HYDRA_DIR" >&2; exit 1; }

step "1/5 Rust toolchain $RUST_VERSION"
if ! command -v rustup >/dev/null 2>&1; then
  curl --proto '=https' --tlsv1.2 -sSf https://sh.rustup.rs | sh -s -- -y --profile minimal --default-toolchain none
fi
# shellcheck disable=SC1091
source "$HOME/.cargo/env"
rustup toolchain install "$RUST_VERSION" --profile minimal
cargo +"$RUST_VERSION" --version

step "2/5 Cargo manifest (dependencies planned for step 3)"
rm -rf "$WORK" && mkdir -p "$WORK/crate/src" "$WORK/bundle/crates"
cat > "$WORK/crate/Cargo.toml" <<'TOML'
[package]
name = "hydra_native"
version = "0.0.0"
edition = "2024"
rust-version = "1.95"
publish = false

[lib]
crate-type = ["cdylib", "rlib"]

[dependencies]
# No abi3: pyo3-arrow needs the full C API (or abi3-py311). Wheels are built per Python version.
pyo3 = { version = "*", features = ["extension-module"] }
pyo3-arrow = "*"
arrow-array = "*"
arrow-schema = "*"
arrow-csv = "*"
arrow-json = "*"
csv = "*"
serde = { version = "*", features = ["derive"] }
serde_json = "*"
TOML
echo "// placeholder so that cargo can resolve and vendor dependencies" > "$WORK/crate/src/lib.rs"

step "3/5 Resolve (MSRV-aware) and vendor crates"
cd "$WORK/crate"
CARGO_RESOLVER_INCOMPATIBLE_RUST_VERSIONS=fallback cargo +"$RUST_VERSION" generate-lockfile
cargo +"$RUST_VERSION" vendor --versioned-dirs --locked "$WORK/bundle/crates/vendor" > "$WORK/bundle/crates/cargo-config.toml"
cp Cargo.toml Cargo.lock "$WORK/bundle/crates/"
echo "--- duplicated crates (arrow versions must be unique):"
cargo +"$RUST_VERSION" tree -d -e normal --locked 2>/dev/null | grep -E '^(arrow|pyo3)' || echo "none"
# Sanity check: the placeholder crate must build offline with the vendored sources.
mkdir -p .cargo && cp "$WORK/bundle/crates/cargo-config.toml" .cargo/config.toml
sed -i "s#directory = .*#directory = \"$WORK/bundle/crates/vendor\"#" .cargo/config.toml
cargo +"$RUST_VERSION" check --offline --locked -q || { echo "offline check FAILED" >&2; exit 1; }
echo "offline check: OK"

step "4/5 Python wheels (Linux x86_64, CPython 3.10 and 3.11)"
if ! python3 -m pip --version >/dev/null 2>&1; then
  curl -sSL https://bootstrap.pypa.io/get-pip.py -o /tmp/get-pip.py
  python3 /tmp/get-pip.py --user --break-system-packages -q
fi
for PY in 3.10 3.11; do
  python3 -m pip download -q --only-binary=:all: \
    --platform manylinux2014_x86_64 --platform manylinux_2_17_x86_64 --platform manylinux_2_28_x86_64 \
    --python-version "$PY" --implementation cp \
    -d "$WORK/bundle/wheels/py${PY/./}" \
    maturin pytest pyarrow
done

step "5/5 Package"
{
  echo "hydra_rust_vendor - built $(date -u +%Y-%m-%dT%H:%M:%SZ)"
  echo "rustc: $(rustc +"$RUST_VERSION" --version)"
  echo "crates: $(ls "$WORK/bundle/crates/vendor" | wc -l)"
  echo "--- key crates:"
  ls "$WORK/bundle/crates/vendor" | grep -E '^(pyo3|pyo3-arrow|arrow-array|arrow-csv|arrow-json|csv|serde_json)-[0-9]' || true
  echo "--- wheels:"
  (cd "$WORK/bundle/wheels" && ls */)
} > "$WORK/bundle/MANIFEST.txt"
mkdir -p "$OUT_DIR"
tar czf "$WORK/hydra_rust_vendor.tgz" -C "$WORK/bundle" .
cp "$WORK/hydra_rust_vendor.tgz" "$OUT_DIR/"
( cd "$OUT_DIR" && sha256sum hydra_rust_vendor.tgz > hydra_rust_vendor.tgz.sha256 )
cat "$WORK/bundle/MANIFEST.txt"
echo
echo "Done: $OUT_DIR/hydra_rust_vendor.tgz ($(du -h "$OUT_DIR/hydra_rust_vendor.tgz" | cut -f1))"
