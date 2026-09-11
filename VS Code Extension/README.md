# HYDRA ETL — VS Code extension

Write Hydra manifests faster: context-aware completion, live validation, hover
documentation and ready-to-fill skeletons.

The extension **runs nothing** and is not a replacement for `hdrctl`. It speeds
up authoring and flags structural mistakes. Cross-file consistency — does the
`from` of `pipeline.yaml` match a declared source, does a step's job directory
exist — remains the job of `hdrctl validate`.

---

## What it covers

| File | What you get |
|---|---|
| `sources.yaml` | connector types, `connection` keys matching the chosen type, extraction and schema options |
| `destinations.yaml` | load modes, `key` required in `upsert` mode, `batch_size` bounds |
| `pipeline.yaml` | `from` / `to` required |
| `transformations.yaml` | all 18 operations and their parameters, with allowed values |
| `workflow.yaml` | steps, dependencies, built-in actions, retry policy, `cron` required in `schedule` mode |

Three complementary mechanisms:

**Context-aware completion.** The keys offered depend on where you are in the
document. Inside a `mysql` source, `connection` offers
`host`/`port`/`database`/`user`/`password`; inside a `web_api` source it offers
`base_url`/`auth`/`pagination`. Enumerated values appear as a list, each with
its explanation.

**Live validation.** Unknown key, wrong type, value outside the allowed set,
missing required field, unsatisfied conditional constraint. Errors are
underlined in the editor and listed in the Problems panel.

**Snippets.** 32 Emmet-style skeletons. Typing `hsrc-mysql` followed by Tab
produces a complete MySQL source, cursor on the first field to fill, Tab to move
on, dropdown menus on fixed-value fields.

---

## Install

No compilation: the extension is purely declarative — no TypeScript, no
`npm install`.

### 1. Prerequisite

The **Red Hat YAML** extension provides the engine. VS Code installs it
automatically (it is declared under `extensionDependencies`), but it can also be
installed by hand:

```
code --install-extension redhat.vscode-yaml
```

### 2. Build the package

```powershell
cd "C:\Users\DELL\Desktop\Hydra\VS Code Extension"
python build_vsix.py
```

This produces `hydra-etl-0.1.2.vsix`. The script needs neither Node, npm nor
`vsce`: a `.vsix` is a ZIP archive, and `build_vsix.py` assembles it with the
Python standard library.

> **Do not copy the folder by hand into `.vscode\extensions`.** Since VS Code
> 1.74, `extensions\extensions.json` acts as the registry: a directory missing
> from it is ignored at startup, silently. Installation must go through a
> `.vsix`.

### 3. Install

```powershell
code --install-extension "C:\Users\DELL\Desktop\Hydra\VS Code Extension\hydra-etl-0.1.2.vsix"
```

Without the command line: `Ctrl+Shift+X` → `...` menu at the top of the panel →
**Install from VSIX…** → pick the file.

Do not double-click the `.vsix` in Explorer — Windows hands it to the Visual
Studio installer, which will refuse it.

Then reload VS Code: `Ctrl+Shift+P` → **Developer: Reload Window**.

### 4. Confirm it is active

`Ctrl+Shift+X`, search for "HYDRA ETL". It should appear under the identifier
`Bechir Bejaoui.hydra-etl`. The identifier contains a space, so quote it in a shell.

### Uninstall

```powershell
code --uninstall-extension "Bechir Bejaoui.hydra-etl"
```

---

## How to test

Open the `examples/` folder in VS Code.

### Test 1 — validation

Open `examples/invalid_examples/destinations.yaml`. It holds four deliberate
errors, each documented in a comment. Open the Problems panel (`Ctrl+Shift+M`):
all four should be listed, with matching line numbers.

Repeat with `workflow.yaml` (5 errors) and `transformations.yaml` (6 errors).

Conversely, `examples/valid_job/` and `examples/valid_workflow/` must produce
**no** error at all.

### Test 2 — completion

In `examples/valid_job/sources.yaml`, put the cursor on an empty line under
`extract:` and press `Ctrl+Space`: the list should offer `table`, `query`,
`collection`, `filter`, `limit` and `batch_size`, each with its description.

Now replace `type: mysql` with `type: web_api`, then press `Ctrl+Space` again
under `connection:`: the offered keys should switch to `base_url`, `auth`,
`pagination` and `headers`. That is conditional validation at work.

### Test 3 — hover documentation

Hover over `mode: upsert` in `examples/valid_job/destinations.yaml`: a tooltip
should explain the three load modes.

### Test 4 — snippets

1. Create an empty file named `sources.yaml`.
2. Type `sources:`
3. On a new line, press `Esc`, then type `hsrc-pg` and press `Tab`.
4. Press `Tab` again to move between fields.

The full PostgreSQL skeleton should appear, cursor on the source name. Tab moves
between fields; on the `table`/`query` field a dropdown should open.

The `Esc` matters: on an empty line the schema opens its own key suggestions, and
that popup captures the `Tab` before the snippet does. Typing `h` then
`Ctrl+Space` lists all 32 prefixes.

### Test 5 — schema consistency (automated)

```
pip install jsonschema pyyaml
python examples/check_schemas.py
```

The script checks that the five schemas are valid, that the correct examples
pass, and that the faulty examples raise the errors they advertise.

---

## Distribution

The `.vsix` produced by `build_vsix.py` can be sent as-is to other people, or
attached to a GitHub release. It installs through `code --install-extension` or
**Install from VSIX…**.

To reproduce the conditions of a clean machine, test it in a fresh profile:

```
code --profile=test-hydra
```

When the time comes to publish on the marketplace, `vsce` (which requires Node)
takes over from `build_vsix.py` — it adds signing and the upload to the gallery.
The package contents will not change.

---

## Layout

```
VS Code Extension/
├── package.json                  declarative wiring (schemas, snippets, defaults)
├── README.md
├── CHANGELOG.md
├── .vscodeignore
├── build_vsix.py                 builds the .vsix without npm or vsce
├── images/
│   ├── icon.png                  128×128, derived from studio/public/Hydra.png
│   └── icon@256.png              spare, excluded from the package
├── schemas/
│   ├── sources.schema.json
│   ├── destinations.schema.json
│   ├── pipeline.schema.json
│   ├── transformations.schema.json
│   └── workflow.schema.json
├── snippets/
│   └── hydra.json                32 snippets
└── examples/                     test sandbox, excluded from the package
    ├── valid_job/
    ├── valid_workflow/
    ├── invalid_examples/
    └── check_schemas.py
```

---

## Limitations of 0.1.2

- **Structural** validation only. No cross-file checking.
- The schemas were written by hand from Hydra's Pydantic models. They may drift
  as the DSL evolves. The planned remedy is a `scripts/gen_schemas.py` on the
  Hydra side that regenerates them from `internal/parser/` and
  `workflow/models.py`.
- Plugin-supplied connectors do not appear in the `type` completion lists,
  though they are accepted without error.
- Snippets apply to every YAML file, not only Hydra manifests. The `h` prefix
  keeps collisions rare.

## Ideas for 0.2.0

- Offer the source and destination identifiers actually declared in the project
  when filling in `pipeline.from` / `pipeline.to`.
- Offer the directories under `jobs/` when filling in `step.job`.
- Complete real file paths on `extract.table` for file connectors.
- Spanish schema descriptions, matching Hydra's `en` + `es` i18n support.
