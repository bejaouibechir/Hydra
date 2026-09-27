#!/usr/bin/env bash
# Pull last night's orders from the upstream drop folder.
set -euo pipefail
cd /root/nightly
# Simulated network blip: fails once, then works.
if [ -f /tmp/flaky ] && [ ! -f /tmp/flaky.done ]; then
  touch /tmp/flaky.done
  echo "fetch: connection reset by peer" >&2
  exit 1
fi
if [ ! -f incoming/orders.csv ]; then
  echo "fetch: incoming/orders.csv not delivered" >&2
  exit 1
fi
mkdir -p work
cp incoming/orders.csv work/orders.csv
echo "fetch: $(($(wc -l < work/orders.csv) - 1)) rows"
