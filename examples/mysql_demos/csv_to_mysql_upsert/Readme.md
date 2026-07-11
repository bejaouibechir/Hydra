# Exemple : CSV → MySQL Upsert

Démontre le mode `upsert` pour synchroniser des données CSV vers MySQL.

## 🎯 Objectif

**Mode Upsert** : INSERT si nouvelle ligne, UPDATE si clé existe déjà.

Cas d'usage :
- Synchroniser données depuis fichier export
- Mettre à jour catalogue produits
- Rafraîchir données employés

---

## 📁 Structure

```
csv_to_mysql_upsert/
├── data/
│   ├── employees.csv         # Données initiales (5 employés)
│   └── employees_update.csv  # Mise à jour (3 lignes : 2 updates + 1 insert)
├── sources.yaml              # Source CSV
├── destinations.yaml         # Destination MySQL (mode upsert)
├── pipeline.yaml             # Pipeline
└── README.md
```

---

## 🚀 Prérequis

1. **MySQL démarré** :
   ```bash
   docker ps | grep hydra_mysql_test
   ```

2. **Variables d'environnement** (.env à la racine) :
   ```bash
   MYSQL_HOST=127.0.0.1
   MYSQL_PORT=3307
   MYSQL_USER=hydra
   MYSQL_PASSWORD=hydra
   MYSQL_DATABASE=hydra_test
   ```

3. **Table MySQL créée** :
   ```sql
   CREATE TABLE employees (
       id INT PRIMARY KEY,
       name VARCHAR(100) NOT NULL,
       email VARCHAR(100),
       department VARCHAR(50),
       salary DECIMAL(10, 2)
   );
   ```

---

## 📝 Étape 1 : Insertion Initiale

**Lancer l'import initial** :

```bash
cd examples/mysql_demos/csv_to_mysql_upsert
python -m cli.main .
```

**Résultat attendu** :
```
✅ Job completed successfully
📊 Rows: 5 in → 5 out
```

**Vérifier dans MySQL** :
```bash
docker exec -it hydra_mysql_test mysql -u hydra -phydra hydra_test \
  -e "SELECT * FROM employees ORDER BY id;"
```

**Données en DB** :
```
+----+----------------+---------------------------+-------------+----------+
| id | name           | email                     | department  | salary   |
+----+----------------+---------------------------+-------------+----------+
|  1 | Alice Johnson  | alice.johnson@example.com | Engineering | 75000.00 |
|  2 | Bob Smith      | bob.smith@example.com     | Sales       | 65000.00 |
|  3 | Charlie Brown  | charlie.brown@example.com | Marketing   | 60000.00 |
|  4 | Diana Prince   | diana.prince@example.com  | Engineering | 80000.00 |
|  5 | Eve Davis      | eve.davis@example.com     | HR          | 55000.00 |
+----+----------------+---------------------------+-------------+----------+
```

---

## 🔄 Étape 2 : Upsert (Update + Insert)

**Modifier source pour utiliser employees_update.csv** :

Éditer `sources.yaml` :
```yaml
extract:
  table: data/employees_update.csv  # ← Changement
```

**Lancer l'upsert** :

```bash
python -m cli.main .
```

**Résultat attendu** :
```
✅ Job completed successfully
📊 Rows: 3 in → 3 out
```

**Vérifier résultat** :

```bash
docker exec -it hydra_mysql_test mysql -u hydra -phydra hydra_test \
  -e "SELECT * FROM employees ORDER BY id;"
```

**Données après upsert** :
```
+----+----------------+---------------------------+-------------+----------+
| id | name           | email                     | department  | salary   |
+----+----------------+---------------------------+-------------+----------+
|  1 | Alice Johnson  | alice.new@example.com     | Engineering | 85000.00 | ← UPDATE
|  2 | Bob Smith      | bob.smith@example.com     | Sales       | 65000.00 |
|  3 | Charlie Brown  | charlie.brown@example.com | Sales       | 70000.00 | ← UPDATE
|  4 | Diana Prince   | diana.prince@example.com  | Engineering | 80000.00 |
|  5 | Eve Davis      | eve.davis@example.com     | HR          | 55000.00 |
|  6 | Frank Miller   | frank.miller@example.com  | Engineering | 78000.00 | ← INSERT
+----+----------------+---------------------------+-------------+----------+
```

**Changements observés** :
- ✅ **id=1** : Email et salaire mis à jour
- ✅ **id=3** : Département et salaire mis à jour
- ✅ **id=6** : Nouvel employé inséré
- ✅ **id=2,4,5** : Inchangés (pas dans CSV update)

---

## 🔑 Points Clés

### Configuration Upsert

```yaml
# destinations.yaml
load:
  table: employees
  mode: upsert      # ← Mode upsert
  key: [id]         # ← Colonne clé primaire
```

**Comment ça marche** :
1. Hydra génère SQL : `INSERT ... ON DUPLICATE KEY UPDATE ...`
2. MySQL vérifie si `id` existe
3. Si existe → UPDATE les autres colonnes
4. Sinon → INSERT nouvelle ligne

### Clés Composites

Pour clé composite (ex: region + product_id) :

```yaml
load:
  table: sales
  mode: upsert
  key: [region, product_id]  # Clé composite
```

---

## 🧹 Nettoyage

**Supprimer la table** :

```bash
docker exec -it hydra_mysql_test mysql -u hydra -phydra hydra_test \
  -e "DROP TABLE IF EXISTS employees;"
```

---

## 📊 Comparaison Modes

| Mode | Comportement | Usage |
|------|--------------|-------|
| `append` | INSERT seulement | Logs, événements |
| `replace` | TRUNCATE puis INSERT | Snapshot quotidien |
| `upsert` | INSERT ou UPDATE | Synchronisation incrémentale |

---

## ✅ DoD Backlog 4.1 Validé

- ✅ Exemple complet fonctionnel
- ✅ Données CSV réalistes
- ✅ Documentation claire
- ✅ Fonctionne via CLI
- ✅ Démontre INSERT + UPDATE

---

**Prochaine étape** : Essayez avec vos propres données !