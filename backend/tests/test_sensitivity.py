import json
from types import SimpleNamespace

from backend.sensitivity import BIAS_KEYS, redact


def test_default_and_per_call_calibration(tmp_path):
    checkpoint = tmp_path / 'checkpoint'
    checkpoint.mkdir()
    baseline = dict.fromkeys(BIAS_KEYS, 0.25)
    (checkpoint / 'viterbi_calibration.json').write_text(json.dumps({'operating_points': {'default': {'biases': baseline}}}))

    class Model:
        def get_runtime(self):
            return SimpleNamespace(checkpoint=checkpoint)
        def redact(self, text, **kwargs):
            return kwargs

    model = Model()
    cache = tmp_path / 'cache'
    assert redact(model, 'sample', 50, cache) == {}
    assert not cache.exists()
    profiles = []
    for level in (0, 100, 0):
        options = redact(model, 'sample', level, cache)['decode']
        assert options.decode_mode == 'viterbi'
        profiles.append((options.viterbi_calibration_path, json.loads(options.viterbi_calibration_path.read_text())['operating_points']['default']['biases']))
    assert profiles[0] == profiles[2]
    low, high = profiles[0][1], profiles[1][1]
    assert low['transition_bias_background_stay'] > baseline['transition_bias_background_stay'] > high['transition_bias_background_stay']
    assert low['transition_bias_background_to_start'] < baseline['transition_bias_background_to_start'] < high['transition_bias_background_to_start']
    assert low['transition_bias_inside_to_continue'] < high['transition_bias_inside_to_continue']
    assert low['transition_bias_inside_to_end'] == high['transition_bias_inside_to_end'] == .25
    assert len(list(cache.glob('*.json'))) == 2
