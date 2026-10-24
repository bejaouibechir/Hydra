### Fixed

- `${SECRET:NAME}` now resolves. Until this release the CLI built its resolver with an empty
  secret store, so every `${SECRET:...}` placeholder failed with a missing-secret error — even
  though the README and the DSL reference documented it as the supported way to keep credentials
  out of a manifest.

  A secret is now looked up in the injected store first, which leaves the door open for Vault, AWS
  or Azure backends, and otherwise in the process environment, under the name upper-cased with dots
  and dashes turned into underscores. So `${SECRET:db.password}` reads `DB_PASSWORD`, and the
  documented `${SECRET:DB_PASSWORD}` works as written. When a secret really is missing, the error
  now names the environment variable to define.

**Install:** `pip install hydra-etl==0.11.3`
