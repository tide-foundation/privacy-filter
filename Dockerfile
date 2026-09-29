# syntax=docker/dockerfile:1
# Prepare model assets first; see the Docker section in README.md.
# This independent target builds without model files or host Python.
FROM python:3.12-slim-bookworm AS model-download
WORKDIR /app
COPY scripts/requirements-download.txt ./scripts/
RUN pip install --no-cache-dir -r scripts/requirements-download.txt
COPY scripts/download-model.py ./scripts/
ENV HF_HOME=/tmp/huggingface
ENTRYPOINT ["python", "scripts/download-model.py"]

FROM node:24-bookworm AS build

RUN apt-get update && \
    apt-get install -y python3 python3-venv git && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies before copying source so app edits reuse these layers.
COPY backend/requirements.txt backend/requirements-model.txt ./backend/
RUN python3 -m venv .venv && \
    .venv/bin/pip install --upgrade pip && \
    .venv/bin/pip install -r backend/requirements.txt && \
    .venv/bin/pip install torch --index-url https://download.pytorch.org/whl/cpu && \
    .venv/bin/pip install -r backend/requirements-model.txt

COPY package.json package-lock.json ./
RUN npm ci
COPY app ./app
COPY public ./public
COPY tsconfig.json next-env.d.ts ./
RUN npm run build
COPY backend ./backend

# Download metadata stays on the host. Only runtime assets enter the image.
FROM build AS model
COPY scripts/download-model.py ./scripts/download-model.py
COPY models/privacy-filter/original/ ./models/privacy-filter/original/
COPY models/privacy-filter/tiktoken/ ./models/privacy-filter/tiktoken/
# Fail the build if the tokenizer still needs a network download.
RUN --network=none .venv/bin/python scripts/download-model.py --check

FROM node:24-bookworm

RUN apt-get update && \
    apt-get install -y python3 python3-venv && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY --from=build /app /app
COPY --from=model /app/models /app/models

ENV NODE_ENV=production \
    OPF_DEVICE=cpu \
    OPF_CHECKPOINT=/app/models/privacy-filter/original \
    TIKTOKEN_CACHE_DIR=/app/models/privacy-filter/tiktoken \
    HF_HUB_OFFLINE=1

EXPOSE 3000
EXPOSE 8000

CMD ["sh", "-c", ".venv/bin/uvicorn backend.app:app --host 0.0.0.0 --port 8000 & npm start"]
