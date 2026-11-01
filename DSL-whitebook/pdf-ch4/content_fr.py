from xml.sax.saxutils import escape as e
R = lambda t: ("role", "Rôle. " + e(t))
P = lambda t: ("p", e(t))
SPEC = [
("h1", "4. Paramètres et secrets"),
("h2", "4.1 Déclaration"),
("h3", "parameters (fichier parameters.yaml, racine du projet)"),
("code", '''version: "1.0"
parameters:
  min_amount:
    type: float            # int | float | str/string | bool/boolean | json | any (défaut any)
    default: 50            # valeur si rien d'autre n'est fourni
    required: false        # true : le run s'arrête si aucune valeur
    description: "Seuil minimal"'''),
R("déclare les valeurs modifiables d'un projet, avec leur type."),
("h3", "type / default / required / description"),
P("Voir ci-dessus. Booléens acceptés : true 1 yes on / false 0 no off."),
("h2", "4.2 Environnements"),
("h3", "environments/<env>.yaml"),
("code", '''# environments/prod.yaml
parameters:
  publish_enabled: true
  country: BE'''),
R("surcharge des paramètres par environnement (dev, test, prod)."),
("h3", "--env / HYDRA_ENV : choix de l'environnement"),
("code", "hdrctl run . --env prod        # ou HYDRA_ENV=prod"),
R("sélectionne le fichier d'environnement."),
("h3", "--param / -P : valeur pour un seul run"),
("code", "hdrctl run . --env prod -P min_amount=100 -P country=BE"),
R("surcharge ponctuelle. Priorité : run > environnement > défaut."),
("h2", "4.3 Notations"),
("h3", "{{ param:NAME }} : valeur d'un paramètre"),
("code", 'when: "{{ param:publish_enabled }} == True"'),
R("injecte un paramètre dans jobs, params, when et scripts d'action. Erreur si inconnu ; garde son type s'il est seul."),
("h3", "{{ env:NAME }} : variable d'environnement (tolérante)"),
("code", 'base_path: "{{ env:DATA_DIR }}"   # pas d\'erreur si absente'),
R("lire une variable système sans bloquer."),
("h3", "${ENV:NAME} : variable d'environnement (stricte)"),
("code", 'host: ${ENV:DB_HOST}   # run arrêté : "Missing environment variable: DB_HOST"'),
R("exiger une variable."),
("h3", "${SECRET:NAME} : secret"),
("code", "password: ${SECRET:db.password}"),
R("injecter une valeur sensible sans l'écrire dans le YAML. La valeur est masquée dans tout ce que Hydra affiche (voir 4.6)."),
("h2", "4.4 Résolution des secrets"),
P("Pour ${SECRET:db.password}, dans l'ordre (la première source qui connaît le nom l'emporte) :"),
("table", ([["#", "Source", "Exemple"],
  ["1", "variable d'environnement normalisée (. et - deviennent _, majuscules)", "DB_PASSWORD"],
  ["2", "variable d'environnement au nom exact", "db.password"],
  ["3", "fichier de secrets local, en clair ou chiffré par SOPS", ".hydra/secrets"],
  ["4", "fournisseur déclaré dans .hydra/secrets.yaml (Hydra 0.17.0+)", "provider: sops"]],
  [10, 49.6, 327])),
P("L'environnement (CI, shell, .env) l'emporte toujours : la production peut fournir toutes les valeurs sans aucun fichier."),
("h3", ".hydra/secrets : fichier local"),
("code", '''# nom=valeur, une par ligne, # = commentaire
db.password=change-me
api.token="abc 123"
export smtp.password=s3cret'''),
R("stockage local, créé par hdrctl init et ajouté à .gitignore. Si le fichier est chiffré par SOPS, Hydra le détecte et le déchiffre (voir 4.7)."),
("h3", "HYDRA_SECRETS_FILE / --secrets-file : autre emplacement"),
("code", "hdrctl run . --secrets-file /etc/hydra/secrets"),
R("changer le fichier de secrets sans modifier le projet. En clair ou chiffré par SOPS."),
("h3", "secret_defined('NAME') : tester un secret (dans when)"),
("code", '''when: "secret_defined('api.token')"'''),
R("n'exécuter une étape que si le secret existe."),
("h2", "4.5 Réglages des secrets (Hydra 0.17.0+)"),
("h3", ".hydra/secrets.yaml : visibilité et fournisseur"),
("code", '''# .hydra/secrets.yaml : réglages seulement, aucun secret (peut être commité)
visibility: masked                  # plain | masked | hidden (défaut masked)
provider: sops                      # none (défaut) | sops
sops:
  file: .hydra/secrets.sops.yaml    # fichier chiffré, relatif à la racine du projet
  format: yaml                      # dotenv | yaml | json (défaut : selon l'extension)
  age_key_file: ~/keys/hydra.txt    # optionnel (défaut : SOPS_AGE_KEY_FILE)'''),
R("choisit comment les secrets apparaissent dans les logs et d'où ils viennent. Clé, valeur ou fournisseur inconnus : le run s'arrête avec une erreur explicite. vault, azure-keyvault et aws-secrets-manager sont des noms réservés, pas encore disponibles."),
("h2", "4.6 Visibilité des secrets dans les logs (Hydra 0.17.0+)"),
("table", ([["Mode", "Ce qui est affiché", "Usage"],
  ["plain", "la valeur, en clair ; un avertissement le rappelle", "débogage uniquement"],
  ["masked", "[MASKED] à la place de la valeur", "défaut"],
  ["hidden", "la ligne est omise et comptée : [1 line(s) hidden: they contain a secret]", "audits stricts, logs partagés"]],
  [10, 90, 380])),
("h3", "--secrets-visibility / HYDRA_SECRETS_VISIBILITY : pour un run"),
("code", '''hdrctl run . --secrets-visibility hidden
hdrctl workflow run load_sales --secrets-visibility plain   # ou HYDRA_SECRETS_VISIBILITY=plain'''),
R("surcharge le réglage du projet pour un run. Priorité : --secrets-visibility > HYDRA_SECRETS_VISIBILITY > visibility: > masked."),
("h3", "Exemple"),
("code", '''- name: notify
  type: action
  action: python
  params:
    script: "print('token=${SECRET:api.token}')"
# masked  ->  token=[MASKED]
# hidden  ->  [1 line(s) hidden: they contain a secret]'''),
R("le script reçoit toujours la vraie valeur ; seul ce qui est affiché ou conservé change."),
("h3", "Ce qui est masqué"),
P("Les logs (tous les loggers, logs des étapes, API, sortie du CLI), les messages d'erreur et les traces, la sortie des actions bash, powershell, python et ssh, les lignes de log des actions webhook et email, le rapport d'annulation (undo) et les runs conservés par l'API."),
P("Formes masquées : la valeur brute, sa forme encodée dans une URL (chaînes de connexion), sa forme échappée en JSON, et chaque ligne d'une valeur multiligne (clés PEM). Toutes les valeurs du fichier de secrets sont masquées, même si aucun ${SECRET:} ne les utilise."),
P("Règles : une valeur de moins de 4 caractères n'est pas masquée et un avertissement la nomme ; si deux réglages divergent pour une même valeur, le plus strict l'emporte. Les valeurs envoyées aux connecteurs, scripts et webhooks ne sont jamais modifiées."),
("h2", "4.7 Secrets chiffrés avec SOPS et age (Hydra 0.17.0+)"),
("h3", "Créer la clé et chiffrer le fichier"),
("code", '''age-keygen -o ~/.config/sops/age/keys.txt        # affiche la clé publique age1...
sops --encrypt --age age1... secrets.yaml > .hydra/secrets.sops.yaml
sops .hydra/secrets.sops.yaml                    # modifier : déchiffré dans l'éditeur seulement'''),
R("SOPS chiffre les valeurs, pas les clés : le fichier peut être commité et relu. Installer d'abord sops et age (Windows : winget install Mozilla.SOPS FiloSottile.age)."),
("h3", "secrets.yaml avant chiffrement"),
("code", '''db:
  password: change-me     # lu par ${SECRET:db.password}
api:
  token: abc123           # lu par ${SECRET:api.token}'''),
R("les clés imbriquées sont jointes par des points. Ne jamais commiter ce fichier en clair : le supprimer une fois chiffré."),
("h3", "Fonctionnement"),
P("Le fichier est déchiffré en mémoire au premier secret demandé ; le clair ne touche jamais le disque. sops choisit la clé (age, PGP, KMS cloud) ; avec age, il lit SOPS_AGE_KEY_FILE ou sops.age_key_file. HYDRA_SOPS_BIN donne le chemin de sops s'il n'est pas dans le PATH."),
P("Hydra Studio refuse de modifier un fichier chiffré (le modifier avec sops). Erreurs explicites : \"sops is not installed or not on PATH\", \"cannot decrypt ... no age key can open this file\"."),
("h2", "4.8 Transmission aux scripts"),
("table", ([["Où", "Comment le paramètre arrive"],
  ["bash, powershell, ssh, python", 'variable d\'environnement du nom du paramètre : $country, $env:country, os.environ["country"]'],
  ["script de transformation", 'mapping en lecture seule params["min_amount"]']],
  [10, 223])),
P("Un secret n'arrive dans un script que par un ${SECRET:NAME} écrit dans ses params."),
("h2", "4.9 Fichiers .env"),
P("Le .env du dossier du job l'emporte sur celui de la racine du projet (priorité : job > racine)."),
P("Limites connues : un secret qu'un script lit directement dans l'environnement, sans ${SECRET:} ni fichier de secrets, n'est pas masqué ; une valeur transformée (base64, découpée) non plus."),
]
HEADER = "RÉFÉRENCE TECHNIQUE"
FOOTER = "hydraetl.com  ·  Hydra DSL v1.0  ·  Hydra 0.16.1"
