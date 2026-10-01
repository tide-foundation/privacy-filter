"""Model-cache reuse must never depend on the Hugging Face service being online."""
import hashlib
import importlib.util
import json
from pathlib import Path
import struct
import sys
from types import SimpleNamespace

import pytest

spec = importlib.util.spec_from_file_location('model_download', Path(__file__).resolve().parents[2] / 'scripts/download-model.py')
download = importlib.util.module_from_spec(spec)
spec.loader.exec_module(download)


def cache_fixture(root, monkeypatch):
    checkpoint = root / 'original'
    checkpoint.mkdir(parents=True)
    (checkpoint / 'config.json').write_text(json.dumps({'encoding': 'o200k_base'}))
    (checkpoint / 'dtypes.json').write_text('{}')
    header = json.dumps({'test': {'dtype': 'U8', 'shape': [4], 'data_offsets': [0, 4]}}).encode()
    (checkpoint / 'model.safetensors').write_bytes(struct.pack('<Q', len(header)) + header + b'1234')
    cache = root / 'tiktoken'
    cache.mkdir()
    data = b'test tokenizer'
    (cache / hashlib.sha1(download.TOKENIZER_URL.encode()).hexdigest()).write_bytes(data)
    monkeypatch.setattr(download, 'TOKENIZER_SHA256', hashlib.sha256(data).hexdigest())
    return checkpoint


def test_valid_cache_skips_hub_download(tmp_path, monkeypatch):
    cache_fixture(tmp_path, monkeypatch)
    def unexpected_download(**kwargs):
        pytest.fail('A cached startup must not contact Hugging Face')
    monkeypatch.setitem(sys.modules, 'huggingface_hub', SimpleNamespace(snapshot_download=unexpected_download))
    encodings = []
    monkeypatch.setitem(sys.modules, 'tiktoken', SimpleNamespace(get_encoding=encodings.append))
    download.ensure_assets(tmp_path)
    download.ensure_assets(tmp_path, check_only=True)
    assert encodings == ['o200k_base', 'o200k_base']


def test_truncated_weights_fail_offline_validation(tmp_path, monkeypatch):
    checkpoint = cache_fixture(tmp_path, monkeypatch)
    path = checkpoint / 'model.safetensors'
    path.write_bytes(path.read_bytes()[:-1])
    assert not download.checkpoint_ready(checkpoint)
    with pytest.raises(RuntimeError, match='incomplete checkpoint'):
        download.ensure_assets(tmp_path, check_only=True)


def test_invalid_tokenizer_fails_offline_before_loading(tmp_path, monkeypatch):
    cache_fixture(tmp_path, monkeypatch)
    for path in (tmp_path / 'tiktoken').iterdir():
        path.write_bytes(b'corrupt')
    with pytest.raises(RuntimeError, match='invalid tokenizer'):
        download.ensure_assets(tmp_path, check_only=True)


def test_missing_assets_download_once_then_reuse(tmp_path, monkeypatch):
    calls = []
    def fetch(**kwargs):
        calls.append(kwargs)
        cache_fixture(tmp_path, monkeypatch)
    monkeypatch.setitem(sys.modules, 'huggingface_hub', SimpleNamespace(snapshot_download=fetch))
    monkeypatch.setitem(sys.modules, 'tiktoken', SimpleNamespace(get_encoding=lambda name: None))
    download.ensure_assets(tmp_path)
    download.ensure_assets(tmp_path)
    assert len(calls) == 1
