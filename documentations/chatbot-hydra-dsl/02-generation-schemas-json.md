# Génération des schémas JSON du Hydra DSL

**Étape 2 — Terminée**  
**Produit :** Hydra `1.2.0`  
**DSL observé :** `1.1`  
**Dialecte JSON Schema :** Draft 2020-12

## Résultat

Le générateur produit **22 schémas JSON** depuis les modèles Pydantic actifs :

- 18 schémas d'opérations de transformation ;
- 4 schémas de manifests : sources, transformations, destinations et workflow ;
- 1 index décrivant tous les artefacts.

## Emplacement

```text
documentations/chatbot-hydra-dsl/schemas/
├── index.json
├── manifests/
│   ├── sources.schema.json
│   ├── transformations.schema.json
│   ├── destinations.schema.json
│   └── workflow.schema.json
└── operations/
    ├── aggregate.schema.json
    ├── calculate.schema.json
    ├── cast.schema.json
    ├── clean.schema.json
    ├── deduplicate.schema.json
    ├── fill_null.schema.json
    ├── filter.schema.json
    ├── join.schema.json
    ├── merge.schema.json
    ├── pivot.schema.json
    ├── rename.schema.json
    ├── script.schema.json
    ├── select.schema.json
    ├── sort.schema.json
    ├── transpose.schema.json
    ├── trim.schema.json
    ├── union.schema.json
    └── unpivot.schema.json
```

## Générateur

Le script reproductible est :

```text
scripts/generate_hydra_dsl_schemas.py
```

Génération :

```powershell
python scripts/generate_hydra_dsl_schemas.py
```

Vérification sans modification :

```powershell
python scripts/generate_hydra_dsl_schemas.py --check
```

Le mode `--check` retourne un code d'erreur si un modèle Pydantic a changé sans régénération des schémas.

## Métadonnées ajoutées

Chaque schéma contient :

- `$schema` : dialecte Draft 2020-12 ;
- `$id` : identifiant stable et versionné ;
- `x-hydra.dslName` ;
- `x-hydra.dslVersion` ;
- `x-hydra.productVersion` ;
- `x-hydra.kind` ;
- `x-hydra.sourceModel` ;
- `x-hydra.generatedFromPydantic`.

Les propriétés, types, contraintes, valeurs par défaut et champs requis restent produits directement par `model_json_schema(mode="validation")`.

## Contrôles automatisés

Le fichier `tests/test_generate_dsl_schemas.py` vérifie :

1. que les 18 opérations du registre possèdent un schéma ;
2. que l'index contient exactement 22 schémas ;
3. que chaque schéma possède les métadonnées Hydra ;
4. que les fichiers présents sont synchronisés avec les modèles actifs.

Résultat observé :

```text
3 tests réussis
22 schémas synchronisés
```

## Limite identifiée

`pipeline.yaml` ne possède pas encore de modèle Pydantic actif. Aucun schéma manuel n'a été inventé afin de respecter la règle « Pydantic comme source de vérité ».

Cette lacune est déclarée dans `schemas/index.json` sous `unmodelledManifests`. La création d'un `PipelineConfig` Pydantic devra faire l'objet d'une évolution séparée avant de générer `pipeline.schema.json`.

## Utilisation future par le chatbot

Ces schémas permettront au chatbot de :

- vérifier l'existence d'une opération ou propriété ;
- connaître les champs obligatoires ;
- expliquer les types et valeurs par défaut ;
- adapter les réponses à la version du DSL ;
- citer le modèle technique ayant produit l'information ;
- éviter d'inventer des propriétés Hydra.
