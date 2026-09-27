#!/bin/bash
# Installs Hydra ETL and prepares /root/nightly. Runs while the user reads the intro.
set -e
cd /root/nightly
chmod +x scripts/*.sh simulate-night.sh
mkdir -p incoming
command -v crontab >/dev/null || { apt-get update -qq && apt-get install -y -qq cron >/dev/null; }
apt-get install -y -qq python3-venv >/dev/null 2>&1 || true
python3 -m venv /opt/hydra
/opt/hydra/bin/pip install --quiet "hydra-etl>=0.11.2"
ln -sf /opt/hydra/bin/hdrctl /usr/local/bin/hdrctl
touch /tmp/setup-done
