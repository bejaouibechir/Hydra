# hdrctl over HTTP

`hdrctl serve` starts a small REST API. It is not a reimplementation of the CLI's logic behind a web framework — every job endpoint (`/api/jobs/run`, `/validate`, `/test`, `/list`, `/init`) literally shells out to `hdrctl` as a subprocess and hands you back its exit code, stdout and stderr as JSON. Same binary, same output, over HTTP instead of a terminal.

In this lab you will start the server, call its health endpoint, then call `/api/jobs/validate` on a job twice — once valid, once with the same broken reference from the earlier labs — and read the CLI's own text sitting inside the JSON.

Hydra ETL installs in the background while you read this.
