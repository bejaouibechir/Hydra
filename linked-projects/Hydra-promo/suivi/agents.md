# Agents et tâches planifiées

> Créés le 21/09/2026. Les deux tâches s'exécutent **sur l'ordinateur de Bechir** : elles ne fonctionnent que s'il est allumé, connecté, avec l'application Claude ouverte.
> Approbation automatique activée : les runs ne s'arrêtent pas pour demander une autorisation. Notification envoyée sur le téléphone à la fin.

## 1. Rapport hebdomadaire — samedi 10 h (heure de Paris)

`trig_011dzVb5mrGpzdiM5deX6MrV`

Lit `CLAUDE.md`, le journal et la liste d'actions, puis relève les chiffres réels (GitHub, PyPI, PR awesome, Actions). Produit :
chiffres et écarts · ce qui a bougé · ce qui bloque · **une** recommandation d'article fondée sur un fait de la semaine · les 3 actions les plus rentables.
Met ensuite à jour `suivi/journal.md` et `suivi/actions-bechir.md`.

**Il ne publie rien.** Si une source est inaccessible, il l'écrit au lieu d'inventer un chiffre.

## 2. Veille forums — samedi 10 h 30 (heure de Paris)

`trig_014YZFUGXwm7o2roPckYH5HV`

Cherche sur Stack Overflow, Reddit, Hacker News les discussions récentes où Hydra ETL répond à un vrai besoin. Retient 3 à 5 maximum, écrit `suivi/veille-forums.md` avec, pour chacune : le besoin, le degré de pertinence, un brouillon de réponse en anglais (affiliation déclarée, une seule mention, extrait de code concret) et le risque lié aux règles d'autopromotion.

**Il ne publie rien.** Bechir publie lui-même, après relecture.

## 3. Filet de sécurité — si la machine était éteinte

Le rattrapage automatique n'existe pas : une tâche manquée ne se relance pas toute seule. Deux parades :

**a) Côté Windows — ouvrir Claude avant l'heure** (à configurer une fois)

1. Ouvrir le **Planificateur de tâches** (`taskschd.msc`).
2. *Créer une tâche…* → Nom : `Ouvrir Claude pour le rapport Hydra ETL`.
3. Onglet **Déclencheurs** → *Nouveau* → Hebdomadaire, samedi, **09 h 50**.
4. Onglet **Actions** → *Nouveau* → *Démarrer un programme* → chemin de `claude.exe`.
   Pour le trouver : clic droit sur le raccourci Claude → *Propriétés* → champ **Cible**.
5. Onglet **Conditions** → cocher **Sortir l'ordinateur de veille pour exécuter cette tâche**.
6. Onglet **Paramètres** → cocher **Exécuter la tâche dès que possible après un démarrage planifié manqué**.

Ça couvre la veille et le démarrage tardif, mais pas une machine restée éteinte tout le samedi.

**b) Côté projet — règle de rattrapage**

Inscrite dans `CLAUDE.md` : au début de chaque session, l'assistant vérifie la date du dernier rapport dans `suivi/journal.md` ; s'il date de plus de 7 jours, il le produit immédiatement. Fonctionne avec n'importe quel assistant, sans infrastructure.

## Modifier ou arrêter une tâche

Dans l'application Claude, section des tâches planifiées : on peut changer l'horaire, désactiver ou supprimer. Ou le demander en session : « change l'horaire du rapport hebdomadaire ».

## Ce qui manque encore pour un rapport complet

| Source | État | Ce qu'il faut |
|---|---|---|
| GitHub, PyPI | ✅ accessibles | — |
| Site (pages, blog) | ✅ code source local | — |
| Umami (trafic) | ❌ | un jeton API Umami |
| Search Console (requêtes) | ❌ | un export CSV ou un accès API |
