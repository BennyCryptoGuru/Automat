import subprocess

import pytest
from selenium.common.exceptions import SessionNotCreatedException

from automat.browser import BrowserManager, PICKER_SCRIPT


def test_browser_options_do_not_use_custom_profiles_or_debugging(tmp_path):
    manager = BrowserManager(tmp_path)

    arguments = manager._options(None).arguments

    assert not any(argument.startswith("--user-data-dir=") for argument in arguments)
    assert not any(argument.startswith("--remote-debugging-port=") for argument in arguments)
    assert "--remote-debugging-address=127.0.0.1" not in arguments
    assert "--disable-logging" in arguments
    assert "--log-level=3" in arguments
    assert not list(tmp_path.glob("browser-profile*"))


def test_browser_options_can_open_initial_url(tmp_path):
    manager = BrowserManager(tmp_path)

    arguments = manager._options(None, "https://example.com").arguments

    assert "https://example.com" in arguments


def test_browser_options_support_stealth_headless_mode(tmp_path):
    manager = BrowserManager(tmp_path)

    arguments = manager._options(None, stealth=True).arguments

    assert "--headless=new" in arguments
    assert "--window-size=1920,1080" in arguments
    assert "--disable-gpu" in arguments


def test_browser_service_is_silent(tmp_path):
    manager = BrowserManager(tmp_path)

    service = manager._service()

    assert service.log_output == subprocess.DEVNULL
    if hasattr(subprocess, "CREATE_NO_WINDOW"):
        assert service.creation_flags == subprocess.CREATE_NO_WINDOW


def test_browser_candidates_are_chrome_only(tmp_path, monkeypatch):
    manager = BrowserManager(tmp_path)
    monkeypatch.setattr("automat.browser.shutil.which", lambda _command: None)

    candidates = manager._browser_candidates("brave")

    assert candidates
    assert all(name == "Chrome" for name, _path in candidates)


def test_picker_collects_all_supported_locator_alternatives():
    assert "strategy:'class name'" in PICKER_SCRIPT
    assert "strategy:'tag name'" in PICKER_SCRIPT
    assert "strategy:'css selector'" in PICKER_SCRIPT
    assert "strategy:'xpath'" in PICKER_SCRIPT
    assert "strategy:'partial link text'" in PICKER_SCRIPT
    assert "const link=el.closest('a')" in PICKER_SCRIPT
    assert "linkText:link ? link.textContent.trim().slice(0,160) : ''" in PICKER_SCRIPT


def test_session_failure_never_creates_profile_directories(tmp_path, monkeypatch):
    manager = BrowserManager(tmp_path)
    monkeypatch.setattr(
        "automat.browser.webdriver.Chrome",
        lambda **_kwargs: (_ for _ in ()).throw(SessionNotCreatedException("relace spadla")),
    )

    with pytest.raises(RuntimeError, match="Chrome could not"):
        manager.start("chrome")

    assert manager.profile_dir is None
    assert not list(tmp_path.glob("browser-profile*"))


def test_failed_session_is_not_retried_to_avoid_extra_windows(tmp_path, monkeypatch):
    manager = BrowserManager(tmp_path)
    starts = []

    def start_driver(**_kwargs):
        starts.append(1)
        raise SessionNotCreatedException("start spadl")

    monkeypatch.setattr("automat.browser.webdriver.Chrome", start_driver)

    with pytest.raises(RuntimeError, match="Chrome could not"):
        manager.start("chrome")

    assert len(starts) == 1
    assert manager.driver is None


def test_start_can_open_target_url_immediately(tmp_path, monkeypatch):
    manager = BrowserManager(tmp_path)
    driver = type("Driver", (), {"current_url": "data:,", "title": "", "urls": [], "get": lambda self, url: self.urls.append(url) or setattr(self, "current_url", url)})()

    monkeypatch.setattr("automat.browser.webdriver.Chrome", lambda **_kwargs: driver)

    status = manager.start("chrome", "example.com")

    assert status["running"] is True
    assert status["url"] == "https://example.com"
    assert driver.urls == ["https://example.com"]


def test_normalize_web_url():
    assert BrowserManager.normalize_url("example.com") == "https://example.com"
    assert BrowserManager.normalize_url("http://localhost:5000/test") == "http://localhost:5000/test"


def test_internal_browser_url_is_rejected():
    with pytest.raises(ValueError, match="valid web address"):
        BrowserManager.normalize_url("chrome://newtab/")


def test_preview_box_adds_context_around_small_element():
    box = BrowserManager._preview_box((400, 300, 430, 320), (1200, 800))

    assert box[2] - box[0] == 240
    assert box[3] - box[1] == 140
    assert box[0] < 400 < 430 < box[2]
    assert box[1] < 300 < 320 < box[3]


def test_preview_box_stays_inside_screenshot_at_edge():
    box = BrowserManager._preview_box((0, 0, 40, 30), (300, 200))

    assert box == (0, 0, 240, 140)


def test_preview_box_limits_large_preview():
    box = BrowserManager._preview_box((100, 100, 1100, 700), (1400, 900))

    assert box[2] - box[0] == 760
    assert box[3] - box[1] == 480
