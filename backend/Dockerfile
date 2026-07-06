FROM python:3.13-slim AS builder

    RUN apt-get update && \
    apt-get install -y --no-install-recommends build-essential libpq-dev && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*
    RUN pip install --no-cache-dir --upgrade pyopenssl

    COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

    WORKDIR /root_project

    # Install dependencies first (cached unless lock/pyproject change)
    COPY uv.lock pyproject.toml ./
    ENV VIRTUAL_ENV=/opt/venv
    ENV UV_PROJECT_ENVIRONMENT=/opt/venv
    RUN uv venv $VIRTUAL_ENV
    ENV PATH="$VIRTUAL_ENV/bin:$PATH"
    RUN uv sync --locked --no-dev --no-install-project

    # Copy source and install the project itself (fast, deps already cached)
    COPY . .
    RUN uv sync --locked --no-dev --no-editable

FROM python:3.13-slim

    RUN apt-get update && \
    apt-get install -y --no-install-recommends libpq5 && \
    apt-get clean && \
    rm -rf /var/lib/apt/lists/*

    WORKDIR /root_project

    COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

    COPY --from=builder /opt/venv /opt/venv
    COPY --from=builder /root_project /root_project
    ENV VIRTUAL_ENV=/opt/venv
    ENV PATH="/opt/venv/bin:$PATH"
    ENV UV_PROJECT_ENVIRONMENT=/opt/venv
    ENV UV_NO_SYNC=true
    # Python buffers stdout in 8KB chunks when not a TTY, which hides logs from
    # Cloud Logging until the buffer fills or the process exits. In prod we
    # want each log line to land immediately.
    ENV PYTHONUNBUFFERED=1

    # Real build version, surfaced on GET /health and FastAPI info.version.
    # Passed by cloudbuild.yaml as --build-arg APP_VERSION=${SHORT_SHA}.
    ARG APP_VERSION=dev
    ENV APP_VERSION=$APP_VERSION

    # Commit SHA for Sentry release tracking. Optional: defaults to empty when
    # not passed (e.g. local builds), in which case the app falls back to the
    # plain package version.
    ARG GIT_SHA=""
    ENV GIT_SHA=$GIT_SHA

    EXPOSE 8000
