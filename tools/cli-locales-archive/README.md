# Archived CLI translations

`hdrctl` supports two interface languages: English (`en`) and Spanish (`es`)
(`_SUPPORTED` in `hydra_etl/cli/i18n.py`). These five files were never loaded by
the CLI and were incomplete (83 to 120 keys out of 168). They were moved here (tools/cli-locales-archive/) on
2026-10-22 so the package only ships the languages it supports.

To bring a language back: complete every key of `en.json`, move the file back to
`hydra_etl/cli/locales/`, add the code to `_SUPPORTED`, and the parity test in
`tests/test_cli_locales.py` will check it.
