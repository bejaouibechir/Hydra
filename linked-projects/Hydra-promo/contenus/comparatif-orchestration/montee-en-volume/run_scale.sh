#!/usr/bin/env bash
# Pour chaque volume : Hydra ETL puis dlt + dbt (sans Airflow), mesure + vérification.
T=~/bench-envs/tools/bin/python
for n in "$@"; do
  for stack in hydra modern; do
    rm -f $stack/data; ln -s ../data_$n $stack/data; rm -f $stack/output/*.csv
    if [ $stack = hydra ]; then
      cmd="$HOME/bench-envs/hydra/bin/hdrctl run ."
    else
      cmd="source $HOME/bench-envs/modern/bin/activate && python ingest.py data/orders.csv && cd dbt && dbt run --profiles-dir . --threads 1"
    fi
    m=$($T measure.py "$cmd" $stack 1800)
    c=$($T check.py data_$n $stack/output 2>/dev/null || echo '{"country_ok":false,"month_ok":false}')
    echo "{\"rows\": $n, \"stack\": \"$stack\", \"run\": $m, \"check\": $c}" | tee -a results.jsonl | $T -c "
import json,sys; d=json.loads(sys.stdin.read()); r=d['run']
print(f\"{d['rows']:>9} {d['stack']:<7} {r['seconds']:>8}s  {r['peak_mb']:>6} Mo  exit={r['exit']} timeout={r['timeout']}  {d['check']}\")"
  done
done
