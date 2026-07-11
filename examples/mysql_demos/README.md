# Démos MySQL/MariaDB - Hydra (Étape 8)

## 📦 Prérequis

1. **Docker** installé et démarré
2. **Python 3.10+** avec les dépendances Hydra installées
3. **Fichier .env** configuré (copier `.env.example` -> `.env`)

## 🚀 Démarrage des Conteneurs

```bash
# Depuis le dossier tests/docker/
cd tests/docker
docker-compose -f docker-compose.test.yml up -d

# Vérifier que les conteneurs sont healthy
docker ps
```

## 🎯 Exécution des Démos

### Démo 1 : MySQL -> CSV

```bash
cd examples/mysql_demos/mysql_to_csv
hydra run .
cat data/employees_export.csv
```

### Démo 2 : CSV -> MySQL

```bash
cd examples/mysql_demos/csv_to_mysql
hydra run .
docker exec -it hydra_mysql_test mysql -uhydra -phydra hydra_test -e "SELECT * FROM employees;"
```

### Démo 3 : MySQL -> MySQL (vers MariaDB)

```bash
cd examples/mysql_demos/mysql_to_mysql
hydra run .
docker exec -it hydra_mariadb_test mariadb -uhydra -phydra hydra_test -e "SELECT * FROM employees;"
```

## 🔧 Configuration

Copier `.env.example` -> `.env` :

```bash
copy .env.example .env
```

## 🛑 Arrêt des Conteneurs

```bash
cd tests/docker
docker-compose -f docker-compose.test.yml down
```

## 📚 Sécurité

✅ Tous les fichiers YAML utilisent `${ENV:...}` pour les secrets
✅ Pas de credentials en dur
✅ Mot de passe masqué dans les logs

## 🎓 Prochaines Étapes

- Étape 9 : Tests d'intégration automatisés
- Étape 10 : Support incrémental
- Étape 11 : Mode upsert
