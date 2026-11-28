export type DeepPage = {
  overview: string[];
  analysis: { title: string; paragraphs: string[]; source: number }[];
  extraSources: { label: string; url: string }[];
  prerequisites: string[];
  procedure: { title: string; detail: string }[];
  commandTitle: string;
  command: string;
  verification: string[];
  rollback: string;
  faqs: { question: string; answer: string }[];
};

export const deepPages: Record<string, DeepPage> = {
  dlt: {
    overview: [
      'The first design question is where the difficult work lives. A dlt source can be a Python generator, a resource or a structured source with its own configuration. dlt then extracts, normalizes and loads records, maintains schema information and can restore state from a destination. Hydra starts from a declared source and applies a named sequence of ETL operations before writing a declared destination. Those models overlap for ordinary batch data movement, but they place customization in different places.',
      'A team with many bespoke REST APIs may value dlt’s Python surface and incremental loading more than a shorter manifest. A team whose workload is stable CSV, SQL or another Hydra-supported connector may value explicit transformations and a project workflow that reviewers can inspect without reading extraction code. Decide per pipeline, not per logo. A useful inventory records source type, cursor, destination write mode, schema policy, transformation logic, schedule and downstream readers.',
      'The browser simulator deliberately reduces this comparison to 14 CSV orders. It can demonstrate the shape of a declarative transformation and how a changed filter threshold affects the output. It cannot compare connector breadth, dlt state recovery, schema evolution, nested records or throughput. Those are acceptance tests for a real migration, not numbers that can be inferred from a toy file.'
    ],
    extraSources: [
      { label: 'dlt pipeline execution', url: 'https://dlthub.com/docs/general-usage/pipeline' },
      { label: 'dlt schema contracts', url: 'https://dlthub.com/docs/general-usage/schema-contracts' },
      { label: 'dlt resource configuration', url: 'https://dlthub.com/docs/general-usage/resource' },
    ],
    analysis: [
      { title: 'Extraction and connector ownership', source: 0, paragraphs: [
        'dlt accepts resources, generators and iterable data. That is particularly useful when the source needs pagination, authentication renewal, nested response handling or custom Python before rows can be produced. The pipeline call turns those records into load packages for the destination. In Hydra, source declarations make routine extraction visible in YAML; any source-specific behavior must be supported by the connector or implemented separately.',
        'For an integration pilot, document the exact dlt resource and the destination table it creates. If that resource is a nontrivial API client, retain dlt for extraction and let Hydra read the landed table or a controlled export. Rewriting the API client first would mix an extraction rewrite with an ETL migration and make any row mismatch hard to diagnose.'
      ] },
      { title: 'Schema evolution and contracts', source: 1, paragraphs: [
        'dlt can evolve destination schemas as new fields appear, and schema contracts can freeze, discard or evolve changes at table, column and type level. Those modes are part of the behavior of a production pipeline. Hydra has schema declarations and drift handling for supported sources, but a similarly named setting should not be assumed to have identical nested-table or coercion semantics.',
        'Test at least three fixtures: a new optional field, a changed type and a missing expected field. Record whether each system adds a column, rejects a row, discards a value or fails the run. Compare the resulting destination schema as well as the row count. A successful run that silently changes a column is not a successful migration if a downstream model expects the old contract.'
      ] },
      { title: 'Incremental state and load disposition', source: 0, paragraphs: [
        'dlt uses pipeline state, incremental cursors and write dispositions such as append, replace and merge. Hydra also has load modes, but a load mode describes target writes; it does not by itself reproduce a dlt cursor or the replay of a partially processed source. The first full load can look identical while the second run diverges.',
        'Write down the dlt state identifier, cursor column, initial cursor value, primary or merge key and late-arrival policy. Run a first batch, then an update to an existing key, then a delayed record older than the current cursor. Observe both destination and state after each run. This sequence reveals whether a direct Hydra replacement is suitable or whether dlt should remain the ingestion layer.'
      ] },
      { title: 'Transformation and review', source: 2, paragraphs: [
        'A dlt resource may map or filter items before load, while heavier transformations commonly take place in Python or a downstream SQL tool. Hydra places supported operations such as cast, filter, aggregate and sort in the job definition. The difference matters when a reviewer needs to answer which rows were dropped and where a derived column was created.',
        'Translate only operations whose Hydra behavior you can verify. For a CSV amount column, cast to a numeric type before summing; treating text as numeric is a common source of apparently successful but wrong results. Save input fixtures and expected output in version control, then run the same fixture through both pipelines during the pilot.'
      ] },
      { title: 'Operations and fit', source: 0, paragraphs: [
        'dlt exposes load information and pipeline state for diagnosing ingestion. Hydra exposes validation, CLI runs and workflow reports for its jobs. Neither product should be judged solely by lines of code. Recovery after a network interruption, behavior under schema drift and visibility of the failed row matter more than a short example.',
        'Keep dlt where Python extraction and its state model are the value. Evaluate Hydra where the source and destination are supported and the transformation is mostly declarative. A mixed architecture is valid: dlt loads a raw table, Hydra validates and transforms it, and one orchestrator owns the schedule and retry boundary.'
      ] },
    ],
    prerequisites: ['A named dlt pipeline and its current destination, with a reproducible input fixture.', 'The dlt cursor, write disposition, schema contract and merge key, if any.', 'A separate Hydra staging output that cannot overwrite the production table.', 'Hydra CLI installed where the handoff command will run, with the same credentials policy as the existing pipeline.'],
    procedure: [
      { title: 'Freeze the current contract', detail: 'Export the dlt schema, current state and destination DDL. Capture two representative runs, including one with a changed record. Record row counts, keys, null rates and the exact query or file consumers use. Without this baseline, a clean Hydra run can still hide a semantic regression.' },
      { title: 'Pick a handoff', detail: 'For coexistence, leave the dlt resource unchanged and expose its landed table or an immutable export to Hydra. For replacement, choose a dlt resource that reads a Hydra-supported source without custom Python pagination or nested normalization. Do not change both extraction and loading in the same first experiment.' },
      { title: 'Build and validate the Hydra job', detail: 'Create sources.yaml, pipeline.yaml, transformations.yaml and destinations.yaml for the chosen input. Point the destination to a new table or file. Start with the downloadable orders fixture to prove the local CLI, then change one connection at a time. Run hdrctl validate with strict checks before reading real data.' },
      { title: 'Run parallel comparisons', detail: 'Feed the same frozen snapshot to dlt and Hydra. Compare keys, values, output schema and rejected rows, not just total row count. Repeat with an added field, a changed type and an empty value so the schema contract difference is visible.' },
      { title: 'Test the second run', detail: 'Insert a new record, update an existing key and supply a late record. Compare the dlt state and target with the Hydra target. If Hydra needs an external watermark or preprocessing step, document that component explicitly before moving the schedule.' },
      { title: 'Cut over one owner', detail: 'Choose which process starts the pipeline and owns retries. Keep dlt state and configuration available until the Hydra run has completed several normal cycles and a recovery drill. Disable the old schedule only after the new path has demonstrated equivalent results.' },
    ],
    commandTitle: 'A minimal handoff after the existing dlt load',
    command: '# In a script or scheduler that already runs the dlt pipeline:\npython load_with_dlt.py\nhdrctl validate /srv/hydra/orders --strict\nhdrctl run /srv/hydra/orders\n# Configure Hydra sources.yaml to read the table/file dlt wrote.\n# Configure Hydra destinations.yaml to write a separate staging target.',
    verification: ['First and second runs have expected key counts and no duplicate keys.', 'Destination types and nullable columns match the published contract.', 'A late-arriving row follows the agreed policy.', 'An interrupted run can be retried without data loss or duplication.', 'The previous schedule is disabled only after the new one succeeds.'],
    rollback: 'Stop the new scheduler, point consumers back to the original dlt destination, and resume the dlt pipeline from its preserved state. Do not reset or delete dlt state during the pilot; a clean rollback depends on it.',
    faqs: [
      { question: 'What is the main difference between dlt and Hydra ETL?', answer: 'dlt is a Python library whose resources produce records for extraction, normalization and loading. Hydra describes supported sources, transformations and destinations in YAML jobs and can coordinate them in workflows. For a custom API, Python extraction may be an advantage; for a stable batch job, an explicit manifest may be easier to review.' },
      { question: 'Can Hydra replace a dlt REST API source?', answer: 'Only if the Hydra connector can express the API’s authentication, pagination, rate limits and response shape. A generic “web API” label does not prove parity. Keep the dlt resource when custom Python handles those details and introduce Hydra after the data lands.' },
      { question: 'Does a Hydra upsert replace dlt incremental loading?', answer: 'No. Upsert controls writes at the destination; incremental extraction controls which source records are read. Test cursor advancement, late arrivals, updates and retry state before treating the behaviors as equivalent.' },
      { question: 'How should schema drift be compared?', answer: 'Use fixtures with a new field, a type change and a missing field. Compare both pipeline status and the physical destination schema. dlt schema contracts and Hydra drift policies must be mapped by observed behavior rather than by similar names.' },
      { question: 'Can dlt and Hydra run in the same project?', answer: 'They can run in the same deployment or be chained by an external scheduler, provided the handoff is a defined table or file. One component should own triggering and retries so a failed transformation does not accidentally rerun ingestion twice.' },
      { question: 'Should I migrate nested JSON normalization to Hydra first?', answer: 'Usually not. Nested-record normalization can create child tables and special keys in dlt. Start with a flat, stable source and verify its semantics before attempting nested data.' },
      { question: 'What should be compared after the first successful run?', answer: 'Run a second and third batch with updates, duplicates and late-arriving records. Count rows by key, inspect changed values and record how each tool resumes after a deliberately interrupted load.' },
      { question: 'Which tool is better for a Python-heavy team?', answer: 'A team that already writes and tests custom Python extractors may prefer dlt’s programming model. Hydra is attractive when the workload fits its supported DSL and the team wants operations expressed and reviewed declaratively.' },
      { question: 'Can the browser simulator measure dlt performance?', answer: 'No. It executes neither dlt nor the Hydra engine. It models one small Hydra transformation on sample rows and shows line counts for the displayed examples, which are not a throughput or cost benchmark.' },
      { question: 'What is the safest rollback after a dlt migration pilot?', answer: 'Preserve the original dlt pipeline, state and destination. Stop the new schedule, restore downstream reads to the old target and resume dlt from the saved state. Avoid deleting or rewriting state during the pilot.' },
    ],
  },
  talend: {
    overview: [
      'Talend Studio Jobs are designed as connected components. Components can extract, filter, map, aggregate, route rejected rows and load targets, while context variables select different environment values. Hydra describes an ETL job through source, pipeline, transformation and destination YAML files. The comparison is therefore not “visual versus text” alone: connector behavior, metadata propagation, rejection paths and deployment controls must all be examined.',
      'A complex Talend estate may contain reusable Joblets, tMap expressions, Java routines, context groups and Talend Management Console schedules. A small file-to-file Job may use only a handful of components. Those two cases have very different migration costs. The first Hydra pilot should select a Job with a stable schema, a single output and no proprietary or custom Java component. Record what the Job actually writes, including rejected rows and side effects.',
      'The simulator presents a component map because a Talend Job is not normally represented by a single hand-written script. Its apparent line count cannot be compared fairly with YAML. Treat the map as a guide to the operation sequence and use the actual Talend Job export and runtime results for a professional evaluation.'
    ],
    extraSources: [
      { label: 'Talend components for Jobs', url: 'https://help.qlik.com/talend/en-US/components/8.0/About' },
      { label: 'Talend contexts and variables', url: 'https://help.qlik.com/talend/en-US/studio-user-guide/8.0-R2026-09/contexts-and-variables?ver=22' },
      { label: 'Talend tSystem component', url: 'https://help.qlik.com/talend/en-US/components/8.0/system/tsystem' },
    ],
    analysis: [
      { title: 'Component graph and transformation semantics', source: 0, paragraphs: [
        'Talend’s component palette provides dedicated building blocks. A tFileInputDelimited to tMap to tAggregateRow to tFileOutputDelimited chain may look similar to a Hydra source, cast/filter/aggregate steps and destination. But the Talend graph also carries row links, error links, component order and component-specific settings. A visual resemblance does not prove the same output.',
        'During migration, map each input and output link, not just each component name. Check tMap expression language, null behavior, lookup join strategy, sort ordering and reject links. If a Talend component emits two outputs, a single linear Hydra job may not preserve that routing without a second job or explicit intermediate target.'
      ] },
      { title: 'Schemas, metadata and rejected rows', source: 0, paragraphs: [
        'Talend schema metadata can define field types, lengths, date formats and nullable flags at the component level. Hydra source schema, casts and destination settings must be chosen to reproduce the intended contract. A field typed as string in a CSV may look correct in a preview yet fail when an amount is aggregated or loaded into a numeric SQL column.',
        'Create a fixture with valid records, one malformed number, one missing mandatory value and one duplicate business key. Capture Talend’s main and reject outputs separately. In Hydra, decide explicitly whether the equivalent behavior is failure, cleaning, filling or a separate reject path. Count every input row: accepted, rejected and duplicated.'
      ] },
      { title: 'Contexts, secrets and deployment', source: 1, paragraphs: [
        'Talend context variables allow a Job to run with values for development, test or production. Values can also be loaded dynamically. Hydra has project parameters, named environments and secret resolution, but their precedence and storage are not a byte-for-byte copy of Talend contexts. A migration must include a mapping table for each setting, its source and its effective value at run time.',
        'Do not place database passwords in YAML merely because the new job is text based. Test the same job under dev and prod-like settings with separate credentials and targets. Capture how both systems log failures so connection details or secrets are not exposed in run reports.'
      ] },
      { title: 'Coexistence inside a Talend Job', source: 2, paragraphs: [
        'Talend tSystem can invoke a system command as part of a larger Job. That provides a reversible integration path: keep the existing upstream Talend components, materialize a file or staging table, then call hdrctl on a separate Hydra job. Talend remains the scheduler and failure owner while the ETL slice is evaluated.',
        'This bridge needs operational discipline. Use an absolute Hydra project path, ensure hdrctl is installed on the same execution host or container, supply credentials through approved environment or secret mechanisms, and propagate the exit code. Configure the Talend link so a failed Hydra command cannot be reported as an overall success.'
      ] },
      { title: 'When a full replacement is a poor fit', source: 0, paragraphs: [
        'Talend installations often carry connectors, data quality rules, reusable components and administrative processes that go far beyond a simple row transform. Replacing those capabilities requires workload-specific evidence. Keep Jobs that depend on unsupported connectors, complex routing or Java routines in Talend while simpler Jobs move incrementally.',
        'The professional question is not whether the YAML is shorter. Ask whether the same dataset is produced, whether bad rows and retries are handled, whether operations staff can diagnose a failed run, and whether downstream consumers see the same contract. If any of those answers is unknown, keep the Talend Job in control.'
      ] },
    ],
    prerequisites: ['A Talend Job export or screenshots of every component and row link.', 'The input and output schema, context groups, secret sources and reject flow.', 'A representative fixture with valid and invalid records.', 'Hydra CLI installed on the host that will execute tSystem, if coexistence is the chosen route.'],
    procedure: [
      { title: 'Document the Job graph', detail: 'List components in run order, including pre- and post-job components, lookups, reject links and triggers. Record every expression and context variable. The first pilot should have one source, one main output and a simple deterministic transform.' },
      { title: 'Preserve Talend output', detail: 'Run the current Job on a frozen input and save the main output, rejected rows, schema and Job log. Do not replace the Talend destination yet. These artifacts become the acceptance reference for Hydra.' },
      { title: 'Create a parallel Hydra job', detail: 'Map the input to sources.yaml, the main transformation to transformations.yaml and the output to a separate destination. Reproduce casts and null handling explicitly. Use hdrctl validate --strict before the first run; then run against the same frozen input.' },
      { title: 'Compare row paths', detail: 'Compare sorted output by business key, not display order. Reconcile row counts across accepted and rejected paths, numeric rounding, date parsing and duplicates. If Talend produces multiple outputs, build and test each target separately.' },
      { title: 'Integrate through tSystem if useful', detail: 'For coexistence, leave Talend scheduling in place and add a tSystem component after the source handoff. Call hdrctl with an absolute path and verify that nonzero status fails the Talend Job. Keep the Hydra destination isolated until the comparison is clean.' },
      { title: 'Switch a single Job', detail: 'Move only this Job’s trigger after several clean cycles. Map Talend contexts to Hydra environments and parameters, document the new secret source, and keep the original Job deployable for rollback.' },
    ],
    commandTitle: 'Command for a Talend tSystem bridge',
    command: '# Configure tSystem on the same host as the Hydra CLI.\n# Command text (Linux example):\nhdrctl validate /srv/hydra/orders --strict && hdrctl run /srv/hydra/orders\n# Feed Hydra from a Talend staging file/table.\n# Keep the output separate until row and reject counts match.',
    verification: ['Talend main and reject counts reconcile with Hydra outcomes.', 'The effective dev/test/prod values match the context mapping.', 'A Hydra failure produces a failing Talend Job status.', 'No secrets appear in YAML or logs.', 'The original Job remains deployable.'],
    rollback: 'Disable the new Hydra call or schedule, restore the Talend output link and rerun the preserved Talend Job on the affected batch. Keep the frozen fixture and original context configuration until the replacement has proven stable.',
    faqs: [
      { question: 'Can Hydra import a Talend Studio Job automatically?', answer: 'This guide does not claim an automatic Job importer. Talend component graphs, expressions, contexts and reject links need an explicit mapping. Start with a small Job and compare actual output before considering a wider migration.' },
      { question: 'What is the closest Hydra equivalent of tMap?', answer: 'There is no universal one-to-one equivalent. A simple tMap expression may translate to select, rename, cast, calculate, filter or join steps. Multiple output links and Java expressions may require more than one Hydra job or a retained Talend component.' },
      { question: 'Can Talend call Hydra without replacing the Job?', answer: 'Yes. A Talend tSystem component can run hdrctl on the execution host. Use an absolute path, make credentials available securely, and ensure a nonzero Hydra exit code fails the Talend Job.' },
      { question: 'How do Talend contexts map to Hydra environments?', answer: 'List each Talend context variable, its default and any dynamically loaded value. Map nonsecret settings to Hydra parameters or environment configuration, and secrets to Hydra’s secret resolution. Test effective values in each environment rather than assuming identical precedence.' },
      { question: 'What happens to Talend reject rows?', answer: 'They must be accounted for explicitly. Capture the Talend reject link output and decide whether the Hydra job should fail, clean, skip or write an equivalent reject target. Equal main-row counts alone do not prove equal error behavior.' },
      { question: 'Is YAML easier to review than a Talend Job?', answer: 'A small linear job may be easier to diff as YAML, but that is a review preference, not an objective quality score. Talend visual graphs can be clearer for branching flows. Evaluate review and troubleshooting with the real Job your team owns.' },
      { question: 'Can Hydra replace Talend’s connector catalog?', answer: 'Only where Hydra supports the exact source and destination behavior required by the Job. A Talend connector may include application-specific semantics that a generic file or SQL connector does not reproduce.' },
      { question: 'Which Talend Job should migrate first?', answer: 'Choose a deterministic file or database Job with one main output, stable schema and no custom Java or specialized connector. Avoid complex tMap branching, CDC and data-quality routing in the first pilot.' },
      { question: 'How should numeric and date fields be tested?', answer: 'Create boundary fixtures with empty values, invalid dates, decimals and large numbers. Compare parsed types and final destination values. Explicit Hydra casts are important when CSV input begins as text.' },
      { question: 'What is a safe Talend rollback plan?', answer: 'Retain the original Job and context definitions. Stop the Hydra call or schedule, restore the original destination link and rerun the affected batch using Talend’s existing operational procedure.' },
    ],
  },
  dbt: {
    overview: [
      'dbt and Hydra overlap at the word “transformation,” but their data boundaries differ. dbt models transform data inside a supported warehouse or database using SQL and materializations. Its graph also includes tests, sources, snapshots, exposures and documentation. Hydra can read from supported systems, transform with its DSL and write to destinations, then orchestrate project jobs and actions. A dbt estate should usually be integrated before any model is considered for replacement.',
      'The most common useful boundary is an ingestion handoff: Hydra loads or prepares a source table, then dbt builds the downstream analytical models. This keeps dbt’s model tests and exposures intact. A second boundary is a file export after dbt, which Hydra can deliver to another destination. Replacing a dbt model is justified only when the model is simple, isolated and its test and lineage responsibilities are reassigned.',
      'The sample simulator filters and aggregates a tiny order file. A dbt SQL model could produce the same final rows in a warehouse, but the browser example does not represent dbt materialization, incremental models, warehouse optimizer behavior or test execution. Those are significant parts of a production comparison.'
    ],
    extraSources: [
      { label: 'dbt data tests', url: 'https://docs.getdbt.com/docs/build/data-tests' },
      { label: 'dbt incremental models', url: 'https://docs.getdbt.com/docs/build/incremental-models' },
      { label: 'dbt exposures', url: 'https://docs.getdbt.com/docs/build/exposures' },
      { label: 'dbt build command', url: 'https://docs.getdbt.com/reference/commands/build' },
    ],
    analysis: [
      { title: 'Transformation location and compute', source: 0, paragraphs: [
        'dbt compiles model SQL and asks the warehouse to execute it. That makes the warehouse’s SQL dialect, access control, materialization and optimizer part of the result. Hydra executes its supported ETL steps in its engine and can write to a warehouse or file. A comparison should specify whether the data is already in a warehouse or must first be moved there.',
        'If the source is a CSV and the target is another file, dbt would require a loading boundary before its SQL model. If the source is already a warehouse table with many downstream models, dbt can be a natural place to keep the transformation. Count all components required for the full workflow, but do not attribute an unrelated ingestion tool’s behavior to dbt itself.'
      ] },
      { title: 'Tests, lineage and consumers', source: 0, paragraphs: [
        'dbt data tests can assert conditions on models, sources, snapshots and seeds. Exposures describe downstream uses such as dashboards. The ref() graph makes dependencies explicit and lets teams select related models. Removing one model can therefore break a test, a selector, a consumer or documentation even when its SQL is short.',
        'Before moving a model, inspect its parents, children, tests and exposures. If it is a published analytical contract, keep it in dbt. A Hydra job can own ingestion or pre-cleanup and leave the dbt model as the authoritative published dataset.'
      ] },
      { title: 'Incremental and historical behavior', source: 1, paragraphs: [
        'An incremental dbt model uses SQL filters and often a unique key so subsequent runs process only the intended rows. Snapshots serve historical change tracking. A Hydra upsert may keep a target current, but it does not automatically reproduce an incremental model’s is_incremental() predicate or snapshot history.',
        'If replacing a model, test first build, a second build with a changed row, a full refresh and late-arriving data. Inspect the resulting table and downstream dependencies. For history, compare validity intervals or snapshot semantics explicitly; a current-state table is not a substitute for a historical one.'
      ] },
      { title: 'A practical shared architecture', source: 3, paragraphs: [
        'Hydra can own a bounded extract-and-load job into a raw or staging table. On successful completion, the existing scheduler can call dbt build for the relevant model selection. dbt build runs selected resources and their tests according to its selection rules. This keeps one quality gate for warehouse models while Hydra owns the cross-system movement.',
        'Define one handoff contract: table name, schema, update cadence, transaction visibility and the condition that means data is ready. Keep a single schedule owner. If dbt already runs through Airflow, it may be simplest to add a Hydra task before the dbt task rather than moving the entire schedule.'
      ] },
      { title: 'When to migrate a simple model', source: 2, paragraphs: [
        'A model that only filters and groups a single source may be a reasonable Hydra candidate if no downstream ref(), test, exposure or BI reader depends on the intermediate relation. Even then, verify data types, null grouping, sort order and destination mode. The existence of a short SQL query does not itself make migration beneficial.',
        'Prefer coexistence when dbt’s tests, documentation and lineage are already delivering value. A migration should remove a concrete operational cost or simplify a cross-system boundary; it should not remove a working analytical contract to make a comparison chart look favorable.'
      ] },
    ],
    prerequisites: ['A dbt project with the selected model’s parents, children, tests and exposures inventoried.', 'The warehouse source table or file Hydra will produce, and a staging target for the pilot.', 'A frozen input fixture and expected model output.', 'A clear schedule owner and credentials for Hydra and dbt without placing passwords in project files.'],
    procedure: [
      { title: 'Trace the dbt graph', detail: 'Use the dbt project to identify source(), ref(), model materialization, tests, snapshots and exposures for the target area. Record whether a dashboard or another model reads the table directly. This defines what Hydra must not disturb.' },
      { title: 'Choose the boundary', detail: 'The low-risk choice is Hydra ingestion into a staging relation followed by the existing dbt models. Only consider moving a simple model when it has no important downstream dbt contract. Create a new schema or table for the pilot.' },
      { title: 'Build the Hydra ingestion job', detail: 'Define source, pipeline and destination YAML and any necessary cast or cleaning steps. Validate the project with hdrctl validate --strict. Confirm that the destination table matches the columns and types expected by dbt source definitions.' },
      { title: 'Run the chain once', detail: 'Run the Hydra job, then run dbt build for a narrow selection. Keep the commands serial so dbt starts only after Hydra reports success. Save both logs and the target data for comparison.' },
      { title: 'Exercise quality gates', detail: 'Run the model’s existing dbt tests, freshness checks where configured, and any downstream model selection. Test a malformed row and a delayed batch. Compare warehouse row counts and source freshness against the previous ingestion path.' },
      { title: 'Assign ownership and cut over', detail: 'Choose whether Hydra, the existing orchestrator or dbt platform scheduling starts the chain. Disable the duplicate trigger. Keep dbt model definitions, tests and exposures unless a separate reviewed change explicitly retires them.' },
    ],
    commandTitle: 'Hydra ingestion followed by dbt model build',
    command: '# Run in one existing scheduler or deployment script.\nhdrctl validate /srv/hydra/ingest_orders --strict\nhdrctl run /srv/hydra/ingest_orders\ndbt build --project-dir /srv/dbt --select orders_by_status+\n# dbt must point at the staging relation written by Hydra.\n# Do not start dbt when hdrctl exits nonzero.',
    verification: ['dbt source relation has the expected schema and freshness.', 'Selected dbt tests still pass after Hydra ingestion.', 'Downstream ref() models and exposures remain intact.', 'Second run does not duplicate records or change materialization unexpectedly.', 'One scheduler owns the chain.'],
    rollback: 'Stop the new Hydra ingestion schedule, restore the previous source table or loader, and rerun the existing dbt build selection. Preserve dbt models, tests and exposure definitions throughout the pilot so rollback does not require rebuilding the analytical graph.',
    faqs: [
      { question: 'Is Hydra ETL a replacement for dbt?', answer: 'Usually it is a complement. dbt specializes in warehouse SQL models and their tests, documentation and lineage. Hydra can move and prepare data before dbt. Replace a model only if its consumers and quality contract have been inventoried and the new behavior has been verified.' },
      { question: 'Where should Hydra hand data to dbt?', answer: 'Use an explicit staging table or file that dbt can declare as a source. Document its schema, update cadence and readiness condition. Run dbt only after the Hydra job has completed successfully.' },
      { question: 'Can Hydra execute dbt models directly?', answer: 'Hydra can be placed in a workflow that invokes an external command where the deployment supports that action, or an existing scheduler can call hdrctl followed by dbt. This guide uses the second, transparent pattern and does not imply a special dbt connector.' },
      { question: 'Should I remove dbt tests when moving ingestion to Hydra?', answer: 'No. Keep model and source tests during the pilot. They are a valuable acceptance gate for the new ingestion path and may catch type, null or duplicate changes that row counts miss.' },
      { question: 'What happens to dbt ref() dependencies?', answer: 'They remain in dbt if the models remain. Before deleting any model, inspect its downstream ref() users, selectors and exposures. A Hydra output table is not automatically a drop-in replacement for a dbt graph node.' },
      { question: 'Does Hydra upsert equal a dbt incremental model?', answer: 'No. A dbt incremental model has a SQL selection predicate, materialization rules and possibly a unique key. A Hydra upsert describes destination writes. Compare first, repeated, late and full-refresh runs before treating them as equivalent.' },
      { question: 'Can dbt still own transformations after Hydra is added?', answer: 'Yes. This is often the preferred design: Hydra ingests and performs limited pre-cleanup, then dbt builds warehouse models and runs tests. Each layer has a clear output contract.' },
      { question: 'How do I avoid duplicate schedules?', answer: 'Choose one scheduler for the combined chain. Disable the previous loader’s trigger only after the Hydra path has succeeded in parallel, and ensure dbt is invoked once per completed input batch.' },
      { question: 'Can the browser simulator benchmark dbt against Hydra?', answer: 'No. It uses 14 local sample rows and executes neither dbt SQL on a warehouse nor the Hydra engine. It is useful for understanding the displayed transformation, not for cost or performance claims.' },
      { question: 'What is the safe rollback if the new ingestion fails?', answer: 'Restore the previous loader or source table, keep the dbt project unchanged and rerun the selected dbt models. An isolated Hydra staging target allows this without repairing dbt model definitions.' },
    ],
  },
  airbyte: {
    overview: [
      'Airbyte’s central unit is a connection between a configured source and destination. The connection selects streams, sync modes, schedules and schema propagation behavior. Hydra’s central ETL unit is a job that reads a supported source, applies transformations and writes a destination; project workflows can sequence jobs and actions. Those models meet at the landing zone, but they should not be treated as identical products.',
      'Airbyte is often retained for a specialized SaaS connector or CDC stream. Hydra can begin after Airbyte writes a raw table or file, where it casts, filters, joins or aggregates data for a second destination. A full connector replacement is a much higher bar: the new path must reproduce incremental cursor behavior, deletes, normalization, schema changes, retries and monitoring. A first pilot should deliberately avoid a high-value CDC feed.',
      'The simulator’s CSV fixture is only a transformation exercise. It cannot model Airbyte connector availability, replication checkpoints or sync modes. The comparison below separates ingestion from downstream ETL so teams can decide where coexistence is useful and where a connector migration is genuinely justified.'
    ],
    extraSources: [
      { label: 'Airbyte core concepts', url: 'https://docs.airbyte.com/platform/using-airbyte/core-concepts' },
      { label: 'Airbyte sync modes', url: 'https://docs.airbyte.com/platform/using-airbyte/core-concepts/sync-modes' },
      { label: 'Airbyte CDC behavior', url: 'https://docs.airbyte.com/platform/understanding-airbyte/cdc' },
      { label: 'Airbyte sync schedules', url: 'https://docs.airbyte.com/platform/using-airbyte/core-concepts/sync-schedules' },
    ],
    analysis: [
      { title: 'Connectors and source-specific behavior', source: 0, paragraphs: [
        'Airbyte connector configuration can include API authentication, pagination, stream selection and source-specific state. A Hydra source declaration is concise when a supported connector covers the requirement, but “both read APIs” is not evidence that a particular SaaS source behaves the same. Connector maturity and operational support are part of the decision.',
        'Inventory the exact Airbyte source and destination versions, selected streams and fields, and whether the connector is managed or self-hosted. If any part of the source is not supported by Hydra, keep Airbyte as the extraction layer and add Hydra after the landing table. That hybrid design avoids rewriting a reliable connector to improve a downstream transformation.'
      ] },
      { title: 'Full refresh, incremental and CDC', source: 1, paragraphs: [
        'Airbyte sync mode has two sides: how the source is read and how the destination is written. Incremental reading can use a cursor or CDC, and the first incremental run is generally a full load. Hydra load modes describe the destination side of a job; they do not automatically supply Airbyte’s source checkpoints or deletion semantics.',
        'Build a test matrix that includes initial snapshot, new row, updated row, deleted row, connector restart and schema change. For CDC, also inspect transaction ordering and how the source database log is retained. A replacement that matches the initial table but loses deletes or late updates is not equivalent.'
      ] },
      { title: 'Landing-zone contract', source: 0, paragraphs: [
        'An Airbyte connection may write raw or typed tables depending on destination and configuration. Hydra should read a named, stable relation or file, not an undocumented intermediate that a connector upgrade may change. Give the handoff an owner: schema, completion signal, retry policy and the moment when downstream readers may start.',
        'For a coexistence pilot, keep the Airbyte connection active and point Hydra at a separate staging read or copied snapshot. After each sync, compare Airbyte’s stream count and the Hydra output count by business key. If Airbyte retries a sync, make sure the downstream Hydra load mode does not duplicate already processed rows.'
      ] },
      { title: 'Transformation and quality responsibilities', source: 0, paragraphs: [
        'Airbyte primarily replicates data, with typing and deduplication features depending on destination and edition. Hydra can apply in-job transformations, but it should not be credited with Airbyte’s connector reach. Define which tool casts, deduplicates and filters each field to avoid applying the same rule twice.',
        'If dbt already transforms Airbyte output, the professional comparison is three-way: Airbyte ingests, dbt models, and Hydra could replace only a bounded part. A Hydra introduction should simplify a real handoff or add a needed output, not create another opaque stage with no clear quality contract.'
      ] },
      { title: 'Scheduling and observability', source: 3, paragraphs: [
        'Airbyte can schedule syncs or start them manually or by API. Hydra can run jobs under its own project workflow. Leaving both schedules enabled for the same destination can create duplicate writes, conflicting retries and ambiguous incident ownership. Decide which system initiates the chain before cutover.',
        'Record connection ID, sync job ID, Hydra run ID and input batch identifier together. When a downstream transformation fails, the operator must know whether to rerun only Hydra or to repeat the Airbyte sync. That decision depends on whether the Airbyte landing output is immutable and whether the Hydra destination load is idempotent.'
      ] },
    ],
    prerequisites: ['The exact Airbyte connection, stream list, sync mode and cursor or CDC configuration.', 'A stable landed table or file that Hydra can read without modifying Airbyte state.', 'A separate Hydra target, plus credentials and schema access.', 'A replayable sample containing inserts, updates, deletes and schema drift where applicable.'],
    procedure: [
      { title: 'Record connection behavior', detail: 'Export or document the Airbyte source, destination, stream selection, sync schedule and destination namespace. For each stream record full-refresh or incremental reading, append/overwrite/deduped writing, cursor and primary key. This is the contract the next stage receives.' },
      { title: 'Start at the landing zone', detail: 'Keep Airbyte as ingestion owner. Give Hydra read access to one completed stream table or export. Avoid reading a partially written table; use the Airbyte job success state or a controlled snapshot as the readiness condition.' },
      { title: 'Create Hydra transformation output', detail: 'Define a Hydra job that reads the landed relation and writes a distinct staging destination. Start with cast and filter operations before adding joins or aggregation. Validate the YAML strictly, then run against a frozen Airbyte output snapshot.' },
      { title: 'Compare records and sync cycles', detail: 'Reconcile keys, nulls, types and counts for the first sync. Repeat after inserts and updates. If the source uses CDC, verify deletes and ordering. Inspect how a repeated Airbyte sync affects the Hydra target, especially with append or upsert modes.' },
      { title: 'Choose one trigger', detail: 'Either keep Airbyte’s schedule and start Hydra after a successful sync, or place both under one external orchestrator. Do not enable Hydra and Airbyte triggers independently against the same writable target. Record how a failed Hydra run is retried without re-extracting source data.' },
      { title: 'Consider connector replacement separately', detail: 'Only after the hybrid path is stable should you test replacing a simple Airbyte connection. Use a supported source and destination, parallel outputs and a CDC or cursor test suite. Retain the old connection configuration until multiple normal and recovery cycles pass.' },
    ],
    commandTitle: 'Run Hydra after a completed Airbyte sync',
    command: '# First confirm the Airbyte sync is SUCCESS in its UI/API.\n# Configure Hydra sources.yaml for the landed table or export.\nhdrctl validate /srv/hydra/airbyte_orders --strict\nhdrctl run /srv/hydra/airbyte_orders\n# The Hydra destination must be separate during the pilot.\n# Record the Airbyte job ID beside the Hydra run report.',
    verification: ['Initial, repeated and incremental syncs produce the expected key set.', 'CDC deletes and updates are preserved where used.', 'Hydra never reads a partially completed landing table.', 'A retry does not duplicate destination rows.', 'Exactly one schedule owns the sequence.'],
    rollback: 'Stop the Hydra downstream step and return consumers to the Airbyte landing or previous transformation path. Keep the Airbyte connection, state and schedule intact until the replacement path has passed recovery tests; never reset its cursor merely to rerun Hydra.',
    faqs: [
      { question: 'Can Hydra replace an Airbyte connector?', answer: 'Only when Hydra supports the exact source, destination and sync semantics required. Airbyte’s specialized connector catalog is often a reason to keep it and use Hydra downstream instead.' },
      { question: 'Can Airbyte feed Hydra?', answer: 'Yes. Airbyte can write a stable table or file and Hydra can read it after the sync completes. Define a completion signal and let one scheduler own retries so an ETL failure does not automatically repeat ingestion.' },
      { question: 'Is Hydra upsert the same as Airbyte incremental sync?', answer: 'No. Airbyte incremental sync controls source extraction state; Hydra upsert controls destination writes. Both sides must be tested with new, changed, late and deleted records.' },
      { question: 'What should be done with CDC streams?', answer: 'Keep CDC in Airbyte during the first Hydra pilot. If considering replacement, test initial snapshot, updates, deletes, transaction ordering and recovery after interruption. A static CSV comparison cannot establish CDC parity.' },
      { question: 'How do I prevent duplicate loads?', answer: 'Assign one owner for the schedule, use a stable batch or sync identifier, and choose a destination mode that is safe to retry. Turn off the old schedule only after the new sequence has been validated.' },
      { question: 'Should Hydra read an Airbyte raw table?', answer: 'Only if the raw table’s schema and lifecycle are understood. A typed or explicitly exported staging relation may be safer than relying on an internal layout that could change with connector or destination settings.' },
      { question: 'Can Airbyte and dbt remain alongside Hydra?', answer: 'Yes. Airbyte can ingest, Hydra can handle a bounded ETL step or delivery, and dbt can keep warehouse models and tests. Document the handoff contracts and avoid two systems applying the same cleaning rule.' },
      { question: 'How should schema changes be evaluated?', answer: 'Run fixtures with added, removed and type-changed fields. Inspect Airbyte schema propagation, Hydra source validation and the final destination schema. A successful sync does not guarantee downstream consumers still see the expected types.' },
      { question: 'Does the simulator compare connector performance?', answer: 'No. It runs no Airbyte connector and no Hydra engine. It uses local sample rows to explain one transformation and cannot measure throughput, cost or recovery behavior.' },
      { question: 'What is the rollback path?', answer: 'Keep the Airbyte connection and its state unchanged, stop the Hydra step and restore the previous downstream target. Re-run only the necessary downstream processing; resetting the Airbyte source cursor may create duplicates.' },
    ],
  },
  meltano: {
    overview: [
      'Meltano is a composable project for ELT. Extractors, loaders and utilities are installed as plugins, commonly Singer taps and targets, with optional dbt or orchestration utilities. Hydra provides supported connectors, transformation steps and workflows in its own DSL. Both can be managed as code, but their extension models are different: Meltano assembles specialized plugins, while Hydra executes a defined job through its engine.',
      'A Meltano project may already have mature state handling for an extractor/loader pair and environment-specific configuration. Those are operational assets. A sensible Hydra introduction often leaves the tap and target in place, then runs a Hydra job against the landed table or file. A full replacement should be limited to a connector pair that Hydra actually supports and whose incremental behavior can be reproduced.',
      'The simulator compares a small transformation only. It cannot score Singer plugin availability, bookmark state, the behavior of a target plugin or Meltano’s environment resolution. Treat the code examples as a starting point for a handoff design, not a proof that one framework is universally simpler.'
    ],
    extraSources: [
      { label: 'Meltano plugins', url: 'https://docs.meltano.com/concepts/plugins' },
      { label: 'Meltano CLI and run', url: 'https://docs.meltano.com/reference/command-line-interface' },
      { label: 'Meltano environments', url: 'https://docs.meltano.com/concepts/environments' },
      { label: 'Meltano replication state', url: 'https://docs.meltano.com/guide/integration' },
    ],
    analysis: [
      { title: 'Plugin composition versus engine operations', source: 0, paragraphs: [
        'Meltano’s extractor and loader plugins can be combined with mappers, dbt and other utilities in a run sequence. The catalog and Singer ecosystem are major reasons teams adopt it. Hydra supports a defined set of source and destination types and executes supported transforms inside a job. A shorter YAML job does not replace an unavailable plugin.',
        'List every tap, target, mapper and utility in the current pipeline, including plugin version and configuration. Identify which part is data acquisition, which part is transformation and which part is delivery. This makes it possible to move one responsibility at a time rather than translating an entire plugin graph into a single Hydra manifest.'
      ] },
      { title: 'State and incremental extraction', source: 3, paragraphs: [
        'Meltano tracks state for extractor/loader pairs in an active environment, using a state ID that can include a suffix. Changing the environment or pair can change which state is resumed. A Hydra load mode does not reproduce that extractor state. This is one of the most important migration boundaries.',
        'Before a replacement pilot, record the current state ID, bookmark and last successful load. Test an initial batch, a repeated batch, a delayed update and a failed load. If that behavior is hard to reproduce, retain Meltano for extraction and use Hydra after the target.'
      ] },
      { title: 'Environments and credentials', source: 2, paragraphs: [
        'Meltano environments select configuration and contribute to state IDs. Hydra also supports named environments and secret resolution, but naming a Hydra environment “dev” does not automatically carry over Meltano plugin settings or bookmarks. The data contract must include both connection values and state ownership.',
        'Build a configuration matrix for dev, test and prod: source endpoint, target database, schema, batch size, state ID and secret source. Test effective values without printing secrets. If a Meltano run uses one environment and Hydra uses another, make that choice explicit in the orchestration script.'
      ] },
      { title: 'Sequencing with meltano run', source: 1, paragraphs: [
        'Meltano run can sequence extractors, loaders and utilities, and its CLI documentation describes how state and environment flags affect execution. A practical integration is to run the current tap-to-target pair, verify success, then invoke Hydra on the landed data. That bridge can live in an existing scheduler or a configured utility, depending on the project.',
        'Do not let Hydra read the target while Meltano is still loading. Use job completion as the handoff and ensure a failed Hydra step can be retried without accidentally moving the Meltano bookmark again. A frozen table snapshot or batch identifier makes that recovery safer.'
      ] },
      { title: 'Choosing a migration candidate', source: 0, paragraphs: [
        'A simple file or SQL source with a standard target and a small transform may move cleanly. A tap with SaaS-specific pagination, rate limiting or community-maintained behavior is a poor first target. The cost of replacing a plugin includes ownership of future source API changes.',
        'Keep Meltano where its plugin ecosystem is doing hard work. Use Hydra when supported connectors and in-job transformations can remove a separate utility or make a small pipeline easier to validate and operate. Measure failure recovery and maintenance effort, not only the length of meltano.yml.'
      ] },
    ],
    prerequisites: ['The Meltano project’s plugin list, versions, environment and state ID.', 'A stable target table or file for the handoff.', 'A frozen input and expected output, including an incremental second batch.', 'Hydra CLI and credentials on the execution host, with a separate output target.'],
    procedure: [
      { title: 'Inventory the run chain', detail: 'Read meltano.yml and record extractors, loaders, mappers, utilities, schedules and environments. Determine the state ID for the exact extractor/loader pair. Save the previous successful run result and target schema.' },
      { title: 'Keep the extraction stable', detail: 'For coexistence, run the existing Meltano tap and target unchanged. Mark the target table or exported file as ready only after meltano run succeeds. Do not start with a tap rewrite.' },
      { title: 'Add a Hydra job downstream', detail: 'Define Hydra source, transformations and destination. Point the source at Meltano’s landed data and the destination at a new staging target. Validate strictly and run one frozen batch.' },
      { title: 'Test incremental and repeat behavior', detail: 'Run Meltano again with new and updated source records, then run Hydra again. Compare business keys and values and confirm the Meltano bookmark advanced only for successful extraction. Repeat a Hydra failure without repeating the tap unnecessarily.' },
      { title: 'Unify the schedule boundary', detail: 'Place the two commands in one existing orchestrator or a carefully configured Meltano utility sequence. Record which tool owns alerts, retries and the batch identifier. Avoid starting the same pair through both a Meltano schedule and a separate Hydra trigger.' },
      { title: 'Replace only a supported pair', detail: 'If a full replacement is still useful, choose one simple tap/target pair. Compare source extraction and target writes on parallel outputs over several cycles. Preserve plugin configuration and state until rollback is no longer required.' },
    ],
    commandTitle: 'A transparent Meltano-to-Hydra handoff',
    command: '# Example for a configured Meltano project and active dev environment.\nmeltano --environment=dev run tap-orders target-postgres\nhdrctl validate /srv/hydra/orders --strict\nhdrctl run /srv/hydra/orders\n# Hydra reads the table written by target-postgres.\n# A scheduler should stop if either command fails.',
    verification: ['Meltano state ID and bookmark are recorded for each run.', 'Hydra starts only after the target load completes.', 'Repeated runs do not duplicate destination business keys.', 'Environment values and secret sources are mapped explicitly.', 'A Hydra-only retry does not re-extract data.'],
    rollback: 'Stop the Hydra downstream command and return consumers to the original Meltano target or transform utility. Preserve Meltano plugin versions, environment and state ID throughout the pilot so extraction can continue from the previous bookmark.',
    faqs: [
      { question: 'What is the main difference between Meltano and Hydra?', answer: 'Meltano composes plugins such as Singer extractors and loaders, along with utilities. Hydra runs supported sources, transformation steps and destinations in its own ETL job model. The extension and state models differ even though both can be configured as code.' },
      { question: 'Can Hydra replace a Singer tap?', answer: 'Only if Hydra supports the specific source behavior, including authentication, pagination, schema and incremental state. A tap with specialized SaaS behavior is often better retained.' },
      { question: 'Can a Meltano target feed a Hydra job?', answer: 'Yes. Let Meltano finish the tap-to-target load, then point Hydra at a stable landed table or file. Keep the Hydra output separate during the pilot and make one scheduler own the sequence.' },
      { question: 'What happens to Meltano state IDs?', answer: 'They stay with the extractor/loader pair and active Meltano environment. Hydra does not inherit them. Record the exact state ID and bookmark before any replacement experiment.' },
      { question: 'Can I use dbt, Meltano and Hydra together?', answer: 'Yes, with explicit boundaries. Meltano can ingest, Hydra can perform a bounded ETL or delivery step, and dbt can model warehouse data. Decide which tool owns each transformation and avoid duplicated schedules.' },
      { question: 'Does a Hydra environment map directly to a Meltano environment?', answer: 'No. Names may be similar, but configuration resolution and state tracking differ. Map endpoints, secrets, schema and state separately, then test the effective values in every environment.' },
      { question: 'Which Meltano pipeline should migrate first?', answer: 'Choose a standard file or SQL extractor and target with a stable flat schema, limited transformation and a replayable fixture. Avoid a stateful SaaS tap as the first candidate.' },
      { question: 'How do I retry only the Hydra step?', answer: 'Use a durable handoff table or immutable export produced by Meltano. When Hydra fails, rerun it against that same completed batch instead of automatically repeating extraction and advancing state.' },
      { question: 'Can the simulator benchmark Meltano plugins?', answer: 'No. It executes neither a Singer tap nor a Meltano target. It models 14 rows locally and explains one Hydra transformation sequence.' },
      { question: 'What is a safe rollback?', answer: 'Retain the original Meltano project, plugins, environment and state. Stop the new Hydra step and restore the previous downstream target or utility. Do not reset Meltano state to recover a Hydra-only failure.' },
    ],
  },
  airflow: {
    overview: [
      'Airflow is a general-purpose orchestrator. A DAG defines tasks, dependencies and scheduling; the work performed inside those tasks may be Python, SQL, a container command or an external ETL product. Hydra includes its own ETL engine and can orchestrate Hydra jobs and workflow actions. A fair comparison asks whether Hydra should own an ETL-focused workflow, not whether Airflow itself can transform a CSV.',
      'The lowest-risk integration is often to keep the Airflow DAG and make Hydra one task in it. Airflow continues to own scheduling, retries, backfills and cross-system dependencies, while hdrctl runs a versioned ETL job. A full move to Hydra becomes reasonable when the DAG is mostly a linear chain of Hydra-supported jobs and actions and the team does not need Airflow-specific operators or distributed scheduling behavior.',
      'The old side-by-side code demonstration can make a Hydra job look shorter than an Airflow DAG, but the two snippets carry different responsibilities. The new page separates DAG orchestration from the ETL payload, and the browser simulation is explicitly limited to the payload on sample data.'
    ],
    extraSources: [
      { label: 'Airflow DAG concepts', url: 'https://airflow.apache.org/docs/apache-airflow/stable/concepts/dags.html' },
      { label: 'Airflow architecture', url: 'https://airflow.apache.org/docs/apache-airflow/stable/concepts/overview.html' },
      { label: 'Airflow backfill', url: 'https://airflow.apache.org/docs/apache-airflow/stable/core-concepts/backfill.html' },
    ],
    analysis: [
      { title: 'Orchestration versus ETL execution', source: 0, paragraphs: [
        'An Airflow DAG specifies when tasks run and how they depend on one another. The task body or provider performs the extraction, transformation or load. Hydra jobs contain supported ETL behavior themselves, while Hydra workflows arrange jobs and actions. Therefore, compare the Airflow DAG to the Hydra workflow, and separately compare the ETL code inside an Airflow task to the Hydra job.',
        'This distinction prevents a misleading line-count claim. A one-line Airflow BashOperator can invoke an entire external pipeline; a short DAG is not evidence of a simple ETL. Conversely, a Hydra job that includes extraction and transformation is not an equivalent substitute for a broad DAG with many unrelated providers.'
      ] },
      { title: 'Scheduling, data intervals and backfill', source: 2, paragraphs: [
        'Airflow schedules produce DAG runs associated with data intervals, and its backfill tooling can create runs for a historical date range. A move to Hydra must decide how an execution date or batch identifier is passed into jobs and whether historical reruns are required. Merely copying a cron expression is not enough.',
        'For a pilot, capture one normal scheduled run, one manually triggered run and one historical backfill. Verify the effective dates, parameter values and output partition paths. If the Hydra workflow cannot represent the current backfill policy, retain Airflow as the scheduler and call Hydra inside a task.'
      ] },
      { title: 'Operators, sensors and provider ecosystem', source: 0, paragraphs: [
        'Airflow can coordinate many systems through operators, sensors and providers. A DAG that waits for an external dataset, launches a cloud job, branches, and updates several services is not automatically an ETL workflow. Hydra actions and triggers cover specific patterns, but provider names should never be translated by label alone.',
        'List each task with its input, output, retry rule and external dependency. A task that simply runs a Hydra-supported ETL job is a candidate to move; a specialized cloud provider task may remain in Airflow. Hybrid architecture avoids rebuilding mature integrations without a business reason.'
      ] },
      { title: 'Failure and retry boundaries', source: 1, paragraphs: [
        'Airflow retries task instances and records DAG-run state. Hydra can validate jobs and report its run results. When Airflow invokes hdrctl, the process exit code must tell Airflow whether the task succeeded. The Hydra job’s destination mode must also be safe when Airflow retries a task after a partial failure.',
        'Test a deliberate failure after the source is read but before the destination is complete. Determine whether retry duplicates rows, overwrites a target, or resumes safely. Keep Airflow and Hydra logs linked by a shared run identifier or batch date so operators can diagnose both sides.'
      ] },
      { title: 'When to migrate the DAG itself', source: 0, paragraphs: [
        'A DAG dominated by one or two ETL jobs and a notification may be simpler as a Hydra workflow. A DAG with backfills, dynamic mapping, multiple providers or organization-wide observability may be better left in Airflow. The decision should include the people who maintain scheduling, not only the author of the data transformation.',
        'Move one DAG only after a parallel run demonstrates dependency order, parameter transfer, retry behavior, alerts and historical reruns. Keep the Airflow DAG paused rather than deleted during the cutover window so the team can restore the previous schedule quickly.'
      ] },
    ],
    prerequisites: ['The selected DAG file, schedule, task graph, retry policy and backfill expectations.', 'An isolated Hydra job and destination for the ETL payload.', 'hdrctl installed in the Airflow task environment with absolute project paths.', 'A run identifier or date that can be correlated across Airflow and Hydra logs.'],
    procedure: [
      { title: 'Separate DAG control from data logic', detail: 'For each Airflow task, note whether it schedules/waits, invokes a service or transforms records. Extract the ETL payload as its own unit. Do not count Airflow’s operator plumbing as if it were ETL implementation.' },
      { title: 'Wrap one Hydra job in Airflow', detail: 'Install Hydra in the worker environment and deploy the YAML project at a stable path. Add a task that invokes hdrctl validate --strict and hdrctl run. Keep the DAG schedule and surrounding tasks unchanged.' },
      { title: 'Propagate parameters and status', detail: 'Pass the Airflow batch date or run ID into the Hydra job through a reviewed parameter mechanism. Use a command that exits nonzero on validation or run failure. Capture the Hydra report path or run ID in the Airflow task log.' },
      { title: 'Test retries and backfill', detail: 'Run a normal interval, a failed task retry and a historical interval. Verify idempotency at the destination and that the same input period is selected each time. If these semantics diverge, keep the DAG as the orchestrator.' },
      { title: 'Evaluate a workflow move', detail: 'Only after the Hydra task is stable, map DAG dependencies and actions to a Hydra workflow. Compare task order, branching, failure rules and alerts. Leave specialized Airflow provider tasks in the DAG if Hydra has no equivalent.' },
      { title: 'Cut over without duplicate schedules', detail: 'When a full move is justified, enable the Hydra trigger and pause the Airflow DAG for the same workload. Observe several scheduled cycles, then retire the old DAG according to the team’s normal change process.' },
    ],
    commandTitle: 'Airflow task invoking a Hydra ETL job',
    command: '# Airflow 3 example; adapt imports for your installed version.\nimport pendulum\nfrom airflow.sdk import dag\nfrom airflow.providers.standard.operators.bash import BashOperator\n\n@dag(\n    schedule="0 6 * * *",\n    start_date=pendulum.datetime(2025, 1, 1, tz="UTC"),\n    catchup=False,\n)\ndef hydra_orders():\n    BashOperator(\n        task_id="run_hydra_orders",\n        bash_command=(\n            "hdrctl validate /srv/hydra/orders --strict && "\n            "hdrctl run /srv/hydra/orders"\n        ),\n    )\n\nhydra_orders()\n# Keep Airflow as the sole scheduler during this pilot.',
    verification: ['Airflow marks a Hydra failure as a failed task.', 'Task retry does not duplicate or corrupt the destination.', 'A historical run selects the correct input period.', 'Task and Hydra logs share a batch identifier.', 'Only one schedule runs the production workload.'],
    rollback: 'Pause the new Hydra trigger or remove the Hydra task from the active DAG revision, restore the previous ETL task, and rerun the affected Airflow interval. Keep the old DAG code and output contract available throughout the pilot.',
    faqs: [
      { question: 'Is Airflow an ETL engine?', answer: 'No. Airflow orchestrates tasks and their dependencies. ETL logic lives in task code or external tools. Hydra can be the ETL engine that an Airflow task invokes.' },
      { question: 'Can Airflow orchestrate Hydra?', answer: 'Yes. Deploy Hydra where an Airflow worker can call hdrctl, invoke validation and run in a task, and use the process status to mark task success or failure. Keep one scheduler owner.' },
      { question: 'When should a DAG be replaced by a Hydra workflow?', answer: 'Consider it when the DAG is mainly Hydra-supported ETL jobs and simple actions, and when schedule, retry, alert and backfill behavior can be reproduced. Keep Airflow for broad provider-heavy orchestration.' },
      { question: 'How does Airflow backfill affect migration?', answer: 'Backfill creates runs for historical intervals. Verify how each interval becomes a Hydra parameter, source filter and output partition. Copying a cron string without this mapping can process the wrong data.' },
      { question: 'What happens to Airflow operators and sensors?', answer: 'Inventory them individually. Some may map to Hydra actions or triggers, but many specialized providers and sensors have no direct equivalent. Those tasks can remain in Airflow while Hydra handles the ETL payload.' },
      { question: 'How should Airflow retries be configured around Hydra?', answer: 'Make the Hydra destination idempotent for the chosen batch and let a nonzero hdrctl exit status fail the task. Test a partial failure and retry before using the pattern in production.' },
      { question: 'Can both Airflow and Hydra schedules be enabled?', answer: 'They can, but not for the same writable workload without careful coordination. For the migration pilot, keep Airflow as owner; during cutover, pause the DAG before enabling the corresponding Hydra trigger.' },
      { question: 'Does a shorter Hydra YAML prove lower operating cost?', answer: 'No. Code length does not measure scheduler capacity, reliability or team operations. Compare the real deployment, recovery drills and maintenance effort for the selected workload.' },
      { question: 'What does the browser simulator execute?', answer: 'It calculates a four-step transformation on local sample rows. It does not start an Airflow scheduler, run a DAG or invoke the Hydra engine.' },
      { question: 'What is the safest Airflow rollback?', answer: 'Keep the previous DAG code and schedule configuration. Pause the new trigger, restore the old ETL task or DAG revision, and rerun only the affected data interval after checking destination idempotency.' },
    ],
  },
  kestra: {
    overview: [
      'Kestra and Hydra both make YAML central to authoring, but they apply it at different levels. A Kestra flow contains tasks, inputs, outputs, triggers and error behavior for broad automation. Hydra jobs describe supported ETL operations and Hydra workflows sequence jobs and actions. A team should compare the actual work performed by Kestra tasks with Hydra ETL steps, not conclude equivalence because both files have indentation.',
      'Kestra can remain the orchestrator while a task invokes hdrctl. This is often the safest way to introduce Hydra in a Kestra estate: the flow keeps its schedule, retries, plugin integrations and execution history, while Hydra owns a bounded ETL transformation. A full move is narrower and requires a check of triggers, concurrency, task plugins and failure states.',
      'The browser simulator runs neither Kestra nor Hydra. It is a local example of filter, cast, aggregate and sort. It does not model Kestra worker execution, task plugins, event triggers, flow inputs or output storage.'
    ],
    extraSources: [
      { label: 'Kestra flows', url: 'https://kestra.io/docs/workflow-components/flow' },
      { label: 'Kestra tasks', url: 'https://kestra.io/docs/workflow-components/tasks' },
      { label: 'Kestra triggers', url: 'https://kestra.io/docs/workflow-components/triggers' },
      { label: 'Kestra executions', url: 'https://kestra.io/docs/workflow-components/execution' },
    ],
    analysis: [
      { title: 'Flow tasks versus ETL steps', source: 1, paragraphs: [
        'Kestra distinguishes runnable tasks that do work from flowable tasks that control orchestration, such as parallel branches, switches and loops. Hydra transformations such as cast, filter and aggregate operate inside a data job. A single Kestra shell or Python task may contain an entire ETL program, while a Hydra job makes many of those operations explicit.',
        'Classify each Kestra task by purpose before translating it. A log or notification belongs to orchestration, a database query may remain a plugin task, and a linear data transformation may become a Hydra job. Do not translate task count to step count; compare the data contract and graph behavior.'
      ] },
      { title: 'Triggers and schedule ownership', source: 2, paragraphs: [
        'Kestra flows can start from schedules, webhooks and other events. Hydra also has project triggers, but their event payload, concurrency and failure semantics must be checked independently. In a coexistence pilot, keep Kestra’s trigger and add Hydra as a task. That leaves one owner for when the work begins.',
        'A full switch requires a trigger inventory: cron expression, timezone, backfill expectations, event deduplication, input payload and concurrent-run policy. Test an event while a previous execution is still running and confirm the desired behavior before disabling the Kestra flow.'
      ] },
      { title: 'Inputs, outputs and file handoff', source: 0, paragraphs: [
        'Kestra flows can pass typed inputs and outputs and may store files in internal execution storage. A Hydra CLI job expects its own project files and access to its configured source path or connection. A path that exists inside a Kestra task container may not exist on the host where Hydra is installed.',
        'For integration, select a durable handoff: a database table, object storage key or explicitly mounted file. Pass only the identifier or path to the Hydra step and verify that both processes see the same bytes. Do not rely on a temporary container path without declaring how it is shared.'
      ] },
      { title: 'Execution state and retries', source: 3, paragraphs: [
        'Kestra records execution and task states such as success, failure, retrying and skipped. When it invokes hdrctl, map Hydra’s process exit code and report to those states. A task that logs an error but exits zero will appear successful even though the data job failed.',
        'Test the chain with a bad source, a malformed amount and an unavailable destination. Observe the Kestra task state, Hydra report and target table after each fault. Then retry the task and verify whether the destination mode prevents duplicates.'
      ] },
      { title: 'Choosing whether to replace Kestra', source: 0, paragraphs: [
        'Keep Kestra for broad cross-system automation, event-driven flows or plugin tasks that have no Hydra equivalent. Evaluate a Hydra workflow when the flow is predominantly Hydra ETL jobs plus simple actions and the existing triggers and recovery behavior can be reproduced.',
        'A shorter flow definition is not the acceptance criterion. Operators must be able to find the same input batch, determine which step failed and replay it safely. Preserve the Kestra flow definition during a pilot even if a Hydra trigger is eventually enabled.'
      ] },
    ],
    prerequisites: ['The Kestra flow YAML, task/plugin versions, triggers, inputs and error settings.', 'A shared path or table visible to the Hydra execution environment.', 'Hydra CLI installed in the relevant task image or worker host.', 'A separate target and reproducible fixture for a parallel run.'],
    procedure: [
      { title: 'Classify the flow', detail: 'Mark each Kestra task as ETL work, orchestration control or external integration. Record plugin types, trigger configuration and the execution environment. Choose a linear ETL slice rather than a flow with loops or event payloads for the first pilot.' },
      { title: 'Create a Hydra job for the slice', detail: 'Translate the selected data input, casts, filters and output to Hydra YAML. Use a separate target. Validate the job strictly and run it outside Kestra on a frozen fixture before adding a task to the flow.' },
      { title: 'Make data visible to the task', detail: 'Provide the Hydra project and input through a mounted path or a stable database connection. If Kestra stores an input file internally, export or stage it to a location hdrctl can read; do not assume a task container sees the same local filesystem as another worker.' },
      { title: 'Invoke hdrctl from Kestra', detail: 'Add a shell Commands task in the existing flow after the data-ready task. Call validation and run in sequence. Keep the Kestra trigger and downstream tasks, and ensure a failed command produces a failed Kestra task.' },
      { title: 'Exercise failure and parallelism', detail: 'Test a successful run, a missing input, an invalid schema and a retry while a previous run is active. Compare Kestra execution state, Hydra report and destination rows. Review concurrency rules before moving a schedule.' },
      { title: 'Decide on long-term ownership', detail: 'Keep Kestra when its wider plugins or triggers still add value. If a complete Hydra workflow is justified, reproduce the task graph and trigger policy, run it in parallel, then disable the Kestra trigger for this flow only.' },
    ],
    commandTitle: 'Kestra shell task running an isolated Hydra project',
    command: 'id: run_hydra_orders\ntype: io.kestra.plugin.scripts.shell.Commands\ncommands:\n  - "hdrctl validate /srv/hydra/orders --strict"\n  - "hdrctl run /srv/hydra/orders"\n# Package hdrctl and the project in the task environment.\n# Mount or stage the input so both processes see the same data.',
    verification: ['The Kestra task fails when hdrctl fails.', 'The Hydra project and input path exist in the task runtime.', 'Output values match the prior task or pipeline.', 'Task retry does not duplicate rows.', 'Exactly one trigger starts production runs.'],
    rollback: 'Remove or disable the Hydra task in the active Kestra flow revision, restore the previous task path and rerun the affected execution or input batch. Keep the original flow and task image available during the trial.',
    faqs: [
      { question: 'Are Kestra and Hydra direct competitors?', answer: 'They overlap in YAML workflow orchestration. Kestra is a broad task orchestration platform; Hydra also executes its own ETL transformations. The overlap is greatest for a flow dominated by data movement and supported ETL steps.' },
      { question: 'Can a Kestra flow run Hydra?', answer: 'Yes, with a task that invokes hdrctl in an environment where the CLI, project and input data are available. Keep Kestra’s trigger and use the command exit status to signal failure.' },
      { question: 'Can Hydra replace Kestra triggers?', answer: 'Some trigger patterns may be representable, but inspect the exact schedule, webhook payload, concurrency and event semantics. Do not infer parity from the word “trigger” alone.' },
      { question: 'What happens to Kestra plugin tasks?', answer: 'Retain tasks that integrate with systems Hydra does not support. A hybrid flow can use Kestra for those plugins and Hydra for a bounded ETL step.' },
      { question: 'How should files be passed between Kestra and Hydra?', answer: 'Use a shared mounted path, database table or object storage handoff. A temporary path inside one Kestra task container may be unavailable to the next task or to hdrctl.' },
      { question: 'Does a Hydra job replace a Kestra flow?', answer: 'Not necessarily. A Hydra job is the ETL work unit; a Kestra flow includes orchestration, inputs, triggers and error behavior. Compare a Hydra workflow with a Kestra flow and a Hydra job with the transformation inside a task.' },
      { question: 'How do retries interact?', answer: 'Kestra may retry a task that runs hdrctl. Choose a Hydra destination mode and batch key that make reruns safe. Test a failure after partial output before enabling retries in production.' },
      { question: 'Can both schedules run during a parallel test?', answer: 'Only if outputs are isolated and tagged by run. For production, choose one schedule owner before writing to the same target.' },
      { question: 'Does the simulator run a Kestra worker?', answer: 'No. It is a browser-local sample transformation. It does not start a Kestra flow, plugin or worker and cannot benchmark the runtime.' },
      { question: 'What is the rollback plan?', answer: 'Keep the old Kestra flow revision. Disable the Hydra task or trigger, restore the previous task path and replay the affected batch after checking for partial Hydra output.' },
    ],
  },
  flowman: {
    overview: [
      'Flowman is a declarative ETL framework powered by Apache Spark. Its specifications describe physical relations, mappings, targets and jobs. Hydra also uses declarative configuration, but its supported ETL operations run in the Hydra engine. The engines are a decisive difference: a Spark workload may depend on distributed compute, partitioning and Hive or Delta integrations that a small Hydra job cannot simply inherit.',
      'The strongest migration candidates are bounded file or JDBC jobs whose input size and transformations fit Hydra’s engine and connector set. Flowman jobs that create relations or manage schemas need special attention because moving the data flow may leave schema-management responsibilities behind. The useful coexistence pattern is to keep Flowman for Spark-scale builds and let Hydra own a small adjacent ingestion or delivery job.',
      'The simulator’s 14 orders are intentionally favorable to a local ETL engine. It is not a performance comparison with Spark, and neither execution plan nor memory use is measured. A professional decision requires a representative data volume and a realistic run schedule.'
    ],
    extraSources: [
      { label: 'Flowman framework overview', url: 'https://flowman.io/' },
      { label: 'Flowman relations', url: 'https://docs.flowman.io/en/latest/spec/relation/index.html' },
      { label: 'Flowman mappings', url: 'https://docs.flowman.io/en/latest/spec/mapping/index.html' },
      { label: 'Flowman jobs', url: 'https://docs.flowman.io/en/latest/spec/job/index.html' },
    ],
    analysis: [
      { title: 'Relations and connection contracts', source: 1, paragraphs: [
        'Flowman relations define physical data sources and sinks, including connection and schema information. Some relation types can create tables or perform schema management. In Hydra, sources and destinations describe connections and extraction or load behavior. The same table name may hide different coercion, DDL or overwrite semantics.',
        'For every candidate, record relation type, format, schema, partition columns and creation behavior. Test both read and write sides with nulls, incompatible values and missing columns. If Flowman currently creates a Hive or JDBC table, assign that DDL responsibility explicitly before Hydra takes over the data movement.'
      ] },
      { title: 'Mapping graph versus transformation steps', source: 2, paragraphs: [
        'Flowman mappings represent a data flow and can be composed into targets. Hydra transformation steps can express many common row and table operations, but the evaluation strategy and intermediate data model differ. A named Flowman mapping reused by several targets should not be collapsed into one Hydra step without checking every consumer.',
        'Draw the Flowman mapping graph, including filters, joins, aggregations and sort requirements. Translate one target at a time, preserving grouping keys and output schema. Compare results by stable business key; Spark output order is not generally a meaningful equality criterion unless sorting is part of the contract.'
      ] },
      { title: 'Spark scale and engine selection', source: 0, paragraphs: [
        'Flowman’s Spark foundation can distribute transformations across a cluster. Hydra’s available engine backends and deployment topology must be tested on the actual workload. A toy line-count comparison says nothing about 500 GB joins, shuffle cost, memory pressure or partitioned output.',
        'Benchmark with representative row count, column width, skew and destination format. Record elapsed time, peak memory, failure recovery and cost for both systems. If the Spark job is genuinely distributed, keep it in Flowman and migrate adjacent small jobs first.'
      ] },
      { title: 'Jobs, targets and parameters', source: 3, paragraphs: [
        'A Flowman job lists targets to build, and Flowman determines build order from dependencies. Job parameters can influence the processing date or output. A Hydra workflow explicitly sequences jobs and actions. To migrate, map target dependencies and each parameter’s effective value, not just the final target name.',
        'Exercise a normal date, an empty date and a historical rerun. Confirm that filters and partition destinations use the same range. If Flowman’s dependency discovery builds a shared target once, ensure the Hydra workflow does not run it twice or publish partially built outputs.'
      ] },
      { title: 'Operational coexistence', source: 3, paragraphs: [
        'Flowman may continue to own large transformations while Hydra performs a small preflight, file normalization or downstream delivery. A stable file or database table is the handoff. The upstream job’s completion status must be observed before Hydra reads the output.',
        'During migration, keep the old Flowman job and its scheduler entry available. Do not decommission Spark infrastructure based on a successful small-file pilot. The operational benefit only exists when the complete set of dependent jobs and workloads has been accounted for.'
      ] },
    ],
    prerequisites: ['A Flowman project inventory: relations, mappings, targets, jobs and scheduler entries.', 'Representative input size and data distribution, not only a sample fixture.', 'A separate staging output and an explicit owner for DDL/schema management.', 'Hydra-supported source and destination types for the selected target.'],
    procedure: [
      { title: 'Classify by compute requirement', detail: 'Separate small file/JDBC mappings from jobs that need distributed Spark, Hive or Delta behavior. Pick a bounded job for the pilot and record typical and peak volume, row width and skew. Leave cluster-scale jobs in Flowman.' },
      { title: 'Map relations and DDL', detail: 'For the selected target, document read relation, output relation, schema, partitioning and whether Flowman creates or alters physical tables. Decide which system will own that DDL after migration.' },
      { title: 'Translate one mapping chain', detail: 'Convert the needed filter, cast, join and aggregate operations into Hydra transformations, keeping a separate destination. Validate the YAML and run a frozen fixture before using production-scale data.' },
      { title: 'Compare outputs and resource use', detail: 'Compare row-level values, nulls and target schema. Then benchmark on representative data. Capture elapsed time and memory, especially for joins and aggregate skew. A correct small fixture is necessary but not sufficient.' },
      { title: 'Preserve job parameter behavior', detail: 'Map Flowman processing-date and environment parameters to Hydra parameters or source filters. Test a historical run and ensure the same partition or date range is produced.' },
      { title: 'Cut over one target', detail: 'Disable only the selected Flowman scheduler entry after repeated successful Hydra runs. Retain the Flowman project and Spark runtime for other jobs and for rollback until every dependent target has been reviewed.' },
    ],
    commandTitle: 'Validate and run the bounded Hydra replacement',
    command: '# First export a frozen input from a Flowman relation.\n# Configure Hydra sources.yaml for that file or supported JDBC table.\nhdrctl validate /srv/hydra/flowman_small_job --strict\nhdrctl run /srv/hydra/flowman_small_job\n# Compare against the Flowman target in a separate staging location.\n# Benchmark representative volume before switching the schedule.',
    verification: ['Result values and schema match, not only row counts.', 'Any Flowman-created table has an explicit new DDL owner.', 'Historical parameters produce the same range.', 'Representative data fits the Hydra runtime envelope.', 'Spark-scale Flowman jobs remain unaffected.'],
    rollback: 'Re-enable the selected Flowman scheduler entry, point consumers back to its original target and rerun the affected parameter range. Keep Flowman relation definitions and Spark infrastructure intact until the corresponding Hydra target has passed production-scale and recovery tests.',
    faqs: [
      { question: 'How are Flowman and Hydra similar?', answer: 'Both support declarative ETL definitions. Flowman uses relations, mappings, targets and jobs on Apache Spark; Hydra uses sources, transformations, destinations and workflows in its own engine.' },
      { question: 'Can Hydra replace a Spark-scale Flowman job?', answer: 'Only after a representative performance and correctness test. A small CSV example cannot establish parity for distributed joins, shuffles or large partitioned output.' },
      { question: 'What is a Flowman relation?', answer: 'It describes a physical source or sink and may include connection and schema behavior. When moving to Hydra, map both access and any table-creation or schema-conversion responsibility.' },
      { question: 'Do Flowman mappings map one-to-one to Hydra steps?', answer: 'Not always. A Flowman mapping can be reused and can express a graph. A Hydra transformation step is part of a job sequence. Translate the behavior of each target and its consumers, not only names.' },
      { question: 'How should Flowman job parameters be migrated?', answer: 'Record every parameter that changes source filtering, target partition or date range. Map it to a Hydra parameter and test normal and historical runs with the same effective value.' },
      { question: 'Can Flowman and Hydra coexist?', answer: 'Yes. Keep Flowman for large Spark workloads and use Hydra for a bounded adjacent ETL job. Connect them through a completed file or table and one scheduler owner.' },
      { question: 'What happens to Flowman-managed schemas?', answer: 'Someone must own DDL and schema migration after a target moves. Do not assume a Hydra load automatically creates, alters or converts a table exactly as a Flowman relation did.' },
      { question: 'What metrics matter in a Flowman comparison?', answer: 'Correctness, schema, representative elapsed time, memory, cluster cost, partition behavior and recovery. Code length or 14-row browser output is not a performance measure.' },
      { question: 'Does the simulator execute Spark?', answer: 'No. It models one tiny transformation in the browser and does not start Flowman, Spark or the Hydra engine.' },
      { question: 'How can a Flowman migration be rolled back?', answer: 'Retain the original project and schedule entry. Restore the Flowman target as the consumer source and rerun the affected parameter range after checking for partial Hydra output.' },
    ],
  },
  dagster: {
    overview: [
      'Dagster is organized around software-defined assets and their materializations, with jobs, schedules, sensors and a UI that makes the asset graph visible. Hydra is organized around ETL jobs and workflow steps. A linear data transformation can look similar in both, but an asset has identity, history, partitions and downstream consumers that a job output does not automatically replace.',
      'The safest integration is to keep Dagster as the asset owner and let an asset or op invoke a Hydra job. The Hydra job writes a defined output, and Dagster records a materialization or check after verifying that output. Full migration is a narrower option for a pipeline whose intermediate stages are not valuable as separately tracked assets and whose consumers can accept a different operational model.',
      'The browser example demonstrates only a small order aggregation. It cannot measure asset lineage, materialization metadata, partition backfills, sensors or Dagster’s run coordination. A professional comparison should evaluate those capabilities as first-class requirements rather than treating them as framework overhead.'
    ],
    extraSources: [
      { label: 'Dagster asset jobs', url: 'https://dagster.io/docs/guides/build/jobs/asset-jobs' },
      { label: 'Dagster schedules and sensors', url: 'https://dagster.io/docs/api/dagster/schedules-sensors' },
      { label: 'Dagster webserver and asset catalog', url: 'https://dagster.io/docs/guides/operate/webserver' },
      { label: 'Dagster shell integration', url: 'https://dagster.io/integrations/dagster-shell' },
    ],
    analysis: [
      { title: 'Asset identity versus pipeline output', source: 0, paragraphs: [
        'A Dagster asset is a named data product with dependencies and materialization events. An asset job targets a selection of assets. Hydra jobs read, transform and write data, and a Hydra workflow sequences jobs and actions. A table written by Hydra can represent the same physical data, but Dagster’s logical asset identity and history remain separate unless the integration records them.',
        'Before migration, ask which assets are truly consumed as products and which are implementation intermediates. Keep published assets with downstream owners in Dagster. A chain of private intermediate frames may be consolidated into a Hydra job if the final contract and diagnostic visibility remain adequate.'
      ] },
      { title: 'Lineage, partitions and freshness', source: 2, paragraphs: [
        'Dagster’s asset catalog exposes dependencies, partition status and run information. A Hydra report can show that a job ran, but it does not automatically reproduce Dagster’s lineage view. If an audit or operations team uses asset materializations and partition status, losing them is a meaningful regression.',
        'For a hybrid design, let Dagster retain the asset definition and call Hydra during its computation. After the Hydra output is checked, Dagster can record the materialization under the existing key. Test a missing partition and a late partition as well as the normal daily path.'
      ] },
      { title: 'Schedules, sensors and automation', source: 1, paragraphs: [
        'Dagster jobs can be started by schedules or sensors. A sensor may make decisions based on external events and run keys. Hydra triggers can start project workflows, but event deduplication, partition mapping and sensor evaluation behavior must be assessed separately.',
        'During coexistence, keep Dagster automation active and do not add an independent Hydra trigger for the same asset. If a full move is considered, map every schedule and sensor to an explicit replacement and test a repeated event so the same output is not built twice.'
      ] },
      { title: 'Invoking Hydra from Dagster', source: 3, paragraphs: [
        'Dagster can run shell commands and capture their outcomes. A bounded Hydra job can therefore be invoked from an asset or op using a subprocess or shell integration. The Dagster execution environment must contain hdrctl, the Hydra project and access to its source and destination.',
        'Use a stable path and a process call that raises on nonzero exit. Do not mark the Dagster asset materialized merely because the command was launched; verify that the Hydra destination contains the expected partition or batch and propagate failure to Dagster.'
      ] },
      { title: 'Choosing a full migration', source: 0, paragraphs: [
        'A full move may suit a small linear ETL pipeline where asset lineage, sensors and partition history are not central. It is less suitable where the asset graph is the team’s operational language or where downstream users rely on materialization metadata.',
        'Evaluate the complete work of the pipeline: execution, data contract, alerting, replay and lineage. The goal is not to replace Python with YAML at any cost. A hybrid system can keep Dagster’s asset model while Hydra provides the data transformation.'
      ] },
    ],
    prerequisites: ['A Dagster asset/job selection with upstream and downstream asset keys.', 'Schedules, sensors, partitions, checks and materialization metadata for that selection.', 'A Hydra job with a separate destination and a stable path in the Dagster execution environment.', 'A frozen fixture and acceptance query for the published asset.'],
    procedure: [
      { title: 'Classify assets', detail: 'Draw the Dagster asset graph around the candidate. Mark published data products, consumers, partitions and checks. Choose a private linear intermediate chain for a replacement pilot, or retain the final asset as Dagster-owned for a hybrid pilot.' },
      { title: 'Build the Hydra ETL slice', detail: 'Implement the source-to-destination operation in Hydra YAML and validate it strictly. Use a separate target so the existing asset remains untouched. Test on a frozen input and compare the final table or file by business key.' },
      { title: 'Invoke from the existing asset', detail: 'Install hdrctl in the Dagster execution environment and call it from an asset or op with a checked subprocess. Pass an explicit partition or batch identifier. Keep Dagster’s schedule or sensor active and do not add a second Hydra trigger.' },
      { title: 'Verify before materialization', detail: 'After hdrctl succeeds, query or read the destination to confirm the expected partition, row count and schema. Only then report the Dagster asset as materialized. Preserve existing asset checks and metadata where they still apply.' },
      { title: 'Test historical and failed runs', detail: 'Run a normal partition, a missing partition and a retry after an intentional Hydra failure. Compare Dagster run state, Hydra output, asset check result and any duplicate materialization events.' },
      { title: 'Choose the long-term graph', detail: 'Keep Dagster when its asset catalog, lineage and automation are valuable. If moving a whole chain to a Hydra workflow, document replacement observability and disable the corresponding Dagster schedule only after parallel evidence.' },
    ],
    commandTitle: 'A Dagster asset that delegates ETL to Hydra',
    command: 'import subprocess\nimport dagster as dg\n\n@dg.asset\ndef orders_by_status():\n    subprocess.run(\n        ["hdrctl", "validate", "/srv/hydra/orders", "--strict"],\n        check=True,\n    )\n    subprocess.run(\n        ["hdrctl", "run", "/srv/hydra/orders"],\n        check=True,\n    )\n    # Verify the output before treating the asset as materialized.\n\ndefs = dg.Definitions(assets=[orders_by_status])',
    verification: ['The Dagster asset fails if hdrctl exits nonzero.', 'Materialization is recorded only after output verification.', 'Partition and freshness expectations still hold.', 'Existing asset checks and downstream dependencies remain valid.', 'Dagster and Hydra do not schedule duplicate builds.'],
    rollback: 'Restore the prior asset implementation or job revision, disable the Hydra invocation and rematerialize only affected partitions. Preserve the existing Dagster asset keys, checks and schedule definitions during the pilot so downstream consumers continue to recognize the asset.',
    faqs: [
      { question: 'Can Hydra replace a Dagster asset?', answer: 'Hydra can produce the same physical dataset for some ETL workloads, but it does not automatically replace the asset key, materialization history, partition status or lineage. Keep those requirements explicit when considering migration.' },
      { question: 'Can Dagster run a Hydra job?', answer: 'Yes. An asset or op can invoke hdrctl through a checked subprocess or shell integration. The execution environment needs the CLI, project files and access to the same data sources and destinations.' },
      { question: 'What happens to Dagster lineage?', answer: 'It remains in Dagster only for assets still represented and materialized there. A Hydra job report is not the same as an asset graph. A hybrid design can retain the Dagster asset key while delegating computation to Hydra.' },
      { question: 'How should partitions be passed to Hydra?', answer: 'Pass a stable partition key or date as an explicit parameter and use it in source filtering and output paths. Test normal, late and missing partitions before replacing partitioned Dagster automation.' },
      { question: 'Should sensors move to Hydra triggers?', answer: 'Only after their event, run-key, deduplication and failure behavior is mapped. In a first pilot, keep the Dagster sensor and invoke Hydra inside the resulting run.' },
      { question: 'Can I consolidate intermediate Dagster assets?', answer: 'Possibly, when they are implementation details rather than published data products. Confirm that no checks, consumers, partition reports or audits rely on their individual materializations.' },
      { question: 'How do asset checks interact with Hydra?', answer: 'Keep Dagster checks around the output produced by Hydra or replace them with an explicitly reviewed quality mechanism. Do not mark an asset successful based only on a zero exit code if the target data contract needs verification.' },
      { question: 'Is Hydra simpler than Dagster for every pipeline?', answer: 'No. Hydra may simplify a small source-to-destination ETL chain. Dagster’s asset model and catalog can make a complex data product graph easier to understand and operate.' },
      { question: 'Does the simulator model asset lineage?', answer: 'No. It computes one sample transformation locally. It does not run Dagster, record materializations, evaluate checks or show partition history.' },
      { question: 'What is a safe rollback after a hybrid pilot?', answer: 'Keep the previous asset implementation. Disable the Hydra call, restore the original compute path and rematerialize affected partitions while preserving the same Dagster asset keys for consumers.' },
    ],
  },
};
