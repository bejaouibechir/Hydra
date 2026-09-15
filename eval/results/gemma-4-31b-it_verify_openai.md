# Évaluation — gemma-4-31b-it — mode `verify`

- Cas mesurés : **31** sur 34 — **3 non mesurés** (erreur du fournisseur, exclus des moyennes)
- Temps total : **1499 s**
- **Taux d'erreur silencieuse : 6%** (2/31) — cas faux qu'aucun garde-fou n'a signalés
- Cas assortis d'au moins une alerte : 14
- Few-shot : 1 exemple(s) · thinking : off

| Niveau | Cas | Validité | Exactitude | Sobriété | s/cas |
|---|---:|---:|---:|---:|---:|
| adversarial | 5 | 100% | 100% | 100% | 22.7 |
| base_de_donnees | 5 | 60% | 87% | 100% | 59.9 |
| compose | 5 | 0% | 76% | 100% | 35.1 |
| intermediaire | 6 | 0% | 76% | 100% | 55.8 |
| simple | 7 | 57% | 95% | 100% | 57.9 |
| workflow | 3 | 100% | 100% | 100% | 57.2 |
| **total** | **31** | **48%** | **88%** | **100%** | **48.4** |

## Erreurs silencieuses

- `gen-004` — destinations.yaml manquant; câblage incorrect : from=src_commandes to=dst_commandes_en
- `gen-033` — type de destination attendu ['postgres'], obtenu ['postgresql']

## Non mesurés (3)

- `gen-008` — fournisseur injoignable: HTTP 503 — [{
  "error": {
    "code": 503,
    "message": "This model is currently experiencing high demand. Spike
- `gen-012` — fournisseur injoignable: HTTP 503 — [{
  "error": {
    "code": 503,
    "message": "This model is currently experiencing high demand. Spike
- `gen-042` — fournisseur injoignable: HTTP 503 — [{
  "error": {
    "code": 503,
    "message": "This model is currently experiencing high demand. Spike

## Échecs (18)

- `gen-002` (simple) — V0 E1.00 S1 — 
- `gen-004` (simple) — V0 E0.67 S1 — destinations.yaml manquant; câblage incorrect : from=src_commandes to=dst_commandes_en
- `gen-006` (simple) — V0 E1.00 S1 — 
- `gen-010` (intermediaire) — V0 E1.00 S1 — 
- `gen-011` (intermediaire) — V0 E1.00 S1 — 
- `gen-013` (intermediaire) — V0 E1.00 S1 — 
- `gen-014` (intermediaire) — V0 E0.00 S1 — sources.yaml manquant; destinations.yaml manquant; transformations.yaml manquant; pipeline.yaml manquant; opération 'select' absente; opération 'filter' absente; câblage incorrect 
- `gen-015` (intermediaire) — V0 E1.00 S1 — 
- `gen-016` (intermediaire) — V0 E0.57 S1 — destinations.yaml manquant; opération 'sort' absente; câblage incorrect : from=src_commandes to=dst_stats
- `gen-020` (compose) — V0 E1.00 S1 — 
- `gen-021` (compose) — V0 E1.00 S1 — 
- `gen-022` (compose) — V0 E0.00 S1 — sources.yaml manquant; destinations.yaml manquant; transformations.yaml manquant; pipeline.yaml manquant; opération 'cast' absente; opération 'pivot' absente; câblage incorrect : f
- `gen-023` (compose) — V0 E1.00 S1 — 
- `gen-024` (compose) — V0 E0.82 S1 — destinations.yaml manquant; câblage incorrect : from=src_commandes to=dst_top_pays
- `gen-031` (base_de_donnees) — V0 E1.00 S1 — 
- `gen-032` (base_de_donnees) — V0 E1.00 S1 — 
- `gen-033` (base_de_donnees) — V1 E0.86 S1 — type de destination attendu ['postgres'], obtenu ['postgresql']
- `gen-034` (base_de_donnees) — V1 E0.50 S1 — 'env:' absent; '${' absent
