ARG PYTHON_VERSION=3.12
FROM python:${PYTHON_VERSION}-slim-bookworm

ARG PYTHON_VERSION
ENV PYTHON_VERSION=${PYTHON_VERSION} \
    PYTHONUNBUFFERED=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

COPY dist/pydepot.pyz /opt/pydepot.pyz
COPY examples/ml-cpu/requirements.txt /opt/example/requirements.txt
COPY examples/ml-cpu/build-linux-bundle.sh /usr/local/bin/build-linux-bundle

RUN chmod +x /usr/local/bin/build-linux-bundle

ENTRYPOINT ["/usr/local/bin/build-linux-bundle"]

