# Protocole du benchmark reproductible (Bechir exécute, Claude rédige la page)

> But : une page publique qui prouve « lecture CSV ~4× plus rapide avec Rust » — ou qui la corrige.
> Base existante : `bench/perf_bench.py` (scénarios S1 filtre CSV, S2 JSON→CSV, S3 agrégat).

## 1. Machine (à noter tel quel)
- CPU (modèle, nb cœurs), RAM, type de disque (SSD/NVMe), OS + version
- Python (version exacte), `pip freeze | grep -i -E "hydra|pandas|duckdb|pyarrow"`
- Machine au repos : fermer navigateur/IDE, secteur branché

## 2. Commandes (à lancer dans cet ordre)
```bash
python -m venv .venv-bench && . .venv-bench/bin/activate     # Windows : .venv-bench\Scripts\activate
pip install "hydra-etl[native,duckdb,parquet]==0.10.1"
git clone https://github.com/bejaouibechir/Hydra && cd Hydra

# 3 tailles × moteur python puis rust ; 5 répétitions chacune
for rows in 100000 1000000 5000000; do
  HYDRA_BACKEND=python python bench/perf_bench.py --rows $rows --scenarios s1,s2,s3 > res_py_$rows.txt
  HYDRA_BACKEND=rust   python bench/perf_bench.py --rows $rows --scenarios s1,s2,s3 > res_rs_$rows.txt
done
```
⚠️ À vérifier : que `perf_bench.py` respecte `HYDRA_BACKEND` et fait bien plusieurs répétitions. Sinon, l'ajouter (et le dire sur la page).

## 3. Ce qu'il faut me renvoyer
Les fichiers `res_*.txt` + la fiche machine. Je rédige la page avec :
- tableau médiane / min / max par scénario, taille et moteur ;
- **les cas sans gain** (ex. petits fichiers, scénarios non accélérés) — obligatoire ;
- les commandes exactes pour que n'importe qui reproduise.

## 4. Règle
Si le gain mesuré n'est pas ~4×, on corrige le chiffre partout (README, site, annuaires) plutôt que de l'arrondir.
