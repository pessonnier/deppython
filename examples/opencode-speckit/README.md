# OpenCode + Spec Kit pour Linux, construit depuis Windows

Cet exemple fabrique sous Windows un unique `.pybundle` destiné à Linux x86-64
avec Python 3.12. Il contient :

- `specify-cli==1.0.3` et tous ses wheels transitifs ;
- le binaire Linux OpenCode 1.18.26, installé sous le nom `opencode` ;
- les empreintes SHA-256 de chaque wheel et de l'exécutable.

L'archive ne contient pas Python, Git, les clés d'accès aux modèles ni un
modèle LLM. La cible doit fournir Python 3.12 avec `pip`; Git est recommandé
pour le workflow Spec Kit.

## Archive générée

La reconstruction du 2 septembre 2026 a produit :

| Archive | Taille | Wheels | Outils | SHA-256 |
|---|---:|---:|---:|---|
| `opencode-speckit-linux-x64-py312.pybundle` | 61,29 Mio | 16 | 1 | `792fa04f32a8a64c1aa4565b7f18de0ac212a5a32ad7f572572950a128211399` |

Le binaire décompressé est un ELF 64 bits x86-64 de 176,07 Mio. Son empreinte
interne est `63b57d58c9304bf4ddc75490bb9b36f1eb04cbfd059e4c768abe1278a624d7f2`.
L'archive GitHub OpenCode téléchargée a été contrôlée avec l'empreinte publiée
`7c20c1ffa91bcca0ac903752260bcc36307dff656833baead2f5ef3b224b16c6`.

## Construction sous Windows

Prérequis : PowerShell 7, Python 3.12 avec pip, `tar.exe` (inclus dans les
versions modernes de Windows) et un accès à GitHub/PyPI.

Depuis la racine du dépôt :

```powershell
python .\tools\build_zipapp.py
.\examples\opencode-speckit\build-windows.ps1 -Python python
```

Le script interroge la release GitHub épinglée, télécharge
`opencode-linux-x64.tar.gz`, vérifie l'empreinte publiée par GitHub, extrait le
binaire, puis appelle :

```powershell
python .\dist\pydepot.pyz export `
  -r .\examples\opencode-speckit\requirements.txt `
  -o .\dist\opencode-speckit-linux-x64-py312.pybundle `
  --python-version 3.12 `
  --platform manylinux_2_17_x86_64 `
  --abi cp312 `
  --allow-cross-platform `
  --include-executable C:\chemin\vers\opencode=opencode
```

`--allow-cross-platform` est volontairement explicite : `pip --platform`
sélectionne bien les wheels Linux, mais certains marqueurs de dépendances sont
encore évalués avec le système hôte. Les métadonnées des 16 wheels ont été
contrôlées dans ce cas : le seul marqueur système est la dépendance Windows
`colorama` de Typer. Elle ajoute ici un wheel pur Python inutile mais inoffensif
sous Linux; aucune dépendance réservée à Linux n'est omise. Pour un autre
requirements, construire dans un conteneur Linux reste préférable.

Pour un processeur x86-64 ancien sans AVX2, sélectionner la variante publiée
par OpenCode :

```powershell
.\examples\opencode-speckit\build-windows.ps1 `
  -Python python `
  -OpenCodeVariant x64-baseline
```

## Import hors ligne sous Linux

Copier `dist/pydepot.pyz` et le `.pybundle` sur la cible, puis :

```bash
python3.12 pydepot.pyz verify opencode-speckit-linux-x64-py312.pybundle
python3.12 pydepot.pyz import \
  opencode-speckit-linux-x64-py312.pybundle \
  --venv ./opencode-speckit

. ./opencode-speckit/bin/activate
specify version
opencode --version
```

L'import n'accède à aucun index. Il installe les wheels avec `pip --no-index`,
copie OpenCode dans `opencode-speckit/bin/` et lui applique le droit
d'exécution.

Pour préparer un projet sans accès réseau et activer l'intégration OpenCode :

```bash
specify init mon-projet \
  --integration opencode \
  --script py \
  --offline
cd mon-projet
opencode
```

Spec Kit sait initialiser ses ressources intégrées hors ligne. OpenCode a
ensuite besoin d'un fournisseur LLM accessible ou d'un modèle local configuré.
