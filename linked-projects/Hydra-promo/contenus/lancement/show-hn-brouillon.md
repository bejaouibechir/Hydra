# Brouillon Show HN — NE PAS PUBLIER avant : 3 pilotes, GIF de démo, page benchmark, bugs `validate` corrigés

**Titre (80 caractères max) :**
Show HN: Hydra ETL – declarative YAML pipelines, validated before they run

**URL :** https://github.com/bejaouibechir/Hydra

**Premier commentaire (posté par Bechir juste après) :**

Hi HN, I'm Bechir, a software architect in Tunis. Hydra ETL is a side project I've been building alone for about a year.

The problem: most of the data jobs I saw in client projects were Python scripts moving files into databases. They worked, but nobody could review them, and errors showed up halfway through a load.

Hydra ETL describes a job as four small YAML files (sources, transformations, destinations, pipeline). `hdrctl validate` checks them against typed schemas and cross-references before any data is touched; `hdrctl test` checks connections; `hdrctl run` executes on pandas or DuckDB. The same files can be edited in a browser Studio, and there's an MCP server so an AI assistant can draft pipelines that Hydra then validates.

What it is not: an orchestrator for hundreds of heterogeneous tasks (use Airflow/Dagster), or a warehouse transformation tool (use dbt).

Honest status: beta, one maintainer, AGPL-3.0. [N] teams use it on real jobs: [1 ligne par pilote]. Benchmarks and their limits: [lien page benchmark].

I'd love feedback on the DSL design and on what validation should catch that it doesn't yet.
