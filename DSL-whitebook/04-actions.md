<!-- Hydra DSL White Paper — Chapter 4: Actions
     DSL format version: 1.0 · Hydra 0.16.0
     Sources: workflow/models.py (ACTION_PARAMS, SIDE_EFFECT_ACTIONS), workflow/runner.py
     (_run_action, _resolve_action_params, _action_*), workflow/expr.py,
     internal/config/parameters.py (coerce_value) -->

# Hydra DSL - Actions

An **action** is a workflow step that does something **other than moving data**: write a message, wait, call a URL, send an email, run a script, set a parameter, evaluate a condition.

```yaml
- name: notify
  type: action
  action: log
  params:
    message: "Sales loaded."
  depends_on: [load_sales]
```

> **[FIGURE fig-04-01 · diagram]** A workflow graph where job steps are drawn as data cylinders and action steps as rounded boxes with an icon per action (log, clock, HTTP, envelope, terminal, Python, variable, diamond).

## The 11 actions

| Family | Action | Purpose |
|---|---|---|
| Flow | `log` | Write a message in the run log |
| | `delay` | Wait a number of seconds |
| | `condition` | Compute true/false and store it as a parameter |
| Notification | `webhook` | Call a URL |
| | `email` | Send an email |
| Scripts | `bash` | Run a Bash command (Linux, macOS) |
| | `powershell` | Run a PowerShell command (Windows) |
| | `ssh` | Run a command on a remote server |
| | `python` | Run a Python script |
| Parameters | `set_param` | Create a parameter during the run |
| | `assign_param` | Change a parameter created during the run |

No other action exists.

## Rules for actions

- `action` must be one of the 11 names above. A typo is refused, with a suggestion.
- `params` accepts only the parameters of that action. An unknown parameter is refused.
- A required parameter that is missing or empty is refused.
- All of this is checked **before** the run starts.
- In `params`, you can use `{{ param:NAME }}`, `{{ env:NAME }}`, `${SECRET:NAME}` and `${ENV:NAME}`. They are replaced just before the action runs.
- A `{{ param:NAME }}` that does not exist makes the action fail.
- An action fails if its command returns a non-zero exit code, or its HTTP call returns an error.

---

# Hydra DSL - Flow Actions

## log

| Parameter | Required | Default |
|---|---|---|
| `message` | No | `Step '<name>' executed` |

```yaml
- name: start
  type: action
  action: log
  params:
    message: "Starting the load for {{ param:country }}"
```

## delay

| Parameter | Required | Default | Description |
|---|---|---|---|
| `seconds` | No | `1` | Seconds to wait (a number) |
| `duration` | No | – | Same as `seconds` |

```yaml
- name: wait_replica
  type: action
  action: delay
  params:
    seconds: 120
```

## condition

Evaluates a condition and stores the result (`True` or `False`) in a parameter. Other steps read it in `when:`.

| Parameter | Default | Description |
|---|---|---|
| `name` | the step name | Name of the parameter that receives the result |
| `mode` | `expr` | `expr` (an expression) or `structured` (left / op / right) |
| `expr` | – | The expression, in `expr` mode |
| `left`, `op`, `right` | – | The comparison, in `structured` mode |

### Example 1: expression mode

```yaml
- name: check_env
  type: action
  action: condition
  params:
    name: is_prod
    expr: "{{ env:HYDRA_ENV }} == 'prod'"
```

The expression follows the rules of `when` (see *Workflows*).

### Example 2: structured mode

```yaml
- name: check_threshold
  type: action
  action: condition
  params:
    name: above_threshold
    mode: structured
    left: "{{ param:row_count }}"
    op: ">="
    right: 1000
```

`op`: `==` · `!=` · `<` · `<=` · `>` · `>=` · `contains`.

```yaml
- name: check_recipients
  type: action
  action: condition
  params:
    name: finance_in_list
    mode: structured
    left: "{{ param:recipients }}"
    op: contains
    right: finance@example.com
```

### Example 3: using the result

```yaml
- name: publish
  type: job
  job: ../jobs/publish
  depends_on: [check_env]
  when: "{{ param:is_prod }} == True"
```

> **[LAB lab-04-01 · Killercoda]** **Branching a workflow** — Build a workflow that takes one of two branches depending on a parameter, then switch the branch by running the project with `hdrctl run . --env dev` and `hdrctl run . --env prod`.

---

# Hydra DSL - Notification Actions

## webhook

| Parameter | Required | Default | Description |
|---|---|---|---|
| `url` | Yes | – | Address to call |
| `method` | No | `POST` | HTTP method |
| `body` | No | – | Body, as a mapping (sent as JSON) or as text |
| `headers` | No | – | Extra headers |

The request is sent with `Content-Type: application/json`. It fails after 30 seconds without an answer, or if the server answers with an error status.

### Example 1: simple notification

```yaml
- name: ping
  type: action
  action: webhook
  params:
    url: https://hooks.example.com/hydra
```

### Example 2: JSON body and authentication

```yaml
- name: notify_api
  type: action
  action: webhook
  params:
    url: https://api.example.com/v1/events
    method: POST
    headers:
      Authorization: "Bearer ${SECRET:API_TOKEN}"
    body:
      event: load_finished
      workflow: daily_sales
      country: "{{ param:country }}"
```

### Example 3: a chat notification that must never block

```yaml
- name: notify_chat
  type: action
  action: webhook
  params:
    url: ${SECRET:CHAT_WEBHOOK_URL}
    body:
      text: "Daily sales loaded."
  depends_on: [load_sales]
  on_failure: continue
  retry:
    max: 2
    delay: 10
```

## email

| Parameter | Required | Default | Description |
|---|---|---|---|
| `to` | Yes | – | Recipient |
| `subject` | No | – | Subject |
| `body` | No | empty | Plain-text body |
| `from_addr` | No | `hydra@localhost` | Sender |
| `smtp_host` | No | `localhost` | SMTP server |
| `smtp_port` | No | `1025` | SMTP port |
| `username`, `password` | No | – | SMTP login |
| `use_tls` | No | `false` | Use STARTTLS |

The defaults point to a local test mail server. In production, set `smtp_host`, `smtp_port`, `use_tls` and the login.

```yaml
- name: mail_finance
  type: action
  action: email
  params:
    to: finance@example.com
    subject: "Monthly close done"
    body: |
      The monthly close finished successfully.
      Environment: {{ env:HYDRA_ENV }}
    from_addr: etl@example.com
    smtp_host: smtp.example.com
    smtp_port: 587
    use_tls: true
    username: etl@example.com
    password: ${SECRET:SMTP_PASSWORD}
```

<!-- REVIEW (décision J) : sujet par défaut « (sans objet) » en français dans le code. -->

> **[LAB lab-04-02 · Killercoda]** **Notify the team** — Send a webhook to a local request inspector and an email to a test mail server at the end of a workflow, and read both.

---

# Hydra DSL - Script Actions

## bash and powershell

| Parameter | Required | Default | Description |
|---|---|---|---|
| `command` | Yes | – | The command |
| `working_dir` | No | current folder | Folder in which it runs |
| `timeout` | No | `60` | Seconds before it is stopped |

- `bash` runs on Linux and macOS only; `powershell` on Windows only. Using the other one fails with a clear message.
- The output of the command is copied into the run log.
- **Parameters are available as environment variables**: `$NAME` in Bash, `$env:NAME` in PowerShell. Booleans become `true` / `false`.

### Example 1: Bash

```yaml
- name: archive_input
  type: action
  action: bash
  params:
    command: "mv Data/in.csv Data/archive/in_$(date +%F).csv"
    working_dir: ..
```

### Example 2: reading a parameter from the environment

```yaml
- name: purge_old_files
  type: action
  action: bash
  params:
    command: 'find outputs/ -mtime +"$RETENTION_DAYS" -delete'
    timeout: 120
```

`RETENTION_DAYS` comes from `parameters.yaml` or from a `set_param` earlier in the run.

### Example 3: PowerShell

```yaml
- name: copy_to_share
  type: action
  action: powershell
  params:
    command: 'Copy-Item outputs\report.csv "\\fileserver\reports\report_$env:country.csv"'
```

## ssh

| Parameter | Required | Default | Description |
|---|---|---|---|
| `host` | Yes | – | Remote server |
| `username` | Yes | – | Login |
| `command` | Yes | – | Command to run |
| `port` | No | `22` | SSH port |
| `key_path` | No | – | Private key file (used first) |
| `password` | No | – | Password, if no key |
| `timeout` | No | `30` | Seconds |

Requires `pip install paramiko`.

```yaml
- name: refresh_cache
  type: action
  action: ssh
  params:
    host: app01.internal
    username: deploy
    key_path: ~/.ssh/hydra_deploy
    command: "sudo systemctl restart report-cache"
```

## python

| Parameter | Required | Default | Description |
|---|---|---|---|
| `script` | one of the two | – | Python code, inline |
| `file_path` | one of the two | – | A `.py` file |
| `working_dir` | No | current folder | Folder in which it runs |
| `timeout` | No | `60` | Seconds |

- The script runs with the same Python as Hydra, on any system.
- A relative `file_path` is looked for next to the workflow, then from the project root.
- Parameters are available in `os.environ`, and `{{ param:NAME }}` is replaced in the code before it runs.

### Example 1: inline

```yaml
- name: check_file
  type: action
  action: python
  params:
    script: |
      import os, sys
      size = os.path.getsize("Data/in.csv")
      print(f"in.csv: {size} bytes")
      sys.exit(0 if size > 0 else 1)
```

A non-zero exit code makes the step fail.

### Example 2: a script file

```yaml
- name: build_kpis
  type: action
  action: python
  params:
    file_path: scripts/build_kpis.py
    timeout: 600
```

### Example 3: reading a parameter

```yaml
- name: show_country
  type: action
  action: python
  params:
    script: |
      import os
      print("Country:", os.environ["country"])
      print("Threshold:", {{ param:min_amount }})
```

> The `python` **action** runs a full Python script, with imports and file access. The `script` **transformation** (see *Jobs*) runs restricted Python on columns. They are not the same thing.

> **[LAB lab-04-03 · Killercoda]** **Scripts around your jobs** — Archive the input file with `bash`, compute a check with `python`, and run a remote command with `ssh` on a second machine of the lab.

> **[GITHUB gh-04-01 · example]** **workflow_actions** — Project with one workflow using every action at least once, the `scripts/` it calls, a `docker-compose.yml` with a test mail server and a request inspector, and a README.

---

# Hydra DSL - Parameter Actions

Parameters created during a run live **only for that run**. They are shared by all its steps.

| | `set_param` | `assign_param` |
|---|---|---|
| Creates a parameter | ✔ | – |
| Changes an existing one | – | ✔ |
| Fails if the parameter… | already exists | does not exist |

| Parameter | Required | Default | Description |
|---|---|---|---|
| `name` | Yes | – | Parameter name |
| `value` | Yes | – | Value |
| `type` | No | `any` | `int` · `float` · `str` / `string` · `bool` / `boolean` · `json` · `any` |

### Example 1: create, then use

```yaml
steps:
  - name: init_batch
    type: action
    action: set_param
    params:
      name: batch_label
      value: "nightly"
      type: str

  - name: announce
    type: action
    action: log
    params:
      message: "Batch {{ param:batch_label }} started"
    depends_on: [init_batch]
```

### Example 2: change a value later

```yaml
  - name: mark_partial
    type: action
    action: assign_param
    params:
      name: batch_label
      value: "nightly-partial"
    depends_on: [load_optional]
```

### Example 3: typed values

```yaml
- name: set_limits
  type: action
  action: set_param
  params:
    name: max_rows
    value: "500000"
    type: int          # stored as the number 500000
```

```yaml
- name: set_flag
  type: action
  action: set_param
  params:
    name: full_load
    value: "true"
    type: bool         # stored as True
```

A value that does not match `type` makes the step fail.

> **[FIGURE fig-04-02 · diagram]** Timeline of one run: `set_param batch_label=nightly` → `log` reads it → `assign_param batch_label=nightly-partial` → `bash` reads `$batch_label`, showing the value at each step.

---

# Hydra DSL - Actions and Rollback

With `rollback: true` on the workflow (see *Workflows*), actions that act **outside Hydra** must declare how to undo them.

| Action | Needs `undo:` with `rollback: true` |
|---|---|
| `webhook`, `email`, `bash`, `powershell`, `ssh`, `python` | Yes: an action, or `none` |
| `log`, `delay`, `condition`, `set_param`, `assign_param` | No |

```yaml
- name: create_partition
  type: action
  action: bash
  params:
    command: "./scripts/create_partition.sh {{ param:month }}"
  undo:
    action: bash
    params:
      command: "./scripts/drop_partition.sh {{ param:month }}"
```

- `undo.action` and `undo.params` follow the same rules as any action.
- `undo: none` says "nothing to reverse" explicitly.
- The undo actions run from the last step done to the first.

> **[LAB lab-04-04 · Killercoda]** **Reversible actions** — Write a workflow that creates a folder and calls a webhook, give each an `undo:`, make the last step fail, and watch the undo actions run in reverse order.
