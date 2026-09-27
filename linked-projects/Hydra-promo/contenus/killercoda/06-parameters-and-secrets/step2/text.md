# Read the parameterised job

The job already exists. Read it before changing anything:

`cat jobs/export-orders/sources.yaml`{{exec}}

This is the job as too many of them are written: the port, the database, the
user **and the password** are hard-coded. It works — against dev, once. It
cannot run against prod, and that password is now in version control forever.

There are exactly five values to move out, and two different destinations for
them.

## Parameters: everything that is not a secret

`host`, `port` and `database` describe *where* the job runs. They belong to the
environment, they are reviewable, and they use `{{ param:name }}`.

## Secrets: the two that must never be written down

`user` and `password` use `${ENV:NAME}` — read from the environment at run time,
never from a file that git can see.

Replace the file:

```
cat > jobs/export-orders/sources.yaml <<'EOF'
version: "1.0"
sources:
  src_orders:
    type: mysql
    connection:
      host: "{{ param:mysql_host }}"
      port: "{{ param:mysql_port }}"
      database: "{{ param:mysql_database }}"
      user: ${ENV:MYSQL_USER}
      password: ${ENV:MYSQL_PASSWORD}
    extract:
      table: orders
EOF
```{{exec}}

The destination has the same problem — `destination_dev.csv` is a hard-coded
name, so a prod run would overwrite the dev file:

```
cat > jobs/export-orders/destinations.yaml <<'EOF'
version: "1.0"
destinations:
  dst_csv:
    type: csv
    connection: {}
    load:
      table: ../../output/destination_{{ param:env_name }}.csv
      mode: replace
EOF
```{{exec}}

Read the result and notice that the two syntaxes are visually distinct:

`cat jobs/export-orders/sources.yaml`{{exec}}

`{{ param:… }}` is safe to read. `${ENV:…}` is a value you will never find in
the repository. You can audit a manifest at a glance.

Click **Check** to continue.
