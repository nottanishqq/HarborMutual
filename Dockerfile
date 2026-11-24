# One container for the hosted demo (Hugging Face Spaces, free CPU tier):
# SurrealDB v4 in memory, loaded from data/harbor.surql at boot, plus the FastAPI app on :7860.
FROM surrealdb/surrealdb:v4.0.1 AS surreal

FROM python:3.12-slim
COPY --from=surreal /surreal /usr/local/bin/surreal
COPY --from=ghcr.io/astral-sh/uv:0.11 /uv /usr/local/bin/uv

RUN useradd -m -u 1000 user
WORKDIR /app
ENV UV_PROJECT_ENVIRONMENT=/opt/venv FASTEMBED_CACHE_PATH=/opt/models PATH=/opt/venv/bin:$PATH

COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-default-groups
# Bake the embedding model into the image so boot needs no download.
RUN python -c "from fastembed import TextEmbedding; TextEmbedding('BAAI/bge-small-en-v1.5')" && chmod -R a+rX /opt/models

COPY --chown=user . .
USER user
EXPOSE 7860
CMD ["sh", "scripts/start.sh"]
