"""Optional end-to-end check against running services and the real installed model.
Uses invented input, verifies downloads, and removes its output documents.
"""
from io import BytesIO
import os
import time
import httpx
import pymupdf
from docx import Document

BASE = os.environ.get('BASE_URL', 'http://127.0.0.1:3000') + '/api/service'
SENSITIVITY = int(os.environ.get('SENSITIVITY', '50'))
TEXT = 'Please contact Alice Smith at alice.smith@example.com. Alice Smith is our account contact.'


def verify(client, identifier):
    for _ in range(600):
        row = next(r for r in client.get(BASE + '/documents').json() if r['id'] == identifier)
        if row['status'] == 'failed':
            raise AssertionError(row['error'])
        if row['status'] == 'complete':
            break
        time.sleep(1)
    else:
        raise TimeoutError('Model job did not finish within ten minutes.')
    assert row['sensitivity'] == SENSITIVITY, row
    assert row['counts'].get('private_person') == 2, row
    assert row['counts'].get('private_email') == 1, row
    for ext in ('txt', 'docx', 'pdf'):
        response = client.get(f'{BASE}/documents/{identifier}/download/{ext}')
        response.raise_for_status()
        if ext == 'txt':
            text = response.text
        elif ext == 'docx':
            text = '\n'.join(p.text for p in Document(BytesIO(response.content)).paragraphs)
        else:
            with pymupdf.open(stream=response.content, filetype='pdf') as pdf:
                text = '\n'.join(p.get_text() for p in pdf)
        assert 'Alice Smith' not in text and 'alice.smith@example.com' not in text, (ext, text)
    return row['counts']


with httpx.Client(timeout=30) as client:
    for suffix, mode in (('.docx', 'placeholder'), ('.pdf', 'synthetic')):
        if suffix == '.docx':
            doc = Document(); doc.add_paragraph(TEXT)
            buffer = BytesIO(); doc.save(buffer); payload = buffer.getvalue()
        else:
            pdf = pymupdf.open(); page = pdf.new_page()
            page.insert_textbox(pymupdf.Rect(50, 50, 540, 200), TEXT)
            payload = pdf.tobytes(); pdf.close()
        response = client.post(BASE + f'/documents?type={suffix}&mode={mode}&sensitivity={SENSITIVITY}', content=payload)
        response.raise_for_status()
        identifier = response.json()['id']
        try:
            counts = verify(client, identifier)
            print(f'{suffix} / {mode}: real inference and all three exports passed; {counts}', flush=True)
        finally:
            deleted = client.delete(f'{BASE}/documents/{identifier}')
            deleted.raise_for_status()
            assert client.get(f'{BASE}/documents/{identifier}/download/txt').status_code == 404
    print('Real-model smoke passed. Test documents deleted.')
