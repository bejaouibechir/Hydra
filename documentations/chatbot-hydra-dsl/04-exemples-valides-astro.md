# Corpus d'exemples Hydra DSL pour Astro

**Étape 4 — Terminée**  
**Cible :** site Astro statique hébergé sur GitHub Pages  
**Runtime côté site :** JavaScript uniquement, aucun Python requis

## 1. Résultat

Le corpus contient **40 exemples**, soit quatre exemples pour chacune des dix notions du MVP :

| Variante | Rôle | Nombre |
|---|---|---:|
| `minimal` | Comprendre la syntaxe minimale | 10 |
| `practical` | Manipuler un cas plus réaliste | 10 |
| `challenge` | Déclencher une erreur pédagogique | 10 |
| `correction` | Réparer l'erreur du challenge | 10 |

Répartition de la validation :

- 30 exemples valides ;
- 10 défis volontairement invalides ;
- chaque défi produit le fragment d'erreur attendu.

## 2. Corpus statique

Le fichier directement consommable par Astro est :

```text
documentations/chatbot-hydra-dsl/examples/examples.json
```

Il contient pour chaque exemple :

- un identifiant stable ;
- la notion et la variante ;
- le titre ;
- la question utilisateur ;
- la réponse pédagogique attendue ;
- au moins deux indices progressifs ;
- le YAML à afficher ;
- les données d'entrée lorsque nécessaire ;
- le résultat attendu ;
- le diagnostic attendu pour les exercices incorrects.

Le JSON ne contient aucune fonction, aucun import Python et aucun appel réseau.

## 3. Validation au build

Le script suivant valide le corpus avec les parseurs et le moteur Hydra réels :

```text
scripts/validate_chatbot_dsl_examples.py
```

Commande :

```powershell
python scripts/validate_chatbot_dsl_examples.py
```

Résultat observé :

```text
OK — 40 exemples validés (30 valides, 10 défis invalides attendus)
```

Les transformations valides ne sont pas seulement analysées : elles sont exécutées par `PandasEngine`, puis leur sortie est comparée avec `expectedRows`.

## 4. Contrôles effectués

Le validateur vérifie :

1. exactement dix notions ;
2. exactement quatre exemples par notion ;
3. les quatre variantes obligatoires ;
4. l'unicité des identifiants ;
5. la présence des questions, réponses et indices ;
6. la validité du JSON et du YAML ;
7. la validation Pydantic des sources, destinations, transformations et workflows ;
8. la cohérence `pipeline.from` et `pipeline.to` ;
9. les dépendances et cycles des workflows ;
10. l'exécution des transformations et la comparaison des résultats ;
11. le message produit par chaque exemple volontairement incorrect.

## 5. Tests automatisés

Les tests se trouvent dans :

```text
tests/test_chatbot_dsl_examples.py
```

Ils vérifient également que le corpus est un JSON directement importable par Astro.

Résultat groupé avec les tests de génération des schémas :

```text
5 tests réussis
```

## 6. Intégration dans Astro

### Option recommandée : import au build

Copier ou synchroniser le corpus dans le projet Astro, par exemple :

```text
src/data/hydra-dsl/examples.json
```

Puis l'importer :

```ts
import corpus from '../data/hydra-dsl/examples.json';

const filterExamples = corpus.examples.filter(
  example => example.notion === 'transform.filter'
);
```

Astro intègre alors les données dans les pages générées. GitHub Pages ne réalise aucun appel à Python ou au moteur Hydra.

### Option alternative : chargement côté navigateur

Placer le fichier sous :

```text
public/data/hydra-dsl/examples.json
```

Puis respecter le chemin de base GitHub Pages :

```ts
const url = `${import.meta.env.BASE_URL}data/hydra-dsl/examples.json`;
const corpus = await fetch(url).then(response => response.json());
```

Il ne faut pas utiliser `/data/...` directement, car le site peut être publié sous `/nom-du-depot/`.

## 7. Intégration GitHub Actions

La validation doit s'exécuter avant `astro build` :

```yaml
- name: Validate Hydra DSL schemas
  run: python scripts/generate_hydra_dsl_schemas.py --check

- name: Validate chatbot examples
  run: python scripts/validate_chatbot_dsl_examples.py

- name: Build Astro site
  run: npm run build
```

Un exemple incorrect ou désynchronisé bloque ainsi la publication.

## 8. Fonctionnement du chatbot sans backend

Le chatbot statique peut répondre localement aux questions couvertes en recherchant dans :

- `notion` ;
- `question` ;
- `answer` ;
- `title` ;
- les identifiants et propriétés présents dans `yaml`.

Il peut aussi proposer les indices dans l'ordre sans appel à un LLM. Un futur service IA pourra utiliser le même corpus sans modifier les contenus Astro.

## 9. Incohérence technique isolée

Le modèle Pydantic `CastOp` accepte le type `date`, mais le moteur Pandas actif ne possède pas de branche d'exécution pour `date` ; il accepte `datetime`.

Décision pour le MVP :

- ne pas enseigner ni générer `date` dans les exercices exécutables ;
- continuer à enseigner `datetime` ;
- corriger ultérieurement le modèle ou le moteur afin de retrouver une source de vérité unique.

## 10. Commandes de contrôle

```powershell
python scripts/generate_hydra_dsl_schemas.py --check
python scripts/validate_chatbot_dsl_examples.py
python -m pytest tests/test_generate_dsl_schemas.py tests/test_chatbot_dsl_examples.py -q
```
