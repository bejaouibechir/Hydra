# Brief de rédaction — pages du Hydra DSL

À remettre à qui rédige le contenu, humain ou modèle. Tient en une lecture.
Trois pages déjà écrites servent de référence : `/dsl/sources`, `/dsl/sources-yaml`,
`/dsl/transformations-yaml`.

---

## 1. Ce qu'est une page, ce qu'elle n'est pas

Une page **documente**. Elle n'est ni un validateur, ni un linter, ni un simulateur d'erreurs.

- Tout manifeste affiché **s'exécute**. Aucun exemple fautif, aucune ligne soulignée en rouge,
  aucun statut d'échec mis en scène.
- Ce qui peut échouer se dit **en prose** — « l'ordre compte », « ce fichier est requis ».
  On l'explique, on ne le joue pas.
- Un sélecteur propose des **variantes correctes** : deux formes acceptées, un fichier omis,
  un exemple plus riche. Jamais un cas cassé à observer.

Seule exception, imposée par la règle 7 de la charte : un secret en clair saisi par
l'utilisateur est refusé en erreur bloquante. C'est une protection, pas une démonstration.

---

## 2. La structure d'une page d'élément

Toujours dans cet ordre. Une page qui invente sa structure est à refaire.

1. **Le poste de travail** — le manifeste à gauche, une visite guidée, un panneau de notes à droite.
2. **`What <élément> is`** — la définition. Ce que la chose est, ce qu'elle n'est pas, où elle se
   place par rapport à ses voisines. Deux paragraphes.
3. **`What it contains`** — les composants, **groupés par rôle**, jamais recopiés du modèle.
   Un tableau de clés n'explique rien ; il se consulte dans la référence.
4. **L'idée à retenir** — un titre qui énonce la thèse, un paragraphe qui la tient.
   Exemple : « Declared is not opened », « Order is the whole idea ».
5. **Un schéma SVG** — voir §5.
6. **La démarche** — le YAML minimal **complet**, puis la commande exacte, puis la sortie réelle.
   Voir §4. C'est le point sur lequel les premières versions ont échoué.
7. **`Close by`** — quatre à cinq liens vers les pages voisines.

**Budget** : 500 mots de prose maximum, hors code, hors tableaux, hors schéma.

---

## 3. La structure d'une leçon de tutoriel

Calquée sur Flowman, identique d'une leçon à l'autre. Référence : `/dsl/tutorial/01-first-job`.

```
1. What to Expect
   ├── Objectives        3 puces, ce que le lecteur saura faire
   ├── Description       le contexte, un paragraphe
   └── Processing Steps  la liste numérotée de ce qui va se passer
2. Implementation        un fichier après l'autre, YAML puis explication
3. Execution             la commande exacte, puis la sortie réelle
4. Next Lesson           ce qui vient après
```

Les leçons sont **cumulatives** : chacune reprend le projet de la précédente et ne repart jamais
de zéro. Un seul jeu de données pour toute la série — `customers` / `products` / `orders`, dans
`data/canonical/`.

**Budget** : 900 mots de prose maximum.

---

## 4. La règle qui fait la différence : montrer la démarche

Quand une page affirme qu'une chose est possible, elle donne de quoi l'éprouver **sans réfléchir** :

1. **Le YAML minimal complet.** Pas un extrait, pas un fragment à compléter. Le lecteur copie, ça marche.
2. **La commande exacte**, telle qu'on la tape, sur le projet du dépôt qui existe :
   `hdrctl run examples/tutorial/01-first-job`
3. **La sortie réelle**, recopiée depuis le terminal.
4. **La syntaxe de la commande**, avec les options qui servent ici, tirées de `--help`.

Écrire « les deux formes sont acceptées » sans montrer les deux formes complètes et la commande
qui les compare, c'est laisser le débutant sur le bord de la route. C'est le retour le plus
important que ce brief transmet.

---

## 5. Le schéma

Un schéma par page, en **SVG inline**, jamais une image.

- Il dit la thèse de la page d'un coup d'œil. Il ne redit pas le texte, il le remplace en partie.
- **Aucune couleur en dur** : uniquement les variables du thème — `var(--accent)`, `var(--border)`,
  `var(--text)`, `var(--muted)`. Sinon le mode sombre casse.
- Accessibilité obligatoire : `role="img"`, un `<title>`, un `<desc>`, liés par `aria-labelledby`.
- Classes disponibles, déjà stylées : `d-panel`, `d-box`, `d-box lit`, `d-key`, `d-txt`, `d-sub`,
  `d-cap`, `d-arrow`, `d-arrow lit`, `d-foot`.
- Poids visé : 2 à 3 ko.

---

## 6. Ce qui ne se délègue pas

**Un modèle ne peut pas vérifier.** Il ne fait pas tourner le moteur, ne lit pas le terminal, et
produira des chiffres plausibles et faux si on le laisse faire. Donc :

- **Aucun chiffre inventé.** Nombre de lignes lues, écrites, durée, message d'erreur : ces valeurs
  viennent d'une exécution réelle et de nulle part ailleurs.
- **Aucune clé inventée.** Les clés d'un bloc viennent de `src/data/dsl-specs.json`, généré depuis
  les modèles Pydantic par `scripts/gen_specs.py`.
- **Aucune commande inventée.** Les options viennent de `hdrctl <commande> --help`.

**Protocole** : le rédacteur écrit le contenu en laissant un marqueur explicite — `[[À VÉRIFIER : …]]` —
partout où un chiffre, une sortie ou un comportement est affirmé. Ces marqueurs sont ensuite levés
un par un en exécutant. Un marqueur restant bloque la publication.

Ce qui se délègue bien, en revanche : la définition, le groupement par rôle, la formulation de la
thèse, les liens voisins, la composition du schéma, la relecture.

---

## 7. Les fichiers à produire

Pour une page d'élément nommée `X` :

```
src/_mock/dsl-X.head.html    le poste de travail
src/_mock/dsl-X.js           la visite guidée et les exemples
src/_mock/dsl-X.tail.html    définition, schéma, démarche, liens
src/pages/dsl/X.astro        15 lignes, sur le modèle des pages existantes
```

Puis deux enregistrements : la route dans `src/data/dsl-menu.json`, et la page dans
`scripts/check_charte.cjs`.

Conventions à respecter, sinon les contrôles échouent :
`class="yaml"` pour un manifeste · `class="cmd"` pour une commande ou une sortie ·
`class="linklist"` pour les liens voisins · une seule balise `h1` par page ·
tout lien doit pointer vers une route qui existe.

---

## 8. Avant de livrer

```
node scripts/check_charte.cjs      structure, budgets, exemples corrects, liens
node scripts/test_dsl.cjs src/_mock   les interactions de la page
node scripts/check_astro.mjs <page>   la compilation
```

Les trois doivent passer. Un livrable présenté au motif qu'il « devrait marcher » est refusé —
c'est la règle 10 de la charte, et elle n'a pas d'exception.
