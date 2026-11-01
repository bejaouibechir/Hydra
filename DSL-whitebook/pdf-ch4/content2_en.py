"""Pages 11 à la fin (EN) : 2.3, 2.4, 3. Actions ; le ch. 4 vient de content_en."""
from xml.sax.saxutils import escape as e
import content_en
R = lambda t: ("role", "Role. " + e(t))
P = lambda t: ("p", e(t))
NEW = " (Hydra 0.17.0+)"

SPEC = [
("h2top", "2.3 Pipeline (pipeline.yaml)"),
("h3", "pipeline, from, to"),
("code", '''version: "1.0"
pipeline:
  from: orders        # ID declared in sources.yaml
  to: dwh_orders      # ID declared in destinations.yaml'''),
R("links one source to one destination; transformations are applied between them."),

("h2", "2.4 Transformations (transformations.yaml)"),
("code", '''transformations: ordered list of operations
version: "1.0"
engine: auto           # auto | pandas | duckdb (see below)
transformations:
  - select: { columns: [id, country, amount] }
  - filter: { expr: "amount > 0" }'''),
R("describes data operations executed in their listed order."),
("h3", "Column operations"),
("code", '''select: keeps selected columns.
- select:
    columns: [id, country, amount]   # other columns are removed
rename: renames columns.
- rename:
    mapping: { cust_id: customer_id }   # old: new
cast: changes data types (int, float, str, bool, datetime).
- cast:
    mapping: { amount: float, created: datetime }'''),
("h3", "Row operations"),
("code", '''filter: keeps rows matching the condition.
- filter: { expr: "country == 'BE' and amount >= {{ param:min_amount }}" }
sort: stable sort.
- sort: { by: [country, amount], ascending: [true, false] }
deduplicate: removes duplicates.
- deduplicate: { columns: [customer_id], keep: last }   # first | last
fill_null: fills missing values.
- fill_null: { columns: { country: "N/A", amount: 0 } }   # or value: 0 for all
trim: trims whitespace.
- trim: { columns: [name] }   # default: every text column
clean: cleans text.
- clean: { columns: [status], case: upper }   # none | lower | upper'''),
("h3", "text_to_rows: one row per value" + NEW),
("code", '''- text_to_rows:
    column: tags            # "a;b;c" -> 3 rows, the other columns are copied
    sep: ";"                # default ","
    regex: false            # true: sep is a regular expression, e.g. "[,;]"
    trim: true              # default true: spaces around each value removed
    keep_empty: false       # default false: empty values dropped
    index_column: tag_pos   # optional: position 1, 2, 3...'''),
R("splits a list stored in one cell. A null value, or one with no non-empty part, keeps one row with a null value: no input row is lost."),
("h3", "Calculation"),
("code", '''calculate: creates a column.
- calculate: { column: total_ttc, expr: "amount * 1.2" }
script: restricted Python.
- script:
    inputs: [amount]
    outputs: { amount_x2: float }
    mode: vectorized         # vectorized | row
    code: |
      amount_x2 = amount * params["factor"]   # columns are variables; params = run parameters'''),
("h3", "Aggregation"),
("code", '''aggregate: groups and aggregates.
- aggregate:
    by: [country]
    agg:
      total: { func: sum, col: amount }   # sum | count | mean | avg | min | max | first | last
      n:     { func: count, col: id }'''),
R("one row per group; columns absent from by and agg are dropped."),
("h3", "Window functions: window" + NEW),
("code", '''- window:
    partition_by: [customer_id]                  # optional: whole table without it
    order_by: [order_date, {col: amount, desc: true}]
    columns:
      order_rank:  { func: row_number }
      prev_amount: { func: lag, col: amount, offset: 1, default: 0 }
      running:     { func: cumsum, col: amount }
      cust_total:  { func: sum, col: amount }'''),
R("adds columns and keeps every row, in its input order (unlike aggregate)."),
("table", ([["Family", "Functions", "Options"],
  ["Rank", "row_number, rank, dense_rank", "none"],
  ["Offset", "lag, lead", "col, offset (default 1), default (null)"],
  ["Running", "cumsum, cumcount, cummin, cummax", "col (optional for cumcount)"],
  ["Whole partition", "sum, mean, min, max, count, first, last", "col"]],
  [10, 110, 330])),
P("Rank, offset and running functions need order_by. Null values sort last, even with desc; ties keep the input order. A running function skips null values (the row keeps the running value). Partition functions ignore nulls, as aggregate does; first and last return the first and last non-null value in order_by order. cumsum, cummin, cummax, sum and mean need a numeric column."),
("h3", "Combining data (an additional source declared in sources.yaml)"),
("code", '''join: join.
- join:
    right: customers
    key: customer_id          # or left_key / right_key
    how: left                 # inner | left | right | outer | cross
merge: merge/update.
- merge: { right: corrections, key: id, delete_unmatched: false }
union: stacks rows.
- union: { right: orders_archive, distinct: true }'''),
("h3", "Cross join: every row × every row" + NEW),
("code", '''- join:
    right: calendar
    how: cross                # no key, left_key or right_key
    max_rows: 5000000         # default 10,000,000 rows produced'''),
R("pairs each row with each row of right (left order, then right order). The run stops before producing the batch that would exceed max_rows."),
("h3", "Reshaping"),
("code", '''pivot: rows into columns.
- pivot: { index: [country], column: month, values: amount, aggfunc: sum }
unpivot: columns into rows.
- unpivot: { id_vars: [id], value_vars: [jan, feb], var_name: month, value_name: amount }
transpose: transposes rows and columns.
- transpose: { index_col: id, header_name: column }
engine: execution engine (at transformations.yaml root)
engine: duckdb   # auto (default) | pandas | duckdb'''),
R("auto chooses DuckDB above 2,000,000 rows for global operations (aggregate, sort, right/outer join, window). HYDRA_ENGINE overrides the file setting."),
("h3", "Expressions (expr, when)"),
P("Comparison, logical (and, or, not), and arithmetic operators; safe evaluation without arbitrary code execution."),

("h1", "3. Actions"),
("h3", "An action is a step with type: action. Common structure:"),
("code", '''- name: my_step
  type: action
  action: <name>
  params: { ... }
  undo: { ... }      # required for webhook, email, bash, powershell, ssh, python'''),
("h3", "log: writes a message"),
("code", '''action: log
params: { message: "Loading complete" }   # default: "Step '<name>' executed"'''),
R("records execution progress."),
("h3", "delay: waits"),
("code", '''action: delay
params: { seconds: 30 }   # or duration'''),
R("allows an external system to stabilize between steps."),
("h3", "condition: evaluates a condition and stores the result"),
("code", '''action: condition
params:
  name: is_big                      # parameter receiving the result
  mode: expr                        # expr | structured
  expr: "{{ param:rows }} > 1000"
  # structured: left / op / right'''),
R("provides a value for the when expressions of subsequent steps."),
("h3", "webhook: HTTP call"),
("code", '''action: webhook
params:
  url: https://hooks.example.com/notify
  method: POST                      # default POST
  headers: { Authorization: "Bearer ${SECRET:api.token}" }
  body: { status: done }            # mapping (JSON) or text
undo:
  action: webhook
  params: { url: https://hooks.example.com/cancel }'''),
R("notifies or triggers an external system."),
("h3", "email: sends an email"),
("code", '''action: email
params:
  to: ops@example.com
  subject: "Report ready"
  body: "See attachment"
  from_addr: hydra@example.com      # default hydra@localhost
  smtp_host: smtp.example.com       # default localhost
  smtp_port: 587                    # default 1025
  username: etl
  password: ${SECRET:smtp.password}
  use_tls: true                     # STARTTLS
undo: none'''),
R("alerts the relevant recipients."),
("h3", "bash: shell command"),
("code", '''action: bash
params:
  command: "./scripts/archive.sh"
  working_dir: ./scripts            # default current directory
  timeout: 60                       # seconds, default 60
undo: { action: bash, params: { command: "./scripts/restore.sh" } }'''),
R("executes a system command (Linux/macOS)."),
("h3", "powershell: PowerShell command"),
("code", '''action: powershell
params: { command: "Copy-Item a.csv b.csv", timeout: 60 }
undo: { action: powershell, params: { command: "Remove-Item b.csv" } }'''),
R("Windows equivalent of bash."),
("h3", "ssh: remote command"),
("code", '''action: ssh
params:
  host: srv1.example.com
  username: etl
  command: "systemctl restart app"
  port: 22                          # default 22
  key_path: ~/.ssh/id_ed25519       # preferred
  password: ${SECRET:ssh.password}  # if no key
  timeout: 30
undo: none'''),
R("controls a remote server."),
("h3", "python: Python code"),
("code", '''action: python
params:
  script: |                         # inline code or file_path: job.py
    print("hello")
  working_dir: .
  timeout: 60
undo: none'''),
R("implements custom logic not covered by the DSL."),
("h3", "set_param: creates a parameter for subsequent steps"),
("code", '''action: set_param
params: { name: batch_label, value: "nightly", type: str }   # fails if already defined'''),
R("shares a value between steps ({{ param:batch_label }})."),
("h3", "assign_param: updates an existing parameter"),
("code", '''action: assign_param
params: { name: batch_label, value: "partial" }   # fails if it does not exist'''),
R("updates an existing value during a run."),
("pagebreak", None),
] + content_en.SPEC

HEADER, FOOTER = content_en.HEADER, content_en.FOOTER
