# Rapport d'exigences pour l'amélioration des prototypes Hydra Guide

**Version :** 1.0  
**Date :** 30 juillet 2026  
**Périmètre analysé :** `documentations/mockups/`  
**Statut :** cahier d'exigences proposé pour validation avant implémentation

---

## 1. Objet

Ce rapport transforme l'analyse des prototypes en exigences fonctionnelles,
éditoriales et techniques vérifiables. Il couvre :

- le catalogue du Guide ;
- la fiche canonique `filter` ;
- le Playground ;
- le parcours Migrate ;
- la navigation et le design system communs ;
- l'accessibilité, le responsive, le SEO, les performances et la sécurité ;
- la transposition des prototypes vers Astro et les îlots interactifs ;
- les tests et critères de livraison.

Les exigences complètent la stratégie définie dans `documentations.md` et le
séquencement de `PLAN_DE_CONSTRUCTION.md`. En cas de divergence, les décisions
figées dans ces deux documents restent prioritaires.

### 1.1 Prototypes de référence

- `mockups/guide.html`
- `mockups/fiche-filter.html`
- `mockups/playground.html`
- `mockups/migrate.html`
- captures desktop, tablette et mobile présentes dans `mockups/`

### 1.2 Terminologie normative

| Terme | Signification |
|---|---|
| **DOIT** | Exigence bloquante pour la livraison concernée |
| **DEVRAIT** | Exigence importante, différable seulement avec justification |
| **PEUT** | Amélioration utile mais non bloquante |
| **P0** | Bloquant : sécurité, accessibilité majeure, navigation ou architecture |
| **P1** | Requis pour une première publication utile de qualité |
| **P2** | Requis pour l'industrialisation ou l'enrichissement suivant |
| **P3** | Optimisation ultérieure |

---

## 2. Synthèse de la cible

Le produit final DOIT proposer un parcours continu :

```text
Recherche web ou accès direct
            ↓
Catalogue, fiche Guide ou page Migrate
            ↓
Compréhension par un exemple immédiatement manipulable
            ↓
Modification du DSL et validation
            ↓
Exécution ou simulation et visualisation du résultat
            ↓
Ouverture dans le Playground, export ou Hydra Studio
```

Les quatre portes d'entrée restent :

```text
Playground | Learn | Guide | Migrate
```

Le Guide statique et le Playground interactif DOIVENT rester découplés dans le
calendrier. La publication du Guide complet ne DOIT pas attendre
l'industrialisation de toutes les expériences interactives.

---

## 3. Principes non négociables

### EXG-GEN-001 — Expérience interactive

**Priorité : P0**

Chaque notion centrale du DSL DOIT à terme posséder une expérience interactive.
La première publication PEUT toutefois ne rendre pleinement interactive que la
fiche `filter`, conformément au plan incrémental.

**Acceptation :**

- `filter` permet de modifier, valider, exécuter et réinitialiser l'exemple ;
- le résultat change réellement lorsque l'expression change ;
- les autres fiches restent utiles et complètes sans JavaScript.

### EXG-GEN-002 — Contenu essentiel statique

**Priorité : P0**

Le contenu documentaire essentiel DOIT être rendu en HTML statique par Astro.
Il ne DOIT pas dépendre d'une injection JavaScript après chargement.

**Acceptation :**

- avec JavaScript désactivé, les titres, définitions, propriétés, exemples,
  capacités, erreurs et relations restent lisibles ;
- le catalogue contient des liens HTML indexables vers les fiches ;
- le YAML d'exemple est présent dans le DOM initial.

### EXG-GEN-003 — Source de vérité

**Priorité : P0**

Les propriétés, types, valeurs par défaut et contraintes DOIVENT être générés
depuis les modèles Pydantic du moteur via `model_json_schema()`.

**Acceptation :**

- aucune propriété technique n'est dupliquée manuellement dans les pages ;
- le build échoue lorsqu'une fiche générée n'est plus conforme au schéma ;
- les exemples YAML sont testés contre le schéma ou le moteur Hydra.

### EXG-GEN-004 — Continuité produit

**Priorité : P1**

Le Guide, le Playground, Migrate, le CLI, l'API et Hydra Studio DOIVENT employer
les mêmes concepts, noms de fichiers et exemples canoniques.

**Acceptation :**

- « Ouvrir dans Playground » conserve le DSL, les données et l'exemple actifs ;
- l'export produit une structure compatible avec le CLI ou Studio ;
- les termes source, transformation, destination, workflow et mode d'écriture
  restent identiques dans toutes les interfaces.

### EXG-GEN-005 — Honnêteté des simulations

**Priorité : P0**

Toute simulation DOIT être explicitement distinguée d'une exécution par le vrai
moteur Hydra.

**Acceptation :**

- l'interface indique « Simulation locale » ou « Moteur Hydra » ;
- aucune métrique simulée n'est présentée comme une mesure réelle ;
- la documentation explique les limites du niveau d'exécution actif.

---

## 4. Exigences communes de navigation et de design

### EXG-NAV-001 — En-tête unique

**Priorité : P0**

Un composant d'en-tête partagé DOIT être utilisé sur Guide, fiche, Playground,
Learn et Migrate.

**Acceptation :**

- logo, ordre des liens, thème, recherche et état actif sont cohérents ;
- aucune page ne maintient une copie indépendante de la navigation ;
- la hauteur de l'en-tête ne change pas entre deux pages.

### EXG-NAV-002 — Navigation mobile complète

**Priorité : P0**

La navigation principale ne DOIT jamais être seulement masquée sur mobile. Un
bouton menu accessible DOIT la remplacer.

**Acceptation :**

- à 320, 360, 390 et 430 px, les quatre sections restent accessibles ;
- le bouton expose `aria-expanded` et `aria-controls` ;
- `Escape`, un clic hors du menu et l'activation d'un lien ferment le menu ;
- le focus revient au bouton après fermeture ;
- le défilement de la page derrière le menu est contrôlé.

### EXG-NAV-003 — Recherche globale

**Priorité : P1**

La commande `Ctrl/⌘ K` DOIT être disponible de façon cohérente.

**Acceptation :**

- le raccourci place le focus dans la recherche ou ouvre la palette globale ;
- le raccourci affiché correspond à la plateforme ;
- aucun raccourci navigateur critique n'est détourné ;
- la recherche est utilisable intégralement au clavier.

### EXG-NAV-004 — Liens réels et URLs stables

**Priorité : P0**

Les liens `href="#"`, alertes simulant une navigation et routes fictives DOIVENT
être remplacés par des routes réelles avant publication.

**Acceptation :**

- aucun lien principal ne recharge ou ne remonte inutilement la page ;
- chaque fiche possède une URL canonique ;
- les routes suivent `/guide/{categorie}/{element}` ;
- les paramètres partageables du catalogue sont conservés dans l'URL.

### EXG-UI-001 — Design tokens communs

**Priorité : P1**

Couleurs, espacements, rayons, typographies, ombres, focus et états DOIVENT être
centralisés dans des tokens partagés.

**Acceptation :**

- aucune divergence entre les quatre prototypes pour un même composant ;
- les thèmes clair et sombre utilisent les mêmes noms de tokens ;
- les couleurs d'état ne sont jamais la seule information disponible.

### EXG-UI-002 — États standardisés

**Priorité : P1**

Chaque action asynchrone DOIT prévoir les états : initial, en cours, succès,
avertissement, erreur, résultat obsolète et indisponible.

**Acceptation :**

- le bouton Run indique l'exécution en cours et empêche les doubles soumissions ;
- une modification après exécution marque le résultat comme obsolète ;
- l'erreur n'efface pas le dernier résultat réussi sans explication ;
- les états sont annoncés aux technologies d'assistance.

### EXG-UI-003 — Langue cohérente

**Priorité : P1**

Une langue principale DOIT être choisie pour la première livraison. Le mélange
français/anglais dans un même parcours est interdit hors noms techniques.

**Acceptation :**

- navigation, boutons, erreurs et textes éditoriaux suivent la locale active ;
- `lang` dans le document correspond au contenu ;
- les formats de nombres, durées et dates suivent la locale.

---

## 5. Exigences du catalogue Guide

### EXG-GUI-001 — Trois modes de navigation

**Priorité : P1**

Le catalogue DOIT offrir Groupes, A–Z et Intention.

**Acceptation :**

- le mode actif est identifiable visuellement et via `aria-pressed` ;
- le changement de mode conserve autant que possible la recherche active ;
- l'état est partageable par URL ;
- le bouton Précédent du navigateur restaure l'état attendu.

### EXG-GUI-002 — Catalogue statique et enrichissement client

**Priorité : P0**

La liste initiale des éléments DOIT être générée par Astro. Le JavaScript PEUT
améliorer le filtrage, mais ne DOIT pas créer l'unique copie du catalogue.

**Acceptation :**

- tous les éléments sont présents dans le HTML initial ;
- sans JavaScript, les liens vers les fiches fonctionnent ;
- avec JavaScript, les filtres opèrent sans rechargement.

### EXG-GUI-003 — Recherche par nom et description

**Priorité : P1**

La recherche DOIT couvrir le nom, la catégorie, la description, les capacités,
les alias et les intentions associées.

**Acceptation :**

- `filter`, `filtrer` et une intention comme « garder certaines lignes »
  conduisent à la fiche pertinente selon la locale ;
- la recherche ignore raisonnablement casse et accents ;
- un état vide explique comment élargir la recherche ;
- le nombre de résultats est annoncé.

### EXG-GUI-004 — Sémantique des filtres

**Priorité : P1**

La logique entre plusieurs filtres DOIT être explicitée et testée. Par défaut :

- catégories sélectionnées : logique OU ;
- statuts sélectionnés : logique OU ;
- capacités sélectionnées : logique ET ;
- groupes différents : logique ET.

**Acceptation :**

- sélectionner Batch et Pushdown ne retourne que les composants ayant les deux ;
- un bouton « Effacer les filtres » apparaît lorsqu'un filtre est actif ;
- l'état actif ne repose pas uniquement sur la couleur ;
- les compteurs se mettent à jour immédiatement.

### EXG-GUI-005 — Métadonnées des cartes

**Priorité : P1**

Chaque carte DOIT afficher au minimum nom, catégorie, résumé, maturité et
capacités principales.

**Acceptation :**

- les badges possèdent une définition accessible ;
- Stable, Beta et Deprecated sont distinguables sans couleur ;
- les homonymes source/destination ont des URLs et libellés non ambigus.

### EXG-GUI-006 — Navigation par intention

**Priorité : P1**

Une intention DOIT mener vers une combinaison d'éléments et, lorsque disponible,
vers un exemple exécutable préchargé dans le Playground.

**Acceptation :**

- « lire un CSV puis filtrer » précharge une source CSV et `filter` ;
- l'URL de l'intention est partageable ;
- le résultat explique les éléments proposés, pas seulement leurs noms.

---

## 6. Exigences de la fiche canonique

### EXG-FIC-001 — Structure normalisée

**Priorité : P0**

Chaque fiche DOIT suivre l'ordre de base suivant :

1. fil d'Ariane ;
2. nom, définition, maturité et capacités ;
3. exemple principal interactif ou aperçu statique ;
4. éventuel bloc de migration contextualisé ;
5. propriétés et schéma ;
6. erreurs fréquentes ;
7. compatibilité et limitations ;
8. éléments liés et alternatives ;
9. discussion ou appel à contribution.

### EXG-FIC-002 — En-tête sémantique

**Priorité : P1**

La page DOIT comporter un seul H1 explicite, une définition courte et un fil
d'Ariane sémantique.

**Acceptation :**

- le fil d'Ariane utilise une liste et `BreadcrumbList` ;
- les badges comportent une explication textuelle ;
- le statut Deprecated indique l'alternative et la version de retrait.

### EXG-FIC-003 — Éditeur DSL

**Priorité : P0 pour `filter`**

L'éditeur DOIT permettre la modification du YAML, la validation et le retour à
l'exemple initial.

**Acceptation :**

- une étiquette accessible identifie l'éditeur ;
- la validation ne dépend pas d'une coloration syntaxique ;
- les erreurs indiquent ligne, champ, cause et correction possible ;
- `Réinitialiser` demande confirmation uniquement si des modifications utiles
  seraient perdues ;
- les raccourcis clavier sont documentés.

### EXG-FIC-004 — Synchronisation

**Priorité : P0 pour `filter`**

Le YAML, le formulaire de propriétés, le diagramme et le résultat DOIVENT
partager une source d'état cohérente.

**Acceptation :**

- changer `expr` dans le YAML met à jour le nœud `filter` ;
- changer `expr` dans le formulaire met à jour le YAML ;
- une entrée invalide n'est jamais exécutée silencieusement ;
- le résultat devient obsolète après une modification valide non exécutée ;
- les mises à jour ne provoquent pas de boucle ou de perte du curseur.

### EXG-FIC-005 — Diagramme

**Priorité : P1**

Le diagramme DOIT avoir une représentation visuelle et une représentation
textuelle équivalente.

**Acceptation :**

- le SVG possède un titre et une description ;
- l'ordre Source → Filter → View est disponible en texte ;
- le nœud concerné est associé à l'erreur active ;
- le diagramme reste lisible sans défilement horizontal à 320 px.

### EXG-FIC-006 — Données et résultats

**Priorité : P1**

Les données d'entrée et de sortie DOIVENT être comparables, accessibles et
cohérentes avec le jeu canonique.

**Acceptation :**

- les tableaux utilisent `caption`, en-têtes et relations de cellules correctes ;
- les lignes écartées sont compréhensibles sans texte barré seul ;
- le nombre initial, conservé et écarté est indiqué ;
- les valeurs nulles, longues et non ASCII sont testées ;
- les tableaux restent utilisables avec zoom à 200 %.

### EXG-FIC-007 — Métriques

**Priorité : P1**

Les métriques DOIVENT identifier leur nature.

**Acceptation :**

- la durée simulée est étiquetée comme telle ;
- la durée réelle provient de l'exécution active ;
- aucune comparaison de performance n'est produite sur une simulation.

### EXG-FIC-008 — Propriétés et schéma

**Priorité : P0**

Le tableau des propriétés DOIT être généré depuis le schéma du moteur.

**Acceptation :**

- nom, type, caractère requis, défaut, contraintes et description sont affichés ;
- chaque propriété possède une ancre stable ;
- les types complexes sont développables ;
- l'origine Pydantic/JSON Schema est indiquée ;
- la version de schéma est disponible.

### EXG-FIC-009 — Apprentissage par l'erreur

**Priorité : P1**

La fiche `filter` DOIT proposer au moins un exercice « casser puis réparer ».

**Acceptation :**

- l'utilisateur peut déclencher une colonne inexistante ;
- l'interface localise `expr` et la colonne ;
- une correction guidée est proposée sans remplacer automatiquement le travail ;
- le succès après correction est confirmé.

### EXG-FIC-010 — Compatibilité

**Priorité : P1**

Chaque fiche DOIT indiquer la version minimale, les changements connus, le statut
et les limitations par runtime ou connecteur.

### EXG-FIC-011 — Migration contextuelle

**Priorité : P2**

Le bloc « Coming from another tool? » DEVRAIT rester après le premier exemple
exécutable. Il PEUT être préselectionné depuis la provenance de l'utilisateur ou
un paramètre d'URL.

**Acceptation :**

- les équivalences Airflow/Dagster/Prefect ne promettent pas une identité
  sémantique lorsqu'elle n'existe pas ;
- le CTA ouvre un parcours avec le contexte `filter` conservé ;
- les deux codes sont disponibles dans le HTML.

### EXG-FIC-012 — Ouverture dans Playground

**Priorité : P1**

Le transfert vers le Playground DOIT conserver l'état courant.

**Acceptation :**

- DSL, jeu de données, version et exemple actif sont transférés ;
- l'URL ne contient aucun secret ;
- un lien trop volumineux emploie un mécanisme de partage explicitement consenti.

---

## 7. Exigences du Playground

### EXG-PLY-001 — Deux niveaux d'usage

**Priorité : P1**

Le Playground DEVRAIT proposer :

- un mode **Guidé**, où seul `transformations.yaml` est éditable ;
- un mode **Job complet**, où les fichiers autorisés deviennent éditables.

**Acceptation :**

- le mode est clairement indiqué et mémorisé ;
- le passage au mode complet explique les responsabilités supplémentaires ;
- les champs verrouillés restent sélectionnables et copiables.

### EXG-PLY-002 — Anatomie du job

**Priorité : P1**

Le Playground DOIT conserver les concepts :

```text
Sources → transformations → destinations
```

et les fichiers :

```text
sources.yaml
transformations.yaml
pipeline.yaml
destinations.yaml
```

### EXG-PLY-003 — Résumé visuel permanent

**Priorité : P1**

Un résumé du pipeline DOIT rester accessible près de l'action Run, particulièrement
lorsque les éditeurs sont empilés.

**Acceptation :**

- le résumé reflète les étapes réellement analysées ;
- une erreur de parsing est visible sur le résumé ;
- sur mobile, le résumé se replie sans disparaître définitivement.

### EXG-PLY-004 — Exemples

**Priorité : P1**

Les exemples DOIVENT être filtrés par source et décrire leur résultat attendu.

**Acceptation :**

- charger un exemple avertit si des modifications seront perdues ;
- chaque exemple est déterministe ;
- l'exemple choisi peut être partagé ;
- les exemples sont testés automatiquement.

### EXG-PLY-005 — Validation YAML

**Priorité : P0**

La validation DOIT distinguer syntaxe YAML, schéma Hydra et erreur sémantique.

**Acceptation :**

- le message précise la catégorie de l'erreur ;
- la position exacte est indiquée ;
- le bouton Run est bloqué pour une erreur empêchant l'exécution ;
- les avertissements non bloquants restent exécutables ;
- la correction automatique montre ce qui sera changé.

### EXG-PLY-006 — Autocomplétion

**Priorité : P2**

L'autocomplétion DOIT être alimentée par les métadonnées canoniques.

**Acceptation :**

- les suggestions sont navigables au clavier ;
- `Escape` ferme la liste ;
- le choix annonce nom, type et courte description ;
- aucune suggestion obsolète n'est codée en dur dans le composant.

### EXG-PLY-007 — Capacités destination × mode

**Priorité : P1**

Les modes non supportés DOIVENT être désactivés avec une justification.

**Acceptation :**

- CSV + upsert est annoncé comme non supporté, avec raison ;
- l'information ne repose pas sur un texte barré ou une faible opacité ;
- changer de destination choisit un mode valide sans modifier silencieusement un
  projet existant ;
- les capacités viennent du registre réel des connecteurs.

### EXG-PLY-008 — Exécution cohérente

**Priorité : P0**

Run DOIT mettre à jour de façon atomique le résultat, le résumé, le journal CLI
et la représentation API.

**Acceptation :**

- toutes les interfaces décrivent le même identifiant d'exécution ;
- une exécution annulée ou en erreur n'affiche pas « wrote N rows » ;
- les résultats obsolètes sont identifiables ;
- l'utilisateur peut relancer après correction.

### EXG-PLY-009 — CLI, API et Studio

**Priorité : P2**

Les trois onglets DOIVENT illustrer le même job sans prétendre exécuter des
interfaces qui sont encore simulées.

**Acceptation :**

- le pattern ARIA Tabs est complet, y compris les flèches clavier ;
- chaque panneau est associé à son onglet ;
- CLI et API indiquent « simulation » lorsqu'ils ne sont pas branchés ;
- Studio est présenté comme indisponible ou ouvre une route réelle.

### EXG-PLY-010 — Partage et export

**Priorité : P1**

Les actions Share et Export DOIVENT produire un résultat réel ou être
explicitement désactivées avant publication.

**Acceptation :**

- Export génère un dossier ou une archive Hydra valide ;
- Share affiche ce qui sera inclus ;
- les secrets et connexions personnelles sont exclus ;
- la restauration du partage reproduit le même job.

### EXG-PLY-011 — Mobile orienté tâche

**Priorité : P0**

À moins de 720 px, le Playground DOIT réduire la longueur cognitive de la page.

**Solution attendue :**

- stepper Sources → Transformations → Destination → Résultat, ou
- panneaux accordéon avec un seul panneau principal ouvert.

**Acceptation :**

- Run reste facilement accessible sans masquer le contenu ;
- l'utilisateur connaît l'étape active et les erreurs dans les autres étapes ;
- aucun contrôle n'est tronqué à 320 px ;
- le parcours principal est réalisable sans plus d'un défilement horizontal
  interne réservé aux données tabulaires.

### EXG-PLY-012 — Assistant conversationnel

**Priorité : P3**

L'assistant « Ask Hydra » ne DOIT pas être présenté comme alimenté par un modèle
réel tant qu'il est simulé. Sa livraison ne doit pas bloquer le Playground.

---

## 8. Exigences Migrate

### EXG-MIG-001 — Priorité Airflow

**Priorité : P1 pour la phase Migrate**

Airflow DOIT être le premier tunnel complet. Dagster et Prefect viennent ensuite.

### EXG-MIG-002 — Tunnel en cinq étapes

**Priorité : P1**

Chaque tunnel DOIT suivre :

1. reconnaître la friction ;
2. importer ou coller le code ;
3. produire un rapport de compatibilité ;
4. modifier et exécuter le résultat ;
5. décider et exporter.

### EXG-MIG-003 — Analyse statique sûre

**Priorité : P0**

Le code concurrent importé DOIT être analysé statiquement et ne DOIT jamais être
exécuté arbitrairement dans le navigateur ou sur le serveur.

**Acceptation :**

- les formats et limites acceptés sont indiqués avant import ;
- le système bloque archives dangereuses, chemins traversants et volumes excessifs ;
- aucun import Python n'est exécuté ;
- les fichiers sont supprimés selon une politique documentée.

### EXG-MIG-004 — Rapport de compatibilité explicite

**Priorité : P0**

Le rapport DOIT séparer :

- converti automatiquement ;
- conversion approximative ;
- non supporté ;
- travail manuel ;
- différence sémantique.

**Acceptation :**

- chaque élément source possède un statut et une explication ;
- le total du rapport correspond au détail ;
- l'utilisateur peut filtrer et exporter le rapport ;
- aucune note globale ne masque un blocage critique.

### EXG-MIG-005 — Comparaison avant/après

**Priorité : P1**

Le code source et le Hydra DSL généré DOIVENT être comparables côte à côte sur
desktop et séquentiellement sur mobile.

### EXG-MIG-006 — Promesses et preuves

**Priorité : P0**

Les affirmations concurrentielles, nombres d'utilisateurs, étoiles, coûts et
durées de migration DOIVENT être sourcés, datés et révisables.

**Acceptation :**

- chaque chiffre possède une source et une date ;
- les estimations internes sont étiquetées comme telles ;
- aucune promesse de conversion automatique à 100 % n'apparaît ;
- le contenu « où Hydra n'est pas adapté » est conservé.

### EXG-MIG-007 — Outils adjacents

**Priorité : P1**

La page DOIT distinguer remplacement, complément et orchestration externe.
Hydra ne doit pas être présenté comme remplaçant systématiquement dbt, Airbyte ou
Databricks.

### EXG-MIG-008 — Sortie utile

**Priorité : P1**

Le tunnel DOIT se terminer par au moins une sortie réelle : export Hydra,
ouverture dans Playground/Studio ou instructions CLI vérifiables.

---

## 9. Exigences responsive

### EXG-RWD-001 — Matrice de tailles

**Priorité : P0**

Les pages DOIVENT être testées au minimum aux tailles suivantes :

| Profil | Dimensions |
|---|---:|
| Petit mobile | 320 × 568 |
| Mobile | 360 × 800 |
| Mobile moderne | 390 × 844 |
| Grand mobile | 430 × 932 |
| Tablette portrait | 768 × 1024 |
| Tablette paysage | 1024 × 768 |
| Laptop | 1366 × 768 |
| Desktop | 1440 × 900 |
| Grand écran | 1920 × 1080 |

### EXG-RWD-002 — Pas de débordement global

**Priorité : P0**

La page ne DOIT produire aucun défilement horizontal global entre 320 et 1920 px.
Un défilement interne PEUT être utilisé pour les tableaux ou le code.

### EXG-RWD-003 — Zoom et redistribution

**Priorité : P0**

À 200 % de zoom sur une largeur CSS équivalente à 1280 px, le contenu DOIT rester
utilisable conformément à WCAG 2.2.

### EXG-RWD-004 — Cibles tactiles

**Priorité : P1**

Les actions principales DOIVENT offrir une cible d'au moins 44 × 44 px ou un
espacement équivalent évitant les activations accidentelles.

### EXG-RWD-005 — Contenu prioritaire

**Priorité : P1**

Le responsive DOIT réordonner selon la tâche et non seulement empiler les colonnes.
Run, état de validation et résultat doivent rester plus prioritaires que les
fonctionnalités secondaires.

---

## 10. Exigences d'accessibilité

La cible minimale est **WCAG 2.2 niveau AA**.

### EXG-A11Y-001 — Clavier complet

**Priorité : P0**

Toutes les fonctions DOIVENT être réalisables au clavier, sans double-clic ni
survol obligatoire.

### EXG-A11Y-002 — Focus

**Priorité : P0**

Le focus DOIT être visible dans les thèmes clair et sombre. Les ouvertures,
fermetures et changements de vue DOIVENT gérer le focus de façon prévisible.

### EXG-A11Y-003 — Dialogues et menus

**Priorité : P0**

Les dialogues DOIVENT piéger le focus, se fermer avec `Escape`, annoncer leur
titre et restituer le focus. Les menus DOIVENT implémenter la navigation clavier
appropriée ou employer des contrôles natifs plus simples.

### EXG-A11Y-004 — Onglets

**Priorité : P1**

Les onglets CLI/API/Studio DOIVENT suivre le pattern WAI-ARIA Tabs : rôles,
relations, sélection, `tabindex` et flèches clavier.

### EXG-A11Y-005 — Formulaires

**Priorité : P0**

Chaque champ DOIT avoir un libellé persistant. Un placeholder ne remplace pas un
libellé. Les erreurs DOIVENT être associées au champ concerné.

### EXG-A11Y-006 — Contrastes

**Priorité : P0**

Les textes et composants DOIVENT respecter les contrastes AA dans les deux thèmes.
Les textes atténués, badges pastel, bordures et états désactivés doivent être
mesurés, pas seulement contrôlés visuellement.

### EXG-A11Y-007 — Mouvement

**Priorité : P1**

Les animations DOIVENT respecter `prefers-reduced-motion`. Aucune information ne
doit dépendre d'une animation du flux.

### EXG-A11Y-008 — Tableaux et code

**Priorité : P1**

Les tableaux DOIVENT avoir légende et en-têtes structurés. Le code DOIT pouvoir
être lu et copié sans dépendre de la coloration syntaxique.

### EXG-A11Y-009 — Lecteur d'écran

**Priorité : P1**

Les parcours Guide, exécution de `filter`, erreur/correction et export DOIVENT
être testés avec au moins NVDA + Chrome ou Firefox sous Windows.

---

## 11. Exigences SEO et éditoriales

### EXG-SEO-001 — Métadonnées

**Priorité : P1**

Chaque page DOIT posséder titre unique, description, URL canonique, langue,
Open Graph minimal et métadonnées sociales appropriées.

### EXG-SEO-002 — Structure HTML

**Priorité : P0**

La hiérarchie H1/H2/H3, les régions `header`, `nav`, `main`, `aside` et `footer`,
les listes, tableaux et blocs de code DOIVENT être sémantiques.

### EXG-SEO-003 — Données structurées

**Priorité : P1**

Les fiches DEVRAIENT employer `TechArticle` et `BreadcrumbList`. `HowTo` ou `FAQ`
ne doivent être utilisés que lorsque le contenu visible satisfait réellement
leur définition.

### EXG-SEO-004 — Liens internes

**Priorité : P1**

Chaque fiche DOIT lier sa catégorie, ses éléments liés, alternatives et
équivalences de migration. Aucun élément important ne doit être orphelin.

### EXG-SEO-005 — Sitemap et indexation

**Priorité : P1**

Le build DOIT produire sitemap, URL canoniques et règles d'indexation adaptées au
base path GitHub Pages.

### EXG-SEO-006 — Discussions

**Priorité : P2**

Le contenu chargé par giscus ne DOIT pas constituer le contenu documentaire
principal. La page doit rester complète sans discussions.

### EXG-EDT-001 — Contenu versionné

**Priorité : P1**

Chaque contenu éditorial DOIT avoir propriétaire, date de révision et statut.
Les comparaisons concurrentielles DOIVENT avoir une fréquence de révision définie.

---

## 12. Exigences techniques et architecture

### EXG-ARC-001 — Astro statique

**Priorité : P0**

Astro est l'hypothèse prioritaire. La tranche `filter` DOIT confirmer :

1. poids de chargement ;
2. temps avant première interaction ;
3. fidélité de simulation ;
4. SEO rendu ;
5. facilité de génération.

### EXG-ARC-002 — Limite des îlots

**Priorité : P0**

Une zone dont l'éditeur, le formulaire, le diagramme et le résultat partagent le
même état DOIT être un seul îlot applicatif ou utiliser un store client explicite.
Elle ne doit pas être découpée en îlots indépendants communiquant indirectement
par le DOM.

### EXG-ARC-003 — Hydratation différée

**Priorité : P1**

Les composants lourds DOIVENT être chargés seulement lorsqu'ils sont nécessaires,
tout en conservant un aperçu statique exploitable.

### EXG-ARC-004 — Exécution hybride

**Priorité : P0**

- TypeScript : simulations simples et pédagogiques ;
- DuckDB-WASM : cas tabulaires tels que join, aggregate et SQL ;
- moteur Hydra distant : orchestration et connecteurs réels ;
- agent local ou Studio : accès aux données de l'utilisateur.

Le DSL Hydra complet ne DOIT pas être réimplémenté en JavaScript.

### EXG-ARC-005 — Modèle d'état

**Priorité : P1**

L'état interactif DOIT distinguer :

- document édité ;
- document validé ;
- document exécuté ;
- résultat courant ;
- résultat obsolète ;
- exemple d'origine ;
- niveau d'exécution ;
- version du schéma.

### EXG-ARC-006 — Persistance

**Priorité : P1**

Le thème PEUT être conservé localement. Un brouillon de travail ne DOIT être
persisté qu'avec une politique explicite et sans secret.

### EXG-ARC-007 — Erreurs de chargement

**Priorité : P1**

Une erreur de chargement d'un îlot, de DuckDB-WASM ou du backend DOIT laisser la
documentation statique utilisable et proposer une récupération.

---

## 13. Exigences de sécurité et confidentialité

### EXG-SEC-001 — Playground hostile par défaut

**Priorité : P0**

Le Playground public DOIT interdire ou isoler strictement Python arbitraire,
Bash, PowerShell, SSH, commandes système, réseau libre, fichiers serveur et
secrets persistants.

### EXG-SEC-002 — Backend éphémère

**Priorité : P0 pour les niveaux 2/3**

Toute exécution distante DOIT avoir limites CPU, mémoire, durée, taille, réseau,
quotas, journalisation et nettoyage systématique.

### EXG-SEC-003 — Secrets

**Priorité : P0**

Aucun secret de production ne DOIT être envoyé au Guide ou stocké dans une URL,
le localStorage, un partage ou un export non protégé.

### EXG-SEC-004 — Import et export

**Priorité : P0**

Les imports DOIVENT valider taille, type, encodage, chemins et structure. Les
exports DOIVENT exclure les secrets et éviter les noms de fichiers dangereux.

### EXG-SEC-005 — HTML dynamique

**Priorité : P0**

Tout contenu utilisateur rendu dans la page DOIT être échappé ou assaini. Les
commentaires, résultats, erreurs moteur et extraits importés sont concernés.

### EXG-SEC-006 — Politique de données

**Priorité : P1**

L'interface DOIT expliquer quelles données restent locales, lesquelles sont
envoyées au backend et leur durée de conservation.

---

## 14. Exigences de performance

Les budgets définitifs doivent être confirmés par la tranche `filter`.

### EXG-PERF-001 — Budgets initiaux

**Priorité : P1**

Sur une connexion mobile moyenne et un appareil de gamme intermédiaire :

- contenu principal statique visible sans attendre l'îlot ;
- LCP cible ≤ 2,5 s au 75e percentile ;
- INP cible ≤ 200 ms au 75e percentile ;
- CLS cible ≤ 0,1 au 75e percentile.

### EXG-PERF-002 — JavaScript

**Priorité : P1**

Le catalogue statique et les fiches non interactives ne DOIVENT pas charger les
dépendances de l'éditeur, de React Flow ou de DuckDB-WASM.

### EXG-PERF-003 — Exécution

**Priorité : P1**

Une simulation simple sur le jeu canonique DEVRAIT répondre en moins de 100 ms
après initialisation. Les temps d'initialisation lourds doivent être indiqués.

### EXG-PERF-004 — Longues listes et tableaux

**Priorité : P2**

Le rendu DOIT rester fluide pour les volumes pédagogiques prévus. La virtualisation
ne doit être ajoutée que lorsqu'une mesure en démontre le besoin.

---

## 15. Tests obligatoires

### EXG-TST-001 — Tests unitaires

**Priorité : P0**

DOIVENT couvrir :

- parsing et validation de `filter` ;
- synchronisation YAML/état ;
- filtrage catalogue ;
- capacités destination × mode ;
- sérialisation et restauration d'un exemple ;
- rapports de migration.

### EXG-TST-002 — Tests de composants

**Priorité : P1**

DOIVENT couvrir clavier, focus, erreurs, états asynchrones et thèmes pour les
composants critiques.

### EXG-TST-003 — Tests end-to-end

**Priorité : P0**

Parcours minimaux :

1. rechercher `filter` dans le Guide et ouvrir la fiche ;
2. modifier l'expression, exécuter et vérifier le résultat ;
3. provoquer une colonne inconnue puis corriger ;
4. ouvrir l'état courant dans le Playground ;
5. charger un exemple, changer la destination et exporter ;
6. ouvrir le tunnel Airflow et obtenir un rapport de compatibilité.

### EXG-TST-004 — Régression visuelle

**Priorité : P1**

Des captures de référence DOIVENT être comparées aux neuf profils responsive.
Les thèmes clair et sombre doivent être couverts sur les vues majeures.

### EXG-TST-005 — Accessibilité automatisée et manuelle

**Priorité : P0**

- axe ou équivalent sur chaque page majeure ;
- navigation clavier manuelle ;
- NVDA sur les parcours principaux ;
- contraste mesuré ;
- zoom 200 % et redistribution.

L'absence d'erreur automatisée ne remplace pas les tests manuels.

### EXG-TST-006 — SEO

**Priorité : P1**

Le build DOIT être inspecté pour vérifier HTML initial, titres, canonicals, sitemap,
données structurées, liens cassés et code YAML présent.

### EXG-TST-007 — Schémas et exemples

**Priorité : P0**

La CI DOIT régénérer les propriétés depuis Pydantic et valider tous les exemples.
Une divergence ou un exemple invalide bloque la fusion.

### EXG-TST-008 — Performance

**Priorité : P1**

Lighthouse ou un outil équivalent DOIT être exécuté sur Guide, fiche `filter` et
Playground. Les régressions de budget doivent être visibles dans la CI.

---

## 16. Observabilité et mesure produit

### EXG-OBS-001 — Événements utiles

**Priorité : P2**

La mesure DEVRAIT couvrir, sans enregistrer le contenu utilisateur :

- première exécution réussie ;
- erreur puis correction ;
- ouverture dans Playground ;
- chargement d'un exemple ;
- export ;
- ouverture Studio/installation ;
- démarrage et achèvement d'une migration.

### EXG-OBS-002 — Indicateur principal

**Priorité : P2**

L'indicateur principal doit mesurer une interaction réussie conduisant à une
compréhension ou à un projet exportable, pas seulement une page vue.

### EXG-OBS-003 — Confidentialité

**Priorité : P0**

La télémétrie ne DOIT collecter ni YAML utilisateur, ni données importées, ni
secrets, ni commentaires sans consentement explicite.

---

## 17. Séquencement recommandé

### Lot 0 — Corrections de conception bloquantes

1. Valider la langue de première livraison.
2. Unifier l'en-tête et la navigation mobile.
3. Valider le modèle canonique de métadonnées.
4. Définir la frontière simulation/moteur réel.
5. Définir le modèle d'état partagé de l'îlot `filter`.

### Lot 1 — Tranche verticale `filter`

1. Générer le contenu statique depuis Astro et les métadonnées.
2. Implémenter l'îlot éditeur/diagramme/données/résultat.
3. Ajouter validation, état obsolète et « casser puis réparer ».
4. Transférer l'état vers le Playground.
5. Auditer SEO, accessibilité, responsive et performances.
6. Confirmer ou invalider Astro selon les cinq critères établis.

### Lot 2 — Guide statique complet

1. Générer toutes les fiches.
2. Rendre le catalogue statiquement.
3. Activer Groupes, A–Z, Intention et filtres.
4. Produire sitemap, liens internes et données structurées.
5. Déployer sur GitHub Pages.

### Lot 3 — Playground

1. Introduire les modes Guidé/Job complet.
2. Réorganiser le mobile en étapes ou accordéons.
3. Brancher capacités, exemples et export sur les sources canoniques.
4. Finaliser CLI/API/Studio sans fausses fonctions.

### Lot 4 — Migration

1. Sourcer et dater les affirmations de la landing Migrate.
2. Construire le tunnel Airflow complet.
3. Ajouter le rapport de compatibilité et l'export.
4. Étendre à Dagster puis Prefect.

---

## 18. Définition de terminé

Une fonctionnalité n'est terminée que si :

- ses exigences P0 et P1 applicables sont satisfaites ;
- le contenu essentiel fonctionne sans JavaScript lorsque prévu ;
- les tests unitaires, composants et end-to-end passent ;
- les exemples sont conformes au schéma Hydra ;
- le parcours clavier est utilisable ;
- aucune violation axe critique ou sérieuse non justifiée ne subsiste ;
- le responsive est validé sur la matrice définie ;
- les budgets de performance ne régressent pas ;
- les textes sont cohérents dans la locale active ;
- les états vide, chargement, erreur, succès et obsolète sont couverts ;
- la sécurité et la confidentialité ont été revues ;
- la documentation d'exploitation et les limitations sont à jour.

---

## 19. Critères de décision pour la première publication utile

La première publication peut être autorisée lorsque :

1. le Guide statique complet est navigable et indexable ;
2. les propriétés sont générées depuis les modèles Pydantic ;
3. les exemples sont validés automatiquement ;
4. la fiche `filter` est pleinement interactive ;
5. le transfert `filter` → Playground fonctionne ;
6. la navigation mobile est complète sur toutes les pages publiées ;
7. les exigences essentielles WCAG 2.2 AA sont satisfaites ;
8. aucune exécution arbitraire ou exposition de secret n'est possible ;
9. les simulations sont identifiées sans ambiguïté ;
10. la CI construit, teste et déploie le site sans intervention manuelle.

Ne bloquent pas cette première publication :

- l'interactivité complète de toutes les fiches ;
- le backend Hydra distant ;
- les connecteurs réels ;
- les tunnels Dagster/Prefect ;
- l'assistant conversationnel ;
- le simulateur complet de Hydra Studio.

---

## 20. Risques principaux

| Risque | Impact | Réponse exigée |
|---|---|---|
| Découpage excessif en îlots | État incohérent, bugs de synchronisation | Un îlot fonctionnel partagé pour le board |
| Catalogue généré uniquement en JS | SEO et fonctionnement sans JS insuffisants | Rendu Astro statique |
| Playground trop dense sur mobile | Abandon du parcours | Stepper ou accordéons orientés tâche |
| Réimplémentation du moteur en TypeScript | Divergence fonctionnelle | Limiter TS aux simulations simples |
| Propriétés écrites à la main | Documentation obsolète | Génération Pydantic obligatoire |
| Promesses migration non prouvées | Perte de confiance et risque éditorial | Sources, dates et limites explicites |
| Navigation mobile masquée | Sections inaccessibles | En-tête partagé avec menu accessible |
| Fonctions simulées présentées comme réelles | Mauvaise compréhension produit | Étiquetage et états indisponibles |
| Interactivité retardant le Guide | Publication trop tardive | Guide statique découplé et incrémental |
| Import de code concurrent | Risque d'exécution arbitraire | Analyse statique stricte et sandbox |

---

## 21. Conclusion

Les prototypes valident la direction produit et visuelle. Les améliorations
prioritaires ne consistent pas à redessiner l'ensemble, mais à :

1. rendre la navigation et les composants communs réellement cohérents ;
2. garantir un HTML statique complet avant hydratation ;
3. construire `filter` autour d'un état interactif unique et testable ;
4. rendre le Playground mobile orienté tâche ;
5. traiter accessibilité, sécurité et fidélité des simulations comme des critères
   de livraison ;
6. conserver une migration honnête, mesurable et techniquement sûre.

Ce rapport peut servir de base au backlog, aux critères d'acceptation des tickets
et à la revue de la tranche verticale `filter`.
