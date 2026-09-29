from io import BytesIO
from types import SimpleNamespace
import time
from concurrent.futures import ThreadPoolExecutor
from fastapi.testclient import TestClient
from docx import Document
from backend import app as service


class Detector:
    _runtime = True
    def redact(self, text):
        start = text.index('Alice')
        return SimpleNamespace(text=text, detected_spans=[SimpleNamespace(start=start, end=start+5, label='private_person')], warning=None)


def test_upload_download_delete_and_origin_protection(tmp_path, monkeypatch):
    monkeypatch.setattr(service, 'ROOT', tmp_path)
    monkeypatch.setattr(service, 'model', Detector())
    monkeypatch.setattr(service, 'pool', ThreadPoolExecutor(max_workers=1))
    original_find = service.importlib.util.find_spec
    monkeypatch.setattr(service.importlib.util, 'find_spec', lambda name: True if name == 'opf' else original_find(name))
    doc = Document(); doc.add_paragraph('Hello Alice.'); data = BytesIO(); doc.save(data)
    with TestClient(service.app) as client:
        assert client.post('/documents?type=.docx', content=data.getvalue(), headers={'origin': 'https://evil.example'}).status_code == 403
        assert client.post('/documents?type=.doc', content=b'invalid').status_code == 400
        response = client.post('/documents?type=.docx&mode=placeholder', content=data.getvalue())
        assert response.status_code == 202
        identifier = response.json()['id']
        for _ in range(100):
            items = client.get('/documents').json()
            if items[0]['status'] in {'complete', 'failed'}: break
            time.sleep(.02)
        assert items[0]['status'] == 'complete', items
        assert items[0]['counts'] == {'private_person': 1}
        assert 'Alice' not in str(items)
        assert client.get(f'/documents/{identifier}/preview').json()['text'].startswith('Hello [Name].')
        for ext in ('pdf', 'docx', 'txt'):
            assert client.get(f'/documents/{identifier}/download/{ext}').status_code == 200
        assert client.get('/documents/not-a-uuid/preview').status_code == 404
        assert client.delete(f'/documents/{identifier}').status_code == 200
        assert not (tmp_path / identifier).exists()
        assert client.get('/documents').json() == []
        assert client.get(f'/documents/{identifier}/download/pdf').status_code == 404
