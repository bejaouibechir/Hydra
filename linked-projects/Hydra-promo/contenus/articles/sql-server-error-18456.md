---
title: "Error 18456: Four Ways SQL Server Misleads You About Login Failures"
seo_title: "SQL Server Error 18456: Find the Real Cause (State 38, 8, 5)"
description: "The client always gets the same vague 'Login failed' message. The real reason is a state number in the server error log. Four traps, how to read the state, and a checklist."
slug: sql-server-error-18456-login-failed
author: Bechir Bejaoui
date_published: "<set on publication>"
date_verified: 2026-09-26
tags: [sql-server, troubleshooting, docker, authentication]
---

# Error 18456: Four Ways SQL Server Misleads You About Login Failures

**Short answer:** the message `Login failed for user ... (Error: 18456)` that your client shows is deliberately vague, and it usually does not mean your password is wrong. SQL Server writes the real reason — a **state number** — only to the server error log. Read that state first: `8` is a wrong password, but `38` means the database was not found, and `5` means the login does not exist.

*By Bechir Bejaoui, maintainer of [Hydra ETL](https://hydraetl.com). The traps below were hit on 23 September 2026 while testing a SQL Server connector against SQL Server 2022 (16.0) on Windows — a named instance — and the `mcr.microsoft.com/mssql/server:2022-latest` image in Docker on Linux. Last verified: 26 September 2026.*

Every developer who connects to SQL Server has seen this:

```
Login failed for user 'app_user'. (Microsoft SQL Server, Error: 18456)
```

And almost everyone does the same thing next: retype the password. On the day these notes come from, I hit `18456` several times, and the password was never the cause. If you connect to SQL Server from anything other than SQL Server Management Studio — a .NET service, a Python script, a CI pipeline, a container — these four traps are waiting for you.

## Why the client message tells you nothing

**The error returned to the client hides the cause on purpose.** Microsoft's documentation for [error 18456](https://learn.microsoft.com/en-us/sql/relational-databases/errors-events/mssqlserver-18456-database-engine-error) says so directly: *"To increase security, the error message that is returned to the client deliberately hides the nature of the authentication error. However, in the SQL Server error log, a corresponding error contains an error state that maps to an authentication failure condition."*

The reason is sound: if the client could tell "this login does not exist" from "this password is wrong", an attacker could enumerate valid logins. The consequence for everyone else is blunt: staring at the client message will not help. The diagnosis is in the server error log.

### How to read the real state

On Windows, the error log is a text file in the instance's `Log` folder (the path below is for a SQL Server 2022 instance; adjust the instance folder name):

```powershell
Get-Content "C:\Program Files\Microsoft SQL Server\MSSQL16.INSTANCE\MSSQL\Log\ERRORLOG" -Tail 20
```

In a Linux container, the error log is written to the container output:

```bash
docker logs <container> 2>&1 | grep "Error: 18456"
```

Either way, you are looking for a line like this one:

```
Logon       Error: 18456, Severity: 14, State: 38.
```

### What the state numbers mean

From [Microsoft's list of 18456 states](https://learn.microsoft.com/en-us/sql/relational-databases/errors-events/mssqlserver-18456-database-engine-error), the ones you are most likely to meet:

| State | Meaning (Microsoft documentation) |
|---|---|
| 2, 5 | User ID isn't valid — the login does not exist |
| 6 | A Windows login name was used with SQL Server Authentication |
| 7 | Login is disabled, and the password is incorrect |
| 8 | The password is incorrect |
| 11, 12 | Login is valid, but server access failed (state 11: for example, a Windows administrator connecting without elevated credentials) |
| 38, 46 | Couldn't find the database requested by the user |
| 58 | SQL authentication attempted against a server set to Windows Authentication only, or mismatched SIDs |

Only one of those rows is "the password is wrong".

## Trap 1 — State 38: the database is not there

**A missing database produces the same client error as a bad password.** This one cost me the most time.

The container was running, the port answered, the credentials were right, and every connection came back `18456`. Because the password contained an exclamation mark and I was passing it through PowerShell, I spent a long time suspecting an escaping problem.

The server log said `State: 38`. The login was fine; the database simply did not exist. An earlier `CREATE DATABASE` had failed without my noticing (see Trap 4), and SQL Server reported the missing database as a login failure.

**Confirm it in five seconds**, connected to `master`:

```sql
SELECT name FROM sys.databases WHERE name = 'your_database';
```

An empty result means the database is missing, renamed or was never created. The password was never the issue.

## Trap 2 — A server login is not a database user

**Being able to connect to the instance does not give you access to a database.** SQL Server has two levels of identity:

- a **login** exists at the server level and lets you connect to the instance;
- a **user** exists inside each database and lets you do anything once you are there.

A login with no user in the database it asks for is refused — and on 23 September that, too, came back as `18456`, pointing me at the password again. Check both levels:

```sql
-- Does the login exist at server level?
SELECT name, type_desc, is_disabled FROM sys.server_principals WHERE name = 'app_user';

-- Does it have a user inside the target database?
USE your_database;
SELECT name, type_desc FROM sys.database_principals WHERE name = 'app_user';
```

If the first query returns a row and the second does not, create the user:

```sql
USE your_database;
CREATE USER app_user FOR LOGIN app_user;
ALTER ROLE db_datareader ADD MEMBER app_user;
```

On a development or test instance, when the login should own the database outright, you can instead make it the owner (`dbo`) with [`ALTER AUTHORIZATION`](https://learn.microsoft.com/en-us/sql/t-sql/statements/alter-authorization-transact-sql):

```sql
ALTER AUTHORIZATION ON DATABASE::your_database TO app_user;
```

**Related surprise: a Windows administrator is not a SQL Server administrator.** Since SQL Server 2008, *"the local Windows Group BUILTIN\Administrator is no longer included in the SQL Server sysadmin fixed server role on new SQL Server 2008 installations"* ([Microsoft, SQL Server 2008 R2 security changes](https://learn.microsoft.com/en-us/previous-versions/sql/sql-server-2008-r2/cc280562(v=sql.105))). You can be a local administrator and still be refused `CREATE DATABASE`. Check what you actually are:

```sql
SELECT SUSER_SNAME() AS current_login,
       IS_SRVROLEMEMBER('sysadmin')  AS is_sysadmin,
       IS_SRVROLEMEMBER('dbcreator') AS is_dbcreator;
```

## Trap 3 — Named instances, and the error that is not 18456

**If the error is 20009 rather than 18456, you never reached SQL Server at all.** This trap announces itself differently, and the difference is the clue.

Connecting to a named instance (`MACHINE\INSTANCE`, no port) from Python with `pymssql`, which embeds the FreeTDS library, I got:

```
20009 ... TDS server is unavailable or does not exist (MACHINE)
```

Look at the parentheses: **the instance name is missing.** The connection went to the machine alone.

Why that matters: according to Microsoft's [SQL Server Browser documentation](https://learn.microsoft.com/en-us/sql/database-engine/configure-windows/sql-server-browser-service-database-engine-and-ssas), *"named instances and SQL Server Express are configured to use dynamic ports by default. That is, an available port is assigned when SQL Server starts."* To find that port, *"the client network library sends a UDP message to the server using port 1434. SQL Server Browser responds with the TCP/IP port or named pipe of the requested instance."* Microsoft's client libraries do this lookup for you, which is why `Server=MACHINE\SQLEXPRESS` just works in a .NET connection string.

FreeTDS documents the same capability — its [user guide](https://www.freetds.org/userguide/PortOverride.html) says that with `servername\instance` *"FreeTDS will attempt to connect to specified instance"* through a UDP query to port 1434. In my test through pymssql, that did not happen: the message above is what came back. I did not isolate why (the pymssql build, how the server string is passed, or the network path to UDP 1434), so treat it as an observation, not a rule — but if you see an error that omits your instance name, suspect this first.

**Two ways out.**

1. **Pass the port explicitly.** Find it, connected to the instance:

   ```sql
   SELECT local_tcp_port FROM sys.dm_exec_connections WHERE session_id = @@SPID;
   ```

   Then pin it so it survives a restart: SQL Server Configuration Manager → *SQL Server Network Configuration* → *Protocols for INSTANCE* → *TCP/IP* → *IP Addresses* → clear **TCP Dynamic Ports**, set **TCP Port**, restart the service.

2. **Do the SQL Browser lookup yourself.** The protocol, [SSRP (MC-SQLR)](https://learn.microsoft.com/en-us/openspecs/windows_protocols/mc-sqlr/1ea6e25f-bff9-4364-ba21-5dc449a601b7), is small: send one UDP datagram to port 1434 made of the byte `0x04` followed by the instance name, and read the reply, which has this shape (example):

   ```
   ServerName;MACHINE;InstanceName;SQLEXPRESS;IsClustered;No;Version;16.0.1000.6;tcp;14330;;
   ```

   The port follows `tcp`. It is about forty lines of socket code. One warning: replies are made of blocks ending with `;;`. Split the blocks first, then the fields. My first parser read all fields in one pass; a unit test with a two-instance reply showed that the empty field created by `;;` shifts every key/value pair — which could hand back **another instance's port** and connect a user, silently, to the wrong database.

## Trap 4 — The tool is not where the tutorial says it is

**Many container tutorials still use a `sqlcmd` path that current SQL Server 2022 images are phasing out.** They create a database like this:

```bash
docker exec -i my-sql /opt/mssql-tools/bin/sqlcmd -S localhost -U sa -P "..." \
  -Q "CREATE DATABASE mydb"
```

Microsoft's [Docker quickstart](https://learn.microsoft.com/en-us/sql/linux/quickstart-install-connect-docker) is explicit: *"Starting with SQL Server 2022 (16.x) CU 14 and SQL Server 2019 (15.x) CU 28, the container images include the new mssql-tools18 package. The previous directory `/opt/mssql-tools/bin` is being phased out. The new directory for Microsoft ODBC 18 tools is `/opt/mssql-tools18/bin`."* The documented form of the command:

```bash
docker exec -i my-sql /opt/mssql-tools18/bin/sqlcmd -S localhost -U sa -P "..." -C \
  -Q "CREATE DATABASE mydb"
```

`-C` tells `sqlcmd` to *"implicitly trust the server certificate without validation"* ([sqlcmd reference](https://learn.microsoft.com/en-us/sql/tools/sqlcmd/sqlcmd-utility)) — acceptable against a local test container, not against a production server.

The real problem is the failure mode. Inside a setup script, where you are watching for the container to come up, a failed `docker exec` scrolls past unnoticed. You believe the database exists. It does not. The next thing you see is `18456` — Trap 1 — and you are back to checking the password.

**Safer: create the database from the client you already use**, so a failure raises an exception instead of an exit code nobody reads:

```python
import pymssql

conn = pymssql.connect(server="127.0.0.1", port=14333, user="sa",
                       password="...", database="master", autocommit=True)
conn.cursor().execute("CREATE DATABASE mydb")
```

`autocommit=True` matters: *"The CREATE DATABASE statement must run in autocommit mode (the default transaction management mode) and isn't allowed in an explicit or implicit transaction"* ([CREATE DATABASE](https://learn.microsoft.com/en-us/sql/t-sql/statements/create-database-transact-sql)).

## The checklist

When `18456` appears, in this order:

1. **Read the server error log** and find the state number. Everything else is guessing.
2. **State 38 or 46** — the requested database was not found. Does it exist? Does your login have a user inside it?
3. **State 8** — now, and only now, it is the password.
4. **State 2 or 5** — the login itself does not exist at server level.
5. **Error 20009 instead of 18456** — you never reached the server: named instance, port, firewall, or SQL Browser. Check whether the message even contains your instance name.

The lesson I took away: **an error message is a claim, not a diagnosis.** SQL Server's login failure message is uninformative by design, and treating it as informative sends you the wrong way. The authoritative answer is a few lines away, in a log file.

---

*I hit these while building the SQL Server connector of [Hydra ETL](https://hydraetl.com), an open-source engine where data pipelines are written in YAML and validated before they run. The connector now performs the SQL Browser lookup itself, so `MACHINE\SQLEXPRESS` works without a port and without a system ODBC driver. The traps themselves have nothing to do with Hydra ETL: they will find you whatever you connect with.*
