# Veille forums — discussions où Hydra ETL est une réponse légitime

> Fichier tenu par l'agent de veille hebdomadaire (samedi matin). Le plus récent en haut.
> **Règle :** l'agent prépare, **Bechir publie**. Rien n'est posté automatiquement.
> Toute discussion listée ici est considérée comme traitée et ne sera jamais reproposée.

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

> ## ⛔ PUBLICATION SUSPENDUE — 17/10, après test réel
>
> Le brouillon ci-dessous **ne doit pas être posté en l'état**. Testé bout en bout contre un
> PostgreSQL 16 réel : **`mode: upsert` est cassé dans la 0.11.3 publiée** (`KeyError: 0`, sur
> n'importe quelle table, même avec la PRIMARY KEY attendue). Or l'upsert est exactement
> l'argument que porte le commentaire. Deux autres défauts dans le brouillon : `SELECT *` fait
> échouer le chargement, et `pip install hydra-etl` n'installe pas le driver PostgreSQL.
>
> Diagnostic, correctif (3 lignes) et mesures : `ressources/patchs/0.11.3-upsert-postgres-RAPPORT.md`.
> **Reprendre la publication seulement après une 0.11.4 publiée sur PyPI**, et en citant
> `pip install "hydra-etl[postgres]"`.

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
