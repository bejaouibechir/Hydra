#!/bin/bash
# Runs once when the Codespace is created.
# MySQL is already up: docker compose waited for its healthcheck before
# starting this container, so there is nothing to wait for here.
set -e

echo "==> Installing Hydra ETL"
pip install --quiet --upgrade pip
pip install --quiet "hydra-etl[server]>=0.11.3" mysql-connector-python

echo "==> Checking the database"
python3 - <<'PY'
import os
try:
    import mysql.connector as m
    c = m.connect(host="mysql", port=3306, user=os.environ["MYSQL_USER"],
                  password=os.environ["MYSQL_PASSWORD"], database="orders_dev")
    cur = c.cursor(); cur.execute("SELECT COUNT(*) FROM orders"); n = cur.fetchone()[0]
    print(f"    orders table reachable on host 'mysql' ({n} rows)")
except Exception as e:
    print(f"    WARNING: could not reach MySQL yet: {e}")
    print("    Try: docker compose logs mysql")
PY

# The welcome message must appear in every new terminal, not just this one.
cat >> "$HOME/.bashrc" <<'BASHRC'

# --- Hydra demo welcome -------------------------------------------------
if [ -z "$HYDRA_WELCOMED" ] && [ -f /workspaces/hydra-demo/tour ]; then
  export HYDRA_WELCOMED=1
  printf '\n'
  printf '  \033[1mWelcome to the Hydra ETL demo.\033[0m\n\n'
  printf '  Everything is already running. To be walked through it,\n'
  printf '  type this one command:\n\n'
  printf '      \033[36m./tour\033[0m\n\n'
  printf '  \033[2m(about five minutes, nothing to install, nothing to type)\033[0m\n\n'
fi
BASHRC

echo
echo "  Setup complete. Type  ./tour  to be walked through the demo."
echo
