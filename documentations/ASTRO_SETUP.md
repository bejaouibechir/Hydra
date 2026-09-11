# Astro Site Setup — hydraetl.com

Guide complet pour monter le site Astro avec les maquettes existantes.

---

## 1. Structure du projet

Copier cette arborescence dans votre nouveau dossier `hydra-site/` (ou équivalent) :

```
hydra-site/
├── .github/
│   └── workflows/
│       └── build.yml                    # CI/CD — compile, teste, déploie
├── src/
│   ├── layouts/
│   │   └── BaseLayout.astro            # Wrapper HTML + nav + footer
│   ├── pages/
│   │   ├── index.astro                 # /
│   │   ├── install.astro               # /install
│   │   ├── playground.astro            # /playground
│   │   ├── build.astro                 # /build
│   │   ├── guide.astro                 # /guide
│   │   ├── learn.astro                 # /learn
│   │   ├── learn/
│   │   │   ├── first-job.astro         # /learn/first-job
│   │   │   ├── transformations.astro   # /learn/transformations
│   │   │   ├── connectors.astro        # /learn/connectors
│   │   │   ├── workflows.astro         # /learn/workflows
│   │   │   └── next.astro              # /learn/next
│   │   ├── migrate.astro               # /migrate
│   │   ├── migrate/
│   │   │   ├── airflow.astro           # /migrate/airflow
│   │   │   ├── dagster.astro           # /migrate/dagster
│   │   │   ├── prefect.astro           # /migrate/prefect
│   │   │   ├── dbt.astro               # /migrate/dbt
│   │   │   ├── databricks.astro        # /migrate/databricks
│   │   │   └── airbyte.astro           # /migrate/airbyte
│   │   ├── reference/
│   │   │   ├── operations.astro        # /reference/operations
│   │   │   ├── connectors.astro        # /reference/connectors
│   │   │   └── cli.astro               # /reference/cli
│   │   └── studio.astro                # /studio
│   ├── components/
│   │   ├── HydraCore.jsx               # Noyau partagé des 6 tunnels
│   │   ├── Nav.astro                   # Navigation principale
│   │   ├── Footer.astro                # Pied de page
│   │   ├── Topbar.astro                # En-tête avec sélecteur de thème
│   │   └── MetaTags.astro              # Balises head
│   └── styles/
│       ├── global.css                  # Variables CSS, règles globales
│       └── components.css              # Styles partagés (cards, buttons, etc.)
├── public/
│   ├── .nojekyll                       # CRITIQUE — dit à GH Pages de skip Jekyll
│   ├── CNAME                           # Domaine personnalisé
│   ├── logo.svg                        # Logo Hydra
│   └── og-image.png                    # Open Graph image
├── astro.config.mjs                    # Configuration Astro
├── tsconfig.json                       # Configuration TypeScript
├── package.json                        # Dépendances et scripts
├── pnpm-lock.yaml                      # Lock file (ou yarn.lock, package-lock.json)
└── README.md                           # Instructions pour développeurs
```

---

## 2. Fichiers de configuration

### astro.config.mjs

```javascript
import { defineConfig } from 'astro/config';
import react from '@astrojs/react';

export default defineConfig({
  integrations: [react()],
  
  // Domaine personnalisé
  site: 'https://hydraetl.com',
  
  // Mode de sortie : static = HTML pré-généré
  output: 'static',
  
  // Dossier de sortie pour GitHub Pages
  outDir: './dist',
  
  // Collecte les fichiers de public/
  publicDir: './public',
  
  // Base path (si déploiement en sous-répertoire — pas utilisé ici)
  base: '/',
  
  vite: {
    build: {
      // Budgets Lighthouse bloquants
      rollupOptions: {
        output: {
          manualChunks: (id) => {
            if (id.includes('node_modules')) return 'vendor';
            if (id.includes('HydraCore')) return 'hydra-core';
          }
        }
      }
    }
  }
});
```

### package.json

```json
{
  "name": "hydraetl-site",
  "version": "1.0.0",
  "type": "module",
  "scripts": {
    "dev": "astro dev",
    "build": "astro build",
    "preview": "astro preview",
    "lint:js": "eslint src --ext .js,.jsx,.astro --fix",
    "lint:html": "htmlhint dist",
    "test:lighthouse": "lighthouse https://hydraetl.com --output-path=./lighthouse.html --budget-path=./budget.json",
    "test:a11y": "node scripts/a11y-test.js"
  },
  "dependencies": {
    "astro": "^5.0.0",
    "@astrojs/react": "^3.0.0",
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "shiki": "^1.0.0",
    "pagefind": "^1.0.0"
  },
  "devDependencies": {
    "@typescript-eslint/eslint-plugin": "^6.0.0",
    "@typescript-eslint/parser": "^6.0.0",
    "eslint": "^8.0.0",
    "eslint-plugin-astro": "^0.30.0",
    "htmlhint": "^1.1.0",
    "lighthouse": "^11.0.0",
    "playwright": "^1.40.0",
    "typescript": "^5.0.0"
  }
}
```

### tsconfig.json

```json
{
  "extends": "astro/tsconfigs/strict",
  "compilerOptions": {
    "jsxImportSource": "react",
    "lib": ["ES2022", "DOM", "DOM.Iterable"],
    "target": "ES2022",
    "module": "ESNext",
    "moduleResolution": "bundler"
  }
}
```

---

## 3. Fichiers publics

### public/.nojekyll

Fichier vide. Critique — sans lui, GitHub Pages ignore les fichiers commençant par `_`, dont `_astro/` qui contient le CSS et le JS compilés.

### public/CNAME

```
hydraetl.com
```

---

## 4. CI/CD — GitHub Actions

### .github/workflows/build.yml

```yaml
name: Build & Deploy

on:
  push:
    branches: [main, develop]
  pull_request:
    branches: [main]

jobs:
  build:
    runs-on: ubuntu-latest
    
    permissions:
      contents: read
      pages: write
      id-token: write
    
    environment:
      name: github-pages
      url: ${{ steps.deployment.outputs.page_url }}
    
    steps:
      - name: Checkout
        uses: actions/checkout@v4
      
      - name: Setup pnpm
        uses: pnpm/action-setup@v2
        with:
          version: 8
      
      - name: Setup Node.js
        uses: actions/setup-node@v4
        with:
          node-version: '20'
          cache: 'pnpm'
      
      - name: Install dependencies
        run: pnpm install --frozen-lockfile
      
      - name: Lint JavaScript
        run: pnpm lint:js
        continue-on-error: false
      
      - name: Build
        run: pnpm build
      
      - name: Lint HTML output
        run: pnpm lint:html
        continue-on-error: true
      
      - name: Run tests
        run: pnpm exec playwright test || true
      
      - name: Lighthouse audit
        run: pnpm test:lighthouse
        continue-on-error: true
      
      - name: Upload pages artifact
        uses: actions/upload-pages-artifact@v2
        with:
          path: './dist'
      
      - name: Deploy to GitHub Pages
        id: deployment
        uses: actions/deploy-pages@v2
```

---

## 5. Adaptation des maquettes en pages Astro

### Principes de conversion

Chaque maquette HTML devient un fichier `.astro` :

```astro
---
// src/pages/migrate/airflow.astro
import BaseLayout from '../../layouts/BaseLayout.astro';
import HydraCore from '../../components/HydraCore.jsx';

// État initial du DSL pour Airflow
const initialState = {
  tool: 'airflow',
  examples: [/* exemples du playground */]
};
---

<BaseLayout title="Migrate from Airflow" description="Translate Airflow DAGs to Hydra manifests">
  <!-- Contenu statique de migrate-airflow.html -->
  
  <!-- Composant interactif -->
  <HydraCore client:visible tool="airflow" initialState={initialState} />
</BaseLayout>
```

### Le composant HydraCore.jsx

C'est le noyau partagé : tokenizer, lint, menus, icônes, provenance.

```jsx
// src/components/HydraCore.jsx
import React, { useState } from 'react';

export default function HydraCore({ tool, initialState }) {
  const [input, setInput] = useState('');
  const [output, setOutput] = useState(null);
  
  // Importer les motifs du bon outil
  const patterns = require(`./tools/${tool}.patterns.js`);
  
  // Importer le tokenizer commun
  const { tokenize, lint } = require('./hydra-core-lib.js');
  
  const handleTranslate = () => {
    const tokens = tokenize(input, tool);
    const result = patterns.translate(tokens);
    const errors = lint(result, tool);
    setOutput({ result, errors });
  };
  
  return (
    <div className="hydra-core">
      <textarea value={input} onChange={(e) => setInput(e.target.value)} />
      <button onClick={handleTranslate}>Translate</button>
      {output && <pre>{JSON.stringify(output, null, 2)}</pre>}
    </div>
  );
}
```

**Les patterns par outil** (400 lignes chacun) :

```javascript
// src/components/tools/airflow.patterns.js
export const translate = (tokens) => {
  // Reconnaître @dag, operators, XCom, etc.
  // Retourner le manifeste YAML
};

export const lint = (yaml) => {
  // Vérifier les erreurs spécifiques à Airflow
};
```

---

## 6. Styles globaux

### src/styles/global.css

```css
:root {
  --bg: #fff;
  --bg-soft: #f6f8f8;
  --bg-panel: #fff;
  --bg-code: #f4f6f6;
  
  --text: #0e1a17;
  --text-soft: #5a6a66;
  --text-mut: #8a9793;
  
  --border: #e2e8e6;
  --border-strong: #cdd8d5;
  
  --accent: #0f766e;
  --accent-soft: #d7efeb;
  --accent-text: #0b5850;
  
  --ok: #15803d;
  --ok-soft: #dcf3e3;
  --warn: #b45309;
  --warn-soft: #fbedd8;
  --err: #b91c1c;
  --err-soft: #fbe4e4;
  
  --mono: ui-monospace, "SF Mono", Menlo, Consolas, monospace;
  --sans: system-ui, -apple-system, "Segoe UI", Roboto, sans-serif;
}

html[data-theme="dark"] {
  --bg: #0d1412;
  --bg-soft: #111b18;
  --accent: #2dd4bf;
  /* ... tous les jetons dark */
}

* { box-sizing: border-box; }

body {
  margin: 0;
  font-family: var(--sans);
  background: var(--bg);
  color: var(--text);
  font-size: 15px;
  line-height: 1.5;
}

:where(button, input, select, summary):focus-visible {
  outline: 2px solid var(--accent);
  outline-offset: 2px;
}

.wrap {
  max-width: 1220px;
  margin: 0 auto;
  padding: 22px clamp(12px, 3vw, 22px) 70px;
}
```

---

## 7. Scripts d'aide

### scripts/copy-mockups.js

Copier les maquettes du dossier `mockups/` et les renommer :

```javascript
// scripts/copy-mockups.js
const fs = require('fs');
const path = require('path');

const mappings = {
  'migrate-airflow.html': 'src/pages/migrate/airflow.astro',
  'migrate-dagster.html': 'src/pages/migrate/dagster.astro',
  // etc.
};

Object.entries(mappings).forEach(([src, dst]) => {
  let content = fs.readFileSync(path.join('mockups', src), 'utf-8');
  
  // Convertir en frontmatter Astro
  const [title, description] = extractMetadata(src);
  const frontmatter = `---
import BaseLayout from '../../layouts/BaseLayout.astro';
const title = "${title}";
const description = "${description}";
---

<BaseLayout title={title} description={description}>
`;
  
  content = frontmatter + content + '\n</BaseLayout>';
  fs.writeFileSync(path.join(dst), content);
  console.log(`✓ ${dst}`);
});
```

### scripts/lighthouse-budget.json

Budgets strictes pour Lighthouse CI :

```json
{
  "bundles": [
    {
      "name": "js",
      "budget": 50,
      "resourceSizes": [
        {
          "resourceType": "script",
          "budget": 50
        }
      ]
    }
  ],
  "metrics": [
    {
      "name": "Largest Contentful Paint",
      "budget": 1500,
      "measurement": "navigation"
    },
    {
      "name": "Cumulative Layout Shift",
      "budget": 0.1,
      "measurement": "navigation"
    }
  ]
}
```

---

## 8. Premier déploiement

### Checklist

- [ ] Repo créé sur GitHub (`hydra-site` ou équivalent)
- [ ] `.github/workflows/build.yml` en place
- [ ] `public/.nojekyll` vide
- [ ] `public/CNAME` contient `hydraetl.com`
- [ ] GitHub Pages configuré pour servir depuis `gh-pages`
- [ ] Premier commit sur `main`
- [ ] Workflow GitHub Actions exécuté
- [ ] Site accessible sur https://hydraetl.com

### Commandes locales

```bash
# Installation
pnpm install

# Développement avec rechargement à chaud
pnpm dev

# Build production
pnpm build

# Serveur de preview (simule GitHub Pages)
pnpm preview

# Vérifier les liens
npx linkinator dist/

# Test Lighthouse local (nécessite lighthouse CLI)
pnpm test:lighthouse
```

---

## 9. Prochaines étapes après le squelette

Une fois le build validé sur `/migrate/airflow` :

1. **Portage du noyau des tunnels** → extraire `HydraCore.jsx` des maquettes
2. **Autres tunnels** → 5 fichiers de 400 lignes
3. **Pages de contenu** → guide, learn, reference (statique)
4. **Fiches de référence** → générées depuis le code du produit
5. **Optimisations Lighthouse** → compression, lazy loading, code splitting

---

## Notes importantes

- **Pas de frameworks CSS** — utilisez les variables et le CSS natif
- **Pas de webfonts** — polices système uniquement
- **Pagefind en différé** — chargé au premier clic sur la recherche, pas au chargement de page
- **Deux fichiers critiques** — `.nojekyll` et `CNAME` doivent être dans `public/`, pas `src/`
- **JavaScript dans les îlots** — `client:visible` pour les traducteurs, `client:idle` pour le playground
- **Images en AVIF** — utiliser `astro:assets` pour l'optimisation automatique

