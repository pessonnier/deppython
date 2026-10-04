# Déploiement hors ligne OpenCode + Spec Kit + Graphify

Cet exemple construit sous Windows un fichier `.pybundle` pour Linux x86-64,
glibc 2.28 ou plus récent, avec Python 3.14. Le bundle contient :

- OpenCode 1.18.34, sous forme d'exécutable Linux ;
- Spec Kit 1.1.0, construit depuis le tag GitHub officiel ;
- Graphify 0.9.76 (`graphifyy` sur PyPI) et tous ses wheels transitifs ;
- les empreintes SHA-256 de chaque wheel et de l'exécutable.

Versions vérifiées le 4 octobre 2026 auprès des releases officielles
[OpenCode](https://github.com/anomalyco/opencode/releases/tag/v1.18.34),
[Spec Kit](https://github.com/github/spec-kit/releases/tag/v1.1.0) et
[Graphify](https://github.com/Graphify-Labs/graphify/releases/tag/v0.9.76).

L'archive ne contient pas Python, Git, les identifiants d'un fournisseur de
modèles ni un LLM. La cible doit fournir Python 3.14 avec `pip`. Git est
recommandé pour les workflows Spec Kit.

## Archive générée

La reconstruction du 4 octobre 2026 a produit :

| Archive | Taille | Wheels | Outils | SHA-256 |
|---|---:|---:|---:|---|
| `opencode-speckit-graphify-linux-x64-py314.pybundle` | 90,71 Mio | 45 | 1 | `c1016767aa867ce6bb93cb0281661faf1787170eb925c227892a56b971ae59ff` |

Contrôles de provenance effectués pendant cette construction :

- archive OpenCode publiée : `0f22479647226d1d2dd99595d20082ee7bda3870b62dc6a90b41efc1a71d7e9a` ;
- binaire OpenCode inclus (185 632 896 octets) : `9ca0b9953d49997601655e54f846a3efa464f237e47c6f1b04716d0f2e64c4c2` ;
- archive source Spec Kit : `e39dc9db2155ab2c987a9ee892428222a44fa263bee5025d4bcceb223f3c078c` ;
- wheel Spec Kit construit : `f6bd760911940f0bcd263bc25ee078e3f4157f7d387cf58b881847364ab90b66`.

## Construction sous Windows

Prérequis : PowerShell 7, Python 3.14 avec pip, `tar.exe` (inclus dans les
versions modernes de Windows) et un accès à GitHub/PyPI.

Depuis la racine du dépôt :

```powershell
python .\tools\build_zipapp.py
.\examples\opencode-speckit-graphify\build-windows.ps1 -Python python
```

Le script effectue les contrôles suivants :

1. il consulte la release OpenCode épinglée, télécharge le binaire Linux et
   compare son SHA-256 avec l'empreinte publiée par GitHub ;
2. il valide la release Spec Kit, télécharge son tag et construit localement
   un wheel pur Python, puis compare les empreintes de la source et du wheel
   avec les valeurs épinglées ;
3. il résout Graphify et toutes les dépendances pour Linux/Python 3.14 ;
4. il construit puis vérifie intégralement le `.pybundle`.

Graphify dépend de wheels publiés sous plusieurs tags manylinux. Le script
fournit donc à pip les tags glibc 2.28, 2.17 et 2.5, ainsi que les alias
manylinux2014/manylinux1. La dépendance la plus exigeante (`numpy`) fixe la
compatibilité réelle de la cible à glibc 2.28+.

Pour un processeur x86-64 ancien sans AVX2 :

```powershell
.\examples\opencode-speckit-graphify\build-windows.ps1 `
  -Python python `
  -OpenCodeVariant x64-baseline
```

## Installation sur la machine Linux hors ligne

Copier `dist/pydepot.pyz` et le `.pybundle` sur la cible, puis :

```bash
python3.14 pydepot.pyz verify \
  opencode-speckit-graphify-linux-x64-py314.pybundle
python3.14 pydepot.pyz import \
  opencode-speckit-graphify-linux-x64-py314.pybundle \
  --venv ./opencode-speckit-graphify

. ./opencode-speckit-graphify/bin/activate
specify version
graphify --version
opencode --version
```

L'import utilise `pip --no-index --no-deps`, contrôle toutes les empreintes,
installe les wheels verrouillés puis copie OpenCode dans le dossier `bin/` du
venv avec le droit d'exécution.

## Initialisation d'un projet

Spec Kit 1.1.0 embarque ses ressources de base : `specify init` fonctionne
hors ligne sans option supplémentaire. Pour créer un projet lié à OpenCode :

```bash
specify init mon-projet --integration opencode --script py
cd mon-projet
graphify install --platform opencode --project
opencode
```

Dans OpenCode, lancer `/graphify .` pour construire le graphe du projet, puis
utiliser les commandes Spec Kit installées (`/speckit-constitution`,
`/speckit-specify`, `/speckit-plan`, `/speckit-tasks`,
`/speckit-implement`, `/speckit-converge`).

La construction Graphify du code est locale et ne requiert pas de clé API. Le
traitement sémantique de documents ou médias, ainsi que l'usage d'OpenCode,
requièrent un fournisseur LLM accessible ou un modèle local configuré.

## Limites et mise à jour

- Le bundle est spécifique à Linux x86-64, glibc 2.28+ et Python 3.14.
- Les extras facultatifs Graphify (`pdf`, `video`, `mcp`, `neo4j`, etc.) ne
  sont pas inclus ; ajouter l'extra voulu dans `requirements.txt` avant de
  reconstruire.
- La résolution est lancée depuis Windows avec
  `--allow-cross-platform`. Les dépendances de base des versions épinglées
  n'ont pas de marqueur système susceptible d'omettre un paquet Linux.
- Pour actualiser OpenCode ou Spec Kit, modifier leurs versions par défaut dans
  `build-windows.ps1`; pour Spec Kit, remplacer également les deux empreintes
  épinglées. Pour Graphify, modifier `requirements.txt`. Reconstruire ensuite
  le bundle et remplacer les empreintes documentées après vérification.
