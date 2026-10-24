# Releases GitHub v0.11.3 et v0.11.4 — notes prêtes (19/10/2026)

> **Le problème :** les tags `v0.11.3` et `v0.11.4` existent, le workflow `release` a réussi sur
> les deux (#11 le 27/09, #14 le 18/10), mais **aucune release GitHub n'a été créée**. L'onglet
> Releases s'arrête à **v0.11.2** alors que PyPI sert la **0.11.4**. Quiconque arrive par cet
> onglet — c'est la page que GitHub met en avant à droite du dépôt — croit le projet à l'arrêt
> depuis le 26 septembre.
>
> Les textes ci-dessous sont dérivés du `CHANGELOG.md` du dépôt, pas réécrits : c'est lui la
> source. Rien n'est ajouté qui n'y figure.

## Pourquoi créer les deux, et dans l'ordre

Créer seulement la 0.11.4 laisserait un trou visible dans l'historique. Créer la 0.11.3 d'abord,
puis la 0.11.4, met la plus récente en tête et marque la précédente comme antérieure.

## ▶️ À EXÉCUTER (par Bechir) — avec `gh`

Les notes vivent dans des fichiers, pas dans la ligne de commande : sous Windows, les accents
graves et les guillemets d'un `--notes "..."` multiligne se font manger par PowerShell. On passe
par `--notes-file`.

Depuis `C:\Users\DELL\Desktop\Hydra` :

```bash
gh auth status     # doit répondre "Logged in to github.com"

gh release create v0.11.3 ^
  --title "v0.11.3 - SECRET placeholders actually resolve" ^
  --notes-file "C:\Users\DELL\Desktop\Hydra-promo\contenus\github\release-notes-0.11.3.md"

gh release create v0.11.4 --latest ^
  --title "v0.11.4 - upsert works on PostgreSQL" ^
  --notes-file "C:\Users\DELL\Desktop\Hydra-promo\contenus\github\release-notes-0.11.4.md"
```

Le `^` est la continuation de ligne de **cmd.exe**. Dans **PowerShell**, remplacer `^` par un
accent grave ` ` ` ` — ou plus simplement écrire chaque commande sur une seule ligne.

Dans cet ordre : la 0.11.3 d'abord, sans `--latest`, puis la 0.11.4 **avec** `--latest`, pour
qu'elle soit celle que GitHub met en avant.

## 📋 POUR INFO — pourquoi aucun `.vsix` en pièce jointe

Les releases v0.10.x et v0.11.x n'ont **aucun asset**. Joindre le `.vsix` de l'extension VS Code
avait été prévu le 19/09 et ne l'a jamais été. Ce n'est pas bloquant ici : l'ajouter plus tard sur
une release existante se fait avec `gh release upload v0.11.4 <chemin du .vsix>`. À traiter avec le
`publisher` du Marketplace, qui est l'autre moitié du sujet.

## Vérification après création

```bash
gh release list --limit 5
```

Doit afficher `v0.11.4` marquée `Latest`, puis `v0.11.3`, `v0.11.2`…

## Au passage — hygiène du dépôt produit

Le diff `v0.11.3...v0.11.4` contient un fichier parasite : **`ctemptest.txt`**, ajouté à la racine
du dépôt public. Même famille que le `brand-motion-design-skill` du dépôt du site. À retirer :

```bash
git rm ctemptest.txt
git commit -m "chore: remove stray temp file from the repository root"
```
