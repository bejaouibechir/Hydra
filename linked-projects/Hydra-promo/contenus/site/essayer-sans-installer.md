# Section « Essayer sans installer » — pour hydraetl.com

> **Où la placer** : en haut de `/get-started`, **avant** les instructions `pip install`.
> Quelqu'un qui découvre Hydra veut voir avant d'installer. La page actuelle demande
> d'installer d'abord, ce qui perd les visiteurs qui évaluent.
>
> Un lien depuis la page d'accueil vers cette section vaut aussi la peine : c'est
> l'appel à l'action le moins engageant du site.

---

## Le texte (anglais, comme le reste du site)

### Try Hydra in your browser

Two sandboxes run Hydra without installing anything on your machine. Nothing is
left behind when you close the tab.

---

#### Guided labs — nothing to sign up for

**killercoda.com/hydra-etl**

Killercoda is a website that gives you a real Linux terminal inside your browser,
with a short lesson beside it telling you exactly what to type. It checks your
work as you go, so you cannot get stuck.

Six labs, ten to fifteen minutes each:

1. **Meet hdrctl** — what a job is, and how to create one
2. **Validate before you run** — catching a broken pipeline before it touches data
3. **test is not validate** — two checks that answer different questions
4. **hdrctl over HTTP** — the same engine behind a REST API
5. **Jobs vs workflows** — chaining jobs together
6. **Parameters and secrets** — one pipeline, two databases, no credentials in any file

Best first lab: **Meet hdrctl**.

*[ Button: Open the labs → https://killercoda.com/hydra-etl ]*

---

#### A full environment, with the visual editor

**One click, then one command.**

GitHub Codespaces starts a real machine in the cloud and opens a code editor in
your browser. You need a free GitHub account; it runs within GitHub's free
monthly allowance.

This environment comes with a MySQL database already running beside it, sample
data, and a pipeline that works. When the editor opens, type:

```
./tour
```

A five-minute walkthrough shows you each command before running it: what a YAML
pipeline looks like, running a five-step workflow, running the same job against
two environments, and opening the visual editor. It is the only thing you have
to type.

Unlike the labs, this one includes **Hydra Studio** — the visual editor — so you
can see the same pipeline as a diagram, move the boxes, and run it from there.

*[ Codespaces badge, linking to https://codespaces.new/bejaouibechir/hydra-demo ]*

```html
<a href="https://codespaces.new/bejaouibechir/hydra-demo">
  <img src="https://github.com/codespaces/badge.svg" alt="Open in GitHub Codespaces">
</a>
```

---

#### Which one should you pick?

|  | Guided labs | Full environment |
|---|---|---|
| Account needed | none | a free GitHub account |
| Time | 10–15 min per lab | 5 min for the tour |
| You are told what to type | yes, step by step | yes, the tour shows every command |
| Visual editor (Studio) | no | yes |
| A database to work against | yes, in some labs | yes, MySQL |
| Best for | learning the commands | seeing the whole product |

Once either one has convinced you:

```
pip install hydra-etl
```

---

## Notes de mise en œuvre

- **Le tableau comparatif compte** : sans lui, le visiteur ne sait pas lequel choisir
  et repart. C'est le composant qui décide.
- **Le `./tour` doit être visible avant le clic**, pas seulement après. Quelqu'un qui
  ouvre un Codespace sans savoir quoi taper referme l'onglet.
- **Expliquer ce que sont Killercoda et Codespaces** en une phrase chacun : ce sont
  des noms inconnus de la plupart des développeurs data.
- **Ordre** : les labos d'abord, parce qu'ils ne demandent aucun compte. Le Codespace
  demande un compte GitHub, ce qui est un frein pour un premier contact.
- Les liens `utm_source` sont déjà en place côté Killercoda et hydra-demo, donc le
  trafic entrant sera attribuable dans Umami.
