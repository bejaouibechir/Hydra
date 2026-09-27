# Two environments, two sets of values

Everything is in `/root/lab`. Start with the declarations:

`cat parameters.yaml`{{exec}}

This file declares **what exists**: four parameters, each with a type, a default
and a description. It does not decide their values for any particular
environment — it is the contract.

Now the values, one file per environment:

`cat environments/dev.yaml environments/prod.yaml`{{exec}}

Same three keys, different values. Dev talks to port `3307` and database
`orders_dev`; prod talks to `3308` and `orders_prod`. Both files are meant to be
committed and read in a pull request — there is nothing dangerous in them.

## The other half

`cat secrets/dev.env secrets/prod.env`{{exec}}

Different credentials for each database. These are **not** YAML, and they are
not in the same place as the parameters, for one reason:

`cat .gitignore`{{exec}}

`secrets/` is ignored. That is the whole distinction — if a value would be
embarrassing in a pull request, it does not belong in `environments/`.

Confirm both databases are up, on their two ports:

`docker ps`{{exec}}

Click **Check** to continue.
