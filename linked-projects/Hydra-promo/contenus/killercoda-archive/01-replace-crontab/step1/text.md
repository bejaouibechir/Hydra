# Watch the crontab lie

Move to the lab folder:

`cd /root/nightly`{{exec}}

Look at the job:

`cat crontab.txt`{{exec}}

Tonight, the upstream system did not deliver `incoming/orders.csv`. Replay the night exactly as cron would — every line at its time, whatever happened before:

`./simulate-night.sh`{{exec}}

Read the output from the bottom up:

- `report.sh` says **Nightly report: 3 orders**. It looks normal.
- Those 3 orders are **yesterday's**, still sitting in `work/`.
- `backup.sh` saved yesterday's file under today's date.
- `fetch.sh` failed at the very first line, and nothing downstream noticed.

Nobody reads cron's exit codes. The only visible signal is a report that is wrong and looks right.

Click **Check** to continue.
