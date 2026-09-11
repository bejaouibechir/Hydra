# Stratégie de documentation interactive de Hydra

## Objet du document

Ce document sert de référence stratégique et fonctionnelle à Claude, Grok et à tout agent chargé de concevoir ou d’implémenter la documentation en ligne de Hydra.

Il ne décrit pas une documentation classique accompagnée de quelques démonstrations. La documentation Hydra doit être une expérience exclusivement interactive, visuelle et exécutable, accessible avant même l’installation du produit.

La règle directrice est :

> Le playground est la documentation. L’utilisateur apprend Hydra en observant, modifiant, exécutant et visualisant le Hydra DSL.

---

## 1. Contexte produit

Hydra est une solution ETL comprenant notamment :

- un moteur d’exécution ;
- un CLI ;
- une API ;
- Hydra Studio ;
- un MCP permettant de commander Hydra depuis une IA ;
- Hydra DSL, un langage déclaratif basé sur YAML.

Hydra DSL décrit les éléments nécessaires aux traitements de données, notamment :

- les sources ;
- les destinations ;
- les transformations ;
- les jobs et pipelines, selon le modèle final retenu ;
- les workflows ;
- les triggers et politiques d’exécution.

Le DSL doit être présenté comme un langage déclaratif comparable, dans sa philosophie, aux manifestes Ansible ou Kubernetes : l’utilisateur décrit l’état et le flux souhaités, tandis que Hydra se charge de la validation, de la planification et de l’exécution.

---

## 2. Vision stratégique

La documentation ne doit pas demander à l’utilisateur de lire de longs chapitres avant de pouvoir agir. Elle doit immédiatement créer une ambiance d’expérimentation.

Le parcours fondamental est :

```text
Observer → Modifier → Exécuter → Visualiser → Comprendre
```

Les objectifs sont les suivants :

1. Permettre de découvrir Hydra sans installation.
2. Réduire le délai avant la première exécution réussie.
3. Expliquer chaque notion par une manipulation.
4. Favoriser les schémas, diagrammes, tableaux et animations.
5. Rendre les exemples modifiables et exécutables.
6. Faciliter la migration depuis les outils concurrents.
7. Conserver un excellent référencement sans imposer de longs articles.
8. Conduire naturellement l’utilisateur vers Hydra Studio, le CLI ou une installation locale.

La documentation doit fonctionner comme un canal d’acquisition produit, et non comme une annexe technique.

---

## 3. Principe non négociable : une documentation exclusivement interactive

Il ne faut pas créer un manuel classique puis ajouter un bouton « Try it » à quelques pages.

Chaque notion documentée doit posséder une expérience interactive. Une fiche qui ne contient qu’une définition, une syntaxe statique et un exemple non exécutable est incomplète.

Chaque leçon ou fiche doit contenir, selon le sujet :

- une phrase courte présentant l’objectif ;
- un exemple Hydra DSL déjà fonctionnel ;
- un éditeur YAML ;
- une validation en temps réel ;
- une visualisation du flux ;
- des données d’entrée consultables ou modifiables ;
- un résultat d’exécution ;
- une explication contextuelle des propriétés ;
- une possibilité de provoquer puis corriger une erreur ;
- un bouton de réinitialisation ;
- une ouverture dans le playground complet ;
- éventuellement un mini-défi validé automatiquement.

Le texte reste utile, mais il est subordonné à l’action. Il sert aux explications brèves, à l’accessibilité et au référencement. Il ne constitue pas le parcours principal.

---

## 4. Inspiration : dax.guide adapté à Hydra

La structure générale doit être proche de [dax.guide](https://dax.guide/), sans en faire une copie.

Les qualités à reprendre sont :

- une recherche centrale et rapide ;
- une navigation A–Z ;
- une organisation par groupes ;
- des filtres par attributs et compatibilité ;
- une fiche normalisée pour chaque élément ;
- des liens entre éléments associés ;
- l’indication des versions, capacités et dépréciations ;
- une URL unique et indexable pour chaque notion.

Les limites à ne pas reproduire sont :

- les exemples principalement statiques ;
- les très longues pages ;
- une navigation latérale surchargée ;
- la séparation entre la référence et l’outil d’exécution ;
- une organisation utile uniquement lorsque l’utilisateur connaît déjà le nom de l’élément recherché.

Le concept recommandé est :

> La rigueur et la capacité de recherche de dax.guide, l’expérimentation de W3Schools et la visualisation de Hydra Studio.

Nom de travail possible :

> **Hydra Guide — Explore, edit and run every Hydra DSL element**

---

## 5. Architecture de l’information

Le site doit proposer quatre portes d’entrée cohérentes, mais toutes reposent sur le même moteur interactif.

### 5.1 Playground

Espace libre permettant de :

- écrire ou coller un Hydra DSL ;
- charger un exemple ;
- modifier des données ;
- exécuter ou simuler le traitement ;
- voir le diagramme ;
- examiner le plan d’exécution, le résultat et les erreurs ;
- partager ou exporter le projet.

### 5.2 Learn

Parcours guidés et interactifs. Une étape transmet une seule idée et exige une action de l’utilisateur.

### 5.3 Guide

Encyclopédie exécutable du DSL, inspirée de dax.guide. Chaque élément possède une fiche interactive normalisée.

### 5.4 Migrate

Laboratoire de migration depuis Airflow, Dagster, Prefect et d’autres outils vers Hydra DSL.

La navigation principale proposée est :

```text
Playground | Learn | Guide | Migrate
```

Il ne faut pas créer une section « Documentation » traditionnelle en parallèle qui deviendrait le véritable centre du site.

---

## 6. Navigation du Hydra Guide

Trois modes de navigation sont nécessaires.

### 6.1 A–Z

Pour les utilisateurs qui connaissent déjà le nom recherché :

```text
aggregate · api · branch · csv · filter · join · parquet · retry · workflow
```

### 6.2 Groupes

Pour explorer une famille fonctionnelle :

```text
Sources
├── Files
├── Databases
├── APIs
└── Messaging

Transformations
├── Rows
├── Columns
├── Joins
├── Aggregations
└── Data quality

Orchestration
├── Jobs
├── Workflows
├── Triggers
├── Branches
└── Retry policies
```

### 6.3 Flux ou intention

Ce mode, propre à Hydra, aide l’utilisateur qui ne connaît pas encore les noms du DSL :

```text
Lire → Transformer → Contrôler → Écrire → Orchestrer
```

La recherche doit accepter des intentions telles que :

- « lire un CSV puis filtrer » ;
- « écrire dans PostgreSQL avec upsert » ;
- « exécuter deux jobs en parallèle » ;
- « migrer un DAG Airflow ».

Les résultats doivent proposer directement les éléments associés et un exemple exécutable.

---

## 7. Catalogue des éléments

La page d’accueil du Guide doit présenter un catalogue filtrable :

```text
Rechercher dans Hydra DSL…                              [Ctrl/⌘ K]

[Sources] [Destinations] [Transforms] [Jobs]
[Workflows] [Triggers] [Policies] [Expressions]

Filtres :
[Batch] [Streaming] [Pushdown] [Stable] [Beta] [Deprecated]
```

Filtres complémentaires possibles :

- type de données ;
- moteur ou runtime ;
- local ou distribué ;
- état de maturité ;
- support incrémental ;
- CDC ;
- parallélisme ;
- idempotence ;
- version minimale de Hydra.

---

## 8. Modèle canonique d’une fiche interactive

Chaque élément du DSL doit suivre une structure commune.

Exemple pour une transformation `filter` :

```text
Transforms / Rows / Filter

FILTER
Conserve les lignes qui satisfont une expression.

[Stable] [Batch] [Streaming] [SQL Pushdown]
```

La zone principale doit être immédiatement interactive :

```text
┌────────────────────────┬────────────────────────┐
│ Hydra DSL              │ Pipeline               │
│                        │                        │
│ - filter:              │ Source → Filter → View │
│     amount > 100       │                        │
├────────────────────────┼────────────────────────┤
│ Données d’entrée       │ Résultat               │
│ 45, 120, 300           │ 120, 300               │
└────────────────────────┴────────────────────────┘

[Exécuter] [Réinitialiser] [Ouvrir dans Playground]
```

Une fiche doit pouvoir comporter :

1. Une définition courte.
2. Les badges de capacité et de maturité.
3. L’éditeur Hydra DSL.
4. Le diagramme synchronisé.
5. Les données d’entrée et de sortie.
6. Les paramètres modifiables.
7. Le schéma YAML interactif.
8. Les résultats et métriques d’exécution.
9. Les erreurs fréquentes.
10. Les éléments liés.
11. Les alternatives recommandées.
12. La compatibilité par version.
13. Les équivalents dans les outils concurrents.

Modifier une propriété depuis un tableau ou un formulaire doit mettre à jour le YAML. Modifier le YAML doit mettre à jour le formulaire, le diagramme et le résultat.

---

## 9. Progression pédagogique

### Niveau 1 — Découverte

L’utilisateur modifie des valeurs simples et observe les effets sur une source, une transformation et une destination.

### Niveau 2 — Construction visuelle

L’utilisateur assemble des composants. Le Hydra DSL correspondant est généré en temps réel.

### Niveau 3 — Écriture du DSL

L’utilisateur complète ou écrit le YAML avec :

- autocomplétion ;
- documentation contextuelle ;
- validation immédiate ;
- explication visuelle des erreurs ;
- propositions de correction.

### Niveau 4 — Orchestration

L’utilisateur manipule :

- les dépendances ;
- les branches ;
- les conditions ;
- le parallélisme ;
- les triggers ;
- les retries ;
- les workflows imbriqués.

### Niveau 5 — Projet réel

L’utilisateur réalise un mini-projet complet, puis l’exporte vers Hydra Studio ou le CLI.

Le passage au niveau suivant doit être déclenché par une action réussie, et non par la simple lecture d’une page.

---

## 10. Types d’interactions

L’expérience ne doit pas se résumer à un éditeur YAML et un bouton d’exécution. Les formes d’interaction peuvent inclure :

- édition directe du DSL ;
- construction visuelle ;
- glisser-déposer ;
- sélection d’un nœud du diagramme ;
- inspection du schéma ;
- modification des données d’entrée ;
- animation du passage des données ;
- aperçu après chaque transformation ;
- comparaison avant/après ;
- correction guidée ;
- exercices « casser puis réparer » ;
- génération du DSL depuis un diagramme ;
- génération du diagramme depuis le DSL ;
- comparaison Hydra/Airflow/Dagster/Prefect ;
- affichage du plan d’exécution et du pushdown.

---

## 11. Sources et destinations : stratégie des données

Il ne faut ni connecter le playground public à de véritables bases externes par défaut, ni présenter toutes les technologies comme de simples tableaux identiques.

La stratégie retenue est hybride :

> Utiliser un jeu de données standard pour apprendre et comparer, puis simuler fidèlement les capacités propres à chaque technologie.

### 11.1 Jeu de données canonique Hydra

Créer un petit domaine pédagogique commun :

```text
customers
- customer_id
- name
- country
- created_at

orders
- order_id
- customer_id
- amount
- status
- ordered_at

products
- product_id
- name
- category
- price
```

Ces mêmes données doivent être exposées sous plusieurs formes :

- CSV ;
- JSON ;
- Parquet ;
- SQLite ou DuckDB ;
- PostgreSQL simulé ;
- API REST simulée ;
- messages ou événements simulés.

Cela permet de comparer les sources sans changer de problème métier.

### 11.2 Fiche d’une source de base de données

Exemple pour PostgreSQL :

```text
┌────────────────────────┬────────────────────────┐
│ Configuration Hydra    │ Base simulée           │
│                        │                        │
│ type: postgresql       │ customers              │
│ table: customers       │ orders                 │
│ mode: full             │ products               │
├────────────────────────┼────────────────────────┤
│ Requête exécutée       │ Données extraites      │
│ SELECT * FROM ...      │ Tableau de résultats   │
└────────────────────────┴────────────────────────┘
```

L’utilisateur doit pouvoir :

- choisir une table ;
- parcourir son schéma ;
- écrire une requête ;
- sélectionner des colonnes ;
- ajouter un filtre ;
- simuler une lecture complète ou incrémentale ;
- voir le SQL produit ;
- distinguer ce qui est exécuté dans la base de ce qui est exécuté dans Hydra.

### 11.3 Fiche d’une destination

Une destination doit montrer l’effet réel de l’écriture :

```text
Avant exécution                 Après exécution
3 lignes                        5 lignes
```

Les modes suivants doivent pouvoir être expérimentés :

- append ;
- replace ;
- merge ;
- upsert ;
- truncate, si supporté.

L’interface montre :

- le schéma cible ;
- les lignes insérées ;
- les lignes mises à jour ;
- les lignes rejetées ;
- les conflits de types ;
- les contraintes violées ;
- le SQL ou le plan logique généré ;
- l’état final ;
- une restauration ou réinitialisation du laboratoire.

### 11.4 Contrat commun et capacités spécifiques

Chaque connecteur doit présenter deux couches :

1. Le contrat commun Hydra : connexion, sélection, schéma, incrémental, lots, erreurs et stratégie d’écriture.
2. Les capacités propres au moteur : pushdown, CDC, parallélisme, transactions, upsert et limitations.

Exemple :

| Capacité     | PostgreSQL | MySQL               | SQLite  |
| ------------ | ----------:| -------------------:| -------:|
| Lecture SQL  | Oui        | Oui                 | Oui     |
| Pushdown     | Oui        | Oui                 | Partiel |
| CDC          | Oui        | Selon configuration | Non     |
| Upsert       | Oui        | Oui                 | Oui     |
| Parallélisme | Oui        | Oui                 | Limité  |

### 11.5 Trois niveaux d’exécution

#### Niveau 1 — Simulation immédiate

Une base embarquée, par exemple SQLite ou DuckDB derrière l’abstraction Hydra, fournit une exécution rapide, reproductible et sans secrets.

#### Niveau 2 — Bac à sable réaliste

Pour les ateliers avancés, un véritable PostgreSQL ou MySQL éphémère peut être lancé dans un environnement strictement isolé, limité et automatiquement détruit.

#### Niveau 3 — Connexion à la base de l’utilisateur

Cette possibilité doit être réservée à Hydra installé localement, Hydra Studio ou un agent local sécurisé. Les secrets de production ne doivent pas être envoyés au navigateur ou au playground public.

```text
Documentation web
        ↓ configuration
Agent Hydra local
        ↓ connexion sécurisée
Base de l’utilisateur
```

---

## 12. Apprentissage par les erreurs

Le laboratoire doit permettre de provoquer volontairement :

- une colonne inexistante ;
- une incompatibilité de types ;
- une clé dupliquée ;
- une table absente ;
- une violation de contrainte ;
- un timeout ;
- une connexion refusée simulée ;
- un échec partiel d’écriture.

L’utilisateur doit voir :

1. l’endroit exact du problème ;
2. son effet sur le diagramme ou l’exécution ;
3. une explication concise ;
4. une suggestion de correction ;
5. le résultat après correction.

---

## 13. Migration depuis les concurrents

Une part importante des nouveaux utilisateurs proviendra d’Airflow, Dagster, Prefect, NiFi, Talend, Informatica, dbt ou d’autres environnements.

La migration n’est pas une annexe. Elle constitue un produit d’acquisition à part entière, selon une stratégie de **migration-led growth**.

Ordre de priorité recommandé :

1. Airflow ;
2. Dagster et Prefect ;
3. dbt associé à Airbyte ou Meltano ;
4. NiFi, Talend et Informatica ;
5. Kestra et autres orchestrateurs YAML.

### 13.1 Parcours de migration

```text
Importer ou coller le projet source
                ↓
Analyse statique sans exécution arbitraire
                ↓
Rapport de compatibilité
                ↓
Hydra DSL généré
                ↓
Comparaison visuelle avant/après
                ↓
Validation sur données d’exemple
                ↓
Export vers Hydra
```

Le rapport doit séparer :

- les éléments convertis automatiquement ;
- les conversions approximatives ;
- les éléments non supportés ;
- les interventions manuelles ;
- les différences sémantiques.

Ne jamais promettre une migration automatique à 100 % si elle ne peut pas être garantie.

### 13.2 Correspondances initiales

| Airflow         | Hydra                           |
| --------------- | ------------------------------- |
| DAG             | Workflow                        |
| Operator        | Job, transformation ou action   |
| Task dependency | Dépendance de workflow          |
| Schedule        | Trigger                         |
| Retry policy    | Politique de nouvelle tentative |
| Connection      | Source, destination ou secret   |

Chaque fiche du Guide peut proposer un onglet ou sélecteur `Coming from` :

```text
[Airflow] [Dagster] [Prefect] [NiFi] [Talend]
```

L’équivalent concurrent, le Hydra DSL et les deux représentations visuelles sont alors comparés dans la même interface.

---

## 14. SEO sans longs paragraphes

Les schémas et interactions ne pénalisent pas directement le référencement. Le risque vient du contenu enfermé exclusivement dans un canvas, une image ou une application JavaScript non indexable.

La solution consiste à avoir deux représentations du même contenu :

- une représentation visuelle et interactive ;
- une représentation HTML sémantique, concise et accessible.

Il ne faut pas créer de longs textes cachés ni pratiquer le bourrage de mots-clés.

Chaque fiche doit posséder :

- une URL unique ;
- un titre H1 explicite ;
- une définition courte ;
- le schéma YAML rendu dans le HTML ;
- la liste des propriétés ;
- les paramètres et types ;
- les capacités ;
- les erreurs possibles ;
- le résultat attendu ;
- les éléments associés ;
- les équivalents de migration ;
- des légendes textuelles pour les diagrammes.

Exemples d’URL :

```text
/guide/sources/csv
/guide/sources/postgresql
/guide/transforms/filter
/guide/transforms/join
/guide/destinations/postgresql
/guide/workflows/branch
/guide/triggers/cron
```

Exigences techniques SEO :

- rendu statique ou serveur des informations essentielles ;
- HTML sémantique ;
- diagrammes SVG avec titre et description ;
- textes alternatifs et légendes ;
- code YAML présent dans le DOM ;
- données structurées adaptées, par exemple `TechArticle`, `HowTo`, `FAQ` et `BreadcrumbList` ;
- sitemap ;
- liens internes ;
- URL canoniques ;
- bonnes performances et Core Web Vitals ;
- chargement différé des composants lourds ;
- aperçu statique visible avant le chargement du simulateur.

Les pages de migration ont un fort potentiel SEO :

- migrer un DAG Airflow vers Hydra ;
- convertir un pipeline Dagster en YAML ;
- alternative déclarative à Airflow ;
- Airflow vs Hydra ;
- orchestration ETL avec un DSL YAML.

---

## 15. Parcours d’acquisition cible

```text
Recherche web
      ↓
Fiche Hydra Guide ou page de migration
      ↓
Manipulation immédiate sans installation
      ↓
Hydra DSL et diagramme générés
      ↓
Exécution sur données d’exemple
      ↓
Export du projet
      ↓
Installation de Hydra ou ouverture dans Hydra Studio
```

Le site, le playground, Hydra DSL, le moteur, le CLI, l’API et Studio doivent former une continuité.

---

## 16. Sécurité du playground public

Le playground public doit être considéré comme un environnement hostile.

Par défaut, interdire ou isoler strictement :

- Python arbitraire ;
- Bash ;
- PowerShell ;
- SSH ;
- commandes système ;
- accès libre au réseau ;
- lecture de fichiers du serveur ;
- secrets persistants ;
- connexions directes aux bases de production.

Prévoir :

- environnements éphémères ;
- réinitialisation automatique ;
- limites de temps ;
- limites de mémoire et CPU ;
- quotas ;
- jeux de données contrôlés ;
- audit des opérations ;
- nettoyage systématique.

L’analyse d’un projet Airflow Python doit être statique. Le site ne doit pas exécuter le code importé.

---

## 17. Source de vérité et génération

La documentation ne doit pas diverger du moteur.

Autant que possible, le Hydra Guide doit être généré depuis :

- les schémas officiels du DSL ;
- le registre réel des composants ;
- les métadonnées de capacité ;
- les validations du moteur ;
- les versions et états de maturité ;
- des exemples testés automatiquement.

Chaque composant devrait exposer des métadonnées documentaires structurées :

- nom ;
- catégorie ;
- résumé ;
- schéma ;
- propriétés ;
- exemples ;
- capacités ;
- compatibilité ;
- erreurs ;
- relations ;
- équivalents de migration ;
- statut stable, bêta ou déprécié.

Une modification du DSL doit provoquer une vérification ou une régénération des fiches correspondantes.

---

## 18. Feuille de route recommandée

### Phase 1 — Socle interactif

- éditeur YAML ;
- validation ;
- synchronisation DSL/diagramme ;
- jeux de données canoniques ;
- simulation déterministe ;
- résultats et erreurs ;
- partage et réinitialisation.

### Phase 2 — Parcours canonique interactif

- premier pipeline ;
- sources ;
- transformations ;
- destinations ;
- orchestration ;
- erreurs guidées ;
- mini-projet exportable.

Cette phase ne doit pas produire des chapitres traditionnels.

### Phase 3 — Hydra Guide

- catalogue A–Z ;
- groupes ;
- navigation par intention ;
- recherche ;
- fiches interactives normalisées ;
- compatibilité et relations ;
- génération depuis les schémas réels.

### Phase 4 — Laboratoires de bases de données

- source SQL simulée ;
- destination SQL ;
- modes d’écriture ;
- incrémental ;
- pushdown ;
- erreurs de schéma et contraintes ;
- environnements réalistes éphémères si nécessaire.

### Phase 5 — Migration

- Airflow en premier ;
- Dagster et Prefect ensuite ;
- analyse statique ;
- rapport de couverture ;
- conversion assistée ;
- comparaison visuelle ;
- export.

### Phase 6 — Passage au produit réel

- ouverture dans Hydra Studio ;
- export pour le CLI ;
- dépôt Git ;
- agent local ;
- connexion sécurisée aux systèmes de l’utilisateur.

---

## 19. Indicateurs de réussite

Mesurer au minimum :

- temps avant la première exécution réussie ;
- taux de démarrage du playground ;
- taux de réussite des exercices ;
- nombre de fiches exécutées ;
- taux d’ouverture dans le playground complet ;
- taux d’export ;
- clic vers l’installation ou Hydra Studio ;
- couverture des migrations automatiques ;
- taux de correction après rapport de migration ;
- trafic organique par fiche ;
- performance des pages ;
- taux de retour des utilisateurs.

L’indicateur principal ne doit pas être le nombre de pages lues, mais le nombre d’interactions réussies conduisant à une compréhension ou à un projet exportable.

---

## 20. Critères d’acceptation globaux

La solution est conforme à cette stratégie si :

1. Un visiteur peut comprendre et exécuter un premier exemple sans installer Hydra.
2. Chaque notion centrale du DSL possède une fiche exécutable.
3. Le YAML, le formulaire, le diagramme et les résultats restent synchronisés.
4. Les sources et destinations utilisent un jeu canonique comparable.
5. Les particularités réelles des moteurs restent visibles.
6. Les connexions de production ne sont pas requises dans le navigateur.
7. Airflow dispose d’un parcours de migration prioritaire.
8. Le contenu essentiel est indexable sans longs articles artificiels.
9. Les exemples sont testés contre le schéma ou le moteur Hydra.
10. Le parcours se termine par un export, Hydra Studio ou une installation locale.

La solution n’est pas conforme si elle devient :

- un site de longs tutoriels textuels ;
- une référence statique avec seulement quelques boutons « Run » ;
- un playground isolé de la documentation ;
- une copie visuelle de dax.guide sans exécution ;
- une documentation de connecteurs sans comparaison ni simulation ;
- un convertisseur concurrent opaque promettant une fidélité irréaliste.

---

## Conclusion

Hydra doit posséder une encyclopédie exécutable de son DSL.

Le modèle final repose sur quatre idées complémentaires :

1. **dax.guide** pour la rigueur, la recherche et les fiches canoniques ;
2. **W3Schools** pour la manipulation immédiate ;
3. **Hydra Studio** pour les représentations visuelles ;
4. **la migration interactive** pour attirer et convertir les utilisateurs venant d’autres écosystèmes.

La donnée canonique rend les exemples cohérents. Les simulations propres à chaque moteur rendent la documentation crédible. Le HTML sémantique rend les expériences indexables. Le playground transforme enfin la documentation en véritable expérience produit.

---

# Partie II — Architecture technique de construction

> Cette partie complète la stratégie (Partie I) par les **décisions techniques de
> mise en œuvre**, convergées lors d'une revue croisée entre deux agents (Claude
> et GPT Codex) et vérifiées contre le codebase réel. La Partie I dit *quoi*
> construire ; la Partie II dit *comment* le construire. Aucune décision ci-dessous
> ne contredit la Partie I : elle la rend exécutable.

---

## 21. Reformulation de la contrainte principale

La contrainte fondatrice n'est **pas** « exécuter Hydra dans le navigateur ». Cette
formulation est un raccourci dangereux : elle pousserait à réimplémenter le moteur
en JavaScript, ce que le §17 interdit.

La contrainte réelle est :

> **Manipuler et exécuter Hydra sans installation préalable.**
> L'exécution peut être locale (navigateur) *ou* distante (service sécurisé).

Conséquence : aucun dogme « tout navigateur ». On choisit le mode d'exécution
composant par composant, selon le besoin de fidélité (voir §23).

---

## 22. Stack technique retenu

| Couche                           | Choix                                        | Statut                                            |
| -------------------------------- | -------------------------------------------- | ------------------------------------------------- |
| Générateur de site               | **Astro** (architecture « îlots »)           | Hypothèse prioritaire — à confirmer par prototype |
| Composants interactifs           | React ou Svelte, dans les îlots Astro        | À confirmer avec le prototype                     |
| CI / génération / test           | **GitHub Actions**                           | Retenu                                            |
| Hébergement du Guide statique    | **GitHub Pages**                             | Retenu                                            |
| Exécution réaliste (niveaux 2/3) | Backend Hydra distant, **hors** GitHub Pages | Retenu (infra séparée)                            |

**Pourquoi Astro plutôt que Hugo (stack Kubernetes).** La doc Kubernetes est
*textuelle* ; la nôtre est *interactive-first* (§3). L'architecture « îlots »
d'Astro rend chaque fiche en HTML sémantique statique (indexable, §14) et ne charge
du JavaScript que pour les blocs interactifs, à la demande — exactement le §14
(« aperçu statique avant le chargement du simulateur », « chargement différé des
composants lourds »). De plus, ses *content collections* génèrent chaque fiche à
partir de fichiers de données (JSON/YAML), ce qui sert directement le §17.

**Pourquoi « à confirmer par prototype ».** Le choix n'est pas gravé. Le vertical
slice `filter` (§25) doit mesurer cinq critères avant validation :

1. le poids de chargement ;
2. le temps avant la première interaction ;
3. la fidélité de la simulation ;
4. le SEO effectivement rendu ;
5. la facilité de génération des fiches.

**GitHub Pages ≠ toute l'infrastructure.** Pages héberge le Guide *statique*
uniquement. L'exécution lourde (niveaux 2/3) vit sur une infra distincte
(conteneur / Function / bac à sable éphémère) appelée via API. Hébergement de la
doc et infra d'exécution sont **découplés**.

---

## 23. Stratégie d'exécution hybride (mapping technologie ↔ niveaux du §11.5)

On ne réimplémente **jamais** tout le Hydra DSL en JavaScript.

| Niveau (§11.5)            | Besoin                                               | Technologie retenue                                                                                                                 |
| ------------------------- | ---------------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------------------- |
| 1 — Simulation immédiate  | Pédagogie simple, réponse instantanée, client-side   | **TypeScript** pour les cas simples (filter, select, rename…) ; **DuckDB-WASM** pour les exemples tabulaires (join, aggregate, SQL) |
| 2 — Bac à sable réaliste  | Fidélité au moteur, orchestration, connecteurs réels | **Vrai moteur Hydra distant** (backend éphémère isolé, §16)                                                                         |
| 3 — Base de l'utilisateur | Connexion sécurisée, secrets                         | **Agent Hydra local / Studio uniquement** (jamais le playground public)                                                             |

Points d'attention validés lors de la revue :

- **Pyodide** : à tester, mais probablement trop lourd/contraignant pour faire
  tourner le moteur complet — réservé à une expérimentation, pas au socle.
- **DuckDB-WASM** : excellent pour les exemples tabulaires, mais **insuffisant**
  pour simuler l'orchestration Hydra (jobs, workflows, triggers) → ceux-ci relèvent
  du niveau 2 distant.
- **TypeScript** : réservé aux simulations pédagogiques simples, pas à la
  reproduction du moteur.

---

## 24. Source de vérité : métadonnées dérivées du moteur (§17 rendu concret)

La règle du §17 (« la documentation ne doit pas diverger du moteur ») se traduit
par une décision précise, vérifiée dans le code :

> Les **propriétés, types, valeurs par défaut et contraintes** de chaque fiche sont
> **générés depuis le moteur**, jamais écrits à la main. Seul le contenu éditorial
> (résumé, exemples, erreurs fréquentes, relations, équivalents migration) est
> rédigé, et de façon temporaire.

**Ce qui existe déjà dans le codebase** (contrôlé, pas supposé) :

- `internal/parser/transform.py` — un **modèle Pydantic v2 par transformation**
  (`FilterOp`, `JoinOp`, `AggregateOp`, `SelectOp`, `CastOp`, `ScriptOp`, …), avec
  champs typés, défauts, contraintes (`Field(min_length=1)`) et validateurs.
- Un **registre symétrique des transformations** : `_OP_MODEL_MAP` (18 opérations)
  et l'énumération `OpName`. → l'énumération automatique des transforms est déjà
  possible, contrairement à ce qu'on craignait.
- `internal/parser/source.py` et `destination.py` — modèles Pydantic pour sources
  (`ExtractConfig`, `SchemaFieldConfig`, `SchemaConfig`) et destinations
  (`LoadConfig`).
- `internal/connector/registry.py` — registre factory des connecteurs (énumérables).
- `internal/connector/interface.py` — `ConnectorCapabilities` (`supports_transactions`,
  `supports_upsert`, `supports_incremental`) → embryon des badges de capacité (§8, §11.4).

**Le mécanisme** : Pydantic v2 expose `model_json_schema()`, qui produit
automatiquement un JSON Schema (propriétés, types, requis/optionnel, défauts,
contraintes) pour chaque op / source / destination. C'est la source canonique des
propriétés — **zéro divergence, zéro plomberie nouvelle** pour cette partie.

**Ce qui manque encore** (couche éditoriale et d'agrégation, à ajouter) :

- `description` / `summary` / `category` par composant ;
- catalogue d'erreurs normalisé ;
- relations / alternatives entre éléments ;
- équivalents de migration (Airflow, Dagster…) ;
- statut de maturité (stable / bêta / déprécié).

Cette couche éditoriale peut être écrite à la main **au format canonique dès le
départ** (schéma validable), puis progressivement alimentée / remplacée par une
méthode `describe()` exposée par les composants du moteur, sans casser l'existant
(Règle 0 du `CLAUDE.md`).

---

## 25. Plan de construction convergé et séquencement

L'ordre est important : le **format canonique des métadonnées vient avant** la
première fiche, pour éviter toute divergence dès le départ.

1. **Jeu de données canonique** (§11.1) — `customers` / `orders` / `products`,
   exposé en CSV, JSON, Parquet, SQLite/DuckDB.
2. **Format canonique de métadonnées d'un composant** — schéma JSON/YAML validable,
   avec la partie *propriétés* dérivée de Pydantic (`model_json_schema()`) et la
   partie *éditoriale* écrite à la main.
3. **Vertical slice `filter`** — une fiche `filter` de bout en bout (fiche HTML
   sémantique + îlot playground en simulation TypeScript) construite sur ce format,
   dans Astro. C'est ce prototype qui **valide ou invalide** le stack selon les cinq
   critères du §22.
4. **Industrialisation** — génération des autres fiches depuis les métadonnées via
   GitHub Actions ; test automatique de chaque exemple YAML contre le schéma réel
   (§17) ; déploiement sur Pages.
5. **Backend éphémère** (niveaux 2/3) — infra distante isolée (§16) pour les
   comportements exigeant la fidélité (orchestration, connecteurs réels).

---

## 26. Points à valider et risques

- **Astro** : confirmer par le prototype `filter` (cinq critères du §22) avant de
  figer. Second candidat de repli : Docusaurus (si besoin de versionning de doc
  intégré).
- **Frontière niveau 1 / niveau 2** : décider précisément quels éléments restent en
  simulation client-side et lesquels basculent sur le moteur distant. Critère :
  dès qu'il y a orchestration ou connecteur réel → niveau 2.
- **Couche `describe()`** : concevoir l'ajout de métadonnées éditoriales aux
  composants de façon **non intrusive**, sans casser les 48+ tests CLI ni l'archive
  existante (Règle 0).
- **Backend éphémère** : définir l'infra minimale et sûre (§16) — environnements
  jetables, quotas, limites CPU/mémoire, analyse statique des projets importés
  (jamais d'exécution de code arbitraire importé).
- **Ne pas retomber** dans les anti-patterns du §20 : longs tutoriels, référence
  statique avec quelques boutons « Run », playground isolé de la doc, copie de
  dax.guide sans exécution.

---

## 27. Maîtrise du périmètre (risque n°1) — Guide découplé du playground

> Verdict de la revue croisée : **17/20**. Le risque principal n'est **pas** la
> qualité de l'idée, mais **sa taille**. Si Hydra démarre par une tranche verticale
> réduite et exemplaire, cette documentation devient un avantage concurrentiel réel.
> Si toutes les fonctionnalités sont engagées simultanément, le playground risque de
> retarder longtemps la publication du Guide.

C'est le garde-fou opérationnel le plus important de tout le document.

### 27.1 Règle de découplage

Le **Guide** et le **playground** ne doivent jamais être couplés dans le calendrier :

- Le **Guide statique** (fiches HTML sémantiques, propriétés dérivées du moteur via
  Pydantic + contenu éditorial) apporte déjà de la valeur seul : SEO, référence
  indexable (§14), catalogue navigable. Il peut — et doit — être **publié tôt**.
- Le **playground interactif** est ce qui prend du temps. Il **enrichit** le Guide,
  il ne doit **jamais le retenir en otage**.

### 27.2 Périmètre de première livraison

**Livrer d'abord :**

- le Guide statique complet — toutes les fiches, propriétés générées depuis le
  moteur (§24) ;
- **une seule** fiche pleinement interactive de bout en bout : `filter`, la tranche
  verticale exemplaire (§25).

**Ne pas bloquer** la publication du Guide sur l'interactivité des autres fiches :
chacune gagne son îlot playground **progressivement, fiche par fiche**.

**Repousser explicitement** après la première mise en ligne :

- le backend d'exécution éphémère (niveaux 2/3, §23) ;
- les laboratoires de bases de données (§11) ;
- les parcours de migration (§13).

### 27.3 Principe directeur

> Livraison **incrémentale** : le Guide d'abord, une tranche verticale exemplaire
> ensuite, puis l'interactivité fiche par fiche. Ne jamais engager toutes les
> fonctionnalités en même temps.

Le succès se mesure à la **date de première publication utile**, pas à
l'exhaustivité du premier jour.
