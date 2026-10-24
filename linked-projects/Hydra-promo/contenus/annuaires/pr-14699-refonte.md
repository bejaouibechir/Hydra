# awesome-mcp-servers #14699 — refaire la branche (19/10/2026)

> État vérifié le 19/10 par l'API : `state: open`, **`mergeable: false`**, `mergeable_state: dirty`,
> `rebaseable: false`, `updated_at` toujours au **21/09**. Le dépôt, lui, fusionne chaque semaine
> (#16114 le 15/10, #16032 le 09/10). **Personne n'attend : la PR est inerte.**
> Ne pas relancer dans le fil — un rappel sur une PR en conflit agace sans rien débloquer.

## Deux choses ont changé dans le dépôt depuis le 19/09

1. **L'emplacement tient toujours.** Section « Data Platforms for data integration, transformation
   and pipeline orchestration » (titre ligne 1298 du README actuel). Les deux voisins alphabétiques
   sont encore consécutifs : `aywengo/kafka-schema-reg-mcp` (**l.1315**) puis
   `bintocher/mcp-superset` (**l.1316**). L'entrée se place **entre les deux**.
2. **Le style des descriptions a été raccourci par le mainteneur.** Sur les 41 entrées de la
   section : longueur médiane **141 caractères**, maximum 250, et **aucune ne contient plus
   « Install: »** — il les a retirées, y compris sur les lignes qui en avaient. Notre ligne du
   19/09 fait ~300 caractères et porte un `Install:` : telle quelle, elle est hors style et
   rouvre un tour de relecture.

## La ligne à insérer (version raccourcie, ~155 caractères de description)

```
- [bejaouibechir/Hydra](https://github.com/bejaouibechir/Hydra) [![bejaouibechir/Hydra MCP server](https://glama.ai/mcp/servers/bejaouibechir/Hydra/badges/score.svg)](https://glama.ai/mcp/servers/bejaouibechir/Hydra) 🐍 🏠 🍎 🪟 🐧 - Hydra ETL: lets an assistant draft declarative YAML pipelines (CSV, Parquet, PostgreSQL, MySQL, MongoDB, web APIs) and refuses any job the validator rejects.
```

Le badge Glama est conservé — c'est lui qui a fait passer les trois labels au vert. Les émojis sont
inchangés (🐍 Python, 🏠 local, 🍎 🪟 🐧 les trois systèmes). Ce qui disparaît : la clause
`Install:` et la redondance « MCP server for Hydra ETL, a declarative YAML ETL engine ». Ce qui
reste : le **refus par le validateur**, qui est le seul différenciateur dans une liste où « on a un
serveur MCP » ne dit plus rien.

## Les commandes ▶️ À EXÉCUTER (par Bechir)

**Dans Git Bash**, pas dans PowerShell — la séquence utilise `grep`, `head`, `tail`, `cut`, qui
viennent avec Git pour Windows et n'existent pas dans PowerShell. Tout est complet : aucun
`<...>` à remplir, aucun chemin à adapter. On repart de zéro dans
`C:\Users\DELL\Desktop\pr-14699`, en jetant le clone précédent.

### Pourquoi on repart de zéro

Le dépôt amont n'a **aucun `.gitattributes`** et ses fichiers sont stockés en **LF pur** (vérifié
le 19/10). Git pour Windows étant réglé par défaut sur `core.autocrlf=true`, un `git clone` normal
écrit tout le dossier en **CRLF** ; régler `autocrlf=false` *après* le clone fait alors lire chaque
ligne comme modifiée. Constaté le 19/10 : `git diff --stat` annonçait **8 fichiers, 10 093 lignes**
(les 7 READMEs traduits compris) pour l'insertion d'une seule ligne. Le réglage doit donc être
**sur la commande `clone`**. C'est l'incident de `hydra-site` du 22/09 (`CLAUDE.md` règle 8), cette
fois sur un dépôt qui n'est pas le nôtre : poussé tel quel, il aurait fait fermer la PR.

### Étape 1 — le clone propre

Les commandes sont enchaînées par `&&` : si l'une échoue, la suite ne s'exécute pas. Sans cet
enchaînement, un `git fetch upstream` qui échoue (proxy, VPN, réseau) laisse passer le
`git checkout -B patch-2 upstream/main`, qui ne peut alors pas créer la branche — et l'erreur
n'apparaît que trois commandes plus loin, au `push`, sous la forme trompeuse
`src refspec patch-2 does not match any`. Constaté le 19/10.

```bash
cd /c/Users/DELL/Desktop &&
rm -rf pr-14699 &&
git clone -c core.autocrlf=false https://github.com/bejaouibechir/awesome-mcp-servers.git pr-14699 &&
cd pr-14699 &&
git remote add upstream https://github.com/punkpeye/awesome-mcp-servers.git &&
git fetch upstream &&
git checkout -B patch-2 upstream/main &&
echo "=== branche : $(git rev-parse --abbrev-ref HEAD) ===" &&
git diff --stat &&
git status --short &&
echo "=== etape 1 terminee ==="
```

**Points de contrôle :** la sortie doit se terminer par `=== etape 1 terminee ===`, afficher
`=== branche : patch-2 ===`, et **rien** entre les deux. Si `=== etape 1 terminee ===` n'apparaît
pas, une commande a échoué : lire le message, ne pas passer à l'étape 2.

### Étape 2 — l'insertion

À coller d'un bloc, toujours depuis `pr-14699` :

```bash
LIGNE="/c/Users/DELL/Desktop/Hydra-promo/contenus/github/ligne-pr-14699.txt"
N=$(grep -n '^- \[bintocher/mcp-superset\]' README.md | cut -d: -f1)
echo "position d'insertion : $N"
head -n $((N-1)) README.md > README.new
cat "$LIGNE" >> README.new
tail -n +$N README.md >> README.new
mv README.new README.md
git diff --stat
```

Attendu, exactement :

```
position d'insertion : 1316
 README.md | 1 +
 1 file changed, 1 insertion(+)
```

ℹ️ DÉJÀ FAIT : cette séquence a été exécutée le 19/10 sur une copie du README réel du dépôt.
Résultat vérifié : **1 seule ligne ajoutée**, en position 1316, entre
`aywengo/kafka-schema-reg-mcp` et `bintocher/mcp-superset`, émojis intacts, fichier toujours en
LF pur (4 840 lignes, 0 CRLF). Elle n'est pas livrée « à essayer ».

**Si la sortie diffère, s'arrêter** : `git checkout -- README.md` annule tout et le dossier
redevient propre. Me montrer la sortie obtenue.

### Étape 3 — relire, puis pousser

```bash
git diff
```

La ligne ajoutée doit commencer par `- [bejaouibechir/Hydra]` et se terminer par
`refuses any job the validator rejects.`

```bash
git add README.md
git commit -m "Add Hydra ETL MCP server to Data Platforms"
git push --force-with-lease origin patch-2
```

## Si le `push` répond `src refspec patch-2 does not match any`

La branche `patch-2` n'existe pas localement : une commande de l'étape 1 a échoué sans arrêter la
suite. Diagnostic, un bloc à coller :

```bash
cd /c/Users/DELL/Desktop/pr-14699 || echo "DOSSIER INTROUVABLE"
echo "--- dossier ---"; pwd
echo "--- remotes ---"; git remote -v
echo "--- branche courante ---"; git rev-parse --abbrev-ref HEAD
echo "--- branches locales ---"; git branch --list
echo "--- 3 derniers commits ---"; git log --oneline -3
echo "--- fetch amont ---"; git fetch upstream && echo "fetch OK" || echo "FETCH EN ECHEC"
echo "--- position vs amont ---"
echo "avance : $(git rev-list --count upstream/main..HEAD) | retard : $(git rev-list --count HEAD..upstream/main)"
echo "--- diff vs amont ---"; git diff --stat upstream/main..HEAD
```

Lecture du résultat — quatre cas, un seul remède chacun :

| Ce que tu vois | Ce que ça veut dire | Remède |
|---|---|---|
| `avance : 1`, `retard : 0`, diff `README.md \| 1 +` | Le commit est bon et posé sur l'amont à jour. Seul le **nom** de branche manque | `git branch -f patch-2 HEAD` puis `git push --force-with-lease origin patch-2` |
| `retard : 1` ou plus | L'amont a bougé, ou la base était le `main` périmé du fork. Fusionner créerait un conflit | Refaire **l'étape 1** en entier |
| `FETCH EN ECHEC` | Réseau ou proxy. Rien d'autre n'est en cause | Réessayer `git fetch upstream`, puis reprendre l'étape 1 |
| Le log ne montre pas `Add Hydra ETL MCP server to Data Platforms` | Rien n'a été commité | Reprendre à **l'étape 2** |

ℹ️ DÉJÀ FAIT : la logique de ce tableau (`rev-list --count` dans les deux sens) a été vérifiée le
19/10 sur deux dépôts de test — un cas sain, qui donne `avance : 1 | retard : 0`, et un cas où
l'amont a bougé, qui donne `avance : 1 | retard : 1`.

## Après le push

GitHub recalcule la fusionnabilité en une minute. **Vérifier** sur la PR que
`This branch has no conflicts with the base branch` s'affiche et que les trois labels
(`has-emoji`, `valid-name`, `has-glama`) sont toujours verts.

Puis **un seul** commentaire, factuel, sans relance ni excuse :

```
Rebuilt the branch on current main — the entry had drifted into a conflict.

Also shortened the description to match how the section reads now (no `Install:` clause,
~150 characters), and kept the Glama score badge. Quality score is 83%, with A for license,
tool definition quality and maintenance: https://glama.ai/mcp/servers/bejaouibechir/Hydra
```

## Si la PR reste sans réponse 14 jours après un diff propre

Ne rien faire de plus. Le dépôt fusionne par vagues, et l'entrée n'a de valeur que fusionnée :
une relance de plus n'avance rien. Re-vérifier l'état à chaque rapport hebdomadaire.
