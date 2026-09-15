# Évaluation — gemini-flash-latest — mode `verify`

- Cas joués : **3**
- Temps total : **6 s**
- **Taux d'erreur silencieuse : 0%** (0/3) — cas faux qu'aucun garde-fou n'a signalés
- Cas assortis d'au moins une alerte : 0
- Few-shot : 1 exemple(s) · thinking : off

| Niveau | Cas | Validité | Exactitude | Sobriété | s/cas |
|---|---:|---:|---:|---:|---:|
| simple | 3 | 33% | 33% | 33% | 1.9 |
| **total** | **3** | **33%** | **33%** | **33%** | **1.9** |

## Erreurs silencieuses

Aucune. Tout écart a été signalé à l'utilisateur.

## Échecs (2)

- `gen-002` (simple) — V0 E0.00 S0 — fournisseur injoignable: HTTP 503 — [{
  "error": {
    "code": 503,
    "message": "This model is currently experiencing high demand. Spikes in demand are usually temporary. Pleas
- `gen-003` (simple) — V0 E0.00 S0 — fournisseur injoignable: HTTP 503 — [{
  "error": {
    "code": 503,
    "message": "This model is currently experiencing high demand. Spikes in demand are usually temporary. Pleas
