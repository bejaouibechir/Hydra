# Run against dev

The job no longer contains a host, a port, a database or a password. So how does
it know anything?

Two separate mechanisms, and this is the core of the lab.

## 1. Parameters come from the flag

`hdrctl run` takes `--env`, which selects `environments/<name>.yaml`:

`cd /root/lab/jobs/export-orders`{{exec}}

## 2. Secrets come from the shell

Hydra reads `${ENV:…}` from the process environment. Nothing loads
`secrets/dev.env` for you — **you** load it, which is exactly how a CI runner or
a secret manager injects credentials in production:

`set -a; . /root/lab/secrets/dev.env; set +a`{{exec}}

`set -a` marks everything defined next for export, so the two values become real
environment variables rather than shell variables. Check:

`echo "user=$MYSQL_USER"`{{exec}}

Now run it:

`hdrctl run . --env dev -vv`{{exec}}

Three rows read, three written. Scroll to the `Environment variables` section of
that output and read it carefully:

```
Environment variables
No .env file found
```

**That message is the goal, not a warning.** Hydra looks for a `.env` file on
disk and finds none — because your credentials were never written to a file it
could read. They came from the environment, and they disappear when this shell
does.

Look at what came out:

`cat /root/lab/output/destination_dev.csv`{{exec}}

Three rows of obviously fake test data. Click **Check** to continue.
