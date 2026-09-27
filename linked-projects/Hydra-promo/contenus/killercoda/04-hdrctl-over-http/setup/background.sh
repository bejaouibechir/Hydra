#!/bin/bash
set -e
mkdir -p /root/lab
cd /root/lab
apt-get install -y -qq python3-venv >/dev/null 2>&1 || true
python3 -m venv /opt/hydra
/opt/hydra/bin/pip install --quiet "hydra-etl[server]>=0.11.2"
ln -sf /opt/hydra/bin/hdrctl /usr/local/bin/hdrctl
touch /tmp/setup-done
