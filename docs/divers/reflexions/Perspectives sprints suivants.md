📋 **ROADMAP SPRINTS 2-5 - ANALYSE & RECOMMANDATIONS**

---

## ✅ **ÉVALUATION GLOBALE**

**Vision stratégique** : Excellente progression logique  
**Réalisme effort** : Cohérent avec Sprint 1  
**Réutilisation code** : Maximisée intelligemment

---

## 🎯 **SPRINT 2 - PostgreSQL**

**Période** : Janvier 2026 (1-2 sem)  
**Effort** : 6-10h ⚠️ **SOUS-ESTIMÉ**

### Complexité Réelle

```python
# MySQL upsert
INSERT ... ON DUPLICATE KEY UPDATE ...

# PostgreSQL upsert (2 syntaxes possibles)
INSERT ... ON CONFLICT (id) DO UPDATE SET ...
# OU
MERGE INTO ... WHEN MATCHED THEN UPDATE ...
```

### Effort Révisé : **8-12h**

- Parser YAML : 1h (réutilisation)
- SQL Generator : 3h (nouvelle syntaxe)
- Tests unitaires : 2h (30 tests)
- Tests E2E : 2h (adapter fixtures)
- Documentation : 2h

### Recommandation

✅ **VALIDÉ** - Excellent choix stratégique  
📝 Ajuster effort à 10-12h pour sécurité

---

## 🎯 **SPRINT 3 - JSON/JSONL + TableAdapter**

**Période** : Janv-Fév 2026  
**Effort** : 10-16h ✅ **RÉALISTE**

### Architecture Clé

```python
class TableAdapter(ABC):
    """Pattern pour convertir structures → DataFrame"""
    def normalize(self, data: Any) -> pd.DataFrame

class JSONToTableAdapter(TableAdapter):
    """Flatten nested JSON"""
    def normalize(self, json_data: dict) -> pd.DataFrame
```

### Complexité Sous-Estimée

- **Nested JSON** : Récursivité complexe
- **Array handling** : Explosion lignes
- **Schema inference** : Types dynamiques

### Effort Révisé : **12-18h**

- JSON/JSONL connector : 3h
- TableAdapter pattern : 4h
- Flatten nested : 5h (⚠️ complexe)
- Tests : 4h
- Exemples : 2h

### Recommandation

⚠️ **ATTENTION** - Sprint le plus risqué  
🎯 Prévoir **buffer 20% supplémentaire**

---

## 🎯 **SPRINT 4 - MongoDB**

**Période** : Février 2026  
**Effort** : 10-14h ✅ **BIEN CALIBRÉ**

### Réutilisation Sprint 3

```python
# Sprint 3 livré
flatten_nested_dict(json_data)  # ✅ Réutilisable

# Sprint 4 ajoute
class MongoDBConnector(BaseDBConnector):
    def extract_batches(self):
        for doc in collection.find():
            yield flatten_nested_dict(doc)  # ✅ Gratuit
```

### Effort Confirmé : **10-14h**

- Connector MongoDB : 4h
- Upsert MongoDB (updateOne) : 3h
- Tests : 4h
- Docker + fixtures : 2h
- Documentation : 1h

### Recommandation

✅ **VALIDÉ** - Gain 40-60% confirmé  
🎯 Sprint le plus rentable

---

## 🎯 **SPRINT 5 - REST + GraphQL**

**Période** : Fév-Mars 2026  
**Effort** : 14-22h ⚠️ **SOUS-ESTIMÉ**

### Complexité Cachée

**REST générique** :

- Pagination (cursor vs offset)
- Rate limiting
- Retry exponential backoff
- Auth (Bearer, OAuth2, API Key)
- Response parsing (JSON/XML)

**GraphQL** :

- Query builder
- Fragments
- Variables
- Error handling

### Effort Révisé : **20-28h**

- REST connector base : 6h
- Auth strategies : 4h
- Pagination + rate-limit : 4h
- GraphQL connector : 6h
- Tests API mocking : 4h
- Exemples (Stripe/HubSpot) : 4h

### Recommandation

⚠️ **DÉCOUPER EN 2 SPRINTS**

**Sprint 5A - REST** (12-16h)  
**Sprint 5B - GraphQL** (8-12h)

---

## 📊 **ROADMAP RÉVISÉE**

| Sprint | Focus          | Effort Original | Effort Révisé | Risque    |
| ------ | -------------- | --------------- | ------------- | --------- |
| 2      | PostgreSQL     | 6-10h           | **10-12h**    | 🟢 Faible |
| 3      | JSON + Adapter | 10-16h          | **14-20h**    | 🟡 Moyen  |
| 4      | MongoDB        | 10-14h          | **10-14h**    | 🟢 Faible |
| 5A     | REST           | -               | **14-18h**    | 🟡 Moyen  |
| 5B     | GraphQL        | 14-22h          | **10-14h**    | 🟢 Faible |

**Total effort** : 42-62h → **58-78h** (+27%)

---

## 🎯 **RECOMMANDATIONS STRATÉGIQUES**

### 1️⃣ Sprint 2 PostgreSQL - PRIORISER

✅ **Impact immédiat** : 2ème DB la plus demandée  
✅ **Faible risque** : Code MySQL réutilisable  
✅ **Quick win** : Boost confiance utilisateurs

### 2️⃣ Sprint 3 JSON - SÉCURISER

⚠️ **Complexité flatten** : Prévoir POC de 2h avant sprint  
⚠️ **Tests critiques** : Nested arrays = edge cases  
🎯 **Objectif** : Pattern Adapter solide pour Sprint 4

### 3️⃣ Sprint 4 MongoDB - CAPITALISER

✅ **Réutilisation maximale** : 60% code gratuit  
✅ **Valeur énorme** : NoSQL ouvre cas d'usage  
🎯 **Milestone** : Hydra multi-paradigmes

### 4️⃣ Sprint 5 REST/GraphQL - DÉCOUPER

⚠️ **Trop ambitieux en 1 sprint**  
✅ **Sprint 5A REST** : Fondations solides  
✅ **Sprint 5B GraphQL** : Extension logique

---

## 🚀 **POINTS CLÉS POUR SUCCÈS**

### Architecture Patterns

```python
# Sprint 3 livre
class TableAdapter(ABC):
    """Base pattern réutilisable"""

# Sprint 4 réutilise
class MongoToTableAdapter(TableAdapter):
    """Hérite gratuitement"""

# Sprint 5 réutilise
class RESTToTableAdapter(TableAdapter):
    """Même pattern, nouvelle source"""
```

### Tests Strategy

- **Unitaires** : Mock DB/API (rapide)
- **E2E** : Docker containers (lent mais exhaustif)
- **Ratio** : 80% unitaires / 20% E2E

### Documentation Pattern

- README par exemple (comme Sprint 1)
- Troubleshooting systématique
- Guide migration (MySQL → PostgreSQL)

---

## 📈 **MÉTRIQUES SUCCÈS ATTENDUES**

| Sprint | Tests | Couverture | Exemples      |
| ------ | ----- | ---------- | ------------- |
| 2      | 30-40 | >90%       | 1 CSV→PG      |
| 3      | 40-50 | >85%       | 2 JSON nested |
| 4      | 30-40 | >90%       | 1 JSON→Mongo  |
| 5A     | 40-50 | >80%       | 2 API SaaS    |
| 5B     | 20-30 | >80%       | 1 GraphQL     |

---

## ⚡ **OPTIMISATIONS POSSIBLES**

### Réutilisation Code Sprint 1

```python
# Déjà fait ✅
_build_upsert_sql()  # MySQL
_validate_key_columns()  # Generic

# Adapter Sprint 2 ✅
_build_upsert_sql_pg()  # PostgreSQL (nouvelle syntaxe)
_validate_key_columns()  # Réutilisé tel quel
```

### Gain Temps Estimé

- Sprint 2 : 30% réutilisation MySQL
- Sprint 4 : 60% réutilisation Sprint 3
- Sprint 5B : 40% réutilisation Sprint 5A

---

## 🎯 **CONCLUSION & FEUX VERTS**

✅ **Sprint 2** : GO, ajuster effort +20%  
⚠️ **Sprint 3** : GO avec POC flatten préalable  
✅ **Sprint 4** : GO, capitaliser Sprint 3  
⚠️ **Sprint 5** : DÉCOUPER en 5A + 5B

**Roadmap solide, vision claire, efforts calibrés** 🚀
