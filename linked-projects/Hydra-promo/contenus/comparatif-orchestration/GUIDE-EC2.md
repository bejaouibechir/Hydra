# Mode d'emploi — banc sur EC2

Tout se lance avec **un seul programme**, `run.py`, qui :

- demande **confirmation** avant chaque étape importante (installation, Airbyte, pannes) ;
- affiche une **barre générale** (étapes faites / total) et, pendant chaque étape, le **temps écoulé**, la dernière ligne de la commande et une **barre de progression** pour les pannes ;
- enregistre un **point de reprise** après chaque étape réussie (`results/state.json`) : en cas d'erreur, on relance `python3 run.py` et on **reprend à l'étape en échec**, sans tout refaire ni recréer la machine.

Durée totale estimée : 2 h 30 à 3 h (dont 1 h 30 à 2 h pour Airbyte).

## 1. Créer la machine (console AWS)

| | Valeur |
|---|---|
| AMI | Ubuntu Server 24.04 LTS (x86) |
| Type | m6i.xlarge (à défaut t3.xlarge) |
| Disque | 60 Go gp3, « Delete on termination » coché |
| Région | eu-west-3 (Paris) |
| Groupe de sécurité | SSH (22) depuis **mon IP** uniquement |
| Paire de clés | nouvelle, par ex. `bench-key.pem`, créée pour ce test |

## 2. Copier le dossier sur la machine (PowerShell, sur ton PC)

```powershell
cd C:\Users\DELL\Desktop\Hydra-promo\contenus
scp -i $HOME\Downloads\bench-key.pem -r comparatif-orchestration ubuntu@<IP_PUBLIQUE>:~/
ssh -i $HOME\Downloads\bench-key.pem ubuntu@<IP_PUBLIQUE>
```

## 3. Lancer (sur la machine)

```bash
sudo apt-get update -qq && sudo apt-get install -y -qq tmux
tmux new -s bench            # la session survit si la connexion SSH coupe
cd ~/comparatif-orchestration
python3 run.py               # répondre aux confirmations
```

Si la connexion coupe : se reconnecter puis `tmux attach -t bench`.

### Les phases

| Phase | Contenu | Durée |
|---|---|---|
| 0 | vérification de la machine, paquets, données | 2 min |
| 1 | Hydra ETL : installation, code, pannes ×3 | 5 min |
| 2 | Airflow + dlt + dbt : installation, code, pannes ×3 | 25 min |
| 3 | Airflow + Airbyte + dbt : Docker, Airbyte, PostgreSQL, connexions, pannes ×1 | 1 h 30 à 2 h |
| 4 | compte rendu brut (`results/COMPTE-RENDU-BRUT.md`) | 1 min |

Une phase à la fois : `python3 run.py --phase 1`, etc. Avancement : `python3 run.py --status`.

## 4. En cas d'erreur

Le programme affiche l'erreur, le journal (`results/logs/<étape>.log`) et propose :

- **r** : réessayer l'étape (elle est d'abord remise à zéro) ;
- **s** : passer l'étape (les résultats de la phase seront incomplets) ;
- **q** : quitter. `python3 run.py` reprendra plus tard **à cette étape**.

Refaire une étape déjà réussie : `python3 run.py --redo 2.4`.

## 5. Point de restauration de la machine (recommandé)

À la fin de la phase 2, le programme le rappelle : avant Airbyte, crée un **instantané** du disque.
Console EC2 → Volumes → le volume de l'instance → *Actions* → *Create snapshot*.
Si l'installation d'Airbyte abîme la machine, on recrée un volume à partir de cet instantané au lieu de tout recommencer.
Coût : quelques centimes ; supprime-le à la fin.

## 6. Airbyte : si la configuration automatique échoue (étape 3.6)

L'étape crée les connexions par l'API d'Airbyte. Si elle échoue, ouvre l'interface :

```powershell
ssh -i $HOME\Downloads\bench-key.pem -L 8000:localhost:8000 ubuntu@<IP_PUBLIQUE>
```

puis http://localhost:8000 (identifiants : `sudo abctl local credentials` sur la machine), crée les éléments
avec **les mêmes noms** (`orders_main`, `orders_backup`, `customers`, `bench_postgres`) et relance `python3 run.py`.
Envoie-moi aussi `results/logs/3.6.log`.

## 7. Récupérer les résultats (PowerShell)

```powershell
cd C:\Users\DELL\Desktop\Hydra-promo\contenus\comparatif-orchestration
scp -i $HOME\Downloads\bench-key.pem -r ubuntu@<IP_PUBLIQUE>:~/comparatif-orchestration/results .
```

Puis dis-moi « résultats récupérés » : je les lis directement dans ce dossier.

## 8. Fin

- Terminer l'instance ; vérifier qu'aucun volume ni instantané ne reste (EC2 → Volumes, Snapshots).
- Supprimer la paire de clés (EC2 → Key pairs) et le fichier `.pem`.
