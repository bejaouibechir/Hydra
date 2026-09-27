#!/usr/bin/env bash
# Replays the crontab the way cron does: every line runs at its time,
# whatever happened to the line before. Nobody reads the exit codes.
cd /root/nightly
for s in fetch clean backup report; do
  echo "--- 02:xx  $s.sh"
  ./scripts/$s.sh || true
done
