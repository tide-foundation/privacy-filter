#!/usr/bin/env python3
"""Prepare reusable model assets on disk without installing PyTorch."""

import argparse
import json
import os
from pathlib import Path


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Validate existing assets without downloading the checkpoint.')
    args = parser.parse_args()
    target = Path(__file__).resolve().parents[1] / 'models' / 'privacy-filter'
    checkpoint = target / 'original'

    if not args.check:
        from huggingface_hub import snapshot_download

        # local_dir retains download metadata and partial files for subsequent runs.
        snapshot_download(
            repo_id='openai/privacy-filter',
            allow_patterns=['original/*'],
            local_dir=str(target),
        )

    config = json.loads((checkpoint / 'config.json').read_text())
    if not any(path.is_file() and path.stat().st_size for path in checkpoint.glob('*.safetensors')):
        raise RuntimeError(f'Missing model weights in {checkpoint}; run scripts/download-model.py first.')

    # tiktoken's vocabulary is fetched separately from the Hugging Face checkpoint.
    # Keeping it here makes it available both to future builds and the container.
    os.environ['TIKTOKEN_CACHE_DIR'] = str(target / 'tiktoken')
    import tiktoken

    tiktoken.get_encoding(config['encoding'])
    print(f'Model and tokenizer ready: {target}')


if __name__ == '__main__':
    main()
