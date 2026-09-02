# PyDepot

PyDepot crée un fichier portable contenant des dépendances Python, **tous leurs
wheels transitifs** et, facultativement, des exécutables natifs, puis les installe
sur une machine hors ligne. Il propose la
même logique en ligne de commande et dans une TUI plein écran sans dépendance
externe.

## Installation

Python 3.9 ou supérieur est requis pour exécuter PyDepot.

```console
python -m pip install .
pydepot --help
```

Pour l'utiliser sans installation, depuis le dépôt :

```console
python run_pydepot.py
```

Une archive exécutable mono-fichier peut aussi être produite et copiée telle
quelle (elle ne dépend que de Python et pip sur les machines concernées) :

```console
python tools/build_zipapp.py
python dist/pydepot.pyz
```

Sans sous-commande, PyDepot ouvre automatiquement la TUI dans un terminal
interactif. La sous-commande `tui` permet de la demander explicitement.

## Créer un bundle (machine connectée)

```console
pydepot export requests==2.32.3 rich -o outils.pybundle --python-version 3.11
```

À partir d'un fichier :

```console
pydepot export -r requirements.txt -o outils.pybundle --python-version 3.12
```

Pour préciser l'architecture cible, fournir un tag accepté par `pip download`.
La création doit être exécutée sur la même famille de système que la cible
(Windows, Linux ou macOS) :

```console
pydepot export numpy -o calcul.pybundle --python-version 3.11 --platform win_amd64
pydepot export numpy -o calcul.pybundle --python-version 3.11 \
  --platform manylinux_2_17_x86_64
```

L'interpréteur utilisé pour l'export doit aussi avoir la même version
majeure/mineure que la cible. Par exemple, pour produire un bundle Python 3.12
avec un Python portable :

```console
pydepot export -r requirements.txt -o outils.pybundle --python-version 3.12 \
  --python D:\apps\python-3.12-portable\python\tools\python.exe
```

Ces contrôles sont nécessaires car `pip --python-version` filtre la
compatibilité des wheels mais n'évalue pas tous les marqueurs conditionnels
avec la version ou le système cible.

PyDepot choisit volontairement uniquement des wheels (`--only-binary=:all:`).
C'est ce qui rend l'import reproductible hors ligne sans compilateur ni
téléchargement implicite de dépendances de build. Si un paquet ne publie pas de
wheel compatible avec la cible, l'export échoue avec le diagnostic de pip.

### Ajouter un exécutable natif

Un ou plusieurs outils déjà téléchargés peuvent être ajoutés au bundle. Le nom
après `=` est celui qui sera installé dans le dossier `bin/` du venv cible :

```console
pydepot export specify-cli==1.0.3 -o outils.pybundle \
  --include-executable ./opencode-linux=opencode
```

L'exécutable est décrit dans le manifeste et contrôlé par SHA-256. À l'import,
il est copié dans `bin/` (`Scripts/` sous Windows) et reçoit le droit
d'exécution. Sans `--venv`, préciser `--tools-dir`; avec `--target`, la
destination par défaut est `<target>/bin`. Un fichier existant différent n'est
remplacé que si `--upgrade` est fourni.

### Exporter vers une autre famille de système

Par défaut, PyDepot refuse toujours une résolution Windows→Linux, car `pip`
évalue certains marqueurs de dépendances avec le système qui exécute l'export.
L'option explicite `--allow-cross-platform` l'autorise lorsque les dépendances
ont été contrôlées et que `--platform` et `--abi` décrivent complètement la
cible. Pour un ensemble de dépendances inconnu, une construction dans Docker ou
WSL reste la méthode recommandée.

L'exemple [`examples/opencode-speckit/`](examples/opencode-speckit/README.md)
illustre le cas vérifié Spec Kit + exécutable OpenCode, construit sous Windows
pour Linux x86-64 et Python 3.12.

## Importer hors ligne

Copier le seul fichier `.pybundle` sur la machine isolée, puis :

```console
pydepot verify outils.pybundle
pydepot import outils.pybundle --venv .venv --python /chemin/vers/python3.11
```

Installation dans l'interpréteur courant :

```console
pydepot import outils.pybundle
```

Ou dans un dossier autonome :

```console
pydepot import outils.pybundle --target vendor
```

Durant l'import, `pip` reçoit `--no-index` et un environnement qui interdit les
index. Il reçoit aussi `--no-deps` : toutes les dépendances étant déjà résolues
et verrouillées dans le bundle, aucune nouvelle résolution susceptible de
chercher un paquet absent n'est lancée. Le manifeste et chaque artefact sont
vérifiés par SHA-256 avant l'installation. La version majeure/mineure de Python
doit correspondre à celle du bundle. Après installation dans un venv, `pip
check` confirme également que toutes les dépendances requises sont présentes.

## Installer un Python portable sous Windows

La TUI propose une entrée **Python portable**. Elle consulte les versions
stables publiées par le paquet Python de NuGet, télécharge `nuget.exe` dans le
dossier choisi, installe la version sélectionnée sans suffixe de version, puis
initialise et met à niveau `pip`. L'interpréteur obtenu se trouve dans
`<destination>\python\tools\python.exe` et peut ensuite être choisi lors d'un
export ou d'un import.

## Commandes utiles

```console
pydepot inspect outils.pybundle
pydepot inspect outils.pybundle --verify --json
pydepot verify outils.pybundle
pydepot tui
```

Un bundle est un ZIP lisible contenant :

- `manifest.json` : cible, demande initiale, tailles et empreintes ;
- `requirements.lock` : toutes les distributions résolues, versions exactes ;
- `packages/` : wheelhouse complet utilisé par l'import hors ligne.
- `tools/` : exécutables natifs facultatifs, installés avec leur empreinte.

## Limites connues

- Un bundle cible une version Python majeure/mineure et une famille de
  plateforme données. Pour plusieurs cibles, créer un bundle par cible.
- Les exécutables inclus doivent eux aussi correspondre au système, à
  l'architecture et, sous Linux, à la libc de la cible.
- L'interpréteur et la famille de système servant à l'export doivent
  correspondre à la cible afin que les marqueurs de dépendances soient résolus
  dans le bon environnement.
- `pip` doit être disponible dans l'interpréteur d'export et d'import. La
  création de venv utilise `ensurepip` fourni par Python.
- Les options de type `--find-links`, inclusions récursives et index présentes
  dans un fichier requirements restent interprétées par pip à l'export. Le
  manifeste n'affiche comme demande initiale que les lignes de paquets simples.

## Exemple complet pandas + XGBoost + PyTorch

Un exemple reproductible avec quatre bundles CPU pour Windows/Linux x86-64 et
Python 3.12/3.14 est disponible dans
[`examples/ml-cpu/`](examples/ml-cpu/README.md). Il inclut les archives déjà
produites dans `dist/`, leurs empreintes SHA-256, un script PowerShell pour
Windows et un workflow Docker pour Linux.
