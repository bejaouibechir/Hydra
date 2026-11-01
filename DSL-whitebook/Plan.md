# Plan du livre blanc Hydra DSL : workflows, jobs, actions

*Hypothèse à valider : la hiérarchie est Workflow → Job → Action.*

## 0. Introduction (courte)

- Rôle du Hydra DSL dans Hydra ETL
- Ce qui change avec la nouvelle version
- Le modèle d'exécution en une figure : Workflow → Jobs → Actions
- Conventions de lecture (notation de la grammaire, mots réservés, typographie)

## 1. Les workflows

- 1.1 Définition et rôle (orchestration de bout en bout)
- 1.2 Syntaxe de déclaration : mot-clé, nom, en-tête
- 1.3 Attributs : description, version, paramètres, variables globales
- 1.4 Déclenchement : manuel, planifié (cron), événementiel
- 1.5 Enchaînement des jobs : séquentiel, parallèle, dépendances
- 1.6 Contrôle de flux : conditions, boucles, branchements
- 1.7 Gestion des erreurs au niveau du workflow : arrêt, reprise, notification
- 1.8 Règles de grammaire (EBNF) et contraintes de validation
- 1.9 Exemple complet commenté

## 2. Les jobs

- 2.1 Définition : unité logique de traitement
- 2.2 Syntaxe de déclaration et de nommage
- 2.3 Entrées/sorties : sources, cibles, passage de données entre jobs
- 2.4 Paramètres et portée des variables (job ou workflow)
- 2.5 Dépendances (`depends on` ou équivalent) et ordre d'exécution
- 2.6 Politique d'exécution : retry, timeout, conditions d'exécution
- 2.7 Réutilisation : templates, inclusion, héritage (si supportés)
- 2.8 Règles de grammaire (EBNF) et erreurs fréquentes
- 2.9 Exemples : job simple, puis job paramétré

## 3. Les actions

- 3.1 Définition : opération élémentaire
- 3.2 Syntaxe générale d'une action
- 3.3 Catalogue par famille :
  - Extraction (lecture de sources)
  - Transformation (filtre, mapping, jointure, agrégation…)
  - Chargement (écriture dans les cibles)
  - Utilitaires (log, variables, appels externes, fichiers)
- 3.4 Arguments : obligatoires ou optionnels, types, valeurs par défaut
- 3.5 Expressions et fonctions utilisables dans les actions
- 3.6 Gestion d'erreur au niveau de l'action
- 3.7 Règles de grammaire (EBNF) par famille
- 3.8 Exemples unitaires pour chaque famille

## 4. Synthèse

- Cas pratique complet : un workflow, plusieurs jobs, des actions
- Tableau récapitulatif des mots-clés
- Différences avec l'ancienne version (migration)
- Bonnes pratiques de structuration

## Annexes

- Grammaire complète en EBNF
- Liste des mots réservés
- Codes d'erreur de validation

---

## Ce que Bechir doit fournir, par sujet

- **Workflows** : grammaire du bloc workflow, modes de déclenchement, 1 ou 2 workflows réels
- **Jobs** : syntaxe des dépendances et des politiques retry/timeout, 2 jobs réels
- **Actions** : liste à jour des actions avec leurs arguments, 1 exemple par famille
- **Global** : changelog depuis la version publiée sur le site, et les sections du plan à retirer si elles ne correspondent à aucune fonctionnalité réelle

## Découpage en sessions

- **Session 1** : introduction et chapitre 1 (Workflows)
- **Session 2** : chapitres 2 (Jobs) et 3 (Actions)
- **Session 3** : synthèse, annexes et relecture



J'ai ajouté un chapitre 4 « Paramètres et secrets » au plan, dans le document du projet. La synthèse devient le chapitre 5.

## 4. Paramètres et secrets

- 4.1 Principes : ce qui distingue un paramètre, une variable et un secret
- 4.2 Déclaration des paramètres : syntaxe, types, valeurs par défaut, caractère obligatoire, validation
- 4.3 Portée et héritage : du workflow au job puis à l'action, surcharge, priorité de résolution
- 4.4 Sources de valeurs : ligne de commande, fichier de configuration, variables d'environnement, profils dev/recette/prod
- 4.5 Référencement : syntaxe d'interpolation dans les jobs et les actions
- 4.6 Secrets : déclaration, sources (coffre-fort, variables d'environnement, fichier chiffré), référencement
- 4.7 Sécurité : masquage dans les logs, pas de stockage en clair, rotation, droits d'accès
- 4.8 Erreurs : paramètre manquant, type invalide, secret introuvable
- 4.9 Règles de grammaire (EBNF)
- 4.10 Exemples : workflow paramétré par environnement, connexion à une base via un secret

Les sections 1.3, 2.4 et 3.4 renvoient désormais à ce chapitre pour éviter les doublons. Le découpage passe à 4 sessions : ce chapitre a sa propre session, la 3.

**Bechir doit fournir pour ce chapitre :**

- La syntaxe de déclaration et de référencement des paramètres et des secrets
- L'ordre de priorité quand une même valeur vient de plusieurs sources
- Les sources de secrets supportées par Hydra
- Le comportement de masquage des secrets dans les logs
