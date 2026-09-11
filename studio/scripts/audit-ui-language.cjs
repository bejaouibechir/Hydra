const fs = require('fs')
const path = require('path')
const ts = require('typescript')

const root = path.resolve(__dirname, '..', 'src')
const french = /[àâçéèêëîïôùûüÿœæ]|\b(?:accueil|ajouter|annuler|archiver|aucun|aucune|choisir|colonne|colonnes|créer|démarrer|dossier|dossiers|dupliquer|durée|échec|échoué|enregistrer|erreur|exécuter|fichier|fichiers|fermer|glisser|hôte|importer|invalide|lancer|lecture|lignes|manuel|masquer|modifier|nœud|nom|nouveau|nouvelle|ouvrir|parcourir|planifié|projet|projets|racines|rechercher|réessayer|renommer|répertoire|requis|requise|retirer|retour|sauvegarder|sélection|sélectionner|statistiques|succès|supprimer|taux|terminé|utilisateur|vérifier|vérifiez|voir)\b/i

function files(dir) {
  return fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name)
    if (entry.isDirectory()) return entry.name === '_backups' ? [] : files(full)
    if (!/\.tsx?$/.test(entry.name) || /\.(?:test|spec)\.tsx?$/.test(entry.name)) return []
    return [full]
  })
}

const findings = []
for (const file of files(root)) {
  const source = fs.readFileSync(file, 'utf8')
  const sf = ts.createSourceFile(file, source, ts.ScriptTarget.Latest, true,
    file.endsWith('.tsx') ? ts.ScriptKind.TSX : ts.ScriptKind.TS)

  function check(text, node) {
    const value = text.replace(/\s+/g, ' ').trim()
    if (!value || !french.test(value)) return
    const pos = sf.getLineAndCharacterOfPosition(node.getStart(sf))
    findings.push(`${path.relative(root, file)}:${pos.line + 1}: ${value}`)
  }

  function visit(node) {
    if (ts.isStringLiteralLike(node) || ts.isJsxText(node)) check(node.text, node)
    if (ts.isTemplateExpression(node)) {
      check(node.head.text, node.head)
      for (const span of node.templateSpans) check(span.literal.text, span.literal)
    }
    ts.forEachChild(node, visit)
  }
  visit(sf)
}

if (findings.length) {
  console.error('French UI strings detected:')
  for (const finding of findings) console.error(`  ${finding}`)
  process.exit(1)
}

console.log('UI language audit passed: no French user-facing strings detected.')
