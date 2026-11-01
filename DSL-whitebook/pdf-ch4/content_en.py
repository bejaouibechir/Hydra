from xml.sax.saxutils import escape as e
R = lambda t: ("role", "Role. " + e(t))
P = lambda t: ("p", e(t))
SPEC = [
("h1", "4. Parameters and secrets"),
("h2", "4.1 Declaration"),
("h3", "parameters (parameters.yaml file at the project root)"),
("code", '''version: "1.0"
parameters:
  min_amount:
    type: float            # int | float | str/string | bool/boolean | json | any (default any)
    default: 50            # value used if none is provided
    required: false        # true: fail if no value is provided
    description: "Minimum threshold"'''),
R("declares configurable project values and their types."),
("h3", "type / default / required / description"),
P("See above. Accepted boolean values: true 1 yes on / false 0 no off."),
("h2", "4.2 Environments"),
("h3", "environments/<env>.yaml"),
("code", '''# environments/prod.yaml
parameters:
  publish_enabled: true
  country: BE'''),
R("overrides parameters for each environment (dev, test, prod)."),
("h3", "--env / HYDRA_ENV: environment selection"),
("code", "hdrctl run . --env prod        # or HYDRA_ENV=prod"),
R("selects the environment configuration file."),
("h3", "--param / -P: value for one run"),
("code", "hdrctl run . --env prod -P min_amount=100 -P country=BE"),
R("overrides parameters for one run. Precedence: run > environment > default."),
("h2", "4.3 Parameter notation"),
("h3", "{{ param:NAME }}: parameter value"),
("code", 'when: "{{ param:publish_enabled }} == True"'),
R("injects a parameter into jobs, params, when and action scripts. Unknown parameters raise an error; a standalone value retains its type."),
("h3", "{{ env:NAME }}: optional environment variable"),
("code", 'base_path: "{{ env:DATA_DIR }}"   # no error if absent'),
R("reads an environment variable without failing if it is missing."),
("h3", "${ENV:NAME}: required environment variable"),
("code", 'host: ${ENV:DB_HOST}   # run stopped: "Missing environment variable: DB_HOST"'),
R("requires an environment variable to be present."),
("h3", "${SECRET:NAME}: secret"),
("code", "password: ${SECRET:db.password}"),
R("injects a sensitive value without writing it into YAML. The value is masked in everything Hydra displays (see 4.6)."),
("h2", "4.4 Secret resolution"),
P("For ${SECRET:db.password}, in this order (the first source that knows the name wins):"),
("table", ([["#", "Source", "Example"],
  ["1", "normalized environment variable (. and - become _, uppercase)", "DB_PASSWORD"],
  ["2", "environment variable with the exact name", "db.password"],
  ["3", "local secrets file, plain text or encrypted with SOPS", ".hydra/secrets"],
  ["4", "provider declared in .hydra/secrets.yaml (Hydra 0.17.0+)", "provider: sops"]],
  [10, 49.6, 327])),
P("The environment (CI, shell, .env) always wins: production can supply every value without any file."),
("h3", ".hydra/secrets: local file"),
("code", '''# name=value, one per line, # = comment
db.password=change-me
api.token="abc 123"
export smtp.password=s3cret'''),
R("local storage created by hdrctl init and included in .gitignore. If the file is encrypted with SOPS, Hydra detects it and decrypts it (see 4.7)."),
("h3", "HYDRA_SECRETS_FILE / --secrets-file: alternate location"),
("code", "hdrctl run . --secrets-file /etc/hydra/secrets"),
R("changes the secrets-file location without modifying the project. Plain or SOPS-encrypted."),
("h3", "secret_defined('NAME'): test for a secret (in when)"),
("code", '''when: "secret_defined('api.token')"'''),
R("runs a step only if the secret exists."),
("h2", "4.5 Secrets settings (Hydra 0.17.0+)"),
("h3", ".hydra/secrets.yaml: visibility and provider"),
("code", '''# .hydra/secrets.yaml: settings only, no secret inside (safe to commit)
visibility: masked                  # plain | masked | hidden (default masked)
provider: sops                      # none (default) | sops
sops:
  file: .hydra/secrets.sops.yaml    # encrypted file, relative to the project root
  format: yaml                      # dotenv | yaml | json (default: from the extension)
  age_key_file: ~/keys/hydra.txt    # optional (default: SOPS_AGE_KEY_FILE)'''),
R("chooses how secrets appear in logs and where they come from. An unknown key, value or provider stops the run with an explicit error. vault, azure-keyvault and aws-secrets-manager are reserved names, not available yet."),
("h2", "4.6 Secret visibility in logs (Hydra 0.17.0+)"),
("table", ([["Mode", "What is displayed", "Use"],
  ["plain", "the value, in clear; a warning reminds it", "debugging only"],
  ["masked", "[MASKED] in place of the value", "default"],
  ["hidden", "the line is omitted and counted: [1 line(s) hidden: they contain a secret]", "strict audits, shared logs"]],
  [10, 90, 380])),
("h3", "--secrets-visibility / HYDRA_SECRETS_VISIBILITY: per run"),
("code", '''hdrctl run . --secrets-visibility hidden
hdrctl workflow run load_sales --secrets-visibility plain   # or HYDRA_SECRETS_VISIBILITY=plain'''),
R("overrides the project setting for one run. Precedence: --secrets-visibility > HYDRA_SECRETS_VISIBILITY > visibility: > masked."),
("h3", "Example"),
("code", '''- name: notify
  type: action
  action: python
  params:
    script: "print('token=${SECRET:api.token}')"
# masked  ->  token=[MASKED]
# hidden  ->  [1 line(s) hidden: they contain a secret]'''),
R("the script still receives the real value; only what is displayed or kept changes."),
("h3", "What is masked"),
P("Logs (every logger, step logs, API, CLI output), error messages and tracebacks, the output of bash, powershell, python and ssh actions, webhook and email log lines, the rollback (undo) report and the runs stored by the API."),
P("Masked forms: the raw value, its URL-encoded form (connection strings), its JSON-escaped form, and each line of a multi-line value (PEM keys). Every value of the secrets file is masked, even if no ${SECRET:} uses it."),
P("Rules: a value shorter than 4 characters is not masked and a warning names it; when two settings disagree for the same value, the strictest wins. Values sent to connectors, scripts and webhooks are never modified."),
("h2", "4.7 Encrypted secrets with SOPS and age (Hydra 0.17.0+)"),
("h3", "Create the key and encrypt the file"),
("code", '''age-keygen -o ~/.config/sops/age/keys.txt        # prints the public key age1...
sops --encrypt --age age1... secrets.yaml > .hydra/secrets.sops.yaml
sops .hydra/secrets.sops.yaml                    # edit: decrypted in the editor only'''),
R("SOPS encrypts the values, not the keys: the file can be committed and reviewed. Install sops and age first (Windows: winget install Mozilla.SOPS FiloSottile.age)."),
("h3", "secrets.yaml before encryption"),
("code", '''db:
  password: change-me     # read as ${SECRET:db.password}
api:
  token: abc123           # read as ${SECRET:api.token}'''),
R("nested keys are joined with dots. Never commit this plain file: delete it once encrypted."),
("h3", "Behaviour"),
P("The file is decrypted in memory on the first secret requested; the clear text never touches the disk. sops chooses the key (age, PGP, cloud KMS); with age, it reads SOPS_AGE_KEY_FILE or sops.age_key_file. HYDRA_SOPS_BIN gives the path of sops when it is not on PATH."),
P("Hydra Studio refuses to edit an encrypted file (edit it with sops). Explicit errors: \"sops is not installed or not on PATH\", \"cannot decrypt ... no age key can open this file\"."),
("h2", "4.8 Passing values to scripts"),
("table", ([["Where", "How the parameter is provided"],
  ["bash, powershell, ssh, python", 'environment variable named after the parameter: $country, $env:country, os.environ["country"]'],
  ["transformation script", 'read-only mapping params["min_amount"]']],
  [10, 223])),
P("Secrets reach a script only through ${SECRET:NAME} written in its params."),
("h2", "4.9 .env files"),
P("The job directory .env takes precedence over the project-root .env (priority: job > root)."),
P("Known limitations: a secret that a script reads directly from the environment, without ${SECRET:} or the secrets file, is not masked; nor is a transformed value (base64, split)."),
]
HEADER = "TECHNICAL REFERENCE"
FOOTER = "hydraetl.com  ·  Hydra DSL v1.0  ·  Hydra 0.16.1"
