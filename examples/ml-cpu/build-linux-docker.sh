#!/bin/sh
set -eu

repository=$(CDPATH= cd -- "$(dirname -- "$0")/../.." && pwd)
mkdir -p "$repository/dist"

for version in 3.12 3.14; do
    tag=$(printf '%s' "$version" | tr -d '.')
    image="pydepot-ml-cpu:py${tag}"
    docker build \
        --build-arg "PYTHON_VERSION=$version" \
        --file "$repository/examples/ml-cpu/Dockerfile" \
        --tag "$image" \
        "$repository"
    docker run --rm \
        --user "$(id -u):$(id -g)" \
        --mount "type=bind,source=$repository/dist,target=/out" \
        "$image"
done

sha256sum "$repository"/dist/ml-cpu-linux-*.pybundle

