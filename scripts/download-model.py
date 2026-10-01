#!/usr/bin/env python3
"""Download missing model assets once; reuse the persistent cache thereafter."""

import argparse
import hashlib
import json
import os
from pathlib import Path
import struct

# OPF's pinned checkpoint uses o200k_base. Match tiktoken's cache key and hash.
TOKENIZER_URL = 'https://openaipublic.blob.core.windows.net/encodings/o200k_base.tiktoken'
TOKENIZER_SHA256 = '446a9538cb6c348e3516120d7c08b09f57c36495e2acfffe59a5bf8b0cfb1a2d'


def checkpoint_ready(checkpoint: Path) -> bool:
    """Check metadata and safetensors boundaries without loading weights into RAM."""
    try:
        config = json.loads((checkpoint / 'config.json').read_text())
        json.loads((checkpoint / 'dtypes.json').read_text())
        if config.get('encoding') != 'o200k_base':
            return False
        weights = list(checkpoint.glob('*.safetensors'))
        if not weights:
            return False
        for path in weights:
            with path.open('rb') as source:
                header_size = struct.unpack('<Q', source.read(8))[0]
                if not 0 < header_size <= 16 * 1024 * 1024:
                    return False
                header = json.loads(source.read(header_size))
            ends = [value['data_offsets'][1] for key, value in header.items() if key != '__metadata__']
            if not ends or 8 + header_size + max(ends) != path.stat().st_size:
                return False
        return True
    except (OSError, ValueError, KeyError, TypeError, AttributeError, struct.error):
        return False


def tokenizer_ready(cache: Path) -> bool:
    try:
        path = cache / hashlib.sha1(TOKENIZER_URL.encode()).hexdigest()
        return hashlib.sha256(path.read_bytes()).hexdigest() == TOKENIZER_SHA256
    except OSError:
        return False


def ensure_assets(target: Path, *, check_only: bool = False):
    checkpoint = target / 'original'
    cache = target / 'tiktoken'
    if not checkpoint_ready(checkpoint):
        if check_only:
            raise RuntimeError(f'Missing or incomplete checkpoint: {checkpoint}')
        print(f'Downloading model to {target} (retained for future starts)...', flush=True)
        from huggingface_hub import snapshot_download
        snapshot_download(repo_id='openai/privacy-filter', allow_patterns=['original/*'], local_dir=str(target))
        if not checkpoint_ready(checkpoint):
            raise RuntimeError(f'Checkpoint is incomplete after download: {checkpoint}')
    if check_only and not tokenizer_ready(cache):
        raise RuntimeError(f'Missing or invalid tokenizer cache: {cache}')
    os.environ['TIKTOKEN_CACHE_DIR'] = str(cache)
    # tiktoken reuses the verified local cache; only missing/corrupt assets download.
    import tiktoken
    tiktoken.get_encoding('o200k_base')
    if not tokenizer_ready(cache):
        raise RuntimeError(f'Tokenizer cache was not created: {cache}')
    print(f'Model and tokenizer ready: {target}', flush=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check', action='store_true', help='Validate existing assets without any download.')
    parser.add_argument('--target', type=Path, default=Path(os.environ.get(
        'PRIVACY_MODEL_DIR', Path(__file__).resolve().parents[1] / 'models' / 'privacy-filter')))
    args = parser.parse_args()
    ensure_assets(args.target.resolve(), check_only=args.check)


if __name__ == '__main__':
    main()
