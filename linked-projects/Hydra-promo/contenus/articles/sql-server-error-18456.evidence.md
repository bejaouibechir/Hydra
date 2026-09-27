# Registre des preuves — sql-server-error-18456

Vérifié le 26/09/2026. Source de l'expérience : tests du connecteur SQL Server du 23/09/2026
(`suivi/journal.md`, commits Hydra `21fe2d8`, `0913106`, `tests/test_e2e_sqlserver.py`).

## Intention

- Requête centrale : « sql server error 18456 » / « login failed for user 18456 state 38 ».
- Intention : diagnostic (dépanner maintenant). Public : développeurs .NET/Python/devops qui se connectent à SQL Server hors SSMS.
- Fan-out CORE : que veut dire 18456 ; où lire l'état ; que signifie chaque état ; base manquante ; login sans user ; instance nommée ; conteneur Docker.
- SUPPORTING : admin Windows ≠ sysadmin ; SSRP. OUT_OF_SCOPE : Azure SQL / Entra ID, Kerberos.

## Registre

| ID | Information | Type | Source | Statut |
|---|---|---|---|---|
| E1 | Le message client masque volontairement la cause ; l'état réel est dans le log serveur (citation exacte) | FACT | learn.microsoft.com … mssqlserver-18456-database-engine-error | OK |
| E2 | États 2/5, 6, 7, 8, 11/12, 38/46, 58 et leurs descriptions | FACT | idem | OK |
| E3 | ~~État 40 = base par défaut~~, ~~2 = distant / 5 = local~~, ~~11 = contrôleur de domaine~~, ~~12 = jeton~~ | UNVERIFIED | absents de la doc Microsoft | **RETIRÉ** (étaient dans la v1) |
| E4 | « Le client voit toujours State 1 » | UNVERIFIED sous cette forme | la doc dit « cache la nature », pas « toujours 1 » | **REFORMULÉ** |
| E5 | 18456 State 38 causé par une base inexistante, CREATE DATABASE raté en amont | EXPERIENCE | journal 23/09 (obstacle 4) | OK |
| E6 | Login sans user dans la base → 18456 | EXPERIENCE | journal 23/09 (obstacle 3) ; numéro d'état non consigné | OK, **sans** affirmer l'état |
| E7 | BUILTIN\Administrators plus sysadmin par défaut depuis 2008 (citation exacte) | FACT | learn.microsoft.com … cc280562 (2008 R2 security changes) | OK |
| E8 | Instances nommées en ports dynamiques ; SQL Browser sur UDP 1434 répond le port (citations) | FACT | learn.microsoft.com … sql-server-browser-service | OK |
| E9 | FreeTDS « default port 1433 despite any ports » (citation de la v1) | **FAUX / non trouvé** | la doc FreeTDS dit l'inverse : `server\instance` → requête UDP 1434 | **RETIRÉ** |
| E10 | Via pymssql, `MACHINE\INSTANCE` sans port → 20009, instance absente du message | EXPERIENCE | commit `21fe2d8`, docstring e2e | OK, cause non isolée — dit dans le texte |
| E11 | SSRP : octet 0x04 + nom d'instance, réponse `clé;valeur` terminée par `;;` | FACT (code testé) + spec MC-SQLR | `sqlserver_connector.py`, commit `0913106` | OK |
| E12 | Bug de parsing révélé par un test unitaire à deux instances | EXPERIENCE | commit `0913106` | OK (v1 laissait croire à un incident réel : corrigé) |
| E13 | `/opt/mssql-tools/bin` en voie de retrait, `/opt/mssql-tools18/bin` depuis 2022 CU14 (citation) | FACT | learn.microsoft.com … quickstart-install-connect-docker | OK |
| E14 | « Sur plusieurs images les outils ne sont pas livrés du tout », « flot d'issues GitHub » | UNVERIFIED | aucune source ; contredit par notre propre docstring e2e | **RETIRÉ** |
| E15 | `-C` = faire confiance au certificat sans validation (citation) | FACT | learn.microsoft.com … sqlcmd-utility | OK |
| E16 | CREATE DATABASE interdit dans une transaction (citation) | FACT | learn.microsoft.com … create-database-transact-sql | OK |
| E17 | Environnements : SQL Server 2022 16.0 Windows instance nommée ; image `2022-latest` Docker Linux, port 14333 | EXPERIENCE | commit `21fe2d8` | OK |
| E18 | « J'ai perdu vingt minutes » | UNVERIFIED | non consigné | **RETIRÉ** (« a long time ») |
| E19 | Connecteur Hydra ETL : lookup SQL Browser intégré, pas de pilote ODBC système | FACT | `sqlserver_connector.py`, `pyproject.toml` | OK |

## À confirmer avant publication

- [ ] La commande `docker exec … mssql-tools18 … -C` telle quelle a-t-elle été exécutée sur ton image ? (Le journal dit que sqlcmd manquait ; la docstring e2e l'utilise. Le texte la présente comme « forme documentée », pas comme testée.)
- [ ] Date de publication à renseigner (`date_published`).

## Métadonnées proposées

- URL : `/blog/sql-server-error-18456-login-failed`
- Title SEO : SQL Server Error 18456: Find the Real Cause (State 38, 8, 5)
- Meta : voir front matter.
- Schema : `TechArticle` (headline, author Person « Bechir Bejaoui », datePublished, dateModified = date de vérification, publisher, mainEntityOfPage). Pas de `FAQPage`.
- Liens internes : page d'accueil Hydra ETL (note finale) ; future doc du connecteur SQL Server quand elle existera.
