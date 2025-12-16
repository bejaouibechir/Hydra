# Hydra

Hydra est un framework ETL modulaire, pilote par un DSL declaratif.
L'objectif : definir des pipelines Extract/Transform/Load via YAML, avec un moteur d'execution stable.

## Principes

- Couche publique **etl/** : API stable (point d'entree Engine + types publics)
- Couche interne **internal/** : parsing, execution, connecteurs, engines, cache, logs
- Dossier **plugins/** : extensions decoupees (connecteurs, operations, engines, hooks, error-handlers, metrics, cache, compilers)

## Structure

- **etl/** : API publique
- **internal/** : implementation du coeur
- **plugins/** : 8 points d'extension
- **cli/** : interface ligne de commande

## Prochaine etape

Implementer le PluginLoader et un premier connecteur (MariaDB) + une commande CLI "hydra run".
