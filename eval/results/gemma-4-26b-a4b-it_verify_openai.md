# Évaluation — gemma-4-26b-a4b-it — mode `verify`

- Cas mesurés : **34** sur 34
- Temps total : **139 s**
- **Taux d'erreur silencieuse : 18%** (6/34) — cas faux qu'aucun garde-fou n'a signalés
- Cas assortis d'au moins une alerte : 13
- Few-shot : 1 exemple(s) · thinking : off

| Niveau | Cas | Validité | Exactitude | Sobriété | s/cas |
|---|---:|---:|---:|---:|---:|
| adversarial | 5 | 60% | 60% | 100% | 4.7 |
| base_de_donnees | 5 | 40% | 82% | 100% | 2.8 |
| compose | 5 | 0% | 92% | 100% | 3.0 |
| intermediaire | 7 | 14% | 76% | 100% | 6.1 |
| simple | 8 | 62% | 90% | 100% | 2.9 |
| workflow | 4 | 75% | 75% | 100% | 5.2 |
| **total** | **34** | **41%** | **80%** | **100%** | **4.1** |

## Erreurs silencieuses

- `gen-002` — destinations.yaml manquant; pipeline.yaml manquant; type de destination attendu ['csv'], obtenu []; câblage incorrect : from=None to=None
- `gen-004` — câblage incorrect : from=src_cmd to=dst_mapping_en
- `gen-006` — câblage incorrect : from=src_stock to=dst_trie_stock
- `gen-012` — opération 'cast' absente
- `gen-022` — destinations.yaml manquant; pipeline.yaml manquant; câblage incorrect : from=None to=None
- `gen-033` — type de destination attendu ['postgres'], obtenu ['postgresql']

## Échecs (21)

- `gen-002` (simple) — V0 E0.50 S1 — destinations.yaml manquant; pipeline.yaml manquant; type de destination attendu ['csv'], obtenu []; câblage incorrect : from=None to=None
- `gen-004` (simple) — V0 E0.83 S1 — câblage incorrect : from=src_cmd to=dst_mapping_en
- `gen-006` (simple) — V0 E0.83 S1 — câblage incorrect : from=src_stock to=dst_trie_stock
- `gen-010` (intermediaire) — V0 E0.62 S1 — destinations.yaml manquant; pipeline.yaml manquant; câblage incorrect : from=None to=None
- `gen-011` (intermediaire) — V0 E0.00 S1 — sources.yaml manquant; destinations.yaml manquant; transformations.yaml manquant; pipeline.yaml manquant; opération 'cast' absente; opération 'aggregate' absente; câblage incorrect
- `gen-012` (intermediaire) — V0 E0.86 S1 — opération 'cast' absente
- `gen-014` (intermediaire) — V0 E1.00 S1 — 
- `gen-015` (intermediaire) — V0 E0.86 S1 — câblage incorrect : from=src_  mesures to=dst_parquet
- `gen-016` (intermediaire) — V0 E1.00 S1 — 
- `gen-020` (compose) — V0 E1.00 S1 — 
- `gen-021` (compose) — V0 E1.00 S1 — 
- `gen-022` (compose) — V0 E0.62 S1 — destinations.yaml manquant; pipeline.yaml manquant; câblage incorrect : from=None to=None
- `gen-023` (compose) — V0 E1.00 S1 — 
- `gen-024` (compose) — V0 E1.00 S1 — 
- `gen-031` (base_de_donnees) — V0 E1.00 S1 — 
- `gen-032` (base_de_donnees) — V0 E0.75 S1 — opération 'filter' absente; câblage incorrect : from=src_mongo_cmd to=dst_parquet_2062
- `gen-033` (base_de_donnees) — V1 E0.86 S1 — type de destination attendu ['postgres'], obtenu ['postgresql']
- `gen-034` (base_de_donnees) — V0 E0.50 S1 — 'env:' absent; '${' absent
- `gen-043` (workflow) — V0 E0.00 S1 — workflow.yaml manquant; 4 steps attendus, 0; aucun fan-in
- `adv-050` (adversarial) — V0 E0.00 S1 — aurait dû refuser
- `adv-052` (adversarial) — V0 E0.00 S1 — aurait dû refuser
