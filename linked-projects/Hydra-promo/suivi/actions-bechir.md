# Tes actions — état au 22/09/2026

> Historique complet et décisions : `suivi/journal.md`. Stratégie et feuille de route : `CLAUDE.md` §5.

> Convention : **▶️ À EXÉCUTER** = à toi. **ℹ️ DÉJÀ FAIT** = Claude l'a fait. **📋 POUR INFO** = ne pas exécuter.
> Tout le texte à coller est en anglais et vit dans `contenus/`. Les consignes restent en français.

---

## Article 18456 — publication (26/09)

- [x] **En ligne** (vérifié le 26/09 : listé sur `/blog`, page accessible). ~~Relire la page puis commit + push de `hydra-site` (3 fichiers : `BaseLayout.astro`, `BlogPost.astro`, `src/pages/blog/sql-server-error-18456-login-failed.md`). ℹ️ Build vérifié par Claude : titre, TechArticle, sitemap OK.~~
- [ ] **Indexation** ▶️ Search Console → Inspection d'URL → `https://hydraetl.com/blog/sql-server-error-18456-login-failed/` → Demander l'indexation. **Bing Webmaster Tools** → Soumission d'URL, même adresse (ChatGPT s'appuie sur Bing).
- [ ] Répondre : la commande `docker exec … mssql-tools18 … -C` a-t-elle été exécutée telle quelle ?

## Hydra — Studio ne voit pas les workflows YAML d'un projet clone (27/09)

⚠️ **Meme famille que le bug precedent, et probablement plus genant.** Trouve en testant hydra-demo.

`list_workflows()` (`api/store.py:500`) ne lit que deux sources :

1. `.hydra/workflows/*.json` — metadonnees internes ecrites par Studio ;
2. `workflows/<sous-dossier>/.hydra_workflow.json` — format legacy.

**Un fichier `workflows/mon-workflow.yaml` pose a plat n'est jamais decouvert.** Il tourne pourtant tres bien en
CLI (`hdrctl workflow run`). Resultat : un projet clone depuis git montre « 0 workflow » dans Studio alors que les
manifestes sont la.

Aggravant : le `path` stocke dans ces metadonnees est un **chemin absolu** (`C:\Users\DELL\...` dans
`test_scenarios/first_workflow_demo`). Un projet partage ou clone porte donc un chemin qui n'existe pas chez celui
qui le recoit.

**Le fond du probleme** : pour la CLI, le systeme de fichiers est la source de verite ; pour Studio, ce sont des
metadonnees internes. Les deux divergent des qu'un projet circule.

- [ ] **Decider la source de verite** ▶️ le plus simple et le plus coherent avec le reste d'Hydra : que
  `list_workflows()` **scanne aussi `workflows/*.yaml`** et lise le nom et le trigger dans le YAML lui-meme, comme
  `hdrctl workflow list` le fait deja.
- [ ] **Rendre `path` relatif au projet** ▶️ un chemin absolu dans un fichier destine a etre versionne ne survit pas
  au partage.
- [ ] **Test a ajouter** ▶️ un projet contenant `workflows/x.yaml` et aucun `.hydra/workflows/` doit afficher ce
  workflow dans Studio.

ℹ️ Impact : c'est le parcours exact de quiconque decouvre Hydra par un depot — hydra-demo, un tutoriel, ou le projet
d'un collegue. La CLI marche, Studio semble vide, et l'utilisateur conclut que Studio est casse.

## Hydra — bug Studio : un projet decouvert par scan n'est pas ouvrable (27/09)

⚠️ **Trouve en testant hydra-demo dans un Codespace.** Studio liste le projet (son id apparait dans l'URL) mais
repond « Project not found » a l'ouverture.

Cause, dans `hydra_etl/api/store.py` :

- `list_projects()` **scanne** `WORKSPACE.iterdir()` et lit l'id depuis `.hydra/project.json` (ligne 209) ;
- `get_project(id)` appelle `_resolve_project_path(id)`, qui consulte l'index puis retombe sur
  **`WORKSPACE / project_id`** (ligne 115).

Un projet trouve par scan n'est donc ouvrable que si **le nom de son dossier est exactement son id**. Tout projet
dont l'id differe du nom de dossier est visible mais inutilisable — sauf s'il a ete enregistre dans l'index par
Studio lui-meme.

Contournement applique a hydra-demo : l'id du projet vaut desormais `hydra-demo`, comme le dossier.

- [ ] **Corriger dans Hydra** ▶️ deux pistes, la premiere est la plus propre :
  1. quand `list_projects()` decouvre un projet par scan, **l'ajouter a l'index** (id -> chemin reel) ;
  2. ou faire retomber `_resolve_project_path` sur un scan du workspace a la recherche du `.hydra/project.json`
     portant cet id, au lieu de supposer `WORKSPACE/<id>`.
- [ ] **Ajouter un test** ▶️ un projet dont le dossier ne porte pas le nom de son id doit s'ouvrir.

ℹ️ Impact reel : tout utilisateur qui clone un projet Hydra depuis git tombe dessus, puisque le nom du depot
correspond rarement a l'id genere. C'est exactement le parcours de hydra-demo.

## Codespaces — depot `hydra-demo` pret a creer (27/09)

ℹ️ Projet complet dans `contenus/codespaces/hydra-demo/` (22 fichiers), **teste de bout en bout** avant livraison :
workflow 5 steps sur 5 OK, Studio demarre (API `ok`, HTML servi), jobs dev/prod produisant deux rapports differents.
Decision prise : **depot separe** plutot que dans Hydra, pour que l'essayeur arrive dans ~20 fichiers lisibles au lieu
de 200 fichiers de code Python.

Ce que la demo montre, dans l'ordre du README : un **workflow** avec action bash, deux **jobs**, une action **python**
qui lance un vrai script, un **conteneur MySQL**, **Studio** sur le meme projet, et le parametrage dev/prod.

⚠️ **Depend de la 0.11.3** : `setup.sh` installe `hydra-etl[server]>=0.11.3`, et les manifests utilisent `${SECRET:}`.
A creer seulement une fois la 0.11.3 publiee sur PyPI.

- [ ] **1. Creer le depot public `hydra-demo`** ▶️ sur GitHub (compte `bejaouibechir`), vide, sans README.
- [ ] **2. Pousser le contenu** ▶️ :
  ```
  cd <dossier ou tu clones>
  git clone https://github.com/bejaouibechir/hydra-demo.git
  cd hydra-demo
  cp -a "/c/Users/DELL/Desktop/Hydra-promo/contenus/codespaces/hydra-demo/." .
  git add -A
  git update-index --chmod=+x .devcontainer/setup.sh
  git ls-files -s .devcontainer/setup.sh
  git commit -m "Hydra ETL demo: one-click Codespace with MySQL, Studio and a workflow"
  git push
  ```
  ▶️ `git ls-files -s` doit afficher **100755** pour `setup.sh` (lecon du labo Killercoda).
- [ ] **3. Ouvrir un Codespace depuis le badge** ▶️ et chronometrer le demarrage. Le `postCreateCommand` installe
  Hydra et lance MySQL ; c'est le seul point que je n'ai pas pu tester (pas de daemon Docker ici).
  Verifier ensuite les trois parcours du README.
- [ ] **4. Ajouter le badge dans le README de Hydra** ▶️ une fois le Codespace valide :
  ```
  [![Open in GitHub Codespaces](https://github.com/codespaces/badge.svg)](https://codespaces.new/bejaouibechir/hydra-demo)
  ```

## Hydra — 26 tests rouges en local Windows, a trier (27/09)

ℹ️ Constate en lancant `py -m pytest tests/ -q` le 27/09 : **26 echecs + 3 erreurs, tous anterieurs au correctif
`${SECRET:}`** (verifie : aucun des 9 fichiers concernes ne contient `SECRET`, et un seul fichier de code a ete
modifie). La CI GitHub etait verte pour la 0.11.2, donc ce sont vraisemblablement des echecs **locaux a ta machine**,
pas des regressions. A confirmer par la CI au prochain push.

Quatre familles :

| Famille | Tests | Cause probable |
|---|---|---|
| Verrous de fichiers Parquet (`WinError 5` / `32`) | 7 + 3 erreurs | Windows garde le handle ouvert ; dette deja connue |
| Parser transform renvoie des `dict` au lieu d'objets Pydantic | ~6 | Tests desynchronises du code |
| `dtype 'bool'` attendu `'boolean'`, message « Operation non supportee » | ~6 | Tests desynchronises (pandas recent ?) |
| Fichiers generes obsoletes (`eval-dataset` en 0.9.6, schemas DSL) | 2 | Dettes deja connues |
| `JSONConnector.extract_batches(url=...)` n'existe plus | 2 | Tests obsoletes |

- [ ] **Verifier la CI apres le push de la 0.11.3** ▶️ si elle est verte, ces 26 echecs sont purement locaux et se
  traitent a froid. **Si elle est rouge, me le dire tout de suite** — cela voudrait dire que la dette est reelle et
  qu'elle bloque les releases.
- [ ] **A trier ensuite, par ordre de gout** ▶️ les deux familles « tests desynchronises » (~12 tests) sont les plus
  suspectes : un test qui ne correspond plus au code ne protege plus rien. Dis-moi si tu veux que je les reprenne.

## Hydra — correctif urgent `${SECRET:}` (27/09)

⚠️ **Bug visible publiquement** : le README (lignes 53 et 217) et `docs/6.DSL Hydra.md` documentent
`${SECRET:DB_PASSWORD}` comme moyen de sortir les identifiants d'un manifeste. Or l'executor construisait son
resolver avec un magasin vide (`SecretResolver(secrets={})`), donc **tout** `${SECRET:...}` echouait avec
« Secret manquant ». Un utilisateur qui suivait le README tombait sur un echec.

Corrige : un secret est cherche d'abord dans le magasin injecte (porte ouverte a Vault/AWS), sinon dans
l'environnement du processus, sous le nom en majuscules avec points et tirets convertis en underscores —
`${SECRET:db.password}` lit `DB_PASSWORD`, et la forme documentee `${SECRET:DB_PASSWORD}` marche telle quelle.

Fichiers modifies : `hydra_etl/internal/config/secrets.py`, `tests/test_secrets_resolver.py`, `README.md`,
`CHANGELOG.md`.

Verifie par Claude : 10 cas sur 10 (dont les 5 de non-regression), **plus une preuve de bout en bout** — un vrai
job avec `${SECRET:mysql.user}` / `${SECRET:mysql.password}` echoue avant le correctif et reussit apres
(3 lignes en dev, 5 en prod). Le message d'erreur nomme desormais la variable a definir.

- [ ] **1. Lancer la suite complete** ▶️ (Claude n'a pu tester que le module isole et le bout en bout) :
  ```
  py -m pytest tests/ -q
  ```
  Envoie-moi le resultat. **S'il y a le moindre echec, ne pousse pas.**
- [ ] **2. Bump en 0.11.3** ▶️ dans `hydra_etl/__init__.py` (regle 3.1 : la version n'est ecrite que la).
- [ ] **3. Commit cible** ▶️ (jamais `git add .`) :
  ```
  git add hydra_etl/internal/config/secrets.py tests/test_secrets_resolver.py README.md CHANGELOG.md hydra_etl/__init__.py
  git status
  git commit -m "Fix: ${SECRET:} resolves from the environment when no store is injected"
  git push
  ```
- [ ] **4. Tag et release** ▶️ :
  ```
  git tag v0.11.3
  git push origin v0.11.3
  ```
  Puis verifier l'Action et PyPI, comme pour la 0.11.2.
- [ ] **5. Apres publication** ▶️ le labo Killercoda n°6 pourra montrer `${SECRET:}` en plus de `${ENV:}`.
  Dis-le moi si tu veux que je l'ajoute — pour l'instant le labo n'enseigne que `${ENV:}`, ce qui reste correct.

## Killercoda — labo n°6 « paramètres et secrets » : CORRECTIF à pousser (27/09)

⚠️ **La première version publiée était défectueuse : `/root/lab` n'existait pas.** Cause : Killercoda n'a jamais
exécuté `setup/background.sh`. Le script commence par `set +e` — même si Docker, apt et pip échouaient tous,
`mkdir -p /root/lab` se serait exécuté. Que le dossier n'existe pas prouve que le fichier n'a pas été lancé du tout.
Hypothèse principale : **le bit exécutable perdu au passage par Windows** (`100644` au lieu de `100755` dans git).

Corrigé aussi : le labo est renuméroté **06** (c'est le sixième), le crontab en attente passe à **07**.

- [ ] **1. Confirmer la cause** ▶️ dans ton clone, 10 secondes :
  ```
  git ls-files -s 01-meet-hdrctl/setup/background.sh 07-parameters-and-secrets/setup/background.sh
  ```
  Si le labo 01 affiche `100755` et le 07 `100644`, la cause est confirmée. Dis-le moi dans les deux cas.
- [ ] **2. Pousser le correctif** ▶️ :
  ```
  cd <ton clone hydra-killercoda>
  rm -rf 07-parameters-and-secrets
  cp -a "/c/Users/DELL/Desktop/Hydra-promo/contenus/killercoda/06-parameters-and-secrets" .
  git add -A 06-parameters-and-secrets 07-parameters-and-secrets
  git update-index --chmod=+x 06-parameters-and-secrets/setup/background.sh
  git update-index --chmod=+x 06-parameters-and-secrets/setup/foreground.sh
  git update-index --chmod=+x 06-parameters-and-secrets/step1/verify.sh
  git update-index --chmod=+x 06-parameters-and-secrets/step2/verify.sh
  git update-index --chmod=+x 06-parameters-and-secrets/step3/verify.sh
  git update-index --chmod=+x 06-parameters-and-secrets/step4/verify.sh
  git ls-files -s 06-parameters-and-secrets | grep '\.sh$'
  ```
  ▶️ **Les 6 lignes doivent afficher `100755`.** Si l'une affiche `100644`, arrête-toi et dis-le moi.
  ```
  git commit -m "Fix lab 6: renumber, executable scripts, project files created first"
  git push
  ```
- [ ] **3. Killercoda → Creator** ▶️ *Sync Now*, puis republier. Le titre devient *6. Parameters and secrets*.
- [ ] **4. Rejouer le labo** ▶️ et vérifier d'abord une seule chose : `ls /root/lab` renvoie bien des fichiers.
  Si ça échoue encore : `cat /tmp/setup.log` — le script journalise désormais tout. Envoie-moi ce log.

ℹ️ Durcissements apportés au script : les fichiers du projet sont créés **avant** Docker et pip (donc les étapes 1 et 2
marchent même si l'installation échoue), les deux `docker run` tournent en arrière-plan, repli sur un pip système si
le venv échoue, et toute la sortie est journalisée dans `/tmp/setup.log`.
Revalidé après correction : parcours complet rejoué, **4 étapes sur 4 vertes**.

## Killercoda — 5 scénarios de découverte CLI à publier (26/09)

ℹ️ Le dépôt `hydra-killercoda` existe déjà et est lié à ton profil Creator (`hydra-etl`) — plus besoin de le recréer.
Le lab crontab a été retiré du contenu actif (déplacé dans `contenus/killercoda-archive/`, pas supprimé) et remplacé
par 5 scénarios qui font découvrir `hdrctl` lui-même (install, `validate` vs `run`, `test` vs `validate`, `serve` + `curl`,
`workflow` vs racine) — décision prise ensemble le 26/09. Chaque scénario a été vérifié contre le code source de `Hydra`.

- [ ] **Pousser le nouveau contenu vers `hydra-killercoda`** ▶️ depuis ton clone local du dépôt :
  ```
  cd <ton clone hydra-killercoda>
  rm -rf 01-replace-crontab
  cp -a "C:\Users\DELL\Desktop\Hydra-promo\contenus\killercoda\." .
  git add -A
  git commit -m "Replace crontab lab with 5 CLI-discovery scenarios"
  git push
  ```
  (En Git Bash, adapte le chemin Windows en `/c/Users/DELL/Desktop/Hydra-promo/contenus/killercoda/.` si `cp` ne
  reconnaît pas le chemin `C:\...`, comme la dernière fois.)
- [ ] **Sur killercoda.com → Creator** ▶️ après le push (Sync Now si besoin) :
  - Dépublier / supprimer le scénario crontab existant.
  - Publier les 5 nouveaux : *Meet hdrctl*, *Validate before you run*, *test is not validate*, *hdrctl over HTTP*,
    *hdrctl vs hdrctl workflow*.
- [ ] **Jouer chaque lab une fois en entier** ▶️ et me dire le temps d'installation affiché et tout ce qui accroche.
  ℹ️ Toutes les étapes et leurs `verify.sh` ont été relues contre le comportement réel de `hdrctl` (code source), mais
  aucune n'a pu être rejouée dans un vrai conteneur Killercoda depuis ici.

## Killercoda — labo n°7 crontab prêt, en attente (26/09)

ℹ️ Préparé dans `contenus/killercoda-pending/07-replace-crontab/` (hors du dossier publié, pour qu'un `cp` ne le pousse pas par accident). Titre numéroté « 7. », consignes « Check » ajoutées, étapes 1 à 4 rejouées avec `hydra-etl` 0.11.2 : toutes les vérifications passent. L'étape 5 (`crontab`) avait déjà été validée par toi sur Killercoda.

- [ ] **Publier quand les mesures des 5 labos auront parlé** (1 à 2 semaines : abandons par étape sur Killercoda, trafic `utm_source=killercoda` dans Umami) ▶️
  ```
  cd <ton clone hydra-killercoda>
  cp -a "C:\Users\DELL\Desktop\Hydra-promo\contenus\killercoda-pending\07-replace-crontab" .
  git add -A
  git commit -m "Add scenario 6: replace a fragile crontab"
  git push
  ```
  Puis Sync Now sur killercoda.com.

## Hydra — 2 bugs trouvés en rejouant les labs (26/09)

ℹ️ Trouvés en exécutant réellement les 5 scénarios avec `hydra-etl` 0.11.2. Les labs les contournent déjà.

- [ ] **`hdrctl workflow init` génère un job qui ne tourne pas** ▶️ le filtre placeholder `expr: "1 == 1"` fait échouer `hdrctl workflow run` (`boolean label can not be used without a boolean index`). Et `value` est lu comme texte, donc `value > 6` échoue aussi sans `cast`. Le scaffold devrait tourner tel quel.
- [ ] **`hdrctl validate` affiche « ❌ 0 error(s) detected »** ▶️ quand la seule erreur est `pipeline.from`/`to` introuvable : les erreurs de cohérence ne sont pas ajoutées à `all_errs` (`cmd_validate`, `hdrctl.py`).

## Gratuit et immédiat

- [ ] **Profil C# Corner** ▶️ renseigner `https://hydraetl.com` dans le champ « site web », et ajouter au bio : *« Creator of Hydra ETL, an open-source declarative ETL engine »*. Ce champ apparaît sur tes **119 articles** d'un coup. Pourquoi c'est le meilleur rendement du projet : `CLAUDE.md` §2 bis.
- [ ] **Post LinkedIn n°2** ▶️ texte prêt dans `contenus/posts/linkedin-02-article.md`. Lien du site en 1er commentaire, lien dev.to en 2e.
- [ ] **Glama — « Try in Browser »** ▶️ sur la fiche publique, appeler `hydra_list_operations` et `hydra_list_connectors` pour amorcer le compteur d'usage. C'est le dernier critère actionnable des deux encore en échec (note actuelle : 83 %).

## Chemin critique — rien n'avance sans toi

- [ ] **Recruter 3 utilisateurs pilotes** ▶️ cas réel, retour écrit, accord d'être cités. Pistes : Stack Overflow, r/dataengineering, **r/devops**, tes formations. Kit dans `contenus/pilotes/kit-pilotes.md`.
- [ ] **Mesures du benchmark** ▶️ sur tes deux machines. Protocole : `ressources/benchmark-protocole.md`. J'aurai préparé la page et les scripts avant.
- [ ] **Enregistrer la démonstration** ▶️ d'après le storyboard en 6 plans que je prépare, dont le plan « tentative de sortie du périmètre, refusée ».
- [ ] **Tests E2E du connecteur SQL Server** ▶️ quand le code sera prêt. Docker Desktop, image `mcr.microsoft.com/mssql/server:2022-latest`, ≈2 Go de RAM. **Deux configurations** — Linux conteneurisé et Windows/SQL Express — pour pouvoir annoncer la portabilité honnêtement.

⚠️ Ces quatre points conditionnent le lancement. Pas de Show HN ni de Product Hunt avant les 3 pilotes, la démo et la page benchmark.

## Suivi

- [ ] **PR awesome-mcp-servers #14699** — plus rien à faire : badge posé, 3 labels verts, contrôles 2/2, commentaire posté. Si silence d'ici une semaine, relancer poliment dans le fil.
- [ ] **PR externe #9** — silence depuis le 20/09. Si rien au 25/09 : fusionner et corriger la puce `--strict` toi-même (`contenus/github/pr-9-traitement.md`).

## Intendance

- [ ] **Jeton Umami + accès Search Console** ▶️ sans ça, les rapports hebdomadaires sont aveugles sur le trafic, et l'état réel de l'indexation reste invérifiable — donc les correctifs SEO ne sont pas mesurables.
- [ ] **Après mes correctifs SEO** ▶️ Search Console → inspecter `https://hydraetl.com/` → **Demander l'indexation**.
- [ ] **Compte Buttondown** pour la newsletter.
- [ ] **Remplacer le jeton GitHub classique** par un jeton restreint (dépôt `Hydra` + les forks awesome, expiration 90 jours).
- [ ] **Tâche planifiée Windows** pour ouvrir Claude le samedi à 09 h 50 — procédure dans `suivi/agents.md`. Tu avais dit « on fera ça ensemble ».

## À trancher par toi

- [ ] **Le connecteur SQL Server** est une exception assumée au conseil « arrêter d'ajouter des fonctionnalités ». Justification retenue : c'est le seul connecteur qui ouvre une audience déjà acquise (C# Corner). Tu confirmes.

📋 **Optionnel, cosmétique** : la release Glama s'appelle `0.1.0` alors que PyPI et le `serverInfo` disent `0.10.3`. Pour aligner : onglet Dockerfile → `Build` seul → puis `Make Release` en saisissant `0.10.3`.

---

## FAIT

### 22/09
- [x] Feuille de route révisée (`CLAUDE.md` §2, §2 bis, §5, §9) : promesse unique confirmée, IA sortie de la promesse principale, canaux tranchés, audience C# Corner identifiée
- [x] Audit SEO du site : 6 défauts trouvés en lisant le code, correctifs planifiés

### 21/09
- [x] **Note Glama : 25 % → 83 %**, 8 critères sur 10, `Server Coherence` et `Tool Definition Quality` notés **A**
- [x] **PR awesome-mcp-servers #14699 débloquée** : `missing-glama` → `has-glama`, contrôles 2/2
- [x] **0.10.3 sur PyPI** : serveur MCP en anglais (instructions + 17 tools + `--help`), `serverInfo` complet. 0 régression sur 1158 tests
- [x] `glama.json` au dépôt · badges Glama dans le README · branche `patch-1` nettoyée
- [x] Deux agents hebdomadaires créés (`suivi/agents.md`) · mémoire du projet en place
- [x] awesome-duckdb #353 : ligne corrigée et réponse au mainteneur postée

### 20/09
- [x] **Article n°1 publié** : hydraetl.com/blog/one-million-rows et dev.to (canonical vérifié)
- [x] **0.10.2 sur PyPI**, vérifiée depuis un environnement neuf
- [x] Correctifs `validate --strict` et `workflow run` — 0 régression
- [x] Blog créé sur le site · page `/license` en ligne · mesures Python/Rust complètes
- [x] PR externe #9 : CI approuvée, commentaire de relecture posté

### 19/09
- [x] Dépôt GitHub : description, site, 10 topics, release v0.10.1
- [x] 4 PR « awesome » ouvertes — **awesome-pipeline #246 FUSIONNÉE** ✅
- [x] Post LinkedIn n°1 publié · 6 tickets GitHub créés (#3 à #8)
- [x] Fiches soumises : Glama, AlternativeTo, SaaSHub, LibHunt, SourceForge
