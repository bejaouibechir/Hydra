# Piloter Hydra ETL depuis Claude Code avec le serveur MCP

**Snowflake + MySQL → jointure, sélection, filtre, tri → PostgreSQL, sans écrire une ligne de YAML.**

Les commandes d'un entrepôt Snowflake (jeu TPC-H officiel) sont croisées avec le CRM de l'entreprise (MySQL dans Docker). On garde les clients Gold et Platinum et leurs commandes de plus de 400 000, triées de la plus grosse à la plus petite, et on charge le résultat dans PostgreSQL. Claude Code fait tout à travers le serveur MCP de Hydra ETL.

Prérequis : Windows + PowerShell, Python 3.10+, Docker Desktop, Claude Code, un compte Snowflake (l'essai gratuit suffit), votre paire de clés RSA.

> **Règle d'or** : à partir de l'étape 1, toutes les commandes se lancent depuis `D:\mcp-demo`, y compris `claude`. Hydra cherche le projet et ses secrets dans le dossier courant.

---

## 1. Installer Hydra ETL et créer le projet

```powershell
pip install "hydra-etl[mcp,snowflake,mysql,postgres]"
hdrctl init D:\mcp-demo
cd D:\mcp-demo
```

`D:\mcp-demo` ne doit pas exister, ou doit être vide.

## 2. Lancer MySQL et PostgreSQL

```powershell
docker run -d --name hydra-mysql -e MYSQL_ROOT_PASSWORD=root -e MYSQL_DATABASE=crm -e MYSQL_USER=hydra -e MYSQL_PASSWORD=hydra -p 3306:3306 mysql:8.4
docker run -d --name hydra-pg -e POSTGRES_USER=hydra -e POSTGRES_PASSWORD=hydra -e POSTGRES_DB=analytics -p 5432:5432 postgres:16
```

Une vingtaine de secondes plus tard, remplissez le CRM (150 000 clients) :

```powershell
@'
USE crm;
CREATE TABLE clients (custkey INT PRIMARY KEY, client_name VARCHAR(40), account_manager VARCHAR(40), tier VARCHAR(10), country VARCHAR(30));
SET SESSION cte_max_recursion_depth = 200000;
INSERT INTO clients
WITH RECURSIVE n(i) AS (SELECT 1 UNION ALL SELECT i + 1 FROM n WHERE i < 150000)
SELECT i, CONCAT('Client#', LPAD(i, 9, '0')),
       ELT(1 + i % 5, 'Sarah Martin', 'Karim Haddad', 'Lucia Romero', 'Tom Becker', 'Ines Dupont'),
       CASE WHEN i % 20 = 0 THEN 'Platinum' WHEN i % 7 = 0 THEN 'Gold' WHEN i % 3 = 0 THEN 'Silver' ELSE 'Bronze' END,
       ELT(1 + i % 6, 'France', 'Germany', 'Spain', 'Tunisia', 'Canada', 'Japan')
FROM n;
'@ | docker exec -i hydra-mysql mysql -uroot -proot
```

Vérification :

```powershell
docker exec hydra-mysql mysql -uhydra -phydra crm -e "SELECT COUNT(*) FROM clients"
```

→ `150000`. Les numéros `custkey` (1 à 150 000) sont ceux des clients TPC-H de Snowflake : la jointure trouvera ses correspondances.

## 3. Donner accès à Snowflake avec votre clé

Dans Snowsight, en `ACCOUNTADMIN` :

```sql
CREATE ROLE IF NOT EXISTS HYDRA_DEMO_ROLE;
GRANT USAGE ON WAREHOUSE COMPUTE_WH TO ROLE HYDRA_DEMO_ROLE;
GRANT IMPORTED PRIVILEGES ON DATABASE SNOWFLAKE_SAMPLE_DATA TO ROLE HYDRA_DEMO_ROLE;
CREATE USER IF NOT EXISTS HYDRA_DEMO TYPE = SERVICE DEFAULT_ROLE = HYDRA_DEMO_ROLE DEFAULT_WAREHOUSE = COMPUTE_WH;
GRANT ROLE HYDRA_DEMO_ROLE TO USER HYDRA_DEMO;
ALTER USER HYDRA_DEMO SET RSA_PUBLIC_KEY = 'MIIBIjANBgkqh...';  -- votre clé publique, sans les lignes BEGIN/END
SELECT CURRENT_ORGANIZATION_NAME() || '-' || CURRENT_ACCOUNT_NAME();  -- identifiant du compte
```

## 4. Enregistrer les secrets

Depuis `D:\mcp-demo`, chaque commande demande la valeur au clavier (saisie masquée, demandée deux fois) :

```powershell
hdrctl secret set MYSQL_PASSWORD        # hydra
hdrctl secret set PG_PASSWORD           # hydra
hdrctl secret set SNOWFLAKE_ACCOUNT     # MONORG-MONCOMPTE (résultat du SELECT de l'étape 3)
hdrctl secret set SNOWFLAKE_KEY_FILE    # chemin de la clé privée, avec des / : D:/keys/rsa_key.p8
hdrctl secret list
```

`hdrctl secret list` doit afficher `Secrets of mcp-demo` et les 4 noms. Les valeurs ne sont jamais affichées, ni à vous ni à Claude.

## 5. Brancher Hydra ETL à Claude Code

```powershell
claude mcp add hydra-etl -- hydra-mcp
claude
```

Dans Claude Code, tapez `/mcp` : `hydra-etl` doit être « connected ».

---

## 6. La démo : 5 prompts

**1. Découverte**

> Qu'est-ce que Hydra ETL sait lire et écrire, et quelles transformations propose-t-il ?

**2. Le job**

> Crée le job Hydra ETL `jobs/vip_orders` :
> 
> - source : les commandes Snowflake de `SNOWFLAKE_SAMPLE_DATA.TPCH_SF1.ORDERS` depuis le 1er janvier 1998, colonnes en minuscules. Utilisateur HYDRA_DEMO, rôle HYDRA_DEMO_ROLE, warehouse COMPUTE_WH, authentification par clé ; compte et chemin de la clé dans les secrets SNOWFLAKE_ACCOUNT et SNOWFLAKE_KEY_FILE ;
> - jointure avec la table `clients` du MySQL local (127.0.0.1:3306, base crm, utilisateur hydra, secret MYSQL_PASSWORD) sur `o_custkey` = `custkey` ;
> - garde o_orderkey, o_orderdate, o_orderpriority, o_totalprice, client_name, tier, country, account_manager ;
> - seulement les clients Gold et Platinum avec une commande de plus de 400 000 ;
> - tri par montant décroissant ;
> - chargement dans la table `vip_big_orders` du PostgreSQL local (127.0.0.1:5432, base analytics, utilisateur hydra, secret PG_PASSWORD), en remplaçant son contenu.

Claude Code écrit le job, Hydra le valide avant de l'enregistrer.

**3. Le contrôle**

> Vérifie que le job fait bien ce que j'ai demandé.

**4. L'exécution**

> Lance le job.

Claude Code demande la permission : on autorise à l'écran, le journal affiche lignes lues, lignes écrites et durée.

**5. Changer d'avis en direct**

> Seulement les clients Platinum, au-dessus de 450 000. Modifie le job, relance-le et montre-moi les 10 plus grosses commandes dans PostgreSQL.

---

## Rejouer le tutoriel de zéro

```powershell
docker rm -f hydra-mysql hydra-pg
cd D:\mcp-demo
claude mcp remove hydra-etl
cd D:\
Remove-Item -Recurse -Force D:\mcp-demo
```

Puis reprendre à l'étape 1.

## En cas de problème

| Symptôme                                 | Solution                                                                                                                                                                                                                        |
| ---------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| `hydra-mcp` introuvable                  | Le dossier `Scripts` de Python n'est pas dans le PATH : réinstallez Python en cochant « Add to PATH »                                                                                                                           |
| `hdrctl init` refuse le dossier          | `D:\mcp-demo` existe déjà et n'est pas vide : voir « Rejouer le tutoriel de zéro »                                                                                                                                              |
| `docker run` : nom ou port déjà utilisé  | Un ancien conteneur existe : `docker rm -f hydra-mysql hydra-pg`, ou arrêtez celui qui occupe le port (`docker ps --filter publish=3306`)                                                                                       |
| MySQL : `Access denied for user 'hydra'` | Claude ou `hdrctl` n'ont pas été lancés depuis `D:\mcp-demo` : `hdrctl secret list` doit y afficher les 4 secrets. Une variable d'environnement `MYSQL_PASSWORD` passe aussi avant le secret : `Remove-Item Env:MYSQL_PASSWORD` |
| Le job est créé hors de `jobs\`          | Claude Code a été lancé hors de `D:\mcp-demo`                                                                                                                                                                                   |
| Snowflake : compte inconnu               | `SNOWFLAKE_ACCOUNT` au format `ORGNAME-ACCOUNTNAME`, sans `https://`                                                                                                                                                            |
| Snowflake : `JWT token is invalid`       | Clé publique non posée sur HYDRA_DEMO, ou clé privée différente                                                                                                                                                                 |
| Erreur de lecture de la clé              | La clé doit commencer par `-----BEGIN PRIVATE KEY-----` ; sinon : `openssl pkcs8 -topk8 -in rsa_key.pem -out rsa_key.p8 -nocrypt`                                                                                               |
| `SNOWFLAKE_SAMPLE_DATA` absente          | `CREATE DATABASE SNOWFLAKE_SAMPLE_DATA FROM SHARE SFC_SAMPLES.SAMPLE_DATA;`                                                                                                                                                     |
