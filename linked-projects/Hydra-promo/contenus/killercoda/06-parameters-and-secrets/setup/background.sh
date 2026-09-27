#!/bin/bash
# Runs while the user reads the intro.
# Never abort: a partial setup must still leave /root/lab usable for steps 1-2.
set +e
exec > /tmp/setup.log 2>&1
echo "=== setup started $(date -u) ==="

# --- 1. Start the image pulls in the background so they overlap with the rest.
(
  docker run -d --name mysql-dev  -p 3307:3306 \
    -e MYSQL_ROOT_PASSWORD=root-dev \
    -e MYSQL_DATABASE=orders_dev \
    -e MYSQL_USER=dev_reader -e MYSQL_PASSWORD=dev-password-123 \
    mysql:8.0
) &
(
  docker run -d --name mysql-prod -p 3308:3306 \
    -e MYSQL_ROOT_PASSWORD=root-prod \
    -e MYSQL_DATABASE=orders_prod \
    -e MYSQL_USER=prod_reader -e MYSQL_PASSWORD=prod-password-456 \
    mysql:8.0
) &

# --- 2. Project files FIRST: steps 1 and 2 must work even if everything else fails.
mkdir -p /root/lab/environments /root/lab/secrets /root/lab/output \
         /root/lab/jobs/export-orders /root/lab/.hydra
cd /root/lab

cat > .gitignore <<'EOF'
# Secrets are never committed. Parameters are.
secrets/
output/
EOF

cat > parameters.yaml <<'EOF'
version: "1.0"
parameters:
  mysql_host:
    type: string
    default: 127.0.0.1
    description: Database host. Same in both environments here.
  mysql_port:
    type: string
    default: "3307"
    description: Dev listens on 3307, prod on 3308.
  mysql_database:
    type: string
    default: orders_dev
    description: Database name, different per environment.
  env_name:
    type: string
    default: dev
    description: Written into the output file name.
EOF

cat > environments/dev.yaml <<'EOF'
version: "1.0"
parameters:
  mysql_port: "3307"
  mysql_database: orders_dev
  env_name: dev
EOF

cat > environments/prod.yaml <<'EOF'
version: "1.0"
parameters:
  mysql_port: "3308"
  mysql_database: orders_prod
  env_name: prod
EOF

cat > secrets/dev.env <<'EOF'
MYSQL_USER=dev_reader
MYSQL_PASSWORD=dev-password-123
EOF

cat > secrets/prod.env <<'EOF'
MYSQL_USER=prod_reader
MYSQL_PASSWORD=prod-password-456
EOF

cat > .hydra/project.json <<'EOF'
{
  "id": "0a7f31c2",
  "name": "orders-lab",
  "description": "Parameters and secrets across two environments",
  "jobs": [{ "name": "export-orders", "path": "jobs/export-orders" }]
}
EOF

# The job, deliberately hard-coded. The learner fixes it in step 2.
cat > jobs/export-orders/sources.yaml <<'EOF'
version: "1.0"
sources:
  src_orders:
    type: mysql
    connection:
      host: 127.0.0.1
      port: "3307"
      database: orders_dev
      user: dev_reader
      password: dev-password-123
    extract:
      table: orders
EOF

cat > jobs/export-orders/destinations.yaml <<'EOF'
version: "1.0"
destinations:
  dst_csv:
    type: csv
    connection: {}
    load:
      table: ../../output/destination_dev.csv
      mode: replace
EOF

cat > jobs/export-orders/pipeline.yaml <<'EOF'
version: "1.0"
pipeline:
  from: src_orders
  to: dst_csv
EOF
echo "--- project files written ---"
ls -R /root/lab

# --- 3. Hydra ETL. Fall back to a system-wide pip if venv is unavailable.
apt-get install -y -qq python3-venv
if python3 -m venv /opt/hydra && /opt/hydra/bin/pip install --quiet "hydra-etl>=0.11.2" mysql-connector-python; then
  ln -sf /opt/hydra/bin/hdrctl /usr/local/bin/hdrctl
  echo "--- hydra installed in venv ---"
else
  echo "--- venv failed, falling back to system pip ---"
  pip3 install --quiet --break-system-packages "hydra-etl>=0.11.2" mysql-connector-python \
    || pip3 install --quiet "hydra-etl>=0.11.2" mysql-connector-python
fi
command -v hdrctl && hdrctl --version

# --- 4. Wait for the containers, then seed them.
wait
seed() {
  local name="$1" rootpw="$2" db="$3" sql="$4"
  for _ in $(seq 1 90); do
    docker exec "$name" mysqladmin ping -h 127.0.0.1 -u root -p"$rootpw" >/dev/null 2>&1 && break
    sleep 2
  done
  docker exec -i "$name" mysql -u root -p"$rootpw" "$db" <<SQL
$sql
SQL
}

seed mysql-dev root-dev orders_dev "
CREATE TABLE orders (id INT, customer VARCHAR(60), amount DECIMAL(10,2));
INSERT INTO orders VALUES
 (1,'Test Customer A',10.00),
 (2,'Test Customer B',20.00),
 (3,'Test Customer C',30.00);
"

seed mysql-prod root-prod orders_prod "
CREATE TABLE orders (id INT, customer VARCHAR(60), amount DECIMAL(10,2));
INSERT INTO orders VALUES
 (101,'Contoso Ltd',1500.00),
 (102,'Fabrikam Inc',2750.50),
 (103,'Northwind Traders',980.25),
 (104,'Adventure Works',4200.00),
 (105,'Tailspin Toys',615.75);
"

# --- 5. Guard: if either database did not come up, say so loudly.
check() {
  docker exec "$1" mysql -u root -p"$2" -N -e "SELECT COUNT(*) FROM $3.orders" 2>/dev/null
}
DEV_ROWS=$(check mysql-dev root-dev orders_dev)
PROD_ROWS=$(check mysql-prod root-prod orders_prod)
echo "--- dev=$DEV_ROWS prod=$PROD_ROWS ---"
if [ "$DEV_ROWS" != "3" ] || [ "$PROD_ROWS" != "5" ]; then
  {
    echo "SETUP WARNING: the databases did not seed correctly."
    echo "  mysql-dev  orders_dev.orders  = '${DEV_ROWS:-unreachable}' (expected 3)"
    echo "  mysql-prod orders_prod.orders = '${PROD_ROWS:-unreachable}' (expected 5)"
    echo "Steps 1 and 2 still work. For the rest: docker ps -a ; cat /tmp/setup.log"
  } > /tmp/setup-warning
fi

echo "=== setup finished $(date -u) ==="
touch /tmp/setup-done
