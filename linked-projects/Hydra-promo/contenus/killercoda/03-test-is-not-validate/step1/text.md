# Create a broken job

Scaffold a job from the `mysql` template:

`hdrctl init dbjob --template mysql`{{exec}}

`cat dbjob/destinations.yaml`{{exec}}

The destination loads rows with `mode: upsert` (insert or update on `key: [id]`). Now break it — a one-letter typo:

`sed -i 's/mode: upsert/mode: upsret/' dbjob/destinations.yaml`{{exec}}

`grep mode dbjob/destinations.yaml`{{exec}}

`dbjob` now asks for a load mode, `upsret`, that does not exist.

When you are done, click **Check** to continue.
