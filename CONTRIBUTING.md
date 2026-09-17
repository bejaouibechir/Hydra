# Contributing to Hydra ETL

Thanks for your interest in Hydra! Bug reports, ideas, documentation fixes and pull requests are all welcome.

## Reporting a bug or asking for a feature

Open an [issue](https://github.com/bejaouibechir/Hydra/issues) with:

- your Hydra version (`hdrctl --version`), Python version and OS;
- the manifests involved (remove any secret) and the exact command you ran;
- what you expected and what happened (full error output).

## Development setup

```bash
git clone https://github.com/bejaouibechir/Hydra.git
cd Hydra
python -m venv .venv && source .venv/bin/activate   # Windows: .venv\Scripts\activate
pip install -e ".[dev,all]"
pre-commit install
pytest
```

## Pull requests

1. Open an issue first for anything larger than a small fix, so we can agree on the approach.
2. Create a branch from `main`, keep the change focused, and add or update tests.
3. Make sure `pytest` and `pre-commit run --all-files` pass.
4. Update the docs and `CHANGELOG.md` when behaviour changes.
5. Any change to the YAML DSL must stay backward compatible or be clearly flagged.

## Good first issues

Look for issues labelled [`good first issue`](https://github.com/bejaouibechir/Hydra/labels/good%20first%20issue).

## License

By contributing, you agree that your contributions are licensed under the project's
[AGPL-3.0-or-later](LICENSE) license.
