#!/bin/sh
set -eu
# Reuse valid cached files; first startup alone needs model-download access.
python /app/scripts/download-model.py
# All processing after initialization uses the local checkpoint and tokenizer.
export HF_HUB_OFFLINE=1
exec "$@"
