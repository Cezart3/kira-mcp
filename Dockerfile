# MCP server over stdio: docker run -i --rm kira-mcp
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim
WORKDIR /app
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
RUN uv sync --frozen --no-dev
ENTRYPOINT ["/app/.venv/bin/kira-mcp"]
