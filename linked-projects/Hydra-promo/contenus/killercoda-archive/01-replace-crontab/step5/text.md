# Keep one cron line

Cron is good at one thing: **when**. Keep it for that, and give it a single line:

`echo '0 2 * * * cd /root/nightly && /usr/local/bin/hdrctl workflow run workflow.yaml >> /var/log/nightly.log 2>&1' | crontab - && crontab -l`{{exec}}

What moved out of the crontab and into `workflow.yaml`:

| | crontab | workflow.yaml |
|---|---|---|
| Order | guessed with start times | `depends_on` |
| Parallel steps | same start time, and hope | automatic when nothing links them |
| Failure upstream | downstream runs on stale data | downstream skipped |
| Transient error | loop and `sleep` inside the script | `retry:` on the step |
| Typo | found at 2 a.m. | refused by `validate` |
| Result | one exit code per line, unread | one exit code for the night (`0` or `1`) |

That last line matters: one exit code means your existing alerting — `MAILTO`, a monitoring wrapper, a CI job — sees the whole night at once.
