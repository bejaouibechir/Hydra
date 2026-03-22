<function_results>OK</function_calls>Excellente question sur l'extensibilité ! J'ai créé une analyse complète qui identifie **12 points d'extensibilité** au lieu des 3 que vous aviez mentionnés.

## 🎯 Points d'extensibilité identifiés

### ✅ Déjà prévus (3)

1. **Connecteurs** - Interface existe
2. **DSL Operations** - SQL/Python escape hatches
3. **Migration Go** - Démarche définie

### ⚠️ À ajouter immédiatement (6)

4. **Transform Engines** - Interface manquante ! (critique)
5. **Cache Backends** - Seulement mémoire actuellement
6. **Secret Backends** - Pas d'abstraction Vault/AWS
7. **Validateurs DSL** - Hardcodés dans parser
8. **Error Handlers** - Gestion centralisée non pluggable
9. **SQL Engines** - DuckDB hardcodé (swap impossible)

### 📋 Futures extensions (3)

10. **Logger Backends**
11. **Plugin System** (entry points)
12. **Schedulers**

## 🚀 Points clés de ma recommandation

### 1. **Pattern unifié : Interface + Registry**

Chaque composant suit le même pattern :

```python
# Interface abstraite
class TransformEngine(ABC)

# Registry pour découverte
EngineRegistry.register('pandas', PandasEngine)
EngineRegistry.register('go', GoEngine)  # Ajout facile !
```

### 2. **Migration Go progressive - 4 niveaux**

- **Niveau 1** : CLI wrapper (subprocess) ← **Recommandé MVP**
- Niveau 2 : Service gRPC
- Niveau 3 : Shared library
- Niveau 4 : Réécriture complète

### 3. **Swap DuckDB facilité**

```python
class SQLEngine(ABC)  # Interface commune
├── DuckDBSQLEngine
├── DataFusionEngine  # Alternative Rust
└── PolarsEngine
```

## 📊 Architecture mise à jour

J'ai ajouté dans l'artefact :

- 8 nouvelles interfaces
- Pattern de Registry partout
- Guide "Comment ajouter un plugin"
- Stratégie complète migration Go
- Checklist d'extensibilité

Voulez-vous que je :

1. **Implémente les interfaces prioritaires** (Transform, Cache, Secrets) ?
2. **Crée le système de plugins** avec entry points ?
3. **Code le wrapper Go** (Level 1) en exemple ?

# SmartETL - Architecture d'Extensibilité Complète

## 🎯 Philosophie : "Extensible by Design"

### Principe SOLID appliqué à l'ETL

- **Open/Closed** : Ouvert à l'extension, fermé à la modification
- **Dependency Inversion** : Dépendre d'abstractions, pas d'implémentations
- **Interface Segregation** : Interfaces spécifiques et minimales

---

## 📊 Points d'extensibilité actuels vs. manquants

| Point d'extensibilité         | Statut actuel           | Priorité | Difficulté |
| ----------------------------- | ----------------------- | -------- | ---------- |
| **1. Connecteurs**            | ✅ Prévu (interface.py)  | P0       | ⭐⭐         |
| **2. Moteurs transformation** | ✅ Prévu (pandas/duckdb) | P0       | ⭐⭐⭐        |
| **3. DSL operations**         | ✅ Prévu (SQL/Python)    | P0       | ⭐⭐         |
| **4. Migration Go**           | ⚠️ Flou                 | P1       | ⭐⭐⭐⭐⭐      |
| **5. Cache backends**         | ⚠️ Partiel              | P1       | ⭐⭐⭐        |
| **6. Secrets managers**       | ⚠️ Partiel              | P1       | ⭐⭐⭐        |
| **7. Loggers/observability**  | ⚠️ Partiel              | P2       | ⭐⭐         |
| **8. Validateurs custom**     | ❌ Absent                | P2       | ⭐⭐         |
| **9. Error handlers**         | ❌ Absent                | P2       | ⭐⭐         |
| **10. Schedulers**            | ❌ Absent                | P3       | ⭐⭐⭐⭐       |

---

## 🔌 1. Extensibilité des Connecteurs (Déjà prévu)

### Interface actuelle

```python
# internal/connector/interface.py

from abc import ABC, abstractmethod
from typing import Iterator, Dict, Any, List

class Connector(ABC):
    """Interface de base pour tous les connecteurs"""

    @abstractmethod
    def connect(self) -> None:
        """Établit la connexion"""
        pass

    @abstractmethod
    def test_connection(self) -> bool:
        """Teste la connexion"""
        pass

    @abstractmethod
    def read_batches(self, batch_size: int) -> Iterator[List[Dict[str, Any]]]:
        """Lit les données par batch"""
        pass

    @abstractmethod
    def write_batches(self, batches: Iterator[List[Dict[str, Any]]], mode: str) -> None:
        """Écrit les données par batch"""
        pass

    @abstractmethod
    def close(self) -> None:
        """Ferme la connexion"""
        pass
```

### ✅ Bon - déjà prévu

---

## ⚙️ 2. Extensibilité des Moteurs de Transformation

### Architecture actuelle

```python
# internal/transform/pandas_engine.py
# internal/transform/duckdb_engine.py
```

### ❌ Problème : Pas d'interface commune !

### ✅ Solution : Créer `TransformEngine` interface

```python
# internal/transform/interface.py

from abc import ABC, abstractmethod
from typing import Any, Dict, List
import pandas as pd

class TransformEngine(ABC):
    """Interface pour moteurs de transformation"""

    @abstractmethod
    def execute(self, operation: str, params: Dict[str, Any], data: pd.DataFrame) -> pd.DataFrame:
        """Exécute une opération de transformation"""
        pass

    @abstractmethod
    def supports_operation(self, operation: str) -> bool:
        """Vérifie si l'opération est supportée"""
        pass

    @abstractmethod
    def estimate_cost(self, operation: str, data_size: int) -> float:
        """Estime le coût de l'opération (pour auto-routing)"""
        pass
```

### Implémentations

```python
# internal/transform/pandas_engine.py
class PandasEngine(TransformEngine):
    SUPPORTED_OPS = ['calculate', 'filter', 'clean', 'validate', 'cast']

    def supports_operation(self, operation: str) -> bool:
        return operation in self.SUPPORTED_OPS

    def execute(self, operation: str, params: Dict, data: pd.DataFrame) -> pd.DataFrame:
        if operation == 'calculate':
            return self._calculate(params, data)
        elif operation == 'filter':
            return self._filter(params, data)
        # ...

# internal/transform/duckdb_engine.py
class DuckDBEngine(TransformEngine):
    SUPPORTED_OPS = ['join', 'aggregate', 'window', 'union', 'sql']

    # Implémentation similaire...

# internal/transform/polars_engine.py (futur plugin)
class PolarsEngine(TransformEngine):
    """Alternative à Pandas - plus rapide"""
    SUPPORTED_OPS = ['calculate', 'filter', 'join', 'aggregate']
    # ...
```

### 🔧 Registry pattern pour découverte

```python
# internal/transform/registry.py

class EngineRegistry:
    """Registry pour enregistrer/découvrir des engines"""

    _engines: Dict[str, Type[TransformEngine]] = {}

    @classmethod
    def register(cls, name: str, engine_class: Type[TransformEngine]):
        """Enregistre un engine"""
        cls._engines[name] = engine_class

    @classmethod
    def get(cls, name: str) -> TransformEngine:
        """Récupère un engine"""
        if name not in cls._engines:
            raise ValueError(f"Engine '{name}' not found")
        return cls._engines[name]()

    @classmethod
    def auto_select(cls, operation: str, data_size: int) -> TransformEngine:
        """Sélectionne automatiquement le meilleur engine"""
        candidates = [
            (engine_class(), engine_class().estimate_cost(operation, data_size))
            for engine_class in cls._engines.values()
            if engine_class().supports_operation(operation)
        ]

        if not candidates:
            raise ValueError(f"No engine supports operation '{operation}'")

        # Retourne l'engine avec le coût le plus bas
        return min(candidates, key=lambda x: x[1])[0]

# Enregistrement au démarrage
EngineRegistry.register('pandas', PandasEngine)
EngineRegistry.register('duckdb', DuckDBEngine)
```

---

## 🗄️ 3. Extensibilité des Cache Backends

### ❌ Actuel : Seulement mémoire

```python
# internal/cache/memory.py
```

### ✅ Solution : Interface + Registry

```python
# internal/cache/interface.py

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional

class CacheBackend(ABC):
    """Interface pour backends de cache"""

    @abstractmethod
    def push(self, batch: List[Dict[str, Any]]) -> None:
        """Ajoute un batch au cache"""
        pass

    @abstractmethod
    def pop(self, batch_size: int) -> List[Dict[str, Any]]:
        """Récupère un batch du cache"""
        pass

    @abstractmethod
    def size(self) -> int:
        """Taille actuelle du cache (nombre de lignes)"""
        pass

    @abstractmethod
    def clear(self) -> None:
        """Vide le cache"""
        pass

    @abstractmethod
    def is_full(self) -> bool:
        """Vérifie si le cache est plein"""
        pass
```

### Implémentations multiples

```python
# internal/cache/memory.py
class MemoryCache(CacheBackend):
    """Cache en mémoire (rapide, limité)"""
    def __init__(self, max_size: int = 100000):
        self.max_size = max_size
        self.buffer = []

# internal/cache/disk.py
class DiskCache(CacheBackend):
    """Cache sur disque (lent, illimité)"""
    def __init__(self, temp_dir: str):
        self.temp_dir = temp_dir

# internal/cache/redis.py
class RedisCache(CacheBackend):
    """Cache Redis (distribué, partagé)"""
    def __init__(self, redis_url: str):
        self.redis = redis.from_url(redis_url)

# internal/cache/hybrid.py
class HybridCache(CacheBackend):
    """Cache hybride : mémoire + spill to disk"""
    def __init__(self, memory_cache: CacheBackend, disk_cache: CacheBackend):
        self.hot = memory_cache
        self.cold = disk_cache
```

---

## 🔐 4. Extensibilité des Secrets Managers

### ❌ Actuel : Seulement YAML + ENV

### ✅ Solution : Backend abstrait

```python
# internal/config/secrets_backend.py

from abc import ABC, abstractmethod
from typing import Optional

class SecretBackend(ABC):
    """Interface pour backends de secrets"""

    @abstractmethod
    def get(self, key: str) -> Optional[str]:
        """Récupère un secret"""
        pass

    @abstractmethod
    def set(self, key: str, value: str) -> None:
        """Stocke un secret (pour rotation)"""
        pass

    @abstractmethod
    def delete(self, key: str) -> None:
        """Supprime un secret"""
        pass

    @abstractmethod
    def list_keys(self, prefix: str = "") -> List[str]:
        """Liste les clés disponibles"""
        pass
```

### Implémentations

```python
# internal/config/backends/yaml_backend.py
class YAMLSecretBackend(SecretBackend):
    """Backend YAML (dev/staging)"""
    pass

# internal/config/backends/vault_backend.py
class VaultSecretBackend(SecretBackend):
    """Backend HashiCorp Vault (prod)"""
    def __init__(self, vault_url: str, token: str):
        self.client = hvac.Client(url=vault_url, token=token)

# internal/config/backends/aws_backend.py
class AWSSecretsBackend(SecretBackend):
    """Backend AWS Secrets Manager"""
    def __init__(self, region: str):
        self.client = boto3.client('secretsmanager', region_name=region)

# internal/config/backends/azure_backend.py
class AzureKeyVaultBackend(SecretBackend):
    """Backend Azure Key Vault"""
    pass
```

### Resolver avec fallback chain

```python
# internal/config/secrets.py (modifié)

class SecretResolver:
    def __init__(self, backends: List[SecretBackend]):
        """
        backends ordonnés par priorité
        Ex: [EnvBackend(), VaultBackend(), YAMLBackend()]
        """
        self.backends = backends

    def resolve(self, key: str) -> str:
        """Essaie chaque backend jusqu'à trouver"""
        for backend in self.backends:
            value = backend.get(key)
            if value is not None:
                return value
        raise ValueError(f"Secret '{key}' not found in any backend")
```

---

## 📝 5. Extensibilité des Validateurs DSL

### ❌ Actuel : Validation hardcodée dans parser

### ✅ Solution : Validateurs pluggables

```python
# internal/parser/validators/interface.py

from abc import ABC, abstractmethod
from typing import Any, List

class ValidationError:
    def __init__(self, path: str, message: str):
        self.path = path
        self.message = message

class Validator(ABC):
    """Interface pour validateurs custom"""

    @abstractmethod
    def validate(self, config: Dict[str, Any]) -> List[ValidationError]:
        """Valide une config et retourne les erreurs"""
        pass

# internal/parser/validators/schema_validator.py
class SchemaValidator(Validator):
    """Valide que les colonnes référencées existent"""
    pass

# internal/parser/validators/business_validator.py
class BusinessRulesValidator(Validator):
    """Valide des règles métier custom"""
    def validate(self, config: Dict) -> List[ValidationError]:
        errors = []

        # Exemple : interdire aggregation sans group_by
        for stage in config.get('stages', []):
            if 'aggregate' in stage:
                if not stage['aggregate'].get('by'):
                    errors.append(ValidationError(
                        path=f"stages.{stage.get('name')}",
                        message="Aggregate requires 'by' clause"
                    ))

        return errors
```

### Registry de validateurs

```python
# internal/parser/validation_registry.py

class ValidatorRegistry:
    _validators: List[Validator] = []

    @classmethod
    def register(cls, validator: Validator):
        cls._validators.append(validator)

    @classmethod
    def validate_all(cls, config: Dict) -> List[ValidationError]:
        """Exécute tous les validateurs"""
        all_errors = []
        for validator in cls._validators:
            all_errors.extend(validator.validate(config))
        return all_errors

# Enregistrement
ValidatorRegistry.register(SchemaValidator())
ValidatorRegistry.register(BusinessRulesValidator())
```

---

## 🚨 6. Extensibilité des Error Handlers

### ❌ Actuel : Gestion d'erreur centralisée non pluggable

### ✅ Solution : Error handlers pluggables

```python
# internal/runner/error_handler.py

from abc import ABC, abstractmethod
from typing import Any, Optional

class ErrorContext:
    """Contexte d'une erreur"""
    def __init__(self, job_id: str, step_name: str, row_data: Dict, error: Exception):
        self.job_id = job_id
        self.step_name = step_name
        self.row_data = row_data
        self.error = error

class ErrorHandler(ABC):
    """Interface pour gestion d'erreurs"""

    @abstractmethod
    def handle(self, context: ErrorContext) -> bool:
        """
        Gère une erreur.
        Retourne True si le job doit continuer, False pour abort.
        """
        pass

# internal/runner/handlers/log_handler.py
class LogErrorHandler(ErrorHandler):
    """Log l'erreur et continue"""
    def handle(self, context: ErrorContext) -> bool:
        logger.error(f"Error in {context.step_name}: {context.error}")
        return True

# internal/runner/handlers/skip_handler.py
class SkipRowHandler(ErrorHandler):
    """Skip la ligne en erreur et continue"""
    def handle(self, context: ErrorContext) -> bool:
        logger.warning(f"Skipping row: {context.row_data}")
        return True

# internal/runner/handlers/deadletter_handler.py
class DeadLetterHandler(ErrorHandler):
    """Envoie vers une queue de dead-letter"""
    def __init__(self, deadletter_path: str):
        self.deadletter_path = deadletter_path

    def handle(self, context: ErrorContext) -> bool:
        # Écrit dans un fichier/queue séparé
        with open(self.deadletter_path, 'a') as f:
            f.write(json.dumps({
                'job_id': context.job_id,
                'step': context.step_name,
                'row': context.row_data,
                'error': str(context.error)
            }) + '\n')
        return True

# internal/runner/handlers/retry_handler.py
class RetryHandler(ErrorHandler):
    """Réessaie avec backoff"""
    def __init__(self, max_retries: int = 3, backoff: float = 2.0):
        self.max_retries = max_retries
        self.backoff = backoff
        self.attempts = {}

    def handle(self, context: ErrorContext) -> bool:
        row_id = hash(str(context.row_data))
        attempts = self.attempts.get(row_id, 0)

        if attempts < self.max_retries:
            self.attempts[row_id] = attempts + 1
            time.sleep(self.backoff ** attempts)
            return True  # Réessayer
        else:
            return False  # Abandon
```

---

## 🔄 7. Migration vers Go - Démarche concrète

### Niveaux d'intégration possibles

```
┌─────────────────────────────────────────────────────────────┐
│                    NIVEAU 1 : Wrapper CLI                    │
│  Python reste maître, appelle binaire Go pour tâches lourdes│
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                   NIVEAU 2 : Service gRPC                    │
│   Service Go standalone, Python communique via gRPC/HTTP     │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                  NIVEAU 3 : Shared Library                   │
│     Go compilé en .so/.dll, appelé via ctypes/cffi          │
└─────────────────────────────────────────────────────────────┘
                              ↓
┌─────────────────────────────────────────────────────────────┐
│                NIVEAU 4 : Réécriture complète                │
│          CLI + Engine en Go, Python deprecated               │
└─────────────────────────────────────────────────────────────┘
```

### NIVEAU 1 : Wrapper CLI (Recommandé pour démarrer)

#### Architecture

```python
# internal/transform/go_engine.py

import subprocess
import json
from pathlib import Path

class GoEngine(TransformEngine):
    """Engine qui délègue à un binaire Go"""

    SUPPORTED_OPS = ['join', 'aggregate', 'window']  # Opérations lourdes

    def __init__(self, go_binary_path: str = "./bin/smartetl-go"):
        self.binary = Path(go_binary_path)
        if not self.binary.exists():
            raise FileNotFoundError(f"Go binary not found: {go_binary_path}")

    def execute(self, operation: str, params: Dict, data: pd.DataFrame) -> pd.DataFrame:
        """
        Exécute l'opération via le binaire Go
        Communication via JSON stdin/stdout
        """
        # 1. Sérialiser input
        input_data = {
            'operation': operation,
            'params': params,
            'data': data.to_dict('records')
        }

        # 2. Appeler Go
        result = subprocess.run(
            [str(self.binary), 'transform'],
            input=json.dumps(input_data),
            capture_output=True,
            text=True,
            check=True
        )

        # 3. Désérialiser output
        output_data = json.loads(result.stdout)
        return pd.DataFrame(output_data['data'])
```

#### Binaire Go correspondant

```go
// cmd/smartetl-go/main.go

package main

import (
    "encoding/json"
    "fmt"
    "io/ioutil"
    "os"
)

type TransformRequest struct {
    Operation string                   `json:"operation"`
    Params    map[string]interface{}   `json:"params"`
    Data      []map[string]interface{} `json:"data"`
}

type TransformResponse struct {
    Data []map[string]interface{} `json:"data"`
}

func main() {
    // Lire stdin
    input, _ := ioutil.ReadAll(os.Stdin)

    var req TransformRequest
    json.Unmarshal(input, &req)

    // Exécuter transformation
    result := executeTransform(req.Operation, req.Params, req.Data)

    // Écrire stdout
    resp := TransformResponse{Data: result}
    output, _ := json.Marshal(resp)
    fmt.Println(string(output))
}

func executeTransform(op string, params map[string]interface{}, data []map[string]interface{}) []map[string]interface{} {
    switch op {
    case "join":
        return performJoin(params, data)
    case "aggregate":
        return performAggregate(params, data)
    default:
        return data
    }
}
```

#### Enregistrement dans Registry

```python
# Au démarrage de l'app
if Path("./bin/smartetl-go").exists():
    EngineRegistry.register('go', GoEngine)
    logger.info("Go engine available")
```

### NIVEAU 2 : Service gRPC (Pour production distribuée)

#### Proto definition

```protobuf
// proto/transform.proto

syntax = "proto3";

service TransformService {
    rpc Transform(TransformRequest) returns (TransformResponse);
}

message TransformRequest {
    string operation = 1;
    map<string, string> params = 2;
    bytes data = 3;  // DataFrame sérialisé (Arrow/Parquet)
}

message TransformResponse {
    bytes data = 1;
}
```

#### Client Python

```python
# internal/transform/grpc_engine.py

import grpc
import transform_pb2
import transform_pb2_grpc

class GRPCEngine(TransformEngine):
    def __init__(self, grpc_url: str = "localhost:50051"):
        channel = grpc.insecure_channel(grpc_url)
        self.stub = transform_pb2_grpc.TransformServiceStub(channel)

    def execute(self, operation: str, params: Dict, data: pd.DataFrame) -> pd.DataFrame:
        # Sérialiser avec Arrow (plus rapide que JSON)
        data_bytes = data.to_parquet()

        request = transform_pb2.TransformRequest(
            operation=operation,
            params=params,
            data=data_bytes
        )

        response = self.stub.Transform(request)

        return pd.read_parquet(io.BytesIO(response.data))
```

---

## 📦 8. Remplacement de DuckDB - Démarche

### Pourquoi remplacer ?

- **DataFusion (Rust)** : Plus rapide, moins de RAM
- **Polars** : API Python native, très rapide
- **Apache Arrow** : Pour compatibilité inter-langages

### Architecture pour permettre le swap

```python
# internal/transform/sql_engine_interface.py

from abc import ABC, abstractmethod

class SQLEngine(ABC):
    """Interface pour moteurs SQL"""

    @abstractmethod
    def register_table(self, name: str, data: pd.DataFrame):
        """Enregistre un DataFrame comme table"""
        pass

    @abstractmethod
    def execute_sql(self, query: str) -> pd.DataFrame:
        """Exécute une requête SQL"""
        pass

    @abstractmethod
    def close(self):
        """Ferme les connexions"""
        pass

# internal/transform/duckdb_sql_engine.py
class DuckDBSQLEngine(SQLEngine):
    def __init__(self):
        self.conn = duckdb.connect()

    def register_table(self, name: str, data: pd.DataFrame):
        self.conn.register(name, data)

    def execute_sql(self, query: str) -> pd.DataFrame:
        return self.conn.execute(query).df()

# internal/transform/datafusion_sql_engine.py
class DataFusionSQLEngine(SQLEngine):
    """Alternative à DuckDB via DataFusion (Rust)"""
    def __init__(self):
        import datafusion
        self.ctx = datafusion.SessionContext()

    def register_table(self, name: str, data: pd.DataFrame):
        self.ctx.register_table(name, data)

    def execute_sql(self, query: str) -> pd.DataFrame:
        return self.ctx.sql(query).to_pandas()
```

### Configuration pour choisir l'engine

```yaml
# etl-config.yaml

transform:
  sql_engine: duckdb  # ou datafusion, polars

  # Config spécifique
  duckdb:
    memory_limit: "2GB"
    threads: 4

  datafusion:
    batch_size: 8192
```

---

## 📊 Récapitulatif des points d'extensibilité

### Tableau complet

| #   | Point d'extensibilité | Interface      | Registry         | Config           | Priorité |
| --- | --------------------- | -------------- | ---------------- | ---------------- | -------- |
| 1   | **Connecteurs**       | ✅ `Connector`  | ✅ Auto-discovery | ✅ `type:`        | **P0**   |
| 2   | **Transform Engines** | ⚠️ À créer     | ⚠️ À créer       | ✅ `engine:`      | **P0**   |
| 3   | **Cache Backends**    | ⚠️ À créer     | ⚠️ À créer       | ⚠️ À ajouter     | **P1**   |
| 4   | **Secret Backends**   | ⚠️ À créer     | ⚠️ À créer       | ⚠️ À ajouter     | **P1**   |
| 5   | **Validateurs DSL**   | ⚠️ À créer     | ⚠️ À créer       | N/A              | **P2**   |
| 6   | **Error Handlers**    | ⚠️ À créer     | ⚠️ À créer       | ✅ `error_policy` | **P2**   |
| 7   | **SQL Engines**       | ⚠️ À créer     | ⚠️ À créer       | ⚠️ À ajouter     | **P2**   |
| 8   | **Loggers**           | ⚠️ À créer     | ⚠️ À créer       | ✅ `logging`      | **P3**   |
| 9   | **Go Integration**    | ✅ Via CLI/gRPC | N/A              | N/A              | **P3**   |

---

## 🏗️ Architecture finale avec tous les points d'extensibilité

```
etl-project/
├── etl/                          # API publique
│   ├── engine.py
│   └── types.py
│
├── internal/
│   ├── runner/
│   │   ├── executor.py
│   │   ├── context.py
│   │   └── error_handler.py     # ← NOUVEAU : Error handlers
│   │       ├── interface.py
│   │       ├── log_handler.py
│   │       ├── skip_handler.py
│   │       └── deadletter_handler.py
│   │
│   ├── parser/
│   │   ├── source.py
│   │   ├── destination.py
│   │   ├── transform.py
│   │   └── validators/          # ← NOUVEAU : Validateurs custom
│   │       ├── interface.py
│   │       ├── schema_validator.py
│   │       └── business_validator.py
│   │
│   ├── connector/
│   │   ├── interface.py         # ✅ Déjà prévu
│   │   ├── registry.py          # ← NOUVEAU : Auto-discovery
│   │   ├── mysql.py
│   │   ├── csv.py
│   │   └── plugins/             # ← NOUVEAU : Connecteurs externes
│   │
│   ├── transform/
│   │   ├── interface.py         # ← NOUVEAU : Interface commune
│   │   ├── registry.py          # ← NOUVEAU : Registry engines
│   │   ├── pandas_engine.py
│   │   ├── duckdb_engine.py
│   │   ├── go_engine.py         # ← NOUVEAU : Wrapper Go
│   │   ├── grpc_engine.py       # ← NOUVEAU : Service Go distant
│   │   └── sql_engine/          # ← NOUVEAU : SQL engines swappables
│   │       ├── interface.py
│   │       ├── duckdb_engine.py
│   │       └── datafusion_engine.py
│   │
│   ├── cache/
│   │   ├── interface.py         # ← NOUVEAU : Interface commune
│   │   ├── registry.py          # ← NOUVEAU
│   │   ├── memory.py
│   │   ├── disk.py              # ← NOUVEAU
│   │   ├── redis.py             # ← NOUVEAU
│   │   └── hybrid.py            # ← NOUVEAU
│   │
│   ├── config/
│   │   ├── loader.py
│   │   ├── secrets.py
│   │   └── backends/            # ← NOUVEAU : Secret backends
│   │       ├── interface.py
│   │       ├── yaml_backend.py
│   │       ├── vault_backend.py
│   │       ├── aws_backend.py
│   │       └── azure_backend.py
│   │
│   └── logger/
│       ├── interface.py         # ← NOUVEAU
│       ├── structured.py
│       ├── metrics.py
│       └── backends/            # ← NOUVEAU : Logger backends
│           ├── console.py
│           ├── file.py
│           └── elasticsearch.py
│
├── plugins/                     # ← NOUVEAU : Dossier plugins externes
│   ├── connectors/
│   ├── transforms/
│   └── validators/
│
├── bin/                         # ← NOUVEAU : Binaires Go
│   └── smartetl-go
│
└── examples/
```

---

## 🎯 Recommandations finales

### Phase 1 (MVP) - Priorité P0

1. ✅ **Interface `TransformEngine`** + Registry
2. ✅ **Registry `Connector`** avec auto-discovery
3. ✅ DSL extensible (déjà fait)

### Phase 2 (Production) - Priorité P1

4. ✅ **Interface `CacheBackend`** (memory + disk + hybrid)
5. ✅ **Secret Backends** (YAML → Vault → AWS)
6. ✅ **Error Handlers** pluggables

### Phase 3 (Évolution) - Priorité P2

7. ✅ **Validateurs DSL custom**
8. ✅ **SQL Engine swappable** (DuckDB ↔ DataFusion)
9. ✅ **Go Integration Level 1** (CLI wrapper)

### Phase 4 (Enterprise) - Priorité P3

10. ✅ **Go Integration Level 2** (gRPC service)
11. ✅ **Logger backends** (ElasticSearch, etc.)
12. ✅ **Scheduler integration**

---

## 🔌 Guide : Comment ajouter un plugin

### Exemple : Ajouter un connecteur S3

#### 1. Créer le connecteur

```python
# plugins/connectors/s3_connector.py

from internal.connector.interface import Connector
import boto3
import pandas as pd

class S3Connector(Connector):
    """Connecteur pour AWS S3"""

    def __init__(self, bucket: str, key: str, **aws_config):
        self.bucket = bucket
        self.key = key
        self.s3 = boto3.client('s3', **aws_config)

    def connect(self):
        # Tester l'accès au bucket
        self.s3.head_bucket(Bucket=self.bucket)

    def test_connection(self) -> bool:
        try:
            self.connect()
            return True
        except:
            return False

    def read_batches(self, batch_size: int):
        # Télécharger fichier depuis S3
        obj = self.s3.get_object(Bucket=self.bucket, Key=self.key)
        df = pd.read_csv(obj['Body'])

        # Yield par batch
        for i in range(0, len(df), batch_size):
            yield df.iloc[i:i+batch_size].to_dict('records')

    def write_batches(self, batches, mode: str):
        # Implémenter l'écriture vers S3
        pass

    def close(self):
        pass
```

#### 2. Enregistrer le connecteur

```python
# plugins/connectors/__init__.py

from internal.connector.registry import ConnectorRegistry
from .s3_connector import S3Connector

# Auto-enregistrement au chargement du module
ConnectorRegistry.register('s3', S3Connector)
```

#### 3. Utiliser dans la config

```yaml
# sources.yaml

sources:
  data_s3:
    type: s3  # ← Automatiquement découvert
    bucket: my-bucket
    key: data/file.csv
    aws_access_key_id: ${SECRET.aws_key}
    aws_secret_access_key: ${SECRET.aws_secret}
```

---

## 🚀 Guide : Migration progressive vers Go

### Stratégie recommandée : Remplacement par composant

```
┌──────────────────────────────────────────────────────────────┐
│ PHASE 1 : Identifier les bottlenecks                         │
│ - Profiler le code Python                                    │
│ - Identifier top 3 opérations lentes (ex: joins larges)      │
└──────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────┐
│ PHASE 2 : Implémenter en Go (Level 1 - CLI wrapper)          │
│ - Créer binaire Go pour ces 3 opérations                     │
│ - Python appelle Go via subprocess                           │
│ - Comparer performances : si gain > 3x → valider             │
└──────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────┐
│ PHASE 3 : Migrer vers gRPC service (Level 2)                 │
│ - Si besoin distribué : Go devient service standalone        │
│ - Python communique via gRPC                                 │
│ - Permet scaling horizontal du service Go                    │
└──────────────────────────────────────────────────────────────┘
                              ↓
┌──────────────────────────────────────────────────────────────┐
│ PHASE 4 : Évaluer réécriture complète                        │
│ - Si 80% du code est en Go → considérer réécriture CLI       │
│ - Sinon : garder hybride Python (orchestration) + Go (exec)  │
└──────────────────────────────────────────────────────────────┘
```

### Exemple concret : Migrer l'opération JOIN

#### Avant (Python pur)

```yaml
- name: join_data
  join:
    left: orders
    right: customers
    on: { left: customer_id, right: id }
```

Parser détecte → utilise `duckdb_engine.py`

#### Après (avec Go wrapper)

```python
# Configuration pour activer Go
# etl-config.yaml
transform:
  prefer_go: true  # Active Go pour opérations supportées
  go_binary: ./bin/smartetl-go

# Parser détecte → utilise `go_engine.py` au lieu de DuckDB
# Utilisateur ne change RIEN dans son pipeline.yaml !
```

Le parser détecte automatiquement :

1. Go disponible ? (`./bin/smartetl-go` existe ?)
2. Opération supportée par Go ? (join → oui)
3. → Route vers `GoEngine` au lieu de `DuckDBEngine`

**Zéro changement pour l'utilisateur ! ✅**

---

## 📐 Pattern de conception recommandé : Plugin System

### Entry points Python (setuptools)

```python
# setup.py d'un plugin externe

from setuptools import setup

setup(
    name='smartetl-plugin-snowflake',
    version='1.0.0',
    packages=['smartetl_snowflake'],
    entry_points={
        'smartetl.connectors': [
            'snowflake = smartetl_snowflake.connector:SnowflakeConnector',
        ],
        'smartetl.validators': [
            'pii_validator = smartetl_snowflake.validators:PIIValidator',
        ]
    }
)
```

### Découverte automatique au démarrage

```python
# internal/plugin_loader.py

import pkg_resources

def load_plugins():
    """Charge tous les plugins installés"""

    # Charger connecteurs
    for entry_point in pkg_resources.iter_entry_points('smartetl.connectors'):
        connector_class = entry_point.load()
        ConnectorRegistry.register(entry_point.name, connector_class)
        logger.info(f"Loaded connector plugin: {entry_point.name}")

    # Charger validateurs
    for entry_point in pkg_resources.iter_entry_points('smartetl.validators'):
        validator_class = entry_point.load()
        ValidatorRegistry.register(validator_class())
        logger.info(f"Loaded validator plugin: {entry_point.name}")

# Appelé au démarrage de l'app
# cli/main.py
load_plugins()
```

### Installation d'un plugin

```bash
# Utilisateur installe un plugin
pip install smartetl-plugin-snowflake

# Plugin automatiquement découvert au prochain lancement
etl run --job my_pipeline

# Log affiche :
# [INFO] Loaded connector plugin: snowflake
```

---

## ✅ Checklist d'extensibilité finale

### Pour chaque composant, vérifier :

- [ ] **Interface abstraite définie** (ABC)
- [ ] **Registry pour découverte** automatique
- [ ] **Configuration YAML** pour sélection
- [ ] **Tests unitaires** sur l'interface
- [ ] **Documentation** d'extension
- [ ] **Exemple de plugin** dans `/examples/plugins/`

---

## 🎯 Conclusion

### Points d'extensibilité identifiés : **12**

1. ✅ Connecteurs (déjà prévu)
2. ⚠️ Transform Engines (**à ajouter**)
3. ⚠️ Cache Backends (**à ajouter**)
4. ⚠️ Secret Backends (**à ajouter**)
5. ⚠️ Validateurs DSL (**à ajouter**)
6. ⚠️ Error Handlers (**à ajouter**)
7. ⚠️ SQL Engines (**à ajouter**)
8. ⚠️ Logger Backends (**à ajouter**)
9. ✅ DSL Operations (déjà extensible via SQL/Python)
10. 📋 Go Integration (démarche définie)
11. 📋 Plugin System (entry points)
12. 📋 Schedulers (Phase 4)

### Actions immédiates recommandées

**Pour MVP (Phase 1) :**

1. Créer `internal/transform/interface.py` + Registry
2. Créer `internal/connector/registry.py`
3. Documenter comment ajouter un plugin

**Pour Production (Phase 2) :**
4. Créer `internal/cache/interface.py` + implémentations
5. Créer `internal/config/backends/` pour secrets
6. Créer `internal/runner/error_handler/`

**Cette architecture garantit l'extensibilité maximale sans complexité excessive ! 🎯**
