"""Shared replacement plans and rebuilt text exports."""
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
import html
import secrets
import pymupdf
from docx import Document

LABELS = {
    'private_person': 'Name', 'private_address': 'Address',
    'private_email': 'Email', 'private_phone': 'Phone Number',
    'private_date': 'Date', 'private_url': 'URL',
    'account_number': 'Account Number', 'secret': 'Secret',
}


def extract(data: bytes, suffix: str) -> str:
    from backend.layout import load_document
    source = load_document(data, suffix)
    try:
        return source.text
    finally:
        source.close()


class DocumentError(ValueError):
    """Safe, user-facing document validation failure."""


@dataclass(frozen=True)
class Edit:
    start: int
    end: int
    text: str


def replacement_plan(result, mode: str):
    # OPF offsets refer to result.text, which may differ from the original tokenizer input.
    text = result.text
    cursor, pieces, counts, mapping = 0, [], Counter(), {}
    edits = []
    if mode not in {'placeholder', 'synthetic'}:
        raise DocumentError('Unsupported replacement mode.')
    nonce = secrets.token_hex(3)
    for span in sorted(result.detected_spans, key=lambda s: (s.start, s.end)):
        if span.label not in LABELS or not 0 <= cursor <= span.start < span.end <= len(text):
            raise DocumentError('The model returned unsupported or overlapping spans; no output was saved.')
        original = text[span.start:span.end]
        key = (span.label, original.casefold())
        if key not in mapping:
            n = len(mapping) + 1
            dummy = {
                'private_person': f'Alex Example {n}',
                'private_address': f'{n} Example Street, Sampletown',
                'private_email': f'person{n}.{nonce}@example.invalid',
                'private_phone': f'+1 202 555 {100 + (n % 100):04d}',
                'private_date': f'2000-01-{1 + n % 28:02d}',
                'private_url': f'https://example.invalid/reference/{nonce}/{n}',
                'account_number': f'DEMO-{nonce.upper()}-{n:06d}',
                'secret': f'SYNTHETIC-{nonce}-{n}',
            }
            mapping[key] = f'[{LABELS[span.label]}]' if mode == 'placeholder' else dummy[span.label]
        edits.append(Edit(span.start, span.end, mapping[key]))
        pieces.extend((text[cursor:span.start], mapping[key]))
        cursor = span.end
        counts[span.label] += 1
    pieces.append(text[cursor:])
    return ''.join(pieces), dict(counts), edits


def transform(result, mode: str):
    text, counts, _ = replacement_plan(result, mode)
    return text, counts


def export_files(text: str, folder: Path):
    folder.mkdir(parents=True, exist_ok=False)
    (folder / 'sanitized.txt').write_text(text, encoding='utf-8')
    doc = Document()
    doc.core_properties.author = ''
    doc.core_properties.last_modified_by = ''
    for line in text.split('\n'):
        doc.add_paragraph(line)
    doc.save(folder / 'sanitized.docx')
    story = pymupdf.Story(html='<html><body>' + ''.join(
        '<p>' + html.escape(line) + '</p>' for line in text.split('\n')
    ) + '</body></html>', user_css='body { font-family: sans-serif; font-size: 11pt; } p { overflow-wrap: anywhere; }')
    with pymupdf.DocumentWriter(str(folder / 'sanitized.pdf')) as writer:
        more = True
        pages = 0
        while more:
            pages += 1
            if pages > 1000:
                raise DocumentError('The rebuilt PDF exceeded the output page limit.')
            device = writer.begin_page(pymupdf.Rect(0, 0, 595, 842))
            more, _ = story.place(pymupdf.Rect(45, 45, 550, 797))
            story.draw(device)
            writer.end_page()


def export_with_fallback(text: str, folder: Path, source, suffix: str, edits: list[Edit]) -> bool:
    """Keep a complete clean rewrite unless native export finishes successfully."""
    export_files(text, folder)
    temporary = folder / f'.native{suffix}'
    try:
        source.save(temporary, edits)
        temporary.replace(folder / f'sanitized{suffix}')
        return True
    except Exception:
        # The rewrite already contains the validated replacements. A native
        # renderer failure (even after a partial write) must not destroy it.
        return False
    finally:
        temporary.unlink(missing_ok=True)
