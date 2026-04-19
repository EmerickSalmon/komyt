# Komyt Python dev image
#
# Packs everything opencode needs to implement + verify Python changes without
# Komyt having to install tools at container start:
#   - Python 3.12
#   - Linters / formatters: flake8, black, ruff, isort, pylint
#   - Type checker: mypy
#   - Security scan: bandit
#   - Test: pytest (+ coverage / asyncio / mock / xdist) and plain coverage.py
#   - opencode CLI (invoked as `opencode run '<prompt>'`)
#
# Build: docker build -t komyt-python:latest docker/komyt-python

FROM python:3.12-slim

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PATH="/root/.opencode/bin:/usr/local/bin:${PATH}"

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ca-certificates \
        curl \
        git \
        openssh-client \
        unzip \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

RUN pip install --no-cache-dir \
        flake8 \
        black \
        ruff \
        isort \
        pylint \
        mypy \
        bandit \
        pytest \
        pytest-cov \
        pytest-asyncio \
        pytest-mock \
        pytest-xdist \
        coverage

RUN curl -fsSL https://opencode.ai/install | bash \
    && ln -sf /root/.opencode/bin/opencode /usr/local/bin/opencode \
    && opencode --version || true

WORKDIR /workspace

CMD ["bash"]
