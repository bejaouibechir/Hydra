# Survive a network blip

Real fetches fail for a second and then work. Turn on a simulated blip — `fetch.sh` will fail exactly once:

`touch /tmp/flaky && rm -f /tmp/flaky.done`{{exec}}

`hdrctl workflow run workflow.yaml`{{exec}}

One transient error, and the whole night is lost. With cron you would add a `sleep` and a loop inside the script. Here it is one declaration on the step. Add it to `fetch`:

`sed -i '/scripts\/fetch.sh/a\      retry:\n        max: 2\n        delay: 2' workflow.yaml && sed -n 1,12p workflow.yaml`{{exec}}

```yaml
      retry:
        max: 2      # up to 2 more attempts after the first failure
        delay: 2    # seconds between attempts (backoff: exponential is also available)
```

Reset the blip and run again:

`rm -f /tmp/flaky.done && hdrctl workflow run workflow.yaml`{{exec}}

All four steps pass. The run takes about 2 seconds longer: the first attempt failed, Hydra ETL waited and tried again. The script itself did not change.
