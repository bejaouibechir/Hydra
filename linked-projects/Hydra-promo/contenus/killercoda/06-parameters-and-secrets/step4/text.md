# Run against prod and compare

Nothing in the job changes. You change the environment around it.

Load the other credentials:

`set -a; . /root/lab/secrets/prod.env; set +a`{{exec}}

`echo "user=$MYSQL_USER"`{{exec}}

A different user. Now run with the other flag:

`hdrctl run . --env prod`{{exec}}

Five rows this time, not three — a different database answered:

`cat /root/lab/output/destination_prod.csv`{{exec}}

Real-looking customers instead of `Test Customer A`. And the dev output is still
there, because the file name itself was a parameter:

`ls -1 /root/lab/output/`{{exec}}

Had `destination_dev.csv` stayed hard-coded, this prod run would have silently
overwritten your dev results. Parameterising **outputs** matters as much as
parameterising inputs.

## Prove which port was actually used

A successful run does not print the connection string. The quickest way to see
it is to break the connection on purpose — pass a wrong password for one run:

`MYSQL_PASSWORD=wrong-on-purpose hdrctl run . --env prod`{{exec}}

The failure reports the DSN Hydra assembled:

```
DSN : mysql://prod_reader:***@127.0.0.1:3308/orders_prod
```

Every piece of it was resolved at run time: `3308` and `orders_prod` from
`environments/prod.yaml`, `prod_reader` from the environment. And note the
password: `***`. Hydra masks it even in an error message — the one place
credentials most often leak.

Your `destination_prod.csv` is untouched; the run failed while reading the
source, before writing anything.

## The job itself never changed

`grep -n "param:\|ENV:" /root/lab/jobs/export-orders/sources.yaml`{{exec}}

Five placeholders, zero values. No host, no port, no database name, no
credentials. That file is safe to commit, and it is the only copy of the job you
will ever need.

Click **Check** to finish.
