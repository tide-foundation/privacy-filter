"""App sensitivity scale mapped to OPF's Viterbi transition calibration."""
import hashlib
import json
from pathlib import Path

BIAS_KEYS = (
    'transition_bias_background_stay',
    'transition_bias_background_to_start',
    'transition_bias_inside_to_continue',
    'transition_bias_inside_to_end',
    'transition_bias_end_to_background',
    'transition_bias_end_to_start',
)


def redact(model, text, sensitivity, cache_dir):
    # Preserve the checkpoint's exact default, including its configured decoder.
    if sensitivity == 50:
        return model.redact(text)
    from opf import DecodeOptions
    checkpoint = Path(model.get_runtime().checkpoint)
    calibration = checkpoint / 'viterbi_calibration.json'
    biases = dict.fromkeys(BIAS_KEYS, 0.0)
    if calibration.exists():
        biases.update(json.loads(calibration.read_text())['operating_points']['default']['biases'])
    # +/- 2 log-score units at the extremes. This is an app scale, not confidence.
    offset = (sensitivity - 50) / 25
    biases['transition_bias_background_stay'] -= offset
    biases['transition_bias_background_to_start'] += offset
    biases['transition_bias_inside_to_continue'] += offset / 2
    payload = json.dumps({'operating_points': {'default': {'biases': biases}}}, sort_keys=True)
    directory = Path(cache_dir)
    directory.mkdir(parents=True, exist_ok=True)
    # Content-addressed paths keep OPF's cached decoders valid across app changes.
    path = directory / f'{hashlib.sha256(payload.encode()).hexdigest()}.json'
    if not path.exists():
        path.write_text(payload)
    return model.redact(text, decode=DecodeOptions(decode_mode='viterbi', viterbi_calibration_path=path))
