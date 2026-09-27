#!/bin/bash
cd /root/lab || exit 1
test -f parameters.yaml || exit 1
test -f environments/dev.yaml || exit 1
test -f environments/prod.yaml || exit 1
test -f secrets/dev.env || exit 1
test -f secrets/prod.env || exit 1
command -v hdrctl >/dev/null || exit 1
