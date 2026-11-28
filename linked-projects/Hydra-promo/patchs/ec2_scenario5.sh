#!/usr/bin/env bash
# Scenario 5 on the EC2 machine: Hydra ETL 0.22.0, Hydra + write-ahead patch, the two
# generation variants, Airflow + dlt + dbt. Results: ~/bench/results_ec2/ and
# ~/scenario5-ec2-results.tar.gz.   Usage: bash ~/ec2_scenario5.sh 2>&1 | tee ~/ec2_run.log
set -euo pipefail
cd ~
rm -rf bench && mkdir bench && cd bench
tar xzf ~/benchmark-ec2.tar.gz && mkdir src && tar xzf ~/hydra-patched-src.tar.gz -C src
cd hydra-etl-benchmark
R=$PWD/results_ec2; mkdir -p "$R"

echo "== machine"; { uname -a; nproc; free -m; lsb_release -d 2>/dev/null || true; python3 --version; } | tee "$R/machine.txt"

echo "== install"
sudo apt-get update -qq && sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq python3-venv python3-pip git >/dev/null
python3 -m venv ~/hv0 && ~/hv0/bin/pip -q install -U pip && ~/hv0/bin/pip -q install "hydra-etl==0.22.0" pandas
python3 -m venv ~/hv1 && ~/hv1/bin/pip -q install -U pip && ~/hv1/bin/pip -q install ../src/hydra-src pandas
PYV=$(python3 -c 'import sys;print(f"{sys.version_info.major}.{sys.version_info.minor}")')
python3 -m venv ~/mv && ~/mv/bin/pip -q install -U pip
~/mv/bin/pip -q install "apache-airflow==3.3.2" --constraint "https://raw.githubusercontent.com/apache/airflow/constraints-3.3.2/constraints-$PYV.txt"
~/mv/bin/pip -q install 'dlt[duckdb]' dbt-duckdb pandas pyarrow
~/hv0/bin/hdrctl --version | head -1; ~/hv1/bin/pip show hydra-etl | head -2

echo "== data"
~/hv0/bin/python shared/make_data.py shared/data
python3 shared/make_probe_dag.py 2
( cd modern && . ~/mv/bin/activate && . ./env.sh && airflow db migrate >/dev/null 2>&1 && airflow dags reserialize >/dev/null 2>&1 )

C=~/hv0/bin/python    # the scenario scripts only need pandas
HY='hdrctl run .'
GENCMD='export GEN=g$(date +%s%N); hdrctl run . --param generation=$GEN'
UNDO='hdrctl workflow undo daily_revenue'
AF='. ~/mv/bin/activate && . ./env.sh &&'
AFG='. ~/mv/bin/activate && . ./env.sh && export GEN=g$(date +%s%N) &&'
run() { local name=$1; shift; echo "== $name"; "$@" --out "$R/$name.json" | tail -2; }

echo "######## four original scenarios, Hydra 0.22.0 (same results as the article?)"
PATH=~/hv0/bin:$PATH $C shared/scenarios.py hydra "$HY" --repeat 3 --out "$R/base_hydra.json" | tail -4

echo "######## Hydra ETL 0.22.0 (released)"
export PATH=~/hv0/bin:$PATH
run hydra_0.22.0_observe            $C shared/crash_scenario.py hydra "$HY" observe --repeat 5
run hydra_0.22.0_kill_immediate     $C shared/crash_scenario.py hydra "$HY" kill --repeat 3 --kill-delay 0 --recover "$UNDO"
run hydra_0.22.0_kill_during_step2  $C shared/crash_scenario.py hydra "$HY" kill --repeat 3 --kill-delay 0.3 --recover "$UNDO"
run hydra_gen_observe               $C shared/crash_scenario.py hydra_gen "$GENCMD" observe --manifest --repeat 5
run hydra_gen_kill_immediate        $C shared/crash_scenario.py hydra_gen "$GENCMD" kill --manifest --repeat 3 --kill-delay 0 --recover "$UNDO"
run hydra_gen_kill_during_step2     $C shared/crash_scenario.py hydra_gen "$GENCMD" kill --manifest --repeat 3 --kill-delay 0.3 --recover "$UNDO"

echo "######## Hydra ETL 0.22.0 + write-ahead patch (unreleased)"
export PATH=~/hv1/bin:$PATH
run hydra_patched_kill_immediate    $C shared/crash_scenario.py hydra "$HY" kill --repeat 3 --kill-delay 0 --recover "$UNDO"
run hydra_patched_kill_during_step2 $C shared/crash_scenario.py hydra "$HY" kill --repeat 3 --kill-delay 0.3 --recover "$UNDO"

echo "######## Airflow + dlt + dbt"
export PATH=~/hv0/bin:$PATH
run airflow_observe                 $C shared/crash_scenario.py modern "$AF airflow dags test daily_revenue_safe" observe --repeat 5
run airflow_kill_probe              $C shared/crash_scenario.py modern "$AF airflow dags test daily_revenue_safe_probe" kill --repeat 3
run airflow_gen_observe             $C shared/crash_scenario.py modern "$AFG airflow dags test daily_revenue_safe_gen" observe --manifest --repeat 3
run airflow_gen_kill_probe          $C shared/crash_scenario.py modern "$AFG PROBE_PAUSE=2 airflow dags test daily_revenue_safe_gen" kill --manifest --repeat 3

cd "$R/.." && tar czf ~/scenario5-ec2-results.tar.gz results_ec2
echo "DONE -> ~/scenario5-ec2-results.tar.gz"
