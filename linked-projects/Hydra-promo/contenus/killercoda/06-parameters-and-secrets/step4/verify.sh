#!/bin/bash
D=/root/lab/output/destination_dev.csv
P=/root/lab/output/destination_prod.csv
test -f "$D" || exit 1
test -f "$P" || exit 1
grep -q "Contoso Ltd" "$P" || exit 1
test "$(grep -c . "$P")" -eq 6 || exit 1
# le run prod ne doit pas avoir ecrase le dev
grep -q "Test Customer A" "$D" || exit 1
# aucun secret en dur dans le manifeste
grep -q "dev-password-123" /root/lab/jobs/export-orders/sources.yaml && exit 1
exit 0
