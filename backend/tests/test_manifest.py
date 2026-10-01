import json
from types import SimpleNamespace

import pytest

from backend.documents import DocumentError, Edit, replacement_plan
from backend.manifest import build_manifest, concealed_review, UNKNOWN_WARNING


def model_result(text='🙂 Alice met Alice on Tuesday.', entries=None):
    if entries is None:
        entries = [(2, 7, 'private_person'), (12, 17, 'private_person'), (21, 28, 'private_date')]
    return SimpleNamespace(text=text, detected_spans=[
        SimpleNamespace(start=start, end=end, label=label, text=text[start:end])
        for start, end, label in entries
    ])


def manifest_for(result, edits=None, **kwargs):
    options = dict(mode='redact', sensitivity=50, source_type='.pdf', layout_preserved=True, warnings=[])
    options.update(kwargs)
    if edits is None:
        _, _, edits = replacement_plan(result, options['mode'])
    return build_manifest(result, edits, **options)


@pytest.mark.parametrize('mode', ['redact', 'placeholder', 'synthetic'])
def test_manifest_keeps_exact_export_replacements_and_unicode_locations(mode):
    result = model_result()
    output, counts, edits = replacement_plan(result, mode)
    manifest = manifest_for(result, edits, mode=mode)
    assert json.loads(json.dumps(manifest)) == manifest
    assert manifest['schema_version'] == 1
    assert manifest['mode'] == mode
    assert [item['original'] for item in manifest['detections']] == ['Alice', 'Alice', 'Tuesday']
    assert [item['occurrence'] for item in manifest['detections']] == [1, 2, 1]
    assert manifest['detections'][0]['span'] == {
        'start': 2, 'end': 7, 'unit': 'unicode_code_points', 'basis': 'extracted_text',
    }
    for item, edit in zip(manifest['detections'], edits):
        assert item['replacement'] == edit.text
        assert item['replacement_type'] == mode
        assert item['replacement'] in output
    assert manifest['scan_report']['counts'] == counts
    assert manifest['scan_report']['total_detections'] == 3


def test_synthetic_manifest_reuses_the_exact_email_nonce(monkeypatch):
    result = model_result('a@example.com a@example.com', [(0, 13, 'private_email'), (14, 27, 'private_email')])
    _, _, edits = replacement_plan(result, 'synthetic')

    def no_second_replacement_plan(*args, **kwargs):
        raise AssertionError('Manifest construction must not generate new synthetic values')

    monkeypatch.setattr('backend.documents.secrets.token_hex', no_second_replacement_plan)
    manifest = manifest_for(result, edits, mode='synthetic')
    assert manifest['detections'][0]['replacement'] == edits[0].text
    assert manifest['detections'][1]['replacement'] == edits[0].text


def test_concealed_review_omits_originals_offsets_lengths_and_future_protected_fields():
    manifest = manifest_for(model_result())
    manifest['source'] = 'A future protected original document'
    manifest['detections'][0]['future_sensitive_field'] = 'Alice'
    manifest['scan_report']['future_sensitive_field'] = 'Tuesday'
    review = concealed_review(manifest)
    encoded = json.dumps(review)
    assert 'Alice' not in encoded and 'Tuesday' not in encoded
    assert set(review) == {'detections', 'scan_report'}
    for detection in review['detections']:
        assert set(detection) == {'category', 'occurrence', 'replacement'}
    assert 'future_sensitive_field' not in encoded
    review['scan_report']['counts']['private_person'] = 99
    review['scan_report']['limitations'].append('Changed client-side')
    assert manifest['scan_report']['counts']['private_person'] == 2
    assert 'Changed client-side' not in manifest['scan_report']['limitations']


def test_objective_report_never_invents_confidence_and_sanitizes_warnings():
    result = model_result()
    # Arbitrary added model fields are not calibrated confidence data.
    result.detected_spans[0].confidence = .999
    warning = 'Images are preserved but are not scanned for sensitive data.'
    manifest = manifest_for(result, sensitivity=75, source_type='.docx', layout_preserved=False,
                            warnings=[None, warning, warning, '', 'Private diagnostic: Alice',
                                      'Original layout unavailable; clean rewrite used.'])
    report = manifest['scan_report']
    assert report['sensitivity'] == 75
    assert report['ocr_performed'] is False
    assert report['source_type'] == 'docx' and report['layout_preserved'] is False
    assert report['warnings'] == [warning, UNKNOWN_WARNING, 'Original layout unavailable; clean rewrite used.']
    assert 'Alice' not in json.dumps(report)
    assert 'confidence' not in manifest['detections'][0]
    assert 'confidence' not in report and 'accuracy' not in report


def test_no_detections_is_a_valid_scan_not_a_guarantee():
    manifest = manifest_for(model_result('Ordinary text.', []))
    assert manifest['detections'] == []
    assert manifest['scan_report']['counts'] == {}
    assert manifest['scan_report']['total_detections'] == 0
    assert any('miss sensitive information' in limitation for limitation in manifest['scan_report']['limitations'])


def test_unsorted_model_spans_align_with_sorted_replacement_plan():
    result = model_result()
    result.detected_spans.reverse()
    manifest = manifest_for(result)
    assert [item['original'] for item in manifest['detections']] == ['Alice', 'Alice', 'Tuesday']


@pytest.mark.parametrize('edits', [
    [],
    [Edit(0, 5, '******')],
    [Edit(2, 7, '******'), Edit(21, 28, '**/**/**'), Edit(12, 17, '******')],
    [Edit(2, 7, '******'), Edit(12, 18, '******'), Edit(21, 28, '**/**/**')],
])
def test_mismatched_export_edits_fail_closed(edits):
    with pytest.raises(DocumentError, match='do not match'):
        manifest_for(model_result(), edits)


@pytest.mark.parametrize('entries', [
    [(0, 4, 'private_person'), (3, 5, 'secret')],
    [(-1, 4, 'private_person')],
    [(0, 6, 'private_person')],
    [(1, 1, 'private_person')],
    [(0, 5, 'unsupported_category')],
])
def test_invalid_spans_fail_without_exposing_source_in_error(entries):
    result = model_result('Alice', entries)
    edits = [Edit(start, end, '******') for start, end, _ in entries]
    with pytest.raises(DocumentError) as failure:
        manifest_for(result, edits)
    assert 'Alice' not in str(failure.value)


def test_model_span_text_mismatch_fails_closed():
    result = model_result()
    result.detected_spans[0].text = 'Another name'
    with pytest.raises(DocumentError, match='does not match'):
        manifest_for(result)


@pytest.mark.parametrize('options', [
    {'mode': 'unknown'}, {'sensitivity': True}, {'sensitivity': 51},
    {'sensitivity': 105}, {'source_type': '.txt'}, {'layout_preserved': 1},
    {'warnings': 'Private diagnostic: Alice'},
])
def test_unsupported_scan_metadata_is_rejected(options):
    result = model_result()
    _, _, edits = replacement_plan(result, 'redact')
    with pytest.raises(DocumentError):
        manifest_for(result, edits, **options)


@pytest.mark.parametrize('source_type', ['.pdf', '.docx', 'pdf', 'docx'])
def test_scan_report_normalizes_file_type(source_type):
    manifest = manifest_for(model_result(), source_type=source_type)
    assert manifest['scan_report']['source_type'] == source_type.removeprefix('.')
