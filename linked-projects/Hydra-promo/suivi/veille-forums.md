# Veille forums — discussions où Hydra ETL est une réponse légitime

> Fichier tenu par l'agent de veille hebdomadaire (samedi matin). Le plus récent en haut.
> **Règle :** l'agent prépare, **Bechir publie**. Rien n'est posté automatiquement.
> Toute discussion listée ici est considérée comme traitée et ne sera jamais reproposée.

---

## Semaine du 24 octobre 2026 — **0 nouvelle discussion retenue, 1 suivi à publier**

**Résultat : aucune discussion nouvelle ne qualifie cette semaine.** Ce n'est pas un défaut
d'accès — le balayage a tourné, et plus largement que les semaines précédentes (voir le tableau
des sources). C'est le gisement qui est vide : sur les quatre terrains atteignables, aucun besoin
réel exprimé dans la fenêtre de 10 jours auquel Hydra ETL réponde mieux qu'une autre piste.

**Mais la semaine n'est pas vide pour autant.** Deux choses sont arrivées sur le fil déjà traité
`minimdm#74`, et elles valent plus que trois discussions neuves : **l'auteur de l'issue dit qu'il
va essayer Hydra ETL**, et le mainteneur a relevé **deux erreurs techniques** dans le commentaire
publié. Un suivi court et testé est prêt ci-dessous. Et un concurrent très proche est apparu.

### État des sources (progrès réel : l'API Stack Exchange est exploitable)

| Source | État cette semaine | Verdict |
|---|---|---|
| **API Stack Exchange** (`api.stackexchange.com`, via `fetch` dans le navigateur intégré) | **Fonctionne, sans CAPTCHA** | **Nouveau. C'est la bonne porte d'entrée pour Stack Overflow** — et elle donne aussi dba, datascience, softwareengineering. Plus besoin de passer par `/search` |
| **GitHub** (recherche web dans le navigateur intégré) | Fonctionne (issues + discussions, `created:>=`) | Toujours la source la plus riche, mais la recherche plein texte ne respecte pas les guillemets : les phrases exactes remontent du bruit |
| **Hacker News** (API Algolia) | Fonctionne **depuis le navigateur intégré uniquement** | Le proxy du conteneur cloud refuse désormais `hn.algolia.com` (`connect_rejected`). À faire depuis le navigateur |
| Reddit (r/dataengineering, r/Python) | Refusé (proxy cloud *et* `fetch` depuis le navigateur : CORS) | Structurel. Ne plus réessayer |
| discuss.python.org (API de recherche) | Fonctionne | **Tari** : 0 résultat pour etl, csv+database, data pipeline, parquet depuis le 10/10 |
| API GitHub inter-dépôts (`gh api search/issues`) | `403` — session liée à ses seuls dépôts | Inchangé |

**Stack Overflow reste confirmé mort sur les tags data**, cette fois mesuré par l'API et non à l'œil :
dernière question `[etl]` **13 août**, `[airflow]` **8 septembre**, `[data-engineering]` **18 juin**,
`[duckdb]` **10 août**. Zéro question dans la fenêtre sur sept tags. Le balayage mensuel décidé la
semaine dernière est le bon réglage ; il coûte maintenant un seul appel d'API.

---

### 1 — Suivi · GitHub `planemarlin/minimdm` #74 (fil déjà traité le 18/10)

- **Lien :** <https://github.com/planemarlin/minimdm/issues/74> — **toujours ouvert**
- **Ce qui s'est passé :** Bechir a publié le 18/10. Le commentaire a reçu un 👍, le mainteneur a
  remercié « *and for disclosing your connection to Hydra ETL* », et surtout **`@lij55`, l'auteur de
  l'issue, a répondu : « I will try the hook and Hydra ETL and check whether it could solve my
  problem! »** Il précise son contexte : Debezium pour le temps réel MySQL → PostgreSQL, dbt en ELT.
  Le mainteneur a conclu en demandant à `@lij55` de revenir dire ce qu'il a retenu.
- **Pourquoi c'est le point le plus important de la semaine :** c'est le premier essai annoncé par un
  utilisateur extérieur venant de la veille. Le verrou de `CLAUDE.md` demande **3 pilotes avec cas
  réel** ; voilà un candidat qui s'est déclaré de lui-même, sur un besoin précis et documenté.
- **Les deux corrections du mainteneur, toutes deux justes :**
  1. **La clé primaire est `_id`, pas `record_id`.** `record_id` est le nom du champ dans la charge
     utile du webhook, pas une colonne des tables. Le `SELECT record_id, …` et le `key: [record_id]`
     publiés **échoueraient** contre une vraie base miniMDM.
  2. **Le filtre `_state = 'active' AND _deleted_at IS NULL` perd les rétractations.** Une fiche
     retirée ou supprimée cesse simplement d'apparaître dans le résultat : la ligne reste dans
     l'entrepôt comme si elle était toujours golden. C'est un vrai défaut de la réponse publiée,
     pas une nuance.
- **Hydra ETL est-il pertinent pour le suivi ? → oui, mais à dose minimale.** Le mainteneur a écrit
  noir sur blanc que miniMDM ne recommande pas d'outils tiers. Le suivi doit donc être d'abord une
  **réponse technique à sa correction** ; Hydra ETL n'y apparaît que comme « et voici le changement
  d'une ligne dans le chargeur », sans nouvelle plaidoirie.

**Brouillon de suivi (EN) — un seul commentaire, à publier sur l'issue :**

> @planemarlin is right on both counts, and the second one is the half that matters: an incremental
> load filtered on `_state = 'active' AND _deleted_at IS NULL` can never retract anything. A record
> retired yesterday just stops appearing in the result set, so the warehouse row survives as if it
> were still golden. My query had that hole.
>
> The fix is to stop filtering on state and carry the state instead — take every row whose
> `_updated_at` moved, with "is it golden" as a computed column, and upsert on `_id`:
>
> ```sql
> SELECT _id, sku, name, price,
>        (_state = 'active' AND _deleted_at IS NULL) AS is_golden
> FROM <schema>.<object>
> WHERE _updated_at > '<last committed _updated_at>';
> ```
>
> Retiring and soft-deleting both bump `_updated_at`, so each arrives as an update that flips
> `is_golden` to false — a tombstone your models can filter on, instead of a row that silently rots.
> Deleting the target row works as well; keeping the flag just lets you tell "retired" from
> "never seen".
>
> In the loader that is a one-line change (same disclosure as above): the query goes in
> `sources.yaml`, the destination side keeps `mode: upsert` and `key: [_id]`. Re-run on 0.12.2
> against a PostgreSQL 16 source holding active, draft, retired and soft-deleted rows: the first
> pass loads all five rows with the right flags, a second pass over the same window changes
> nothing, and after retiring one record and soft-deleting another upstream the incremental pass
> reads 3 rows and flips both flags to false.
>
> @lij55 — with Debezium already in place, you may not need a separate loader for this at all. The
> miniMDM tables are ordinary PostgreSQL tables, so CDC gives you the state columns too and the
> `is_golden` derivation can live in dbt. The batch path is the simpler one if you want the golden
> records on a schedule rather than within seconds; the CDC path is the one that fits what you
> already run.

> ### ✅ TESTÉ — 24/10/2026
>
> **Version :** `hydra-etl[postgres]==0.12.2` (dernière sur PyPI ; 0.12.0 → 0.12.2 sont sorties
> depuis la 0.11.4 utilisée le 18/10), installée dans un venv neuf. **Attention : la version
> indiquée dans le commentaire publié le 18/10 était 0.11.4 — le suivi dit 0.12.2.**
>
> **Base réelle :** PostgreSQL 16.15. Source `minimdm_sim`, schéma `mdm`, table `product` avec les
> colonnes internes (`_id`, `_state`, `_deleted_at`, `_updated_at`) et 5 fiches : 2 actives,
> 1 brouillon, 1 retirée, 1 supprimée en douceur. Cible `analytics.product`, clé primaire `_id`,
> colonne `is_golden`.
>
> **Manifestes exactement ceux du brouillon :** `extract.query` avec la colonne calculée et
> `WHERE _updated_at > '${ENV:LAST_RUN}'` ; destination `mode: upsert`, `key: [_id]`.
>
> **Commandes et résultats observés :**
>
> | Étape | Commande | Résultat |
> |---|---|---|
> | Validation | `hdrctl validate <job>` | ✅ *DSL valid — no errors detected* |
> | Passe 1 (fenêtre complète) | `hdrctl run <job>` | ✅ 5 lues / 5 écrites — `is_golden` = t,t,f,f,f (actives vraies, brouillon/retirée/supprimée à faux) |
> | Passe 2 (même fenêtre) | `hdrctl run <job>` | ✅ 5/5, toujours **5 lignes** en cible : pas de doublon, l'upsert sur `_id` est idempotent |
> | Amont modifié | SKU-1 retirée, SKU-2 supprimée en douceur, SKU-3 promue active | — |
> | Passe 3 (fenêtre incrémentale) | `hdrctl run <job>` | ✅ **3 lues / 3 écrites** ; `is_golden` passe à faux pour SKU-1 et SKU-2, à vrai pour SKU-3. **La rétractation se propage.** |
>
> **Où le test a tourné :** l'exécution réelle est dans le conteneur cloud, parce que la VM Linux de
> l'ordinateur de Bechir **n'a pas de PostgreSQL et ne peut pas en installer** (`sudo` refusé, pas de
> Docker, et son réseau ne sort que vers PyPI). Sur sa machine, ce qui a pu être vérifié l'a été :
> `pip install "hydra-etl[postgres]==0.12.2"` dans un venv neuf (Python 3.10.12) et
> `hdrctl validate` sur **les mêmes manifestes** → *DSL valid*. L'extrait publié est celui qui a été
> exécuté, au mot près.
>
> **Observation pour la feuille de route produit** (pas pour le commentaire) : il n'existe pas de
> `mode: delete` ni de notion de tombstone côté destination. La rétractation ne se propage que si
> l'utilisateur la transforme lui-même en colonne, comme ici. Pour un chargement incrémental depuis
> une source qui retire des enregistrements, c'est un manque réel.

**Risque et ton :**
- **Le mainteneur a posé une limite explicite** : « miniMDM doesn't recommend or endorse specific
  third-party tools unless they are named in our docs ». Le suivi la respecte : il corrige d'abord
  l'erreur technique, ne redéfend pas l'outil, et **oriente `@lij55` vers Debezium + dbt** quand
  c'est effectivement mieux adapté à son besoin temps réel. C'est ce qui rend le commentaire
  publiable.
- **Un seul commentaire, et c'est le dernier sur ce fil.** Au-delà, la présence devient de
  l'occupation de terrain.
- **Reconnaître l'erreur franchement** (« My query had that hole ») : c'est le passage qui construit
  la crédibilité, pas celui qui la coûte.
- La divulgation d'affiliation est déjà faite dans le fil, le suivi y renvoie (« same disclosure as
  above ») au lieu de la répéter mécaniquement.
- **Ne pas relancer `@lij55` sur l'essai.** S'il revient, c'est une occasion de pilote ; le pousser
  le ferait fuir.

---

### 2 — À verser dans `suivi/etude-concurrents.md` : `agentl`, apparu il y a 11 jours

<https://github.com/arimayuji/agentl> · site `agentl.com.br` · PyPI `agentl-etl` · MIT · bêta v0.10
· 1 ★ au 24/10 (donc sans traction pour l'instant).

Ce n'est pas une discussion, c'est le concurrent le plus proche vu à ce jour, et le relever vaut
mieux que de le découvrir dans six mois : *« Agentic ETL for Python. Declare pipelines in YAML where
each step is a connector, a function or an LLM agent »*. Recoupements : YAML déclaratif, Python,
serveur MCP, CSV/Excel/PDF/SQL/Postgres/S3, étapes de contrôle avant livraison, bancs d'essai
publiés « y compris là où ça perd », `llms.txt` et copie Markdown de chaque page de doc.

**Ce qui distingue encore Hydra ETL :** la promesse d'`hdrctl validate` — vérifier les manifestes
**sans toucher une donnée** — n'est pas celle d'agentl, qui met en avant des contrôles *pendant*
l'exécution et une revue par agent avant livraison. Ses différenciateurs sont le cache par
enregistrement et le budget d'appels au modèle : c'est un produit **LLM d'abord**, là où Hydra ETL
est déterministe d'abord. Son angle IA est précisément celui que `CLAUDE.md` a écarté le 22/09.
**Rien à changer dans le positionnement**, mais la phrase « ETL déclaratif en YAML » n'est plus
distinctive à elle seule : c'est « validé avant exécution » qui porte, comme décidé.

À faire, côté Bechir ou au prochain relevé : ajouter agentl au tableau de `etude-concurrents.md`.

---

### Examiné puis écarté

- **Apache Hop · discussion « Best way to deploy an Hop project to a customer? »** (15/10, 2 réponses)
  — <https://github.com/apache/hop/discussions> · Un débutant ETL demande comment livrer son projet
  Hop à un client. Écarté : le besoin est le déploiement de Hop, pas un autre outil ; et une mention
  d'Hydra ETL dans le forum d'un concurrent serait du placement, quelle que soit sa formulation.
- **dba.stackexchange #350889 · « Sync data tables between tables in different Postgres schema »**
  (20/10, 1 réponse) — <https://dba.stackexchange.com/questions/350889>
  Vrai besoin, bien posé : synchroniser deux tables PostgreSQL « instantanément » sans le code
  actuel (déclencheur + table de logs + POST toutes les 10 s). **Hydra ETL n'est pas la bonne
  réponse** : il demande « instantly », donc réplication logique ou `postgres_fdw` — ce que dit déjà
  la réponse existante. Proposer un chargement par lots serait une réponse moins bonne que celle qui
  est là. Ne pas y aller.
- **duckdb/duckdb · « Select from many JSON-files: OOM error »** (23/10) — bug mémoire de DuckDB 2.0,
  pas un besoin d'outil. Hydra ETL hériterait du même problème.
- **datazip-inc/olake #1348** (24/10) — rapport de bug dans un outil voisin (MySQL → Parquet).
  Aucun besoin exprimé.
- **arimayuji/agentl · « Welcome to agentl Discussions »** (13/10, 0 commentaire) — annonce d'un
  concurrent. Motif habituel : pas une question, et y répondre serait d'auteur à auteur.
- **Hacker News** — 9 fils thématiquement proches dans la fenêtre (ETL, CSV, Airflow, cron), **tous
  à 0 ou 1 commentaire et tous des auto-publications**. Aucune question. Dont
  « Best Open Source ETL Tools Reviewed in 2026 » (15/10, 1 point, 0 commentaire) : appât à clics
  sans audience.
- **Stack Overflow, dba, datascience, softwareengineering** — balayage par API sur 14 à 16 jours :
  en dehors de la question dba ci-dessus, rien qui touche au chargement de fichiers vers une base.

### Recommandation

**Publier le suivi sur `minimdm#74`, et rien d'autre.** C'est le seul brouillon de la semaine, il est
✅ TESTÉ, il corrige une erreur réelle dans un commentaire déjà public — ce qui en fait moins une
option qu'une dette à régler — et il entretient le seul fil où un utilisateur extérieur a dit vouloir
essayer Hydra ETL.

**Ne rien poster ailleurs.** Aucune des discussions examinées ne mérite une réponse, et la seule qui
exprime un vrai besoin (dba.SE) appelle une réponse où Hydra ETL n'a pas sa place.

**Deux points qui ne sont pas de la veille mais qui en sortent :**
1. `@lij55` est **le candidat pilote le plus avancé** à ce jour. S'il revient sur le fil, c'est là que
   se joue le verrou des 3 pilotes.
2. La **propagation des rétractations** (tombstone / `mode: delete`) est un manque produit identifié
   par un tiers, pas par nous. À verser dans la feuille de route v1.0.

**Pour la semaine prochaine :** interroger Stack Overflow et Hacker News **par API depuis le
navigateur intégré** (c'est fait, c'est rapide, ça coûte un appel chacun) et garder le temps du run
pour GitHub, qui est le seul terrain où des besoins apparaissent encore. Reddit reste hors d'atteinte.

---

## Semaine du 17 octobre 2026 — **1 discussion retenue**

**Résultat : 1 discussion, 1 brouillon.** La veille a pu tourner cette semaine : le navigateur
intégré a ouvert Stack Overflow et GitHub. Reddit reste inaccessible. Une seule discussion
qualifie, et elle est bonne — le reste a été examiné puis écarté, motifs ci-dessous.

### État des sources (changement important par rapport au 10/10)

| Source | État cette semaine | Verdict |
|---|---|---|
| **GitHub** (recherche web dans le navigateur intégré) | **Fonctionne** — issues et discussions, filtre `created:>=` inclus | **La source exploitable.** L'API inter-dépôts reste en `403`, mais l'interface web répond |
| **Stack Overflow** (pages de tags dans le navigateur intégré) | **Fonctionne** — mais `/search` déclenche un CAPTCHA, non résolu (interdit) | Accessible et **vide** : voir ci-dessous |
| Hacker News (API Algolia) | Fonctionne | 0 besoin exprimé |
| Reddit (r/dataengineering, r/Python) | Bloqué au proxy **et** refusé par le navigateur intégré | Structurel, ne pas réessayer |
| discuss.python.org | Fonctionne | Hors sujet : 2 résultats pour « etl pipeline », aucun lié aux données |

**Stack Overflow est accessible mais tari.** Dates des questions les plus récentes, relevées le 17/10 :
`[etl]` 13 août · `[data-engineering]` 18 juin · `[airflow]` 8 septembre · `[postgresql]+[csv]` 22 avril.
Zéro question dans la fenêtre de 10 jours sur les quatre tags. Ce n'est pas un défaut d'accès :
le volume de ces tags s'est effondré. **Conséquence pour la veille : ne plus dépenser le run à
balayer Stack Overflow**, un passage mensuel suffit.

Hacker News : 337 fils `Ask HN` dans la fenêtre, **aucun** sur les pipelines de données, l'ETL ou
le chargement de fichiers. Les deux stories thématiquement proches sont des auto-publications
d'auteurs à 1 point (détail en fin de section).

---

### 1 — GitHub · `planemarlin/minimdm` #74 — *« Sync golden record to down-stream database directly without csv »*

- **Date :** ouverte le 15/10/2026, dernière réponse du mainteneur le 16/10/2026. **Fil ouvert et actif.**
- **Lien :** <https://github.com/planemarlin/minimdm/issues/74>
- **Besoin réel :** l'utilisateur veut que les *golden records* de miniMDM arrivent dans son
  entrepôt sans passer par un chargement CSV manuel, et au bon moment — juste après qu'il a
  publié des fiches.
- **Où en est le fil :** le mainteneur a répondu complètement et bien. Il a donné les deux
  lectures possibles (API REST paginée, ou lecture directe des tables PostgreSQL filtrées sur
  `_state = 'active' AND _deleted_at IS NULL`), puis la réponse au « quand » : un webhook
  `record.published`. Il a aussi posé la limite : miniMDM **n'écrira pas** dans une base externe,
  et il demande explicitement *« which tool would do the loading into your warehouse? »*.
  L'utilisateur, lui, a écrit que construire un agent n'est pas difficile mais que *« it is another
  app anyway »* — il ne veut pas maintenir une application de plus.
- **Hydra ETL est-il pertinent ? → franchement oui.** C'est exactement la pièce manquante que le
  mainteneur a nommée : l'étape de chargement, déclarative, lancée par le webhook ou par cron,
  idempotente grâce à `mode: upsert`. Et le mainteneur a posé la question tout haut, ce qui rend
  la mention légitime au lieu d'être un placement.
- **Angle :** répondre d'abord au vrai problème restant — l'idempotence et le rattrapage, que ni
  le webhook ni l'API ne règlent (livraison en une seule tentative, 5 s de timeout, pas de
  réessai : donc une passe de rattrapage est obligatoire, et elle n'est sûre que si le
  chargement est rejouable). Hydra ETL vient après, en une phrase, avec le YAML.

**Brouillon de réponse (EN) — à publier en commentaire sur l'issue :**

> The missing piece here is idempotency, not the trigger. The webhook tells you *when*, but since
> delivery is a single attempt with a 5s timeout and no retry, you need a catch-up run anyway — and
> a catch-up is only safe if loading the same record twice is a no-op. So make the load an upsert on
> the record id and you can stop caring whether a given notification arrived: the webhook becomes a
> latency optimisation, the scheduled run becomes the correctness guarantee.
>
> Reading straight from the PostgreSQL tables is the simpler of the two paths @planemarlin
> described, and it gives you the watermark for free:
>
> ```sql
> SELECT * FROM <schema>.<object>
> WHERE _state = 'active' AND _deleted_at IS NULL
>   AND _updated_at > :last_run;
> ```
>
> Store `:last_run` as the max `_updated_at` you actually committed, not the clock time, or you will
> silently skip rows written during the run.
>
> On "it is another app anyway" — it doesn't have to be an app you write. Disclosure: I'm the author
> of Hydra ETL (open source, `pip install hydra-etl`), which does exactly this one step: a load is a
> few YAML files, and the target side is the part that matters here:
>
> ```yaml
> destinations:
>   warehouse:
>     type: postgresql
>     connection:
>       host: ${ENV:PG_HOST}
>       database: ${ENV:PG_DB}
>       user: ${ENV:PG_USER}
>       password: ${ENV:PG_PASS}
>     load:
>       table: product
>       mode: upsert
>       key: [record_id]
> ```
>
> `hdrctl validate .` checks the manifests and the source/destination references without touching any
> data, then `hdrctl run .` does the load — so your webhook receiver can be a three-line handler that
> shells out to it, and the same command goes in cron for the catch-up. Fair warning: it's beta and
> I'm the only maintainer, so for a scheduled nightly sync it's a reasonable bet, for a critical path
> you'd want to pin a version.

> ## ✅ PUBLICATION DÉBLOQUÉE — 18/10
>
> La 0.11.4 est sur PyPI (17/10 18:42 UTC) et corrige l'upsert PostgreSQL. Le scénario a été
> **exécuté** le 18/10 contre `hydra-etl[postgres]==0.11.4` téléchargée depuis PyPI dans un
> environnement neuf, face à un PostgreSQL 16.15 réel : 2 fiches golden sur 5 chargées, trois
> passes sans doublon, mise à jour amont propagée.
>
> **Le texte définitif est dans `contenus/github/minimdm-74-reponse.md`** et remplace le brouillon
> ci-dessous. Trois corrections qui venaient du test : l'extra `[postgres]` (sans lui le job échoue
> d'emblée), les colonnes listées explicitement (`SELECT *` casse le chargement), et plus aucune
> mention de `hdrctl init` — en 0.11.4 il crée un projet et non un dossier de job.

**Risque et ton :**
- **Autopromotion dans le dépôt d'un tiers.** C'est le point sensible. Il est atténué ici parce que
  le mainteneur a lui-même demandé quel outil ferait le chargement, et parce que les deux tiers du
  commentaire sont utiles sans Hydra ETL. Ne pas allonger la partie Hydra ETL : telle quelle, elle
  tient en un paragraphe sur trois.
- **Divulgation présente** (« Disclosure: I'm the author of Hydra ETL »), limites reconnues
  (bêta, mainteneur unique). Aucun dénigrement : le commentaire s'appuie sur la réponse du
  mainteneur au lieu de la contredire.
- ✅ **YAML vérifié le 17/10** (levée de la réserve ci-dessus) : job généré avec
  `hdrctl init <nom> --template postgres` sous `hydra-etl` 0.11.3, puis `hdrctl validate .` →
  *DSL valid, no errors detected*. `extract.query` est bien accepté en place de `extract.table`.
  Commandes confirmées : `hdrctl validate [PATH]` et `hdrctl run [PATH]` (défaut : dossier courant).
  **Le texte définitif à copier-coller est dans `contenus/github/minimdm-74-reponse.md`** — il
  remplace le brouillon ci-dessus (même angle, YAML complet et vérifié, et il tient compte du
  3ᵉ commentaire du mainteneur : les imports en masse et l'endpoint entrant ne déclenchent pas
  de webhook).
- Répondre à l'auteur de l'issue (`@lij55`), pas au mainteneur : c'est lui qui a le problème.

---

### Examiné puis écarté

- **HN — « CSV import performance of Scriptella/JDBC and csvsql on PostgreSQL and MariaDB »**
  (15/10, 1 point, 1 commentaire — celui de l'auteur) — <https://news.ycombinator.com/item?id=50108606>
  Thématiquement au cœur de la cible (CSV → PostgreSQL/MariaDB, mesures de débit). Écarté : aucun
  besoin exprimé, c'est l'auteur d'un outil concurrent qui publie son propre banc d'essai, et le fil
  a une audience nulle. Y arriver avec un chiffre d'Hydra ETL se lirait comme une réponse d'auteur à
  auteur. *Reste éligible* si le fil prend de vraies questions.
- **GitHub — `f1db/f1db` discussion #167, « Proposed changes to F1DB release artifacts »**
  — <https://github.com/f1db/f1db/discussions/167>
  Vraie question, vrais consommateurs qui décrivent leurs imports automatisés vers PostgreSQL.
  Écarté quand même : la question porte sur le format des archives publiées (.zip → .tgz), pas sur
  l'outil de chargement. Six réponses, consensus déjà atteint. Hydra ETL n'y répond pas ; s'y
  inviter serait du placement hors sujet.
- **HN — « What breaks if I change this? across SQL, dbt and Airflow »** (14/10, 1 point, 0 commentaire)
  — <https://news.ycombinator.com/item?id=50084486> · auto-publication, pas de question.
- **HN — « Show HN: Stream live open data in two commands »** (13/10, 15 points)
  — <https://news.ycombinator.com/item?id=50071200> · annonce d'un outil voisin, même motif.

### Recommandation

**Publier la réponse à `minimdm#74`, et seulement celle-là.** Elle réunit les trois conditions
qu'on s'est fixées : un besoin réel et récent, un fil encore ouvert, et une question du mainteneur
(*« which tool would do the loading? »*) qui rend la mention attendue plutôt que subie. C'est aussi
le format qui convertit le mieux d'après `CLAUDE.md` — « vous décriviez ce problème, voici le YAML ».
Vérifier le bloc YAML comme indiqué, puis poster en répondant à `@lij55`.

**Ne rien publier ailleurs cette semaine.** Une seule réponse bien placée vaut mieux que trois
approximatives, et le quota « au moins trois réponses utiles sans Hydra pour une avec » reste à
tenir : si l'occasion se présente sur un fil GitHub voisin sans rapport avec l'outil, la prendre.

**Pour la semaine prochaine** — la veille a enfin un terrain : GitHub via le navigateur intégré,
avec `created:>=` et `in:title` pour couper le bruit (la recherche plein texte sans `in:title`
remonte surtout des dépôts générés). Reddit reste hors d'atteinte, et Stack Overflow passe en
balayage mensuel plutôt qu'hebdomadaire — ses tags data n'ont plus de volume.

---

## Semaine du 10 octobre 2026 — **aucune discussion retenue (veille empêchée)**

**Résultat : 0 discussion, 0 brouillon.** Pas par absence de sujets, mais parce que les sources
n'ont pas pu être consultées. À ne pas lire comme « rien d'intéressant cette semaine ».

### Ce qui a bloqué

| Source | État |
|---|---|
| Reddit (r/dataengineering, r/Python) | `SITE_BLOCKED` — domaine refusé par le proxy de l'environnement, en lecture directe comme en recherche |
| Stack Overflow (site + `api.stackexchange.com`) | `SITE_BLOCKED` — idem |
| discuss.python.org, lobste.rs (recherche) | `ROBOTS_DISALLOWED` |
| Recherche GitHub inter-dépôts (issues/discussions) | `403` — la session n'a accès qu'aux dépôts configurés |
| Recherche web générale | Fonctionne, mais n'indexe aucun fil de forum : elle ne renvoie que des articles Medium, dev.to et des pages de documentation |
| Hacker News (API Algolia) | **Seule source réellement exploitable** |

Un miroir Reddit (`redlib`) est apparu dans les résultats de recherche. Non utilisé :
contourner un domaine bloqué par un miroir est explicitement interdit.

### Ce que Hacker News a donné (10 derniers jours, 30/09 → 10/10)

Fenêtre balayée sur les stories : 1 résultat pour « ETL », 11 pour « data pipeline ».
Aucune ne qualifie, et pour une raison de fond : ce sont des *annonces* (Show HN), pas des
*besoins exprimés*. Le critère de sélection est « cette question mérite une bonne réponse » ;
une Show HN à 0 commentaire n'est pas une question, et y répondre serait de l'autopromotion
d'auteur à auteur — exactement ce que la procédure de veille interdit.

Les deux seules thématiquement adjacentes, écartées :

- **Show HN: Paganel — Data migration with a receipt you can verify later**
  (06/10, 3 points, 0 commentaire) — <https://news.ycombinator.com/item?id=49977297>
  Adjacent à l'argument « validé avant exécution », mais c'est un concurrent qui présente son
  outil. Écarté : aucun besoin exprimé, et commenter là serait lu comme du placement.
- **Show HN: Lask — A task runner with a type system and pinned Docker environments**
  (06/10, 2 points, 0 commentaire) — <https://news.ycombinator.com/item?id=49977602>
  Même motif.

Note : aucun de ces deux fils n'est « traité ». S'ils prennent des commentaires et qu'une
vraie question y apparaît, ils redeviennent éligibles.

### Recommandation

**Ne rien publier cette semaine.** Il n'y a rien à publier, et une réponse fabriquée sur un fil
mal choisi coûte plus cher que deux semaines de silence.

**Pour débloquer la veille** — l'arbitrage revient à Bechir, par ordre de rendement :

1. **Faire tourner la veille avec le navigateur, en sa présence.** La session planifiée tourne
   dans le cloud, sans accès à Reddit ni à Stack Overflow. Un passage lancé à la main, pendant
   que Bechir est à son poste, peut ouvrir les fils dans le navigateur (les autorisations de site
   demandent sa réponse — impossible dans un run automatique de 11 h du matin où personne n'est là).
2. **Lui fournir les liens.** S'il croise un fil pertinent dans la semaine, le coller dans
   `suivi/veille-forums.md` sous une rubrique « à traiter » : l'agent rédige le brouillon sans
   avoir besoin d'accéder à la plateforme.
3. **Déplacer la veille vers des sources atteignables.** Les issues GitHub des dépôts voisins
   (Airflow, Airbyte, dlt, petl, Meltano) sont du bon terrain — « votre problème est décrit dans
   cette issue, voici le YAML » convertit environ trois fois mieux qu'un post à froid, et c'est
   déjà l'angle retenu dans `CLAUDE.md`. Mais il faut que les dépôts soient listés dans la
   configuration de la session, sinon la recherche inter-dépôts reste en 403.

À noter : ce blocage est structurel, pas passager. Il se reproduira à l'identique samedi prochain
tant que l'un des trois points ci-dessus n'est pas tranché.
