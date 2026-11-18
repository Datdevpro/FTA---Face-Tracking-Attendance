from types import SimpleNamespace
from unittest.mock import Mock

from scripts import start_go2rtc


def config(**overrides):
    return SimpleNamespace(**{
        "CAMERA_AUDIO_ENABLED": True,
        "CAMERA_AUDIO_GO2RTC_URL": "http://127.0.0.1:1984",
        **overrides,
    })


def prepare(tmp_path):
    directory = tmp_path / "camera_test"
    directory.mkdir()
    (directory / "go2rtc.exe").touch()
    (directory / "go2rtc.yaml").touch()
    return directory


def test_reuses_running_go2rtc_without_spawning(monkeypatch, tmp_path):
    monkeypatch.setattr(start_go2rtc, "is_ready", Mock(return_value=True))
    spawn = Mock()
    monkeypatch.setattr(start_go2rtc.subprocess, "Popen", spawn)
    assert start_go2rtc.start(config(), tmp_path) == 0
    spawn.assert_not_called()


def test_starts_with_workspace_paths_and_waits_for_api(monkeypatch, tmp_path):
    directory = prepare(tmp_path)
    probe = Mock(side_effect=[False, False, True])
    monkeypatch.setattr(start_go2rtc, "is_ready", probe)
    process = Mock()
    process.poll.return_value = None
    spawn = Mock(return_value=process)
    monkeypatch.setattr(start_go2rtc.subprocess, "Popen", spawn)
    monkeypatch.setattr(start_go2rtc.time, "sleep", Mock())
    assert start_go2rtc.start(config(), tmp_path) == 0
    assert spawn.call_args.args[0] == [str(directory / "go2rtc.exe"), "-config",
                                           str(directory / "go2rtc.yaml")]
    assert spawn.call_args.kwargs["cwd"] == str(directory)
    assert probe.call_count == 3
    process.terminate.assert_not_called()


def test_failed_readiness_stops_only_process_started_by_helper(monkeypatch, tmp_path):
    prepare(tmp_path)
    monkeypatch.setattr(start_go2rtc, "is_ready", Mock(return_value=False))
    monkeypatch.setattr(start_go2rtc.time, "monotonic", Mock(side_effect=[0, 11]))
    process = Mock()
    process.poll.return_value = None
    monkeypatch.setattr(start_go2rtc.subprocess, "Popen", Mock(return_value=process))
    assert start_go2rtc.start(config(), tmp_path) == 1
    process.terminate.assert_called_once()
    process.wait.assert_called_once_with(timeout=3)


def test_disabled_and_remote_settings_skip_local_start(monkeypatch, tmp_path):
    probe = Mock()
    spawn = Mock()
    monkeypatch.setattr(start_go2rtc, "is_ready", probe)
    monkeypatch.setattr(start_go2rtc.subprocess, "Popen", spawn)
    assert start_go2rtc.start(config(CAMERA_AUDIO_ENABLED=False), tmp_path) == 0
    assert start_go2rtc.start(config(CAMERA_AUDIO_GO2RTC_URL="http://camera-server:1984"), tmp_path) == 0
    probe.assert_not_called()
    spawn.assert_not_called()


def test_missing_binary_warns_without_spawning(monkeypatch, tmp_path):
    monkeypatch.setattr(start_go2rtc, "is_ready", Mock(return_value=False))
    spawn = Mock()
    monkeypatch.setattr(start_go2rtc.subprocess, "Popen", spawn)
    assert start_go2rtc.start(config(), tmp_path) == 1
    spawn.assert_not_called()
