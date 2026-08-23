#!/bin/sh
set -eu

output_directory=${OUTPUT_DIRECTORY:-/out}
python_tag=$(printf '%s' "$PYTHON_VERSION" | tr -d '.')
bundle="$output_directory/ml-cpu-linux-x86_64-py${python_tag}.pybundle"

mkdir -p "$output_directory"
python /opt/pydepot.pyz export \
    --requirements /opt/example/requirements.txt \
    --output "$bundle" \
    --python-version "$PYTHON_VERSION" \
    --platform manylinux_2_28_x86_64 \
    --abi "cp${python_tag}" \
    --extra-index-url https://download.pytorch.org/whl/cpu
python /opt/pydepot.pyz verify "$bundle"

