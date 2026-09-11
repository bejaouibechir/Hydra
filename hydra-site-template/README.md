# hydraetl.com — Astro Site

Static documentation site for Hydra ETL, built with Astro and deployed to GitHub Pages.

## Quick start

```bash
# Install
pnpm install

# Development
pnpm dev

# Build
pnpm build

# Preview (simulates GitHub Pages)
pnpm preview
```

## Structure

- `src/pages/` — route pages (URL structure mirrors directory)
- `src/components/` — reusable React components
- `src/layouts/` — page templates
- `src/styles/` — global CSS + variables
- `public/` — static assets (CRITICAL: .nojekyll and CNAME)
- `.github/workflows/` — CI/CD pipeline

## Key files

- `public/.nojekyll` — empty file, tells GitHub Pages to skip Jekyll (REQUIRED)
- `public/CNAME` — contains `hydraetl.com` (REQUIRED)
- `astro.config.mjs` — Astro configuration
- `package.json` — dependencies and scripts

## Documentation

See `../documentations/` for setup, architecture, and migration guides:

- `ASTRO_SETUP.md` — full technical setup
- `CLAUDE_ASTRO_SITE.md` — developer guide
- `MIGRATION_EXEMPLE.md` — how to adapt maquettes
- `PLAN_EXECUTION.md` — 3-week roadmap
