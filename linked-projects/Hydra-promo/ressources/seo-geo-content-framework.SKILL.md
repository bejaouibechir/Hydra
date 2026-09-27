---
name: seo-geo-content-framework
description: Rédiger, réviser ou auditer des contenus SEO+GEO vérifiables et citables pour articles, LinkedIn, Reddit, documentation, landing pages et communiqués de presse. À utiliser lorsqu'un contenu doit servir à la fois la recherche classique et les moteurs de réponse IA, sans inventer de faits ni imposer une méthode GEO unique.
---

# SEO + GEO Content Framework

Produire un contenu utile aux lecteurs, découvrable par les moteurs de recherche et facilement interprétable ou cité par les moteurs de réponse. GEO complète le SEO : il ne remplace ni l'intention de recherche, ni la qualité éditoriale, ni l'autorité réelle.

## Principes non négociables

- Ne jamais inventer une caractéristique technique, un chiffre, une citation, un client, un benchmark, une intégration, une compatibilité ou un résultat.
- Séparer explicitement ce qui est établi, allégué, vécu, interprété ou non vérifié en suivant la taxonomie des preuves (l'Annexe B).
- Transformer une information `UNVERIFIED` en question, hypothèse signalée ou élément à confirmer ; ne pas la publier comme un fait.
- Appuyer les affirmations externes importantes sur des sources primaires ou faisant autorité. Ne pas ajouter de source décorative qui ne soutient pas précisément l'affirmation.
- Préserver les nuances, limites et conditions. Une formulation facilement extractible ne doit pas devenir simpliste ou trompeuse.
- Considérer les « Content Capsules » comme un principe d'autonomie sémantique, pas comme une longueur universelle. Une capsule peut dépasser 20–25 mots si l'exactitude ou le contexte l'exige.
- Ne pas optimiser pour une plateforme IA particulière sans preuve actuelle de son fonctionnement. Construire un contenu robuste et interopérable.
- **Code publié = code exécuté.** Toute commande, configuration, sortie de terminal ou message d'erreur cité doit avoir été reproduit, avec la version testée indiquée près de l'exemple. Un extrait non exécuté est `UNVERIFIED`.
- **Une expérience est datée.** Jamais « la semaine dernière », « récemment » : une date, un environnement (OS, version, conteneur) et un périmètre.

## Ce que le GEO peut et ne peut pas faire

- Les moteurs de réponse répondent souvent **sans renvoyer de clic**. L'objectif GEO est d'être **cité, mentionné et décrit correctement**, pas d'attirer du trafic ; mesurer en conséquence (voir KPI).
- Un sujet ou une marque récents ne sont pas dans les données d'entraînement : ils ne sont trouvés que par la **recherche web au moment de la réponse** (index de Google, de Bing et d'autres). **L'indexation et les liens entrants sont donc un prérequis du GEO**, pas une option. Vérifier l'indexation (Search Console, Bing Webmaster Tools) avant d'attendre une citation.

## Entrées minimales

Recueillir ou déduire prudemment : sujet, audience, objectif, format, canal, langue, zone géographique, offre ou entité concernée, sources disponibles, contraintes de marque et appel à l'action. Si une donnée indispensable manque, avancer avec une hypothèse clairement étiquetée ou demander la précision qui change matériellement le résultat.

Langue : rédiger dans la langue du public visé, pas dans celle de la conversation. Pour Hydra ETL, **tout contenu public est en anglais** ; les notes internes (registre, à confirmer) peuvent rester en français.

Pour Hydra ETL, lire obligatoirement le profil Hydra ETL (l'Annexe D) avant toute rédaction factuelle. Pour un autre projet, utiliser la même discipline de preuve sans importer les hypothèses Hydra.

## Workflow obligatoire

Suivre l'ordre ci-dessous. Le détail et les livrables intermédiaires figurent dans l'Annexe A.

1. **Intent Analysis** — déterminer intention principale, intentions secondaires, audience, stade du parcours et résultat attendu.
2. **Fan-out Queries** — cartographier les sous-questions nécessaires pour comprendre, comparer, décider, mettre en œuvre et vérifier.
3. **Facts** — construire un registre des preuves avec les étiquettes `FACT`, `CLAIM`, `EXPERIENCE`, `OPINION`, `UNVERIFIED`.
4. **Content Structure** — concevoir une hiérarchie claire, une réponse directe, des capsules autonomes, des preuves et des liens internes utiles.
5. **GEO Draft** — rédiger d'abord pour l'humain, puis renforcer l'extractibilité, l'attribution, la précision et la citabilité.
6. **SEO Check** — vérifier intention, titre, hiérarchie, couverture, liens, métadonnées proposées et absence de bourrage de mots-clés.
7. **GEO Check** — vérifier réponses explicites, entités, attribution, preuves, capsules, questions dérivées et contexte suffisant.
8. **Hallucination Check** — confronter chaque affirmation publiable au registre ; supprimer, nuancer ou signaler tout élément non étayé.
9. **Final Content** — livrer le contenu final, puis les notes de preuve ou éléments à confirmer si le contexte les rend utiles.

Ne pas sauter le contrôle d'hallucination, même pour un contenu court.

## Routage par format

Lire uniquement le guide correspondant au livrable demandé :

- ARTICLE (Annexe E)
- LINKEDIN_POST (Annexe E)
- REDDIT_POST (Annexe E)
- DOCUMENTATION (Annexe E)
- LANDING_PAGE (Annexe E)
- PRESS_RELEASE (Annexe E)

Pour une révision ou un audit, conserver la voix et l'intention du texte source. Fournir les corrections prioritaires et, si demandé, une version réécrite.

## Structure SEO + GEO commune

- Ouvrir par une réponse ou proposition de valeur claire lorsque le format le permet.
- Organiser les sections autour de questions ou besoins réels, sans forcer chaque titre en question.
- Créer des passages autonomes : sujet nommé, réponse explicite, contexte indispensable, preuve ou attribution proche.
- Définir les entités et termes ambigus à leur première apparition.
- Utiliser listes, tableaux, étapes, exemples ou FAQ uniquement s'ils améliorent la compréhension.
- Relier aux contenus internes qui approfondissent une sous-question ; employer des ancres descriptives.
- Proposer des données structurées Schema.org seulement si elles correspondent au contenu visible et au type de page. Ne jamais fabriquer des avis, notes, auteurs ou dates.
- Donner à chaque source un rôle identifiable : définition, preuve, contexte, comparaison ou expérience.

## KPI et mesure

Choisir les KPI selon l'objectif et distinguer visibilité, influence et conversion. Lire l'Annexe C pour les contrôles et le protocole de mesure. Inclure notamment, lorsque mesurable :

- visibilité organique, impressions, clics et requêtes ;
- couverture des fan-out queries et engagement ;
- citations dans les moteurs de réponse, fréquence de mention de marque et exactitude de la description ;
- trafic référent depuis les assistants ou moteurs de réponse ;
- conversions assistées et demandes qualifiées.

Ne pas présenter une corrélation comme une causalité. Conserver les prompts, dates, marchés et modèles testés pour rendre les observations comparables.

## Sortie par défaut

Sauf demande contraire, retourner :

1. le contenu final prêt à publier ;
2. un titre SEO et une meta description si le format les utilise ;
3. les recommandations de liens internes et de Schema pertinentes ;
4. une courte liste « À confirmer avant publication » pour les éléments non vérifiés restants ;
5. les sources effectivement utilisées, associées aux affirmations qu'elles soutiennent.

Conserver le registre des preuves à côté du contenu, dans un fichier `<slug>.evidence.md` (registre, sources, éléments bloqués, date de vérification). Il sert de piste d'audit et accélère les mises à jour.

---

# Annexe A — Workflow détaillé

## Workflow SEO + GEO

### 1. Intent Analysis

Créer une fiche courte : requête ou sujet central ; intention dominante ; audience, niveau de connaissance et objections ; décision ou action attendue ; entités indispensables ; contexte géographique, linguistique et temporel.

Ne pas confondre le mot-clé avec l'intention. Deux requêtes proches peuvent demander des preuves, formats ou profondeurs différents.

### 2. Fan-out Queries

Énumérer les questions nécessaires pour produire une réponse complète. Couvrir seulement les branches utiles :

- **définir** : qu'est-ce que c'est, pour qui, dans quel contexte ?
- **comprendre** : comment cela fonctionne, pourquoi, avec quelles limites ?
- **comparer** : alternatives, différences, critères et compromis ;
- **agir** : étapes, prérequis, exemples, erreurs à éviter ;
- **évaluer** : coût, performance, sécurité, fiabilité ou résultats ;
- **faire confiance** : auteur, preuves, sources, expérience directe et date.

Classer les questions en `CORE`, `SUPPORTING` ou `OUT_OF_SCOPE`. La carte guide la couverture ; elle n'oblige pas à créer une section pour chaque question.

### 3. Facts

Construire avant rédaction un registre minimal :

| ID | Information | Type | Source/preuve | Portée/conditions | Statut publication |
|---|---|---|---|---|---|
| E1 | ... | FACT | URL, document ou donnée | ... | OK / NUANCER / BLOQUÉ |

Appliquer la taxonomie de l'Annexe B. Pour une affirmation composite, séparer les éléments vérifiables.

### 4. Content Structure

Concevoir une réponse centrale, une progression alignée sur l'intention, les capsules importantes et leurs preuves, les exemples et limites, les liens utiles et une action finale cohérente.

Une **Content Capsule** est une unité autonome que l'on peut comprendre hors de son paragraphe : elle nomme le sujet, donne la réponse, conserve le contexte nécessaire et rapproche la preuve. Sa longueur dépend de la complexité ; ne pas viser mécaniquement 20–25 mots.

### 5. GEO Draft

Rédiger une version naturelle. Puis placer les réponses près des questions, remplacer les pronoms ambigus par l'entité utile, rapprocher sources et affirmations, expliciter conditions et dates, et éliminer les superlatifs non prouvés.

### 6. SEO Check

Vérifier : satisfaction de l'intention, titre fidèle, H1 unique si page web, hiérarchie H2/H3, vocabulaire naturel, couverture suffisante, URL proposée si utile, meta description non trompeuse et ancres descriptives.

### 7. GEO Check

Vérifier : réponses directes, capsules compréhensibles isolément, entités explicites, sources proches, expérience directe attribuée, dates et périmètres, fan-out queries importantes couvertes, limites visibles.

### 8. Hallucination Check

Relire phrase par phrase :

1. S'agit-il d'une affirmation vérifiable ?
2. Quel ID du registre la soutient ?
3. La formulation dépasse-t-elle la portée de la preuve ?
4. Une date, un contexte ou une attribution manque-t-il ?
5. Un lecteur pourrait-il confondre opinion et fait ?

Sans preuve suffisante : supprimer, nuancer, attribuer comme `CLAIM`, convertir en hypothèse ou placer dans « À confirmer ». Une caractéristique technique non documentée reste interdite.

### 9. Final Content

Retirer les étiquettes internes du texte public, sauf si le format demandé est un audit. Conserver séparément le registre des preuves, les sources et les éléments bloqués. Ne jamais masquer un manque de preuve par une formulation assurée.

---

# Annexe B — Taxonomie des preuves et sources

## Taxonomie des preuves et politique de sources

### Étiquettes

- `FACT` — information vérifiable soutenue par une source ou une donnée adéquate. Publier dans la portée exacte de la preuve.
- `CLAIM` — affirmation faite par une organisation, une personne ou un fournisseur, mais non confirmée indépendamment. Attribuer explicitement : « Selon… ».
- `EXPERIENCE` — observation de première main avec auteur, contexte, méthode et limites. Ne pas généraliser au-delà de l'expérience.
- `OPINION` — jugement, recommandation ou interprétation. Signaler la perspective et fournir le raisonnement.
- `UNVERIFIED` — information sans preuve suffisante, contradictoire ou encore à confirmer. Interdite comme fait publiable.

Une même phrase peut contenir plusieurs types : la scinder pour éviter une attribution trompeuse.

### Hiérarchie pratique des sources

Privilégier selon l'affirmation :

1. documentation officielle, norme, texte réglementaire, dépôt ou publication originale ;
2. données internes documentées, protocole reproductible ou témoignage direct clairement attribué ;
3. recherche évaluée, organisme reconnu ou analyse méthodologiquement transparente ;
4. presse spécialisée fiable ou source secondaire reconnue ;
5. agrégateurs et contenus non attribués seulement pour découvrir une piste, jamais comme preuve finale si une source primaire existe.

La réputation seule ne suffit pas : vérifier que la page citée soutient exactement la proposition, qu'elle est assez récente et qu'elle correspond à la version, au marché ou au contexte traité.

### Sources et citabilité

- Associer la source à l'affirmation, pas seulement à la section.
- Nommer l'auteur ou l'organisation et la date quand elles changent l'interprétation.
- Citer la page précise plutôt qu'une page d'accueil.
- Ne pas créer de citation textuelle sans disposer du texte exact.
- Ne pas utiliser une source qui cite une autre source lorsque l'original est accessible.
- Signaler les conflits entre sources ; ne pas choisir silencieusement la version la plus avantageuse.

### First-hand experience

Une expérience directe améliore l'utilité et l'autorité lorsqu'elle est traçable. Documenter : qui a observé quoi, quand, dans quel environnement, avec quelle méthode, sur quel échantillon et avec quelles limites. Les captures, journaux, résultats de tests ou extraits de configuration peuvent servir de preuve s'ils ne révèlent pas de données sensibles.

### Formulations sûres

- `FACT` : formulation directe avec citation proche.
- `CLAIM` : « [Organisation] affirme que… »
- `EXPERIENCE` : « Lors de notre test sur [contexte], nous avons observé… »
- `OPINION` : « Nous recommandons… parce que… »
- `UNVERIFIED` : « À confirmer : … » ; ne pas intégrer au corps comme vérité.

---

# Annexe C — Contrôles qualité et mesure

## Contrôles qualité et mesure

### Contrôle SEO

- L'intention principale est satisfaite sans détour.
- Le titre, le H1 et l'introduction décrivent fidèlement le contenu.
- Les sous-thèmes importants sont couverts sans répétition artificielle.
- Les termes recherchés apparaissent naturellement ; aucune densité fixe n'est imposée.
- Les liens internes approfondissent une question ou accompagnent l'action suivante.
- Les liens externes prouvent une affirmation ou donnent accès à une ressource originale.
- La meta description est une proposition honnête, pas une liste de mots-clés.
- Le contenu apporte une valeur distincte : données, méthode, synthèse, exemple ou expérience.

### Contrôle GEO

- Les réponses centrales sont explicites et attribuables.
- Les capsules importantes restent exactes lorsqu'elles sont extraites seules.
- Les entités, versions, dates, marchés et unités ne sont pas ambigus.
- Chaque chiffre et superlatif a une preuve et un périmètre.
- Les sources d'autorité sont placées près des affirmations.
- L'expérience directe est contextualisée et ne prétend pas être universelle.
- Les limites, inconnues et contradictions sont visibles.
- Les fan-out queries principales sont couvertes ou volontairement déclarées hors périmètre.

### Contrôle Schema.org

Recommander uniquement un type cohérent avec la page visible, par exemple `Article`, `TechArticle`, `HowTo`, `FAQPage`, `SoftwareApplication`, `Product`, `Organization` ou `BreadcrumbList`. Valider l'éligibilité actuelle avant implémentation. Les données structurées doivent refléter le contenu affiché ; ne jamais inventer note, avis, prix, auteur ou date.

### KPI

Établir une base avant publication et observer par période comparable :

- **SEO** : impressions, clics, CTR, position par groupe de requêtes, pages d'entrée et conversions organiques.
- **Couverture** : part des fan-out queries ayant une réponse utile et indexable.
- **GEO citation** : proportion de tests où le contenu ou domaine apparaît comme source citée.
- **Mention de marque** : fréquence de mention, sentiment descriptif et exactitude des attributs associés.
- **Referral IA** : sessions référées par assistants ou moteurs de réponse quand l'analytics le permet.
- **Business** : demandes qualifiées, inscriptions, téléchargements ou conversions assistées.

Le trafic référé par les assistants reste faible même quand le GEO fonctionne (réponse sans clic) : ne pas juger le GEO sur les sessions seules. Le KPI principal est la **fréquence de citation et l'exactitude de la description**.

**Point de départ obligatoire** avant de publier une série de contenus : 10 à 20 questions réelles du public cible, posées aux principaux assistants avec recherche web activée ; archiver les réponses. Reposer les mêmes questions à intervalle fixe (par exemple mensuel).

Pour les tests de citation et mention, archiver prompt exact, langue, pays, date, outil ou modèle, mode connecté au Web, résultat et URL citée. Les réponses étant variables, répéter les tests et rapporter un intervalle ou une fréquence, pas une certitude absolue.

---

# Annexe D — Profil Hydra ETL

## Profil de rédaction Hydra ETL

Ce profil empêche la confusion entre le projet Hydra ETL concerné et d'autres produits ou dépôts nommés « Hydra ».

### Règle d'identité

Avant de rédiger, identifier Hydra ETL à partir des sources fournies ou officielles du projet : site, documentation, dépôt, architecture, tests et déclarations du propriétaire. Ne jamais compléter les zones manquantes avec les caractéristiques d'un autre projet portant le même nom.

En particulier, ne pas présenter Hydra ETL comme fondé sur PostgreSQL, doté d'un stockage colonnaire intégré ou lié à un produit analytique homonyme sans preuve explicite propre à ce Hydra ETL.

### Fiche factuelle — vérifiée le 26/09/2026 sur le dépôt (commit `ed53916`, version 0.11.2)

Revérifier toute ligne dont la date dépasse un mois, et à chaque nouvelle version.

| Champ | Valeur vérifiée | Source | Statut |
|---|---|---|---|
| Nom et désambiguïsation | **Hydra ETL** — paquet `hydra-etl`, CLI `hdrctl`, site `hydraetl.com`. Sans lien avec l'extension PostgreSQL colonnaire « Hydra » ni avec la bibliothèque de configuration « Hydra » (Meta) | `pyproject.toml`, site | FACT |
| Proposition de valeur | Moteur ETL déclaratif : un pipeline se décrit en YAML et se **valide avant exécution** (`hdrctl validate`, `hdrctl workflow validate`) | README, `hydra_etl/cli/hdrctl.py` | FACT |
| Description officielle | « Declarative ETL engine with a CLI, a REST API and a visual studio. » | `pyproject.toml` | FACT |
| Public cible | Data engineers, analystes, consultants data ; devops pour les workflows d'actions | décision projet (`CLAUDE.md`) | OPINION (positionnement) |
| Architecture | Moteur Python ; CLI `hdrctl` ; API REST FastAPI + Studio (éditeur visuel) via `hdrctl serve` (`pip install hydra-etl[server]`) ; workflows en DAG ; serveur MCP local ; extension VS Code | `pyproject.toml`, dépôt | FACT |
| Langages/runtime | Python ≥ 3.9 ; moteurs pandas (défaut) et DuckDB (option) ; accélérateur Rust optionnel `hydra-native` | `pyproject.toml` | FACT |
| Connecteurs | CSV, JSON, Parquet, MySQL/MariaDB, PostgreSQL, SQL Server (`pymssql`, sans pilote ODBC système), MongoDB, Web API | `ai/schemas/connectors.schema.json` | FACT |
| Non supportés | S3, BigQuery, Snowflake | description de l'outil MCP `hydra_list_connectors` | FACT |
| Actions de workflow | 11 : `bash`, `powershell`, `python`, `ssh`, `webhook`, `email`, `log`, `delay`, `condition`, `set_param`, `assign_param` ; `bash` indisponible sous Windows, `powershell` indisponible hors Windows | `workflow/runner.py` | FACT |
| Ce que valide `workflow validate` (0.11.2) | actions, clés et paramètres inconnus (avec suggestion), paramètres requis, cycles de dépendances | `workflow/models.py`, tests | FACT |
| Planification | Déclencheur `schedule` (cron) exécuté **uniquement sous `hdrctl serve`** (APScheduler) ; `hdrctl workflow run` exécute une fois | `api/scheduler.py` | FACT |
| Modèle de déploiement | Local / auto-hébergé, `pip install hydra-etl` ; Linux, macOS, Windows | PyPI, classifiers | FACT |
| Licence/prix | AGPL-3.0-or-later, gratuit ; licence commerciale possible sur demande | `pyproject.toml` ; déclaration du propriétaire | FACT ; CLAIM (commercial) |
| Maturité | Bêta (« Development Status :: 4 - Beta »), un seul mainteneur | classifiers ; propriétaire | FACT |
| Sécurité/gouvernance | Serveur MCP : outils annotés `readOnlyHint`/`destructiveHint`, refus d'écrire un job invalide, confinement au dossier de travail, aucune requête réseau | `hydra_etl/mcp/server.py`, tests | FACT (portée : serveur MCP uniquement) |
| Performances | Lecture CSV « ~4× plus rapide » avec le backend Rust | mesure interne, **pas de page benchmark publique** | UNVERIFIED — ne pas publier de chiffre |
| Limitations connues | Pas de reprise après panne au milieu d'un workflow ; pas de connecteurs cloud data warehouse ; projet jeune, peu d'utilisateurs publics | code ; propriétaire | FACT / EXPERIENCE |
| Roadmap | Non publiée | — | UNVERIFIED |

### Angles GEO utiles

Selon les preuves disponibles, explorer : définition du problème résolu, fonctionnement réel, cas d'usage, exemples de configuration, choix d'architecture, comparaisons honnêtes, limites, migration, exploitation et expérience du développeur. Les exemples issus du projet doivent distinguer état actuel, prototype et feuille de route.

### Entités et désambiguïsation

Au début d'un contenu où la confusion est plausible, employer le nom complet et une définition discriminante. Relier vers la source canonique du projet. Éviter de reprendre des descriptions de tiers sans vérifier qu'elles visent bien la même entité.

### Protocole de publication Hydra ETL

- Publier d'abord sur `hydraetl.com/blog` (URL canonique), puis diffuser ailleurs avec `canonical_url` ou lien retour.
- Tout lien sortant vers le site porte ses paramètres UTM (`utm_source`, `utm_medium`, `utm_campaign`).
- Première mention : « Hydra ETL », jamais « Hydra » seul.
- Ne jamais mentionner les clients de l'auteur (Andaluz Lab notamment) : sans lien avec Hydra ETL.

### Preuves recommandées

- documentation et dépôt officiels avec version ou commit si pertinent ;
- démonstrations reproductibles et configurations réelles ;
- benchmarks avec matériel, jeu de données, paramètres, date et comparaison équitable ;
- retours du développeur ou d'utilisateurs attribués ;
- décisions d'architecture accompagnées de leurs compromis.

---

# Annexe E — Modèles par format

## ARTICLE

### Usage

Contenu approfondi destiné à répondre durablement à une intention, couvrir ses questions dérivées et servir de source citable.

### Modèle

```markdown
# [Titre centré sur le bénéfice ou la question]

[Réponse directe / thèse en 2 à 4 phrases]

## [Définition ou contexte nécessaire]
[Capsule autonome + preuve]

## [Comment cela fonctionne / méthode]
[Étapes, mécanisme, exemple]

## [Comparaison, limites ou critères]
[Tableau seulement si les axes sont homogènes et prouvés]

## [Application concrète / expérience]
[Contexte, méthode, observation, limites]

## [Questions fréquentes pertinentes]
### [Question]
[Réponse directe et autonome]

## Conclusion
[Synthèse + prochaine action]
```

### Exigences propres à l'article technique

- **Réponse en tête.** La thèse ou la réponse centrale figure dans les trois premières phrases ; le récit vient ensuite. Une IA qui n'extrait que le début doit obtenir la bonne réponse.
- **Chaque affirmation technique non évidente a sa source primaire** (documentation officielle de l'éditeur, dépôt, spécification), liée à la page précise, près de l'affirmation.
- **Commandes et sorties reproduites**, versions indiquées (« tested with SQL Server 2022 CU…, Docker image … »).
- **Messages d'erreur cités à l'identique**, y compris codes et numéros : ce sont les chaînes que les lecteurs et les IA recherchent.
- **Auteur et dates visibles** : auteur nommé avec une ligne de contexte, date de publication, date de dernière vérification.
- **Désambiguïsation** des termes ou produits homonymes à leur première mention.

Proposer : slug, title SEO, meta description, liens internes, sources, Schema adapté (`TechArticle` ou `Article`, avec `author`, `datePublished`, `dateModified` réels) et éléments à confirmer. Une FAQ n'est pas obligatoire ; l'ajouter seulement si elle répond à de vraies sous-questions non traitées ailleurs.

## LINKEDIN_POST

### Usage

Partager une idée, une expérience ou un enseignement professionnel avec une preuve suffisante, sans transformer le post en mini-article artificiel.

### Modèle

```markdown
[Accroche spécifique, sans promesse sensationnaliste]

[Contexte : problème, situation ou observation]

[Idée centrale exprimée clairement]

[2 à 5 enseignements, étapes ou contrastes lisibles]

[Preuve, exemple ou expérience de première main avec limites]

[Conclusion utile]

[Question ou CTA naturel]
```

Limiter les hashtags à ceux qui aident réellement la classification. Ne pas inventer de résultat, client ou adoption. La publication doit rester compréhensible sans clic.

## REDDIT_POST

### Usage

Demander un retour, partager une expérience ou expliquer une solution en respectant les normes et la culture de la communauté visée.

### Modèle

```markdown
**Titre :** [Descriptif précis, non promotionnel]

[Pourquoi je publie ici et contexte pertinent]

[Ce que j'ai essayé / observé]

- [Détail concret]
- [Détail concret]

[Résultat, limite ou point d'incertitude]

[Question précise à la communauté]

[Divulgation claire de toute affiliation]
```

Lire les règles du subreddit lorsqu'elles sont disponibles. Divulguer la relation avec un produit ou projet. Éviter l'astroturfing, les titres manipulateurs et les liens promotionnels non nécessaires.

## DOCUMENTATION

### Usage

Expliquer un concept, une procédure, une API ou un comportement de façon exacte, reproductible et versionnée.

### Modèle

```markdown
# [Tâche ou concept]

[Résumé : ce que le lecteur accomplira ou comprendra]

## Prérequis
- [Version, droit, dépendance]

## Procédure / Référence
1. [Action]
2. [Action]

## Exemple
[Exemple minimal valide, avec résultat attendu]

## Limites et erreurs fréquentes
- [Condition, symptôme, résolution]

## Voir aussi
- [Lien interne descriptif]
```

Vérifier chaque commande, paramètre, valeur de retour et version. Distinguer comportement garanti, observation et feuille de route. Ne pas sacrifier la précision technique à l'optimisation éditoriale.

## LANDING_PAGE

### Usage

Présenter une offre à une audience et soutenir une action mesurable avec des preuves vérifiables.

### Modèle

```markdown
# [Résultat crédible pour l'audience]
[Sous-titre : quoi, pour qui, différenciation vérifiable]
[CTA]

## [Problème reconnu]
[Contexte et coût du problème sans dramatisation non prouvée]

## [Comment l'offre aide]
[Capacités vérifiées reliées à des bénéfices]

## [Comment cela fonctionne]
[3 à 5 étapes ou mécanisme]

## [Preuves]
[Démonstration, données, témoignages autorisés, logos autorisés]

## [Cas d'usage / critères]
[Pour qui, quand, limites]

## [FAQ décisionnelle]
[Réponses aux objections réelles]

[CTA final cohérent]
```

Ne pas convertir une fonctionnalité en résultat garanti. Les témoignages, logos, chiffres et comparatifs nécessitent une preuve et une autorisation adaptées. Proposer `Product`, `SoftwareApplication` ou `Organization` seulement si les propriétés visibles et les critères actuels le permettent.

## PRESS_RELEASE

### Usage

Annoncer un événement vérifiable avec date, portée, porte-parole et informations de contact fournies.

### Modèle

```markdown
# [Titre factuel de l'annonce]

## [Sous-titre précisant impact et public]

**[VILLE], [DATE] —** [Lead : qui annonce quoi, quand, pour qui et pourquoi cela compte.]

[Détails vérifiés et contexte]

> « [Citation exacte et approuvée] », déclare [Nom, fonction].

[Disponibilité, conditions, prochaines étapes]

## À propos de [Organisation]
[Boilerplate factuel]

## Contact presse
[Coordonnées fournies]
```

Ne jamais inventer une citation, un porte-parole, une date, une disponibilité ou un contact. Marquer les champs manquants comme placeholders explicites. Maintenir un ton factuel ; les déclarations prospectives doivent être attribuées et nuancées.
