# syntax=docker/dockerfile:1
FROM python:3.12-slim

# WeasyPrint native deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    libcairo2 libpango-1.0-0 libpangoft2-1.0-0 libgdk-pixbuf-2.0-0 \
    libffi-dev shared-mime-info \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# torch CPU-only, ANTES do install principal.
#
# sentence-transformers (backend/core/trends/embeddings.py) arrasta torch, e o
# wheel default do PyPI vem com a stack CUDA inteira: 3,3 GB em nvidia/* mais
# 817 MB de triton. Nada disso executa — o Lightsail não tem GPU e o próprio
# embeddings.py encoda na CPU ("runs on CPU in a few ms per text"). Instalando
# do índice CPU do PyTorch primeiro, o install seguinte encontra torch já
# satisfeito e não baixa a variante CUDA.
#
# Isto é a causa do "no space left on device" recorrente no deploy: cada build
# gerava uma imagem de 10,4 GB, e o servidor guarda a antiga enquanto constrói
# a nova.
RUN --mount=type=cache,target=/root/.cache/pip \
    pip install torch --index-url https://download.pytorch.org/whl/cpu

COPY pyproject.toml ./

# Extras de instalação. O default traz [dev] (pytest, ruff, mypy,
# testcontainers) porque o docker-compose.yml local roda teste e lint pela
# mesma imagem. Produção passa EXTRAS="" no docker-compose.prod.yml — uvicorn
# não precisa de nenhum deles.
ARG EXTRAS="[dev]"
RUN --mount=type=cache,target=/root/.cache/pip pip install -e ".${EXTRAS}"

# Guarda contra regressão. Se um bump de dependência reinstalar torch pelo PyPI,
# a stack CUDA volta e o build falha AQUI — em vez de a gente descobrir pelo
# disco cheio do servidor, no meio de um deploy.
RUN test ! -d /usr/local/lib/python3.12/site-packages/nvidia || { \
      echo "ERRO: a stack CUDA voltou para a imagem (site-packages/nvidia)."; \
      echo "Ver o comentário do torch CPU-only acima."; \
      exit 1; \
    }

COPY backend ./backend
COPY migrations ./migrations
COPY alembic.ini ./

ENV PYTHONUNBUFFERED=1 PYTHONPATH=/app
EXPOSE 8000

CMD ["sh", "-c", "alembic upgrade head && uvicorn backend.app:app --host 0.0.0.0 --port 8000"]
