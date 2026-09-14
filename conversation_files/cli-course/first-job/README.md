# Job : first-job

Template : `csv`

## Structure

- `sources.yaml` — sources de données
- `destinations.yaml` — destinations
- `pipeline.yaml` — orchestration
- `transformations.yaml` — transformations DSL (optionnel)
- `.env` — variables d'environnement (à créer depuis .env.example)

## Utilisation

```bash
hydra test first-job   # valider la config
hdrctl run  first-job   # exécuter
```
