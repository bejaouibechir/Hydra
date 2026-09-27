#!/bin/bash
cd /root/lab || exit 1
S=jobs/export-orders/sources.yaml
D=jobs/export-orders/destinations.yaml
grep -q 'param:mysql_port'     "$S" || exit 1
grep -q 'param:mysql_database' "$S" || exit 1
grep -q 'ENV:MYSQL_USER'       "$S" || exit 1
grep -q 'ENV:MYSQL_PASSWORD'   "$S" || exit 1
grep -q 'param:env_name'       "$D" || exit 1
# aucune valeur en dur ne doit subsister
grep -q 'dev-password-123' "$S" && exit 1
grep -q 'dev_reader'       "$S" && exit 1
exit 0
