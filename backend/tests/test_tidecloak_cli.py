"""Terminal discovery tolerates app restarts without replaying setup writes."""
import importlib.util
from pathlib import Path
import urllib.error
from types import SimpleNamespace

import pytest


@pytest.fixture
def cli():
    spec = importlib.util.spec_from_file_location('tidecloak_cli', Path(__file__).resolve().parents[2] / 'scripts/tidecloak.py')
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_discovery_recovers_after_connection_reset_and_temporary_unavailability(cli, monkeypatch, capsys):
    responses = iter([ConnectionResetError(104, 'Connection reset by peer'),
                      urllib.error.HTTPError('http://localhost:3001', 503, 'Starting', {}, None),
                      {'configured': False, 'reachable': True}])
    calls = []
    def call(origin, path, body=None, *, timeout=20):
        calls.append((path, body, timeout))
        response = next(responses)
        if isinstance(response, Exception):
            raise response
        return response
    monkeypatch.setattr(cli, 'call', call)
    monkeypatch.setattr(cli.time, 'sleep', lambda seconds: None)
    assert cli.wait_for_app('http://localhost:3001') == {'configured': False, 'reachable': True}
    assert len(calls) == 3
    assert all(path == 'tide/status' and body is None and timeout <= 5 for path, body, timeout in calls)
    assert capsys.readouterr().out.count('Waiting for Redacted') == 1


def test_discovery_stops_at_deadline_with_actionable_message(cli, monkeypatch):
    elapsed = [0]
    monkeypatch.setattr(cli.time, 'monotonic', lambda: elapsed[0])
    monkeypatch.setattr(cli.time, 'sleep', lambda seconds: elapsed.__setitem__(0, elapsed[0] + seconds))
    def offline(*args, **kwargs):
        raise urllib.error.URLError('Connection refused')
    monkeypatch.setattr(cli, 'call', offline)
    with pytest.raises(RuntimeError, match='docker compose up -d app'):
        cli.wait_for_app('http://localhost:3001', timeout=3)
    assert elapsed[0] == 3


def test_discovery_does_not_retry_permanent_http_errors(cli, monkeypatch):
    def forbidden(*args, **kwargs):
        raise urllib.error.HTTPError('http://localhost:3001', 403, 'Forbidden', {}, None)
    monkeypatch.setattr(cli, 'call', forbidden)
    monkeypatch.setattr(cli.time, 'sleep', lambda seconds: pytest.fail('Permanent errors must not be retried'))
    with pytest.raises(urllib.error.HTTPError) as error:
        cli.wait_for_app('http://localhost:3001')
    assert error.value.code == 403


def test_interrupted_handoff_is_not_replayed_and_removes_permit(cli, monkeypatch, tmp_path):
    calls = []
    def interrupted(origin, path, body=None):
        calls.append(path)
        assert (tmp_path / 'tide/launch-permit.json').exists()
        raise ConnectionResetError(104, 'Connection reset by peer')
    monkeypatch.setattr(cli, 'call', interrupted)
    with pytest.raises(ConnectionResetError):
        cli.handoff('http://localhost:3001', tmp_path, 'owner', 'test-password', open_browser=False)
    assert calls == ['tide/setup/v2/launch']
    assert not (tmp_path / 'tide/launch-permit.json').exists()


@pytest.mark.parametrize('platform,expected', [('darwin', 'open'), ('linux', '/usr/bin/xdg-open')])
def test_native_launch_passes_url_as_one_argument(cli, monkeypatch, platform, expected):
    monkeypatch.delenv('WSL_DISTRO_NAME', raising=False)
    monkeypatch.setattr(cli.Path, 'read_text', lambda self: 'generic')
    monkeypatch.setattr(cli.sys, 'platform', platform)
    monkeypatch.setattr(cli.shutil, 'which', lambda name: '/usr/bin/xdg-open' if name == 'xdg-open' else None)
    calls = []
    monkeypatch.setattr(cli.subprocess, 'run', lambda args, **kw: calls.append((args, kw)) or SimpleNamespace(returncode=0))
    url = 'http://localhost:3001/secure-history/setup#setup=private&token'
    assert cli.open_setup_browser(url)
    assert calls[0][0] == [expected, url]
    assert not calls[0][1].get('shell')


def test_wsl_falls_back_to_windows_without_interpolating_private_url(cli, monkeypatch):
    monkeypatch.setenv('WSL_DISTRO_NAME', 'Debian')
    monkeypatch.setattr(cli.shutil, 'which', lambda name: {'wslview': '/usr/bin/wslview', 'powershell.exe': '/windows/powershell.exe'}.get(name))
    calls = []
    def run(args, **kw):
        calls.append((args, kw))
        return SimpleNamespace(returncode=1 if len(calls) == 1 else 0)
    monkeypatch.setattr(cli.subprocess, 'run', run)
    url = 'http://localhost:3001/secure-history/setup#setup=private&token'
    assert cli.open_setup_browser(url)
    assert calls[0][0] == ['/usr/bin/wslview', url]
    assert calls[1][0][0] == '/windows/powershell.exe'
    assert url not in ' '.join(calls[1][0])
    assert calls[1][1]['input'] == url
    assert not calls[1][1].get('shell')


@pytest.mark.parametrize('opened', [True, False])
def test_handoff_always_prints_complete_link_and_manual_instructions_on_failure(cli, monkeypatch, tmp_path, capsys, opened):
    url = 'http://localhost:3001/secure-history/setup#setup=private-test-link'
    monkeypatch.setattr(cli, 'call', lambda *a, **kw: {'url': url})
    monkeypatch.setattr(cli, 'open_setup_browser', lambda link: opened)
    assert cli.handoff('http://localhost:3001', tmp_path, 'owner', 'test-password') == url
    output = capsys.readouterr().out
    assert url in output and 'one hour' in output
    assert ('paste the complete private setup link' in output) is not opened
    assert 'test-password' not in output


def test_windows_uses_default_browser_and_reports_failure(cli, monkeypatch):
    monkeypatch.delenv('WSL_DISTRO_NAME', raising=False)
    monkeypatch.setattr(cli.Path, 'read_text', lambda self: 'generic')
    monkeypatch.setattr(cli.sys, 'platform', 'win32')
    urls = []
    monkeypatch.setattr(cli.webbrowser, 'open', lambda url: urls.append(url) or False)
    assert not cli.open_setup_browser('http://localhost:3001/')
    assert urls == ['http://localhost:3001/']


def test_launch_timeout_becomes_manual_fallback(cli, monkeypatch):
    monkeypatch.delenv('WSL_DISTRO_NAME', raising=False)
    monkeypatch.setattr(cli.Path, 'read_text', lambda self: 'generic')
    monkeypatch.setattr(cli.sys, 'platform', 'linux')
    monkeypatch.setattr(cli.shutil, 'which', lambda name: '/usr/bin/xdg-open')
    def timeout(args, **kw): raise cli.subprocess.TimeoutExpired(args, kw['timeout'])
    monkeypatch.setattr(cli.subprocess, 'run', timeout)
    assert not cli.open_setup_browser('http://localhost:3001/')
