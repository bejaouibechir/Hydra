**Extensibilité SmartETL – Les 8 vrais points d’extension (et rien d’autre)**  
Objectif : on reste hyper modulaire, mais on ne crée pas 50 plugins inutiles. Voici les seuls endroits où l’extensibilité est réellement utile, classés par fréquence d’usage réel en 2025.

| #   | Point d’extension                                  | Où le mettre exactement                            | Comment l’utilisateur le déclare                                   | Niveau de difficulté | Fréquence d’usage réel |
| --- | -------------------------------------------------- | -------------------------------------------------- | ------------------------------------------------------------------ | -------------------- | ---------------------- |
| 1   | **Nouveaux connecteurs** (source & dest)           | `internal/connector/` → fichier `monconnecteur.py` | Dans `sources.yaml` ou `destinations.yaml` → `type: monconnecteur` | ★☆☆☆☆                | Très élevé             |
| 2   | **Nouvelles opérations DSL**                       | `internal/transform/operations/` (nouveau dossier) | Dans `pipeline.yaml` → `- mon_op: ...`                             | ★★☆☆☆                | Élevé                  |
| 3   | **Remplacement moteur de transformation**          | `internal/transform/engine_factory.py`             | Dans `pipeline.yaml` → `engine: polars` ou `engine: spark`         | ★★☆☆☆                | Moyen                  |
| 4   | **Custom Python step (déjà dans Hydra)**           | Directement dans `pipeline.yaml` → `python:`       | Aucun code à écrire côté core                                      | ★☆☆☆☆                | Très élevé             |
| 5   | **Custom logger / exporter métriques**             | `internal/logger/plugins/`                         | `logger: prometheus` ou `logger: datadog`                          | ★★☆☆☆                | Moyen                  |
| 6   | **Cache alternatif** (Redis, disk, etc.)           | `internal/cache/backends/`                         | `cache: redis://...` dans config globale                           | ★★★☆☆                | Faible → moyen         |
| 7   | **Artefact compilé Go/Rust**                       | `internal/transform/compilers/go_compiler.py`      | `compile: true` + `language: go` dans job config                   | ★★★★☆                | Faible (perf extrême)  |
| 8   | **Hooks lifecycle** (pre-run, post-step, post-job) | `internal/runner/hooks.py`                         | `hooks: mycompany.hooks` dans config                               | ★★☆☆☆                | Moyen (audit, alertes) |

### Implémentation concrète de chaque point (prête à copier-coller)

#### 1. Nouveaux connecteurs (le plus important)

```python
# internal/connector/shopify.py
from .interface import SourceConnector

class ShopifyConnector(SourceConnector):
    def read_batches(self, **kwargs):
        # implémentation avec shopify-python-api
        yield from self._paginate("/admin/api/2024-07/orders.json")
```

→ Déclaré simplement :

```yaml
# sources.yaml
src_shopify_orders:
  type: shopify
  shop: monboutique.myshopify.com
  api_key: ${SECRET:SHOPIFY_KEY}
```

#### 2. Nouvelles opérations DSL

```python
# internal/transform/operations/haversine.py
def execute(df, lat1, lon1, lat2, lon2, output_col="distance_km"):
    from math import radians, sin, cos, sqrt, atan2
    R = 6371
    # vectorisé avec numba ou numpy
    ...
    return df
```

→ Dans pipeline.yaml :

```yaml
- calc_distance:
    input: deliveries
    haversine:
      lat1: customer_lat
      lon1: customer_lon
      lat2: warehouse_lat
      lon2: warehouse_lon
      output: distance_km
```

#### 3. Remplacer DuckDB par Polars / Spark / etc.

```python
# internal/transform/engine_factory.py
ENGINES = {
    "pandas": PandasEngine(),
    "duckdb": DuckDBEngine(),
    "polars": PolarsEngine(),      # ← nouveau
    "spark": SparkEngine(),        # ← futur
}

def get_engine(name: str = "auto"):
    if name == "auto":
        return AutoRoutingEngine()  # regarde les ops utilisées
    return ENGINES[name]
```

→ Dans pipeline.yaml (global ou par étape) :

```yaml
engine: polars        # tout le job en Polars
# ou
- big_aggregation:
    engine: polars
    aggregate: ...
```

#### 7. Artefact Go (le cas extrême perf)

Structure finale :

```
artifacts/
└── compilers/
    └── go/
        ├── go.mod
        ├── main.go          # généré à partir du DSL
        └── build.sh
```

Le runner appelle :

```bash
/go_compiler build job_123 → artifacts/jobs/job_123_linux_amd64
./artifacts/jobs/job_123_linux_amd64
```

### Recommandation finale : les seuls dossiers "plugins" à créer

```bash
etl-project/
├── plugins/
│   ├── connectors/          # ← shopify.py, salesforce.py, snowflake.py
│   ├── operations/          # ← haversine.py, bloom_filter.py, crypto.py
│   ├── engines/             # ← polars_engine.py, spark_engine.py
│   ├── loggers/             # ← prometheus.py, datadog.py
│   └── hooks/               # ← slack_alert.py, audit.py
```

Et dans la config globale (`config/shared/common.yaml`) :

```yaml
plugins:
  paths:
    - "./plugins"
  auto_discover: true
```

### Conclusion (ce que tu dois retenir)

| Tu veux permettre l’extension | Solution officielle SmartETL |
| ----------------------------- | ---------------------------- |
| Nouveau format de fichier     | → `plugins/connectors/`      |
| Nouvelle transformation       | → `plugins/operations/`      |
| Changer de moteur             | → `engine: polars` dans YAML |
| Perf extrême                  | → artefact Go/Rust optionnel |
| Monitoring custom             | → `plugins/loggers/`         |

Tout le reste (cache Redis, secrets Vault, etc.) se fait déjà via config → zéro code.

Tu veux que je te sorte maintenant :

- le squelette complet des `plugins/` + auto-discovery
- ou le `engine_factory.py` avec Polars déjà intégré ?

Dis-moi, on le fait en 10 min.
