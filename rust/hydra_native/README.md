# hydra_native

Native (Rust) accelerators for Hydra ETL. Optional: Hydra runs without this package and uses its Python implementations.

## Contents

| Component | What it does |
|---|---|
| `CsvBatchReader` | Reads a CSV file into `pyarrow.RecordBatch`es of string columns. Tokenization matches Python's `csv` module exactly (see `src/tokenizer.rs`). |
| `CsvFallback` | Raised when a file must be read by Python instead (BOM, invalid UTF-8, NUL byte, non-ASCII dialect, quoted field left open at EOF, field over `csv.field_size_limit()`). `args[1]` holds the number of rows already returned. |

A batch is returned as a list of rows (`list[list[str]]`) instead of a record batch when it contains a row whose field count differs from the header, or when the header has duplicate names. The caller handles those rows the way `csv.DictReader` does.

## Build

The build works offline, with the vendored sources from `scripts/prepare_rust_vendor.sh`:

```bash
cd rust/hydra_native
mkdir -p .cargo
cat > .cargo/config.toml <<EOF
[source.crates-io]
replace-with = "vendored-sources"
[source.vendored-sources]
directory = "/path/to/crates/vendor"
EOF
cargo test --offline                     # Rust unit tests
maturin build --release --offline        # wheel in target/wheels/
pip install target/wheels/hydra_native-*.whl
python -m pytest tests -q                # parity with Python's csv module
```

Requires Rust 1.95 and CPython 3.9 or newer. Wheels are built for one Python version at a time (no `abi3`, because `pyo3-arrow` needs the full C API).
