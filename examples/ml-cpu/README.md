# Exemple ML hors ligne : pandas, XGBoost et PyTorch CPU

Cet exemple produit quatre bundles x86-64 indépendants :

| Système cible | Python | Archive | Taille | SHA-256 |
|---|---:|---|---:|---|
| Windows x86-64 | 3.12 | `ml-cpu-windows-x86_64-py312.pybundle` | 245,12 Mio | `023809163d7b64e4c003614d837d2c4e481836e279ccdbfd66b4bb27dc486d9d` |
| Windows x86-64 | 3.14 | `ml-cpu-windows-x86_64-py314.pybundle` | 248,06 Mio | `f01b596ea855152fe8a31343089b0e7e59f41e231a766ab55a1ac72ef087c7da` |
| Linux x86-64, glibc 2.28+ | 3.12 | `ml-cpu-linux-x86_64-py312.pybundle` | 342,48 Mio | `7e7ed27cfc4ade57ba8febc071a33e92e1254b730e5453ef424747cf6ec689d7` |
| Linux x86-64, glibc 2.28+ | 3.14 | `ml-cpu-linux-x86_64-py314.pybundle` | 342,44 Mio | `0553c4ebb10bc15fea8167dc89a6b743175264c4f705f6ec80eaa1cd55165e22` |

Ces empreintes, également fournies dans `dist/SHA256SUMS`, correspondent aux
fichiers présents dans `dist/`, produits le 20 août 2026. Une reconstruction
ultérieure peut avoir une autre empreinte : la date de création appartient au
manifeste et une dépendance transitive peut évoluer. Le verrou interne conserve
toutes les versions effectivement résolues dans chaque archive.

## Choix de versions

Le fichier [`requirements.txt`](requirements.txt) fixe :

```text
pandas==3.0.5
xgboost==3.3.0
torch==2.13.0+cpu
```

Le suffixe `+cpu` est intentionnel : ces archives n'embarquent ni CUDA ni les
pilotes NVIDIA. L'index CPU officiel de PyTorch est ajouté à PyPI pendant
l'export. Chaque bundle contient 17 wheels, notamment NumPy, SciPy, Jinja2,
NetworkX et les autres dépendances transitives.

## Produire les archives Windows

Depuis PowerShell à la racine du dépôt :

```powershell
.\examples\ml-cpu\build-windows.ps1 -Python python
```

La commande équivalente pour Python 3.12 est :

```powershell
python .\dist\pydepot.pyz export `
  -r .\examples\ml-cpu\requirements.txt `
  -o .\dist\ml-cpu-windows-x86_64-py312.pybundle `
  --python-version 3.12 `
  --platform win_amd64 `
  --abi cp312 `
  --extra-index-url https://download.pytorch.org/whl/cpu
```

Pour Python 3.14, remplacer `3.12`, `cp312` et `py312` par `3.14`, `cp314` et
`py314`.

## Produire les archives Linux dans Docker

Prérequis : Docker Engine ou Docker Desktop avec les conteneurs Linux. Depuis
PowerShell :

```powershell
.\examples\ml-cpu\build-linux-docker.ps1
```

Depuis Bash :

```bash
sh ./examples/ml-cpu/build-linux-docker.sh
```

Les scripts construisent successivement les images `python:3.12-slim-bookworm`
et `python:3.14-slim-bookworm`, montent `dist/` dans `/out`, lancent PyDepot à
l'intérieur du conteneur et vérifient chaque bundle avant de rendre la main.

> Note de production : Docker n'était pas installé sur la machine ayant généré
> les quatre fichiers livrés. Les deux bundles Linux présents dans `dist/` ont
> donc été résolus avec les mêmes paramètres explicites `manylinux_2_28_x86_64`
> et `cp312`/`cp314`, puis vérifiés par PyDepot. Les scripts Docker sont prêts à
> être rejoués sur une machine Docker afin d'obtenir une provenance entièrement
> conteneurisée.

Exécution manuelle pour Python 3.12 :

```bash
docker build \
  --build-arg PYTHON_VERSION=3.12 \
  -f examples/ml-cpu/Dockerfile \
  -t pydepot-ml-cpu:py312 .

docker run --rm \
  --mount "type=bind,source=$PWD/dist,target=/out" \
  pydepot-ml-cpu:py312
```

## Transférer et importer hors ligne

Copier `pydepot.pyz` et uniquement le bundle correspondant à la machine cible.
Sur Windows avec Python 3.12 :

```powershell
py -3.12 .\pydepot.pyz verify .\ml-cpu-windows-x86_64-py312.pybundle
py -3.12 .\pydepot.pyz import .\ml-cpu-windows-x86_64-py312.pybundle --venv .venv
.\.venv\Scripts\python.exe -c "import pandas, xgboost, torch; print(pandas.__version__, xgboost.__version__, torch.__version__)"
```

Sur Linux avec Python 3.14 :

```bash
python3.14 pydepot.pyz verify ml-cpu-linux-x86_64-py314.pybundle
python3.14 pydepot.pyz import ml-cpu-linux-x86_64-py314.pybundle --venv .venv
.venv/bin/python -c 'import pandas, xgboost, torch; print(pandas.__version__, xgboost.__version__, torch.__version__)'
```

L'import utilise uniquement les wheels du bundle et force `pip --no-index`.
Une archive Python 3.12 ne doit pas être utilisée avec Python 3.14, et une
archive Windows ne peut pas être utilisée sous Linux.
