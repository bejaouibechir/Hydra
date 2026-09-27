# LinkedIn post #2 — l'article + awesome-pipeline

> Consigne : publier 24 à 48 h après la mise en ligne de l'article. Lien dans le 1er commentaire.
> ⚠️ Ne pas publier avant que l'article soit en ligne sur hydraetl.com.

---

Hydra ETL was accepted into awesome-pipeline this week — a curated list of 6,600 stars.

One line, in a file thousands of data engineers browse when they pick a tool. That single merge did more for the project than every post I wrote last month.

So I wrote the tutorial I wish existed for a beta tool: no Docker, no database, no cluster. One `pip install`, a script that generates a million rows, four small YAML files, and a job that cleans them.

Then I measured the optional Rust engine against the default Python one, on the same job, on two machines:

→ Windows laptop: 6.5 s → 3.8 s (~42% faster)
→ Linux VM: 8.7 s → 6.8 s (~22% faster)

Two things I could have hidden, and did not:

→ One run out of six came back twice as slow. A background process, not the engine. It is in the article.
→ Our own README mentioned "CSV reading ~4× faster". True for reading, misleading for the whole job. The article says so.

Numbers that survive a reader reproducing them are worth more than numbers that impress.

The tutorial is in the first comment. If you run it, tell me what broke — that feedback is what I need right now.

#dataengineering #opensource #ETL #python #rust

---

**First comment:**
The tutorial: https://hydraetl.com/blog/one-million-rows?utm_source=linkedin&utm_medium=social&utm_campaign=article-1m-rows
The code: https://github.com/bejaouibechir/Hydra
