# Exemple de conversion : migrate-airflow.html → page Astro

Guide pas-à-pas montrant comment transformer une maquette en page Astro opérationnelle.

---

## 1. La maquette actuelle

**Fichier source :** `documentations/mockups/migrate-airflow.html` (1139 lignes)

**Structure :**
```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <title>…</title>
  <style>
    /* Variables CSS, styles globaux */
  </style>
</head>
<body>
  <nav class="swx">…</nav>
  <div class="wrap">
    <!-- Conteneur principal en deux volets -->
    <textarea id="airflow-input">…</textarea>
    <div id="yml-output">…</div>
  </div>
  <script>
    var $ = function(i) { return document.getElementById(i); };
    var lintPy = function() { /* tokenizer, lint */ };
    var translate = function() { /* DAG → YAML */ };
    var buildYaml = function() { /* construction du manifeste */ };
    var reverse = function() { /* YAML → Python */ };
    var run = function() { /* mise à jour */ };
    // … 620 lignes de JavaScript
  </script>
</body>
</html>
```

---

## 2. Démêler la maquette

Le JavaScript de la maquette fait trois choses :

1. **Interfacer** — gérer les clics, affichages, thèmes
2. **Traiter** — tokenizer Airflow, lint, traduction DAG→YAML
3. **Rendu** — coloration, provenance, validation

En Astro, cela devient :

| Partie | Fichier | Tech |
|---|---|---|
| Interfacer | `HydraCore.jsx` | React |
| Tokenizer Airflow | `airflow.patterns.js` | JavaScript pur |
| Rendu | `global.css` | CSS natif |

---

## 3. Créer la page Astro

**Fichier :** `src/pages/migrate/airflow.astro`

```astro
---
import BaseLayout from '../../layouts/BaseLayout.astro';
import HydraCore from '../../components/HydraCore.jsx';

// État initial
const tool = 'airflow';
const title = 'Migrate from Airflow';
const description = 'Paste a DAG, get a Hydra job manifest and workflow.';
const examples = [
  {
    name: '1-to-N fan-out',
    code: `from airflow import DAG\n@dag\ndef my_dag():\n    ...`
  },
  // Autres exemples dans mockups/migrate-airflow.html
];

---

<BaseLayout {title} {description}>
  <!-- Navigation intérinsèque (déjà dans BaseLayout) -->
  
  <!-- Le composant interactif, hydraté au scroll -->
  <HydraCore 
    client:visible
    tool={tool}
    title={title}
    examples={examples}
  />
</BaseLayout>
```

---

## 4. Créer le composant React

**Fichier :** `src/components/HydraCore.jsx`

C'est l'enveloppe qui gère l'interface et orchestre les outils.

```jsx
import React, { useState, useEffect } from 'react';
import AirflowPatterns from './tools/airflow.patterns.js';

export default function HydraCore({ tool, title, examples }) {
  const [input, setInput] = useState('');
  const [tab, setTab] = useState('inspect');
  const [theme, setTheme] = useState('light');
  
  // Charger le bon outil selon le paramètre
  const patterns = selectTool(tool);
  
  const handleTranslate = () => {
    try {
      const tokens = patterns.tokenize(input);
      const yaml = patterns.translate(tokens);
      const lints = patterns.lint(yaml);
      setOutput({ yaml, lints, success: true });
    } catch (e) {
      setOutput({ error: e.message, success: false });
    }
  };
  
  const handlePaste = async () => {
    const text = await navigator.clipboard.readText();
    setInput(text);
  };
  
  return (
    <div className="hydra-core">
      {/* En-tête avec outils */}
      <div className="topbar">
        <select value={tool} onChange={(e) => setTool(e.target.value)}>
          <option value="airflow">Airflow</option>
          <option value="dagster">Dagster</option>
          {/* etc. */}
        </select>
        <button onClick={handlePaste}>📋 Paste</button>
        <button onClick={handleTranslate}>→ Translate</button>
      </div>
      
      {/* Deux volets */}
      <div className="two-pane">
        {/* Gauche : entrée */}
        <div className="pane">
          <div className="ph"><h2>Input</h2> <span id="fn">{filename}</span></div>
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            placeholder="Paste your DAG here…"
            spellCheck="false"
          />
        </div>
        
        {/* Droite : sortie */}
        <div className="pane out">
          <div className="ph">
            <h2>Output</h2>
            <div className="tabs">
              <button 
                className={tab === 'inspect' ? 'on' : ''}
                onClick={() => setTab('inspect')}
              >
                inspector
              </button>
              <button 
                className={tab === 'yaml' ? 'on' : ''}
                onClick={() => setTab('yaml')}
              >
                workflows/dag.yaml
              </button>
            </div>
          </div>
          
          {/* Affichage du graphe ou YAML */}
          {tab === 'inspect' ? (
            <div className="canvas" dangerouslySetInnerHTML={{
              __html: renderGraph(output?.graph || [])
            }} />
          ) : (
            <pre className="yml">{output?.yaml || ''}</pre>
          )}
          
          {/* Validation */}
          <div className="diag">
            {output?.lints?.map((lint, i) => (
              <div key={i} className={`dg ${lint.level}`}>
                <span className="sv"></span>
                <span><b>{lint.step}</b> {lint.message}</span>
              </div>
            ))}
          </div>
        </div>
      </div>
      
      {/* Exemples */}
      <div className="examples">
        <button 
          onClick={() => setInput(examples[0].code)}
          className="example-btn"
        >
          Load example: {examples[0].name}
        </button>
      </div>
    </div>
  );
}

function selectTool(name) {
  const tools = {
    airflow: AirflowPatterns,
    dagster: require('./tools/dagster.patterns.js'),
    prefect: require('./tools/prefect.patterns.js'),
    // etc.
  };
  return tools[name] || tools.airflow;
}

function renderGraph(steps) {
  // Appeler le moteur de graphe (workflow-view.html)
  // Retourner SVG
}
```

---

## 5. Créer les patterns Airflow

**Fichier :** `src/components/tools/airflow.patterns.js`

C'est le **cœur** — tout ce qui reconnaît et traduit Airflow.

```javascript
// Importer le noyau partagé
import { tokenize as tokenizeCore, colorYaml } from '../hydra-core-lib.js';

export const tokenize = (pythonCode) => {
  // Mini-tokenizer : détecte strings, comments, depth
  // Reconnaît : @dag, operators (BranchPythonOperator, etc.)
  // Retourne un tableau de tokens structurés
  return tokenizeCore(pythonCode, {
    language: 'python',
    keywords: ['@dag', 'DAG', 'task', 'operator'],
    stringDelimiters: ['"', "'", '"""', "'''"],
  });
};

export const translate = (tokens) => {
  // Parse les tokens
  // Extrait : dag_id, schedule_interval, tasks, dépendances, XCom
  // Retourne YAML structuré
  
  let dagId = null;
  let schedule = null;
  let tasks = [];
  let deps = {};
  
  for (let token of tokens) {
    if (token.type === 'dag_decorator') {
      // Trouver le nom du DAG
      dagId = token.value.match(/dag_id=["']([^"']+)["']/)?.[1] || 'dag';
    }
    if (token.type === 'schedule') {
      // Extraire la schedule
      schedule = parseSchedule(token.value);
    }
    if (token.type === 'operator') {
      // Chaque opérateur devient un step
      tasks.push({
        name: token.id,
        type: classifyOperator(token.class),
        path: './jobs/' + token.id + '.yaml'
      });
    }
    if (token.type === 'dependency') {
      // XCom ou >> → depends_on
      deps[token.to] = deps[token.to] || [];
      deps[token.to].push(token.from);
    }
  }
  
  // Construire le manifeste YAML
  return buildYaml(dagId, schedule, tasks, deps);
};

export const lint = (yaml) => {
  // Vérifier erreurs Airflow-spécifiques
  // Avertir sur : days_ago deprecated, provide_context, start_date, etc.
  
  const lints = [];
  
  if (yaml.includes('days_ago')) {
    lints.push({
      level: 'warn',
      step: 'dag',
      message: 'days_ago is deprecated in Airflow 2.7+. Use pendulum instead.'
    });
  }
  
  if (yaml.includes('provide_context=True')) {
    lints.push({
      level: 'info',
      step: 'operator',
      message: 'provide_context is implicit in Hydra. Removed from job manifest.'
    });
  }
  
  return lints;
};

function buildYaml(dagId, schedule, tasks, deps) {
  // Construire le manifeste workflow + jobs
  const workflow = {
    version: '1.0',
    workflow: {
      name: dagId,
      trigger: schedule
        ? { type: 'schedule', cron: schedule }
        : { type: 'manual' },
      steps: tasks.map(t => ({
        name: t.name,
        type: t.type,
        job: t.path,
        depends_on: deps[t.name] || []
      }))
    }
  };
  
  return stringifyYaml(workflow);
}

function stringifyYaml(obj, indent = 0) {
  // Convertir en YAML avec formatage
}

function classifyOperator(className) {
  // BranchPythonOperator → condition
  // PythonOperator → job
  // EmailOperator → action
  // etc.
}

function parseSchedule(cronOrTimedelta) {
  // Convertir @daily, @hourly, timedelta, cron en cron standard
}
```

---

## 6. Styles CSS

Le CSS vient de `src/styles/global.css` et `src/components/HydraCore.css` :

```css
/* global.css contient les variables et les règles de base */
:root {
  --bg: #fff;
  --accent: #0f766e;
  /* etc. */
}

/* HydraCore.css contient l'interface spécifique */
.hydra-core {
  display: flex;
  flex-direction: column;
  height: calc(100vh - 56px);
}

.topbar {
  display: flex;
  gap: 8px;
  padding: 12px;
  border-bottom: 1px solid var(--border);
}

.two-pane {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
  flex: 1;
  overflow: hidden;
}

.pane {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--border);
  border-radius: 12px;
}

.pane.out {
  border-color: var(--accent);
  box-shadow: 0 0 0 3px var(--accent-soft);
}
```

---

## 7. Workflow d'import

```bash
# 1. Copier la maquette
cp documentations/mockups/migrate-airflow.html /tmp/maquette.html

# 2. Extraire les fonctions JavaScript essentielles
# (lintPy, translate, buildYaml, reverse)
# → src/components/tools/airflow.patterns.js

# 3. Créer la page Astro
touch src/pages/migrate/airflow.astro

# 4. Tester localement
pnpm dev
# Ouvrir http://localhost:3000/migrate/airflow

# 5. Vérifier
pnpm build
pnpm preview

# 6. Commit
git add src/pages/migrate/airflow.astro
git add src/components/HydraCore.jsx
git add src/components/tools/airflow.patterns.js
git commit -m "feat: Airflow translator page"
git push
```

---

## 8. Checklist de validation

- [ ] Page accessible sur `/migrate/airflow`
- [ ] Paste fonctionne (clipboard API)
- [ ] Traduction DAG → YAML fonctionne
- [ ] Erreurs Airflow affichées
- [ ] Graphe SVG rendu
- [ ] Téléchargement du projet fonctionne
- [ ] Clavier complet (Tab, Enter, Escape)
- [ ] Thème clair et sombre
- [ ] DevTools : zéro appel réseau au load
- [ ] Lighthouse : < 50 ko JS
- [ ] Liens : tous résolvent
- [ ] Secrets : aucun visible

---

## 9. Après validation

Une fois `/migrate/airflow` en ligne et validé :

1. Créer les 5 autres pages (`/migrate/dagster`, etc.) en reprenant le même pattern
2. Extraire le noyau commun en `HydraCore.jsx` (déjà fait, juste peaufiner)
3. Autres pages de contenu (`/guide`, `/learn`, `/reference`)
4. Fiches de référence générées depuis le code

---

## Fichiers à copier/créer

```
Depuis mockups/migrate-airflow.html → 
  src/pages/migrate/airflow.astro
  src/components/HydraCore.jsx
  src/components/tools/airflow.patterns.js
  src/components/hydra-core-lib.js (tokenizer, lint, menus)
  src/styles/HydraCore.css
```

Taille estimée du JavaScript compact :
- `HydraCore.jsx` : 150 lignes
- `airflow.patterns.js` : 400 lignes
- `hydra-core-lib.js` : 600 lignes
- Total compressé : ~25 ko (sous le budget de 50 ko)

