// n8n Code node : "Run Once for All Items", langage JavaScript.
// Prérequis : variable d'environnement n8n NODE_FUNCTION_ALLOW_BUILTIN=crypto
// Entrée : un item = sortie du Technical Content Agent (contenu_markdown, exemples_code[{fichier, contenu}]).
// Sortie : le même item + content_hash + content_hash_fichiers[].
// Doit rester strictement équivalent à content_hash.py.
const crypto = require('crypto');

const PATH_RE = /^[A-Za-z0-9._\/-]+$/;

function normalizeText(s) {
  s = s.replace(/^\uFEFF/, '').replace(/\r\n/g, '\n').replace(/\r/g, '\n');
  s = s.split('\n').map((l) => l.replace(/[ \t]+$/, '')).join('\n');
  s = s.replace(/\n+$/, '') + '\n';
  return s;
}

function computeContentHash(files) {
  // files : [{ path: 'contenu.md' | 'pipelines/x.yaml', content: string }]
  const seen = new Set();
  for (const f of files) {
    if (!PATH_RE.test(f.path) || f.path.startsWith('/') || f.path.split('/').includes('..')) {
      throw new Error('chemin non autorisé : ' + f.path);
    }
    if (f.path !== 'contenu.md' && !f.path.startsWith('pipelines/')) {
      throw new Error('fichier hors périmètre du hash : ' + f.path);
    }
    if (seen.has(f.path)) throw new Error('chemin en double : ' + f.path);
    seen.add(f.path);
  }
  const sorted = [...files].sort((a, b) => (a.path < b.path ? -1 : a.path > b.path ? 1 : 0));
  const h = crypto.createHash('sha256');
  for (const f of sorted) {
    h.update('\n--FILE:' + f.path + '--\n', 'utf8');
    h.update(normalizeText(f.content), 'utf8');
  }
  return { hash: h.digest('hex'), paths: sorted.map((f) => f.path) };
}

if (typeof module !== 'undefined' && module.exports) {
  module.exports = { normalizeText, computeContentHash };
}

if (typeof $input !== 'undefined') {
  const item = $input.first().json;
  const files = [{ path: 'contenu.md', content: item.contenu_markdown }];
  for (const ex of item.exemples_code || []) {
    files.push({ path: ex.fichier, content: ex.contenu });
  }
  const { hash, paths } = computeContentHash(files);
  return [{ json: { ...item, content_hash: hash, content_hash_fichiers: paths } }];
}