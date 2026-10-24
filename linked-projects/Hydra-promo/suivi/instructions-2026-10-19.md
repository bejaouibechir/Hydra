# Instructions du 19/10/2026 — les 4 actions qui ne passent que par toi

> Les quatre autres tâches ont leur fichier dédié :
> `contenus/articles/en-03-yaml-vs-scripts-devto.md` et `-hashnode.md` (tâche 3) ·
> `contenus/posts/linkedin-03-liens-utm.md` (tâche 2) ·
> `contenus/annuaires/pr-14699-refonte.md` (tâche 6) ·
> `contenus/github/releases-0.11.3-0.11.4.md` (tâche 7).

---

## Tâche 1 — Indexation ▶️ À EXÉCUTER

**Trois URL, dans cet ordre.** Le slash final compte : c'est la forme canonique du site
(`BaseLayout.astro` construit `canonical` depuis `Astro.url.pathname`, et le sitemap l'écrit ainsi).
Soumettre la variante sans slash fait inspecter une URL qui redirige, et le rapport est inutilisable.

```
https://hydraetl.com/blog/why-yaml-pipelines-beat-ad-hoc-scripts/
https://hydraetl.com/blog/sql-server-error-18456-login-failed/
https://hydraetl.com/
```

**Google Search Console** → la propriété `hydraetl.com` → barre « Inspection d'URL » en haut →
coller l'URL → Entrée → attendre le verdict → **« Demander l'indexation »** → recommencer pour la
suivante. Le quota est d'une dizaine de demandes par jour, trois passent sans problème.

**Bing Webmaster Tools** → `hydraetl.com` → **Soumission d'URL** → les trois d'un coup (Bing accepte
le lot). ChatGPT s'appuie sur l'index Bing : sauter cette étape, c'est renoncer à la moitié de
l'objectif GEO.

ℹ️ **Déjà vérifié par moi le 19/10 :** le sitemap `https://hydraetl.com/sitemap-0.xml` contient
bien les trois URL, dont le nouvel article. Rien à corriger de ce côté.

⚠️ Le 18456 est en ligne depuis le **26 septembre et n'a jamais été soumis**. Vingt-trois jours
pendant lesquels il ne pouvait apparaître nulle part. C'est l'action la moins coûteuse et la plus
en retard du projet.

---

## Tâche 5 — Nettoyer le dépôt public du site ▶️ À EXÉCUTER

Le commit « Adding an articleé » du 19/10 a ajouté, en plus de l'article, **37 fichiers
`.claude/skills/brand-motion-design/`** et un fichier `brand-motion-design-skill` à la racine.
Un dépôt public qui sert de vitrine ne porte pas l'outillage local de son auteur — et ces fichiers
ne servent pas au site : Astro ne construit que `src/`.

Dans **PowerShell**, depuis `C:\Users\DELL\Desktop\hydra-site` :

```powershell
cd C:\Users\DELL\Desktop\hydra-site
git status                          # doit être propre avant de commencer

# retirer du suivi git, SANS supprimer du disque (--cached)
git rm -r --cached ".claude/skills/brand-motion-design"
git rm --cached "brand-motion-design-skill"

# empêcher le retour
Add-Content .gitignore "`n# outillage local, hors du dépôt publié`n.claude/`nbrand-motion-design-skill"

git add .gitignore
git status                          # vérifier : 38 suppressions + .gitignore modifié, RIEN d'autre
git commit -m "chore: keep local tooling out of the published repo"
```

**Avant le `git push`, montre-moi `git status` et `git diff --cached --stat`** — la règle du projet
est que rien ne part sans que le diff ait été vu. Le push déclenche *Build & Deploy* ; l'article
n'est pas touché, donc le site ne doit pas changer d'un pixel.

📋 Même chose dans le dépôt **produit** : `ctemptest.txt` traîne à la racine depuis la 0.11.4.
Commandes en fin de `contenus/github/releases-0.11.3-0.11.4.md`.

---

## Tâche 8a — Activer Discussions ▶️ À EXÉCUTER

Vérifié ce matin : `has_discussions: false`. En attente depuis le 19 septembre.

`github.com/bejaouibechir/Hydra` → **Settings** → section **Features** → cocher **Discussions** →
**Set up discussions**. Catégories à garder : *Q&A*, *Ideas*, *Show and tell*. Supprimer
*Announcements* tant qu'il n'y a rien à annoncer — une catégorie vide donne l'image d'un projet
désert.

Pourquoi ça compte maintenant : les 7 tickets ouverts sont **tous les tiens**, aucun commentaire.
Un inconnu qui a une question n'ouvre pas une issue sur un projet bêta, il n'ose pas. Discussions
baisse cette marche. Sur la même page, activer aussi le **signalement privé de vulnérabilités**
(*Private vulnerability reporting*), en attente depuis la même date.

---

## Tâche 8b — Profil C# Corner ▶️ À EXÉCUTER

C'est, de toutes les actions du projet, celle qui a le meilleur rapport effort/portée : **un champ
de formulaire qui apparaît au bas de tes 119 articles d'un coup** (`CLAUDE.md` §2 bis).

`c-sharpcorner.com` → ton profil → **Edit Profile** :

- champ **Website** : `https://hydraetl.com`
- à ajouter au **Bio**, en anglais :

```
Creator of Hydra ETL, an open-source declarative ETL engine: pipelines are YAML files validated before they run.
```

Ne rien toucher d'autre, et surtout **ne pas ajouter de liens dans les anciens articles** :
pertinence nulle, et le motif ressemble à de l'injection de liens, ce qui mettrait en jeu le statut
Platinum — lequel est l'actif lui-même.
