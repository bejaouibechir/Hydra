#!/usr/bin/env bash
# Drop rows with an empty amount.
set -euo pipefail
cd /root/nightly
awk -F, 'NR==1 || $3 != ""' work/orders.csv > work/orders_clean.csv
echo "clean: $(($(wc -l < work/orders_clean.csv) - 1)) rows kept"
