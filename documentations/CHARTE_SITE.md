# Charte du site hydraetl.com

Règles à respecter pour toute page, tout composant, toute contribution — humaine ou IA.
Chaque règle est vérifiable. En cas de doute, la règle l'emporte sur l'élégance.

---

## 1. Montrer avant d'argumenter

- Une page qui veut convaincre commence par **une chose manipulable**, pas par un paragraphe.
- Si l'utilisateur ne peut rien bouger dans les 5 premières secondes, la page est à refaire.
- Un schéma qui réagit à un contrôle vaut mieux qu'un schéma fixe, qui vaut mieux qu'un paragraphe.

**Vérification** : ouvrir la page, chronométrer le premier geste possible.

**Ne s'applique pas aux pages de tutoriel** — voir l'exception ci-dessous.

## 2. Budget de mots

- **Maximum 250 mots de prose** par page hors code, hors YAML, hors légendes de schéma.
- Un verdict tient en **un chiffre et six mots**. Pas de sous-paragraphe explicatif.
- Les citations et sources sont des liens discrets, jamais des blocs.

**Vérification** : script qui dépouille `<style>`, `<script>`, `<svg>` et compte les mots restants.

**Ne s'applique pas aux pages de tutoriel** — voir l'exception ci-dessous.

## 2 bis. Exception — les pages de tutoriel

Les règles 1 et 2 sont écrites pour une page qu'on **consulte** : une fiche de référence, un
comparatif, un verdict. Elles sont fausses pour une page qu'on **suit** : un tutoriel raconte
la construction d'un projet, fichier par fichier, et cette narration ne tient pas en 250 mots.

Sont des pages de tutoriel, et elles seules, les pages sous `/dsl/tutorial/`.

**Ce qui est levé pour ces pages**

- Le plafond de 250 mots. Un tutoriel vise **900 mots au maximum**, prose seule.
- L'obligation d'un geste manipulable dans les 5 premières secondes.

**Ce qui les remplace, et qui est tout aussi contraignant**

1. **Structure fixe, identique d'une leçon à l'autre.** Objectifs, description, étapes, puis
   l'implémentation fichier par fichier, puis la commande d'exécution, puis la leçon suivante.
   Une leçon qui invente sa propre structure est à refaire.
2. **Progression cumulative.** Une leçon reprend le projet de la précédente et ne repart jamais
   de zéro. Un seul jeu de données pour toute la série.
3. **Le code montré doit tourner.** Chaque bloc YAML est extrait d'un projet réel du dépôt,
   exécuté par le moteur en intégration. Un extrait inventé pour l'exemple est un bug.
4. **Le résultat est montré, pas décrit.** Après chaque étape, la sortie réelle du moteur —
   pas une phrase qui prétend ce qu'elle serait.
5. **Une commande exacte, copiable**, à la fin de chaque leçon.

**Ce qui reste dû sans changement** : les règles 3 à 10. Jamais de silence, sortie statique,
aucun appel réseau au chargement, accessibilité, aucun secret en clair, tous les liens résolvent,
vérification programmatique avant livraison.

**Vérification** : le script de charte distingue les deux régimes par le chemin de la page, et
contrôle sur un tutoriel les cinq points ci-dessus au lieu des règles 1 et 2.

*Dérogation accordée par Bechir. Elle vaut pour `/dsl/tutorial/` et pour rien d'autre.*

## 2 ter. Exception — les pages d'explication

Une page qui **définit une notion** ne tient pas non plus en 250 mots. Définir `connection`,
c'est dire ce que le bloc est, ce qu'il n'est pas, et quels éléments le composent — cela demande
trois cents mots, pas quatre-vingts. Le plafond de 250 mots conduisait à des formules allusives :
justes, courtes, et incompréhensibles pour qui découvre.

Sont des pages d'explication : les pages d'accueil de section, et la partie explicative d'une
fiche d'élément.

**Ce qui est levé** : le plafond de 250 mots, remplacé par **500 mots**.

**Ce qui reste dû**

1. **La notion est définie avant d'être commentée.** Une page qui explique une conséquence sans
   avoir dit ce qu'est la chose est à refaire.
2. **Les éléments qui composent la notion sont énumérés**, groupés par rôle et non recopiés du
   modèle — un tableau de clés n'explique rien, il se consulte dans la référence.
3. **Des liens vers les sujets voisins** terminent la page.
4. La règle 1 continue de s'appliquer : la page commence par l'objet manipulable, l'explication
   vient après.

*Dérogation accordée par Bechir. Elle vaut pour les pages d'explication, et le plafond reste 500 mots.*

## 2 quater. Les exemples montrés sont corrects

Une page de documentation **montre du code juste**. Elle n'est pas un validateur, pas un linter,
pas un simulateur d'erreurs.

- Tout manifeste affiché est un manifeste qui s'exécute. Aucun exemple fautif, aucune ligne
  soulignée en rouge, aucun statut d'échec mis en scène.
- Ce qui peut échouer se dit **en prose** : « l'ordre compte », « le fichier est requis ».
  On l'explique, on ne le joue pas.
- Un sélecteur propose des **variantes correctes** — deux formes acceptées, un fichier omis,
  un exemple plus riche — jamais un cas cassé à observer.

**Seule exception, imposée par la règle 7** : un secret en clair saisi par l'utilisateur est
signalé en erreur bloquante. C'est une protection, pas une démonstration d'échec.

**Vérification** : script qui refuse un marqueur d'erreur dans un exemple de manifeste, hors la
page d'interpolation.

## 2 quinquies. Les ateliers du Guide

Un **atelier** part d'une situation de travail réelle et la résout de bout en bout. Ce n'est ni une
fiche de référence, ni une leçon de grammaire : c'est une étude de cas.

Sont des ateliers les pages sous `/guide/`.

**Ce qui est levé** : le plafond de 250 mots, porté à **900 mots**.

**La structure, fixe et obligatoire**

1. **Contexte** — la situation métier, en clair. Qui fait quoi aujourd'hui, et à quel coût.
2. **Où en sont les choses** — l'état des lieux, factuel.
3. **La question** — ce qu'on cherche à résoudre, suivie des contraintes en liste cochée.
4. **La solution en une ligne** — pas un paragraphe.
5. **Les étapes numérotées** — chacune une action à faire, avec la valeur exacte à écrire.
   Chaque étape peut porter un encart **Tip**, **Trap** ou **Check**.
6. **Le résultat attendu** — les chiffres réels du run.
7. **La lecture des résultats** — ce que les chiffres signifient, sous forme de questions.
8. **Avons-nous répondu ?** — un tableau objectif par objectif, y compris ce qui n'est pas atteint.
9. **Avant / après** — ce que le lecteur gagne réellement.

**Ce qui reste dû** : le projet montré existe dans le dépôt et s'exécute ; les chiffres affichés
viennent de cette exécution ; les exemples sont corrects (règle 2 quater) ; les règles 3 à 10.

**Vérification** : le script contrôle la présence des neuf sections et le budget de 900 mots.

*Dérogation accordée par Bechir sur le modèle d'atelier qu'il a fourni.*

## 3. Jamais de silence

- Tout ce qui n'est **pas** traduit, pas supporté, pas couvert doit être **affiché**, jamais omis.
- Trois verdicts et trois seulement : `mapped` / `no longer needed` / `needs a decision`.
- Une ligne d'entrée non reconnue produit un point orange. Le silence est un bug bloquant.
- On nomme ce que le concurrent fait mieux. La crédibilité vient de là.

**Vérification** : coller une construction volontairement non supportée, exiger un signalement.

## 4. Performance : tout côté client, statique par défaut

- Sortie **statique**. Aucune page de lecture ne dépend d'un serveur.
- **Budgets bloquants en CI** : < 50 ko JS sur une page de doc, < 250 ko sur la route Studio, LCP < 1,5 s en 4G.
- Îlots hydratés uniquement là où c'est indispensable, en `client:visible` ou `client:idle`.
- Recherche indexée côté client. Aucune facturation à la requête.
- Images en AVIF, chargement paresseux. Polices système uniquement, aucun webfont.
- **Interdit** : appeler un backend au chargement d'une page.

**Vérification** : Lighthouse CI avec seuils bloquants.

## 5. Pas de dépendance sans contrepartie

- JavaScript sans framework tant qu'il suffit. Un traducteur de 15 ko ne devient pas un composant de 200 ko par cohérence.
- Une bibliothèque s'ajoute si elle fait quelque chose d'irremplaçable — React Flow pour un canvas, rien pour un formulaire.

**Vérification** : justifier chaque dépendance par écrit dans la PR.

## 6. Accessibilité, non négociable

- Toute action à la souris a un équivalent clavier. Toute icône a un `aria-label` et un tooltip.
- Modals : focus au titre à l'ouverture, piège du focus, `Échap` ferme, focus restitué.
- États actifs visibles autrement que par la couleur. Contraste AA minimum.
- Cibles tactiles ≥ 44 px. Lisible à 200 % de zoom.

**Vérification** : parcourir la page au clavier seul, sans souris.

## 7. Sécurité et exemples

- **Jamais** de formulaire demandant un identifiant ou un secret sur le site public.
- Les exemples affichent `${SECRET.X}`, jamais une valeur.
- Un secret en clair détecté dans une saisie utilisateur est signalé en **erreur bloquante**.

## 8. Langue et ton

- Contenu du site en **anglais**. Documentation interne et commentaires de code en français.
- Ton factuel. Pas de superlatif, pas d'emoji, pas de « révolutionnaire ».
- On écrit ce que l'outil fait, pas ce qu'il fera.

## 9. Cohérence des gabarits

- Un tunnel de migration suit toujours la même structure : sélecteur d'outil, deux volets, rapport, menus contextuels.
- Les icônes agissent sur le volet entier. Le menu contextuel agit sur ce qui est sous le curseur. Aucune action n'existe **uniquement** dans un menu contextuel.
- Maximum 5 icônes par en-tête de volet. Au-delà, l'action va dans le menu.

## 10. Rien n'est livré sans vérification programmatique

- Avant toute présentation : syntaxe JS validée, balises équilibrées, tous les liens résolus.
- Chaque interaction est déclenchée par script et son résultat comparé à l'attendu.
- Un fichier écrit sur disque est relu et sa taille contrôlée.
- **Interdit** : présenter un livrable au motif qu'il « devrait marcher ».

---

## Checklist avant merge — pages de consultation

- [ ] Premier geste possible en moins de 5 secondes
- [ ] Moins de 250 mots de prose
- [ ] Les cas non supportés sont visibles
- [ ] Budgets Lighthouse respectés
- [ ] Aucun appel réseau au chargement
- [ ] Parcours clavier complet
- [ ] Aucun secret en clair, aucun formulaire d'identifiants
- [ ] Tous les liens résolvent
- [ ] Interactions testées par script

## Checklist avant merge — pages de tutoriel

- [ ] Structure fixe respectée : objectifs, description, étapes, implémentation, exécution, suite
- [ ] Moins de 900 mots de prose
- [ ] La leçon reprend le projet de la précédente, sur le jeu de données canonique
- [ ] Chaque bloc YAML provient d'un projet du dépôt qui s'exécute réellement
- [ ] La sortie affichée vient du moteur, pas d'une description
- [ ] Une commande exacte et copiable termine la leçon
- [ ] Les cas non supportés sont visibles
- [ ] Budgets Lighthouse respectés
- [ ] Aucun appel réseau au chargement
- [ ] Parcours clavier complet
- [ ] Aucun secret en clair, aucun formulaire d'identifiants
- [ ] Tous les liens résolvent
