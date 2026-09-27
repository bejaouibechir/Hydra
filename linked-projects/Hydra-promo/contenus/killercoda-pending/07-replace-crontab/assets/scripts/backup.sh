#!/usr/bin/env bash
# Keep a copy of the raw file.
set -euo pipefail
cd /root/nightly
mkdir -p backups
cp work/orders.csv "backups/orders-$(date +%F).csv"
echo "backup: saved"
