# Replace a fragile crontab

Most servers have a crontab like this one:

```
0  2 * * *  /root/nightly/scripts/fetch.sh
15 2 * * *  /root/nightly/scripts/clean.sh
15 2 * * *  /root/nightly/scripts/backup.sh
30 2 * * *  /root/nightly/scripts/report.sh
```

Each line **guesses** how long the previous one takes. None of them knows whether the previous one worked.

In this lab you will:

1. watch that crontab produce a report that looks fine and is wrong;
2. rewrite it as a [Hydra ETL](https://hydraetl.com/?utm_source=killercoda&utm_medium=lab&utm_campaign=replace-crontab) workflow, where `clean` runs only if `fetch` succeeded;
3. add a retry for a flaky network;
4. see a typo rejected before anything runs;
5. keep cron for *when*, and hand *what* and *in which order* to Hydra ETL.

No database, no container, no account. The same four shell scripts, unchanged.

The terminal is installing Hydra ETL (`pip install hydra-etl`) while you read.
