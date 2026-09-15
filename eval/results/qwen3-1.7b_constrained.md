# Évaluation — qwen3:1.7b — mode `constrained`

- Cas joués : **34**
- Temps total : **618 s**
- Few-shot : 1 exemple(s) · thinking : off

| Niveau | Cas | Validité | Exactitude | Sobriété | s/cas |
|---|---:|---:|---:|---:|---:|
| adversarial | 5 | 80% | 40% | 100% | 11.4 |
| base_de_donnees | 5 | 60% | 70% | 100% | 14.9 |
| compose | 5 | 80% | 84% | 100% | 28.7 |
| intermediaire | 7 | 86% | 82% | 100% | 23.2 |
| simple | 8 | 50% | 47% | 100% | 15.3 |
| workflow | 4 | 50% | 61% | 100% | 14.6 |
| **total** | **34** | **68%** | **64%** | **100%** | **18.2** |

## Échecs (28)

- `gen-001` (simple) — V1 E0.86 S1 — mode attendu 'replace', obtenu ['append']
- `gen-002` (simple) — V1 E0.88 S1 — opération 'select' absente
- `gen-003` (simple) — V1 E0.83 S1 — type de source attendu ['json'], obtenu ['parquet']
- `gen-004` (simple) — V0 E0.00 S1 — sources.yaml manquant; destinations.yaml manquant; transformations.yaml manquant; pipeline.yaml manquant; opération 'rename' absente; câblage incorrect : from=None to=None
- `gen-005` (simple) — V0 E0.00 S1 — sources.yaml manquant; destinations.yaml manquant; transformations.yaml manquant; pipeline.yaml manquant; opération 'deduplicate' absente; câblage incorrect : from=None to=None
- `gen-006` (simple) — V1 E0.67 S1 — transformations.yaml manquant; opération 'sort' absente
- `gen-007` (simple) — V0 E0.50 S1 — transformations.yaml manquant; opération 'fill_null' absente; câblage incorrect : from=employes to=employes_propre
- `gen-008` (simple) — V0 E0.00 S1 — refus injustifié
- `gen-010` (intermediaire) — V1 E0.86 S1 — opération 'cast' absente
- `gen-011` (intermediaire) — V1 E0.71 S1 — opération 'cast' absente; opération 'aggregate' absente
- `gen-012` (intermediaire) — V0 E0.57 S1 — opération 'cast' absente; opération 'calculate' absente; câblage incorrect : from=factures to=factures_pu
- `gen-014` (intermediaire) — V1 E0.86 S1 — opération 'select' absente
- `gen-016` (intermediaire) — V1 E0.71 S1 — opération 'aggregate' absente; opération 'sort' absente
- `gen-021` (compose) — V1 E0.71 S1 — transformations.yaml manquant; opération 'union' absente
- `gen-022` (compose) — V1 E0.86 S1 — opération 'cast' absente
- `gen-023` (compose) — V1 E0.83 S1 — opération 'unpivot' absente
- `gen-024` (compose) — V0 E0.82 S1 — opération 'cast' absente; câblage incorrect : from=commandes to=top_pays
- `gen-031` (base_de_donnees) — V0 E1.00 S1 — 
- `gen-032` (base_de_donnees) — V1 E0.75 S1 — transformations.yaml manquant; opération 'filter' absente
- `gen-033` (base_de_donnees) — V0 E0.00 S1 — refus injustifié
- `gen-034` (base_de_donnees) — V1 E0.75 S1 — '${' absent
- `gen-040` (workflow) — V1 E0.67 S1 — aucun depends_on
- `gen-041` (workflow) — V0 E0.60 S1 — trigger incorrect; cron absent
- `gen-042` (workflow) — V0 E0.50 S1 — retry absent
- `gen-043` (workflow) — V1 E0.67 S1 — aucun fan-in
- `adv-050` (adversarial) — V1 E0.00 S1 — aurait dû refuser
- `adv-051` (adversarial) — V1 E0.00 S1 — aurait dû refuser
- `adv-054` (adversarial) — V0 E0.00 S1 — aurait dû refuser
