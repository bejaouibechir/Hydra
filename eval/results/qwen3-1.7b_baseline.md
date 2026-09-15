# Évaluation — qwen3:1.7b — mode `baseline`

- Cas joués : **34**
- Temps total : **1526 s**
- Few-shot : 1 exemple(s) · thinking : off

| Niveau | Cas | Validité | Exactitude | Sobriété | s/cas |
|---|---:|---:|---:|---:|---:|
| adversarial | 5 | 60% | 0% | 100% | 25.4 |
| base_de_donnees | 5 | 0% | 36% | 100% | 66.9 |
| compose | 5 | 80% | 60% | 100% | 31.0 |
| intermediaire | 7 | 57% | 50% | 100% | 70.0 |
| simple | 8 | 75% | 78% | 100% | 38.0 |
| workflow | 4 | 25% | 0% | 100% | 29.0 |
| **total** | **34** | **53%** | **43%** | **100%** | **44.9** |

## Échecs (31)

- `gen-001` (simple) — V1 E0.86 S1 — mode attendu 'replace', obtenu ['append']
- `gen-002` (simple) — V1 E0.75 S1 — transformations.yaml manquant; opération 'select' absente
- `gen-003` (simple) — V0 E1.00 S1 — 
- `gen-005` (simple) — V1 E0.67 S1 — transformations.yaml manquant; opération 'deduplicate' absente
- `gen-008` (simple) — V0 E0.00 S1 — sources.yaml manquant; destinations.yaml manquant; pipeline.yaml manquant; mode attendu 'append', obtenu []; câblage incorrect : from=None to=None
- `gen-010` (intermediaire) — V1 E0.57 S1 — transformations.yaml manquant; opération 'cast' absente; opération 'filter' absente
- `gen-011` (intermediaire) — V0 E0.43 S1 — transformations.yaml manquant; opération 'cast' absente; opération 'aggregate' absente; câblage incorrect : from=source_orders to=dest_ok
- `gen-012` (intermediaire) — V1 E0.57 S1 — transformations.yaml manquant; opération 'cast' absente; opération 'calculate' absente
- `gen-013` (intermediaire) — V1 E0.67 S1 — transformations.yaml manquant; opération 'clean' absente
- `gen-014` (intermediaire) — V1 E0.57 S1 — transformations.yaml manquant; opération 'select' absente; opération 'filter' absente
- `gen-015` (intermediaire) — V0 E0.00 S1 — sources.yaml manquant; destinations.yaml manquant; transformations.yaml manquant; pipeline.yaml manquant; type de destination attendu ['parquet'], obtenu []; opération 'cast' absen
- `gen-016` (intermediaire) — V0 E0.71 S1 — opération 'aggregate' absente; opération 'sort' absente
- `gen-020` (compose) — V1 E0.71 S1 — transformations.yaml manquant; opération 'join' absente
- `gen-021` (compose) — V1 E0.71 S1 — transformations.yaml manquant; opération 'union' absente
- `gen-022` (compose) — V0 E0.43 S1 — transformations.yaml manquant; opération 'cast' absente; opération 'pivot' absente; câblage incorrect : from=sources to=destinations
- `gen-023` (compose) — V1 E0.67 S1 — transformations.yaml manquant; opération 'unpivot' absente
- `gen-024` (compose) — V1 E0.46 S1 — transformations.yaml manquant; opération 'cast' absente; opération 'join' absente; opération 'filter' absente; opération 'aggregate' absente; opération 'sort' absente
- `gen-030` (base_de_donnees) — V0 E0.67 S1 — type de source attendu ['postgres', 'postgresql'], obtenu []; câblage incorrect : from=clients to=clients
- `gen-031` (base_de_donnees) — V0 E0.14 S1 — destinations.yaml manquant; pipeline.yaml manquant; type de source attendu ['csv'], obtenu []; type de destination attendu ['mariadb', 'mysql'], obtenu []; mode attendu 'upsert', o
- `gen-032` (base_de_donnees) — V0 E0.50 S1 — transformations.yaml manquant; type de source attendu ['mongodb'], obtenu []; opération 'filter' absente; câblage incorrect : from=commande_db to=commande_2026
- `gen-033` (base_de_donnees) — V0 E0.00 S1 — sources.yaml manquant; destinations.yaml manquant; pipeline.yaml manquant; type de source attendu ['web_api'], obtenu []; type de destination attendu ['postgres'], obtenu []; mode 
- `gen-034` (base_de_donnees) — V0 E0.50 S1 — type de source attendu ['postgres', 'postgresql'], obtenu []; '${' absent
- `gen-040` (workflow) — V0 E0.00 S1 — workflow.yaml manquant; 2 steps attendus, 0; aucun depends_on
- `gen-041` (workflow) — V1 E0.00 S1 — workflow.yaml manquant; 2 steps attendus, 0; trigger incorrect; cron absent; action 'webhook' absente
- `gen-042` (workflow) — V0 E0.00 S1 — workflow.yaml manquant; retry absent
- `gen-043` (workflow) — V0 E0.00 S1 — workflow.yaml manquant; 4 steps attendus, 0; aucun fan-in
- `adv-050` (adversarial) — V1 E0.00 S1 — aurait dû refuser
- `adv-051` (adversarial) — V0 E0.00 S1 — aurait dû refuser
- `adv-052` (adversarial) — V0 E0.00 S1 — aurait dû refuser
- `adv-053` (adversarial) — V1 E0.00 S1 — aurait dû refuser
- `adv-054` (adversarial) — V1 E0.00 S1 — aurait dû refuser
