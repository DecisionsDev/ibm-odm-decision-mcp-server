ARG PYTHON_VERSION=3.15

FROM ghcr.io/astral-sh/uv:bookworm-slim AS builder
ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy
ENV UV_PYTHON_INSTALL_DIR=/python
ENV UV_PYTHON_PREFERENCE=only-managed

RUN uv python install ${PYTHON_VERSION}

WORKDIR /app
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=src,target=src \
    --mount=type=bind,source=README.md,target=README.md \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --no-dev --no-editable


FROM  python:${PYTHON_VERSION}-slim-bookworm

LABEL name="IBM ODM Decision MCP Server"
LABEL summary="The IBM ODM Decision MCP Server exposes decisions (aka rulesets) as tools for AI assistants"

RUN useradd -m worker
USER worker

WORKDIR /app
COPY --from=builder --chown=worker:worker /app/ /app/
ENV PATH="/app/.venv/bin:$PATH"
RUN rm /app/.venv/bin/python && \
    ln -s /usr/local/bin/python /app/.venv/bin/python

ENTRYPOINT ["ibm-odm-decision-mcp-server"]
CMD ["--transport", "streamable-http", "--url", "http://odm:9060/res"]