#!/usr/bin/env bash
# Write the morning report.
set -euo pipefail
cd /root/nightly
mkdir -p reports
n=$(($(wc -l < work/orders_clean.csv) - 1))
echo "Nightly report: $n orders" | tee reports/report.txt
