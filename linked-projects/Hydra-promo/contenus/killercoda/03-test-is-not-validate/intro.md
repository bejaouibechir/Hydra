# hdrctl test

`hdrctl test` reads a job section by section — sources, destinations, transformations, environment — and tells you what is wrong before you run anything.

In this lab you will:

1. Create a MySQL job, then break its destination.
2. Run `hdrctl test` — it shows the error, and where.
3. Fix the job.
4. Run `hdrctl test` again — everything passes. Then read the two lines that tell you what `test` did *not* check.

Hydra ETL installs in the background while you read this.
