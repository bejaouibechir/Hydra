# Brief — Les 6 SVG de la landing page hydraetl.com

Document interne (français). Les libellés **dans** les images sont en **anglais** (charte, règle 8).

Les schémas ne sont pas décoratifs : le budget de 250 mots de prose signifie qu'ils **portent
l'explication**. Un schéma qui n'apprend rien est à supprimer, pas à embellir.

---

## Partie A — Prompt à coller dans ChatGPT

````text
RÔLE
Tu produis des schémas techniques en SVG pour la page d'accueil d'un outil ETL open source.
Tu écris du SVG à la main, propre et lisible. Tu ne produis ni PNG, ni image matricielle.

CONTRAINTES TECHNIQUES — elles s'appliquent aux 6 fichiers, sans exception
1. Un fichier = un <svg> autonome avec viewBox, sans width ni height fixes, et
   preserveAspectRatio="xMidYMid meet". Il sera inséré en ligne dans du HTML.
2. Aucune ressource externe : pas de <image>, pas de <script>, pas de @import, pas de webfont,
   pas de lien vers un CDN. Le fichier doit s'afficher hors ligne.
3. Texte en vrais éléments <text>. Jamais de texte vectorisé en <path>.
4. Police : font-family="system-ui, -apple-system, Segoe UI, Roboto, sans-serif".
   Taille minimale 13 (dans un viewBox de 960 de large). Titres 17, libellés 14, notes 12.
5. Fond transparent. Ne peins jamais un rectangle blanc en fond : la page a un thème sombre.
6. Couleurs — utilise EXCLUSIVEMENT ces variables CSS avec repli, jamais une couleur en dur :
   texte principal   fill="var(--text, #0e1a17)"
   texte secondaire  fill="var(--text-soft, #5a6a66)"
   bordures          stroke="var(--border-strong, #cdd8d5)"
   accent Hydra      stroke/fill="var(--accent, #0f766e)"
   fond d'accent     fill="var(--accent-soft, #d7efeb)"
   succès            var(--ok, #15803d)   attention var(--warn, #b45309)   erreur var(--err, #b91c1c)
   Le thème sombre est géré par la page : ne produis pas de seconde version.
7. Aucune information ne doit reposer sur la seule couleur : double toujours par un libellé,
   une icône ou un style de trait.
8. Tous les id et les identifiants de <marker> sont préfixés par le nom du fichier
   (ex. id="svg01-arrow") : plusieurs SVG cohabiteront dans le même DOM.
9. Accessibilité : <svg role="img" aria-labelledby="svgNN-title svgNN-desc"> avec un <title> et
   un <desc> en première position. Le <desc> décrit le mécanisme, pas l'apparence.
10. Sobriété : pas de dégradé, pas de filtre, pas d'ombre portée, pas de flou. Coins rx="8".
    Traits stroke-width="1.5". Flèches par <marker> partagé.
11. Poids : 12 ko maximum par fichier, indenté, lisible.
12. Rends chaque fichier dans son propre bloc de code, précédé de son nom.

STYLE GRAPHIQUE COMMUN
- Grille implicite de 8 px. Tout s'aligne.
- Un élément Hydra est en accent ; tout ce qui est extérieur à Hydra est en gris de bordure.
- Les boîtes portent un libellé en gras et, si utile, une ligne secondaire en texte secondaire.
- Le sens de lecture est toujours gauche → droite, ou haut → bas. Jamais les deux.
- Aucun libellé ne dépasse de sa boîte : compte environ 7,5 px de large par caractère à 14 px.

────────────────────────────────────────────────────────────────────────

svg-01-job.svg — "A job, end to end"   viewBox="0 0 960 300"
Trois zones alignées horizontalement.
- Gauche (x 0–230) : une carte "job.yaml" figurant 6 lignes de YAML stylisées (des rectangles
  gris de longueurs inégales suffisent, avec 3 libellés lisibles : source:, transform:, destination:).
- Centre (x 270–690) : trois boîtes de 130 de large, reliées par des flèches :
  "Extract" (sous-titre "orders.csv"), "Transform" (sous-titre "filter · cast · select"),
  "Load" (sous-titre "orders_clean.csv").
- Droite (x 730–960) : une carte "Result" montrant 4 lignes d'un tableau et la note
  "1,000,000 rows · 4.6 s".
- Une accolade fine sous les trois boîtes centrales, libellée "Hydra engine".
Message : un fichier YAML entre, des données sortent.

svg-02-connectors.svg — "Connectors"   viewBox="0 0 960 260"
- Colonne de gauche : six pastilles empilées, libellées exactement
  "CSV", "JSON", "Parquet", "PostgreSQL", "MySQL / MariaDB", "Web API".
- Une septième pastille en trait pointillé, libellée "MongoDB (plugin)".
- Toutes convergent par des traits fins vers une boîte centrale "Connector registry",
  elle-même reliée à une boîte "Engine" à droite.
- Sous le registre, une note : "Same interface for sources and destinations."
- À droite de "Engine", une flèche sortante vers une pastille "Your connector" en pointillé.
Message : la liste est ouverte, le point d'entrée est unique.

svg-03-dual.svg — "One operation, two engines"   viewBox="0 0 960 360"
Partie haute (y 0–170) — le mécanisme :
- À gauche une boîte "Operation" (sous-titre "csv.read").
- Un losange "Backend switch" au centre.
- Deux boîtes à droite : "Rust" (en accent) et "Python" (en gris).
- Une flèche pointillée de "Rust" vers "Python", libellée "automatic fallback".
- Note sous le losange : "Per operation. Identical output, byte for byte."
Partie basse (y 190–360) — les mesures, en barres horizontales :
- Quatre lignes. Chaque ligne : un libellé à gauche (largeur 210), puis deux barres superposées —
  la barre "Python" en gris, la barre "Rust" en accent — et la valeur écrite au bout de chaque barre.
- Échelle commune démarrant à zéro, barres proportionnelles aux valeurs. Pas d'axe, pas de grille.
  CSV read, 1M rows        3.55 s → 0.89 s
  CSV write, 700k rows     1.26 s → 0.55 s
  cast, 5 columns          1.61 s → 0.62 s
  Full job                 7.2 s  → 4.4 s
- Une légende de deux pastilles : "Python" (gris), "Rust" (accent).
Message : le gain est mesuré, et le repli est automatique.

svg-04-extensions.svg — "Twelve extension points"   viewBox="0 0 960 300"
- Un hub central "Registry" (boîte en accent, sous-titre "one mechanism").
- Douze pastilles réparties symétriquement autour, six à gauche six à droite, reliées au hub :
  "Connectors", "Engines", "Operations", "Auth providers", "Cache backends", "Compilers",
  "Error handlers", "Hooks", "Metrics sinks", "Pagination strategies", "Retry policies",
  "Web API policies".
- Note en bas : "Register a class. No fork, no patch."
Message : ce n'est pas douze mécanismes, c'est douze prises sur le même.

svg-05-studio.svg — "Build it visually, ship YAML"   viewBox="0 0 960 400"
Diptyque, séparé par une flèche centrale libellée "on export".
- Panneau gauche "Hydra Studio" : un canvas avec un conteneur en trait pointillé, titré
  "Retry Scope" et portant la note "3× / 5 s". À l'intérieur, trois nœuds empilés :
  "Load orders", "Load customers", "Load invoices". À l'extérieur du conteneur, un nœud
  "Read CSV" en amont et un nœud "Write Parquet" en aval, reliés par des flèches.
- Panneau droit "workflow.yaml" : trois blocs YAML lisibles, un par job, chacun portant
  la ligne "retry: { max: 3, delay: 5 }" mise en évidence en accent.
- Sous la flèche, la note : "The container is a canvas concept. Its policy is copied onto
  each job it holds."
Message essentiel : le conteneur n'existe pas dans le YAML, sa politique y est recopiée.

svg-06-positioning.svg — "Where Hydra sits"   viewBox="0 0 960 420"
Un plan à deux axes, cadre gris, graduations discrètes.
- Axe horizontal, de gauche à droite : "Code-first" → "Declarative".
- Axe vertical, de bas en haut : "Single machine" → "Distributed".
- Sept points, chacun une pastille avec son nom, positionnés ainsi :
  Hydra        déclaratif, mono-machine       → en bas à droite, EN ACCENT, pastille plus grande
  dbt          déclaratif, entrepôt           → en haut à droite
  Airbyte      déclaratif, serveur            → milieu droit
  Airflow      code, serveur                  → milieu gauche
  Dagster      code, serveur                  → milieu gauche, légèrement plus déclaratif
  Prefect      code, serveur                  → milieu gauche, plus bas
  Databricks   code, distribué                → en haut à gauche
- Sous le plan, une seule ligne en texte secondaire :
  "Hydra targets pipelines that run on one machine. Beyond that, Spark is the right tool."
Message : Hydra occupe un coin précis, et le dit.

AVANT DE RÉPONDRE, VÉRIFIE POUR CHAQUE FICHIER
- Le SVG est bien formé, toutes les balises sont fermées.
- Aucune couleur en dur hors des replis de var().
- Aucun texte ne déborde de sa boîte.
- <title> et <desc> présents, id préfixés, role="img".
- Poids sous 12 ko.
- Les valeurs chiffrées sont recopiées telles quelles depuis ce brief.
````

---

## Partie B — Vérification à faire de notre côté

- [ ] Ouverture de chaque SVG seul dans un navigateur : rien ne déborde
- [ ] Insertion en ligne dans la page, thème clair **et** thème sombre
- [ ] Lisible à 390 px de large (le viewBox se réduit, le texte doit rester au-dessus de 11 px réels)
- [ ] Lecteur d'écran : le `<desc>` suffit à comprendre le schéma
- [ ] Zoom 200 % sans perte
- [ ] Poids total des 6 fichiers sous 60 ko
- [ ] Les chiffres correspondent à `claude/modules_rust.md`

## Partie C — Correspondance blocs / schémas

| Bloc de la landing | Schéma |
|---|---|
| 2. Un job de bout en bout | `svg-01-job.svg` |
| 4. Connecteurs | `svg-02-connectors.svg` |
| 5. Performance | `svg-03-dual.svg` |
| 6. Extensibilité | `svg-04-extensions.svg` |
| 7. Hydra Studio | `svg-05-studio.svg` |
| 8. Positionnement | `svg-06-positioning.svg` |

Les 4 schémas restants (architecture en couches, anatomie d'un projet, DAG, conteneurs → YAML)
sont destinés aux pages internes et seront spécifiés séparément.
