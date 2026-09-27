# Fix the job

Put the correct load mode back:

`sed -i 's/mode: upsret/mode: upsert/' dbjob/destinations.yaml`{{exec}}

`grep mode dbjob/destinations.yaml`{{exec}}

When you are done, click **Check** to continue.
