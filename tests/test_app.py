import json
import tempfile
from pathlib import Path

import pytest

from automat.app import create_app


@pytest.fixture()
def client():
    with tempfile.TemporaryDirectory() as directory:
        app = create_app({"TESTING": True, "DATABASE": str(Path(directory) / "test.db")})
        yield app.test_client()


def test_index_and_bootstrap(client):
    response = client.get("/")
    assert response.status_code == 200
    assert "Automat" in response.get_data(as_text=True)
    data = client.get("/api/bootstrap").get_json()
    assert data["ok"] is True
    assert "css selector" in data["data"]["locator_strategies"]
    assert "xpath" in data["data"]["locator_strategies"]


def test_dialog_cancel_buttons_do_not_submit_forms(client):
    html = client.get("/").get_data(as_text=True)
    assert html.count('type="button" data-close-dialog') == 10
    assert 'button.closest(\'dialog\').close()' in client.get("/static/app.js").get_data(as_text=True)


def test_static_icon_buttons_use_entities_instead_of_question_marks(client):
    html = client.get("/").get_data(as_text=True)

    assert ">?<" not in html
    assert "Automat - Browser Studio" in html
    assert html.count("&#9881;") >= 4
    assert "&#9658;" in html
    assert "&#10074;&#10074;" in html
    assert "&#9632;" in html
    assert "&#43; Add action" in html


def test_browser_internal_url_cannot_replace_address_input(client):
    javascript = client.get("/static/app.js").get_data(as_text=True)
    assert '/^https?:\\/\\//i.test(b.url||"")' in javascript
    assert 'const target=String(value||$("#urlInput").value).trim()' in javascript


def test_status_poll_does_not_overlap(client):
    javascript = client.get("/static/app.js").get_data(as_text=True)
    assert "if(runnerPollRunning)return" in javascript
    assert "finally{runnerPollRunning=false}" in javascript
    assert "if(browserPollRunning)return" in javascript
    assert "finally{browserPollRunning=false}" in javascript


def test_wait_countdown_is_rendered_in_active_workflow(client):
    javascript = client.get("/static/app.js").get_data(as_text=True)
    html = client.get("/").get_data(as_text=True)
    assert "countdown.remaining" in javascript
    assert "countdown-track" in javascript
    assert "Wait randomly" in html


def test_running_status_uses_pulsing_indicator(client):
    javascript = client.get("/static/app.js").get_data(as_text=True)
    stylesheet = client.get("/static/style.css").get_data(as_text=True)
    assert 'running:"RUNNING"' in javascript
    assert "Loop ·" not in javascript
    assert "@keyframes runningGlow" in stylesheet
    assert "animation: runningGlow" in stylesheet


def test_autorun_setting_is_persisted(client):
    bootstrap = client.get("/api/bootstrap").get_json()["data"]
    assert bootstrap["settings"]["autorun"] is False
    assert bootstrap["settings"]["stealth_run"] is False

    updated = client.put("/api/settings", json={"autorun": True}).get_json()["data"]
    assert updated["autorun"] is True
    assert client.get("/api/bootstrap").get_json()["data"]["settings"]["autorun"] is True

    updated = client.put("/api/settings", json={"stealth_run": True}).get_json()["data"]
    assert updated["stealth_run"] is True
    assert client.get("/api/bootstrap").get_json()["data"]["settings"]["stealth_run"] is True


def test_autorun_settings_controls_are_visible(client):
    html = client.get("/").get_data(as_text=True)
    javascript = client.get("/static/app.js").get_data(as_text=True)
    stylesheet = client.get("/static/style.css").get_data(as_text=True)

    assert 'id="settingsButton"' in html
    assert 'id="settingsDialog"' in html
    assert 'id="autorunEnabled"' in html
    assert 'id="autorunStatus"' in html
    assert 'id="stealthRunEnabled"' in html
    assert 'id="stealthRunStatus"' in html
    assert "/api/settings" in javascript
    assert "renderSettings" in javascript
    assert "Autorun is enabled" in javascript
    assert "Stealth run is enabled" in javascript
    assert ".settings-toggle" in stylesheet
    assert ".toast.success" in stylesheet


def test_language_switcher_is_available(client):
    html = client.get("/").get_data(as_text=True)
    javascript = client.get("/static/app.js").get_data(as_text=True)
    stylesheet = client.get("/static/style.css").get_data(as_text=True)

    assert '<html lang="en">' in html
    assert 'id="languageSelect"' in html
    assert 'value="cs">&#268;e&#353;tina' in html
    assert "setLanguage" in javascript
    assert "automat_language" in javascript
    assert ".language-switch" in stylesheet


def test_language_switcher_does_not_observe_its_own_text_mutations(client):
    javascript = client.get("/static/app.js").get_data(as_text=True)

    assert "if(node.nodeValue!==translated)node.nodeValue=translated" in javascript
    assert "if(element.getAttribute(name)!==translated)element.setAttribute(name,translated)" in javascript
    assert "i18nObserver.observe(document.body,{childList:true,subtree:true})" in javascript
    assert "characterData:true" not in javascript


def test_stealth_monitor_page_is_self_contained(client):
    html = client.get("/monitor").get_data(as_text=True)

    assert "Automat Monitor" in html
    assert "<style>" in html
    assert "<script>" in html
    assert "/api/monitor/status" in html
    assert 'rel="stylesheet"' not in html
    assert 'src="' not in html


def test_root_stealth_status_file_is_self_contained():
    root = Path(__file__).resolve().parents[1]
    html = (root / "stealth_status.html").read_text(encoding="utf-8")

    assert "Automat Stealth Status" in html
    assert "http://127.0.0.1:5000/api/monitor/status" in html
    assert "<style>" in html
    assert "<script>" in html
    assert 'rel="stylesheet"' not in html
    assert 'src="' not in html


def test_monitor_status_allows_root_file_access(client):
    response = client.get("/api/monitor/status")

    assert response.headers["Access-Control-Allow-Origin"] == "*"


def test_monitor_status_returns_logs_and_action_window(client):
    site = client.post("/api/sites", json={"name": "Monitor", "url": "https://example.test"}).get_json()["data"]
    element = client.post("/api/elements", json={
        "site_id": site["id"], "name": "Button", "strategy": "id", "locator": "button",
        "capture_preview": False,
    }).get_json()["data"]
    workflow = client.post("/api/workflows", json={"site_id": site["id"], "name": "Monitor flow"}).get_json()["data"]
    for action_type in ["click", "wait", "refresh", "back"]:
        client.post(f"/api/workflows/{workflow['id']}/actions", json={
            "action_type": action_type,
            "element_id": element["id"] if action_type == "click" else None,
            "parameters": {"seconds": 1} if action_type == "wait" else {},
        })
    runner = client.application.extensions["automat_runner"]
    with runner.lock:
        runner.state.update({
            "status": "running",
            "workflow_id": workflow["id"],
            "current": {"index": 1, "total": 4, "cycle": 1, "action_id": 2, "type": "wait"},
            "repeat_count": 1,
            "message": "2/4 · wait",
            "logs": [
                {"time": "10:00:00", "level": "info", "message": "old"},
                {"time": "10:00:01", "level": "info", "message": "current"},
                {"time": "10:00:02", "level": "success", "message": "next"},
            ],
        })

    data = client.get("/api/monitor/status").get_json()["data"]

    assert data["online"] is True
    assert data["actions"]["workflow"]["name"] == "Monitor flow"
    assert [item["label"] for item in data["actions"]["previous"]] == ["Click"]
    assert data["actions"]["current"]["label"] == "Wait"
    assert [item["label"] for item in data["actions"]["next"]] == ["Refresh", "Back"]
    assert [log["message"] for log in data["logs"]] == ["current", "next"]


def test_stealth_recovery_helper_is_available():
    root = Path(__file__).resolve().parents[1]
    script = root / "scripts" / "disable_stealth_run.ps1"
    batch = root / "disable_stealth_run.bat"

    assert script.exists()
    assert batch.exists()
    text = script.read_text(encoding="utf-8")
    assert "stealth_run" in text
    assert "json.dumps(False)" in text
    assert "/api/browser/quit" in text
    assert 'Join-Path $Root "start.bat"' in text
    assert "disable_stealth_run.bat" in (root / "scripts" / "update.ps1").read_text(encoding="utf-8")


def test_update_script_downloads_from_github_and_preserves_local_data():
    root = Path(__file__).resolve().parents[1]
    text = (root / "scripts" / "update.ps1").read_text(encoding="utf-8")
    watchdog = (root / "scripts" / "watchdog.py").read_text(encoding="utf-8")

    assert "https://github.com/$RepoOwner/$RepoName/archive/refs/heads/$Branch.zip" in text
    assert "Invoke-WebRequest" in text
    assert "Expand-Archive" in text
    assert "Backup-LocalData" in text
    assert "Backing up local data" in text
    assert "Local data in data and the .venv environment will be preserved." in text
    assert "Automat will use visible mode unless Stealth run is enabled in settings." in text
    assert "production version" in text
    assert "produkcni verze" in text
    assert "data\\update.lock" in text
    assert "Set-UpdateLock" in text
    assert "Clear-UpdateLock" in text
    assert "update_in_progress" in watchdog
    assert "UPDATE_LOCK" in watchdog


def test_start_scripts_default_visible_and_stealth_only_when_enabled():
    root = Path(__file__).resolve().parents[1]
    start_batch = (root / "start.bat").read_text(encoding="utf-8")
    start_helper = (root / "scripts" / "start.ps1").read_text(encoding="utf-8")
    hidden_helper = (root / "scripts" / "start_hidden.ps1").read_text(encoding="utf-8")
    runner = (root / "run.py").read_text(encoding="utf-8")

    assert "scripts\\start.ps1" in start_batch
    assert "Invoke-WebRequest" in start_helper
    assert "$AppUrl/api/bootstrap" in start_helper
    assert "Test-StealthRunEnabled" in start_helper
    assert "Starting Automat in visible mode." in start_helper
    assert "Stealth run is enabled. Starting Automat in the background." in start_helper
    assert ".venv\\Scripts\\python.exe" in start_helper
    assert "scripts\\start_hidden.vbs" in start_helper
    assert "pythonw.exe" in hidden_helper
    assert 'Join-Path $Root "run.py"' in start_helper
    assert 'CreateMutexW(None, True, "Local\\\\AutomatBrowserStudio")' in runner


def test_manual_launchers_stay_in_root_and_helpers_live_in_scripts():
    root = Path(__file__).resolve().parents[1]
    manual_launchers = {
        "install.bat",
        "start.bat",
        "update.bat",
        "disable_stealth_run.bat",
        "add_watchdog_to_startup.bat",
        "remove_watchdog_from_startup.bat",
        "start_watchdog.bat",
        "stop_watchdog.bat",
    }
    helper_files = {
        "install.ps1",
        "update.ps1",
        "disable_stealth_run.ps1",
        "add_watchdog_to_startup.ps1",
        "start.ps1",
        "start_hidden.ps1",
        "start_hidden.vbs",
        "watchdog.py",
        "watchdog_hidden.ps1",
        "watchdog_hidden.vbs",
        "start_watchdog.ps1",
        "stop_watchdog.ps1",
    }

    for launcher in manual_launchers:
        assert (root / launcher).exists()
    for helper in helper_files:
        assert not (root / helper).exists()
        assert (root / "scripts" / helper).exists()


def test_manual_watchdog_scripts_can_start_and_stop_only_watchdog():
    root = Path(__file__).resolve().parents[1]
    start_batch = (root / "start_watchdog.bat").read_text(encoding="utf-8")
    stop_batch = (root / "stop_watchdog.bat").read_text(encoding="utf-8")
    start_script = (root / "scripts" / "start_watchdog.ps1").read_text(encoding="utf-8")
    stop_script = (root / "scripts" / "stop_watchdog.ps1").read_text(encoding="utf-8")
    update_script = (root / "scripts" / "update.ps1").read_text(encoding="utf-8")

    assert "scripts\\start_watchdog.ps1" in start_batch
    assert "scripts\\stop_watchdog.ps1" in stop_batch
    assert "watchdog.py" in start_script
    assert "pythonw.exe" in start_script
    assert "Watchdog start requested" in start_script
    assert "watchdog\\.py" in stop_script
    assert "watchdog_hidden\\.ps1" in stop_script
    assert "Stop-Process" in stop_script
    assert "start_watchdog.bat" in update_script
    assert "stop_watchdog.bat" in update_script


def test_runner_controls_are_enabled_only_for_valid_state(client):
    html = client.get("/").get_data(as_text=True)
    javascript = client.get("/static/app.js").get_data(as_text=True)
    stylesheet = client.get("/static/style.css").get_data(as_text=True)
    assert 'id="pauseButton" title="Pause" disabled' in html
    assert 'id="stopButton" title="Stop" disabled' in html
    assert '$("#playButton").disabled=running' in javascript
    assert '$("#pauseButton").disabled=!running' in javascript
    assert '$("#stopButton").disabled=!(running||paused)' in javascript
    assert ".control:disabled" in stylesheet


def test_saved_items_have_individual_delete_controls(client):
    javascript = client.get("/static/app.js").get_data(as_text=True)
    html = client.get("/").get_data(as_text=True)
    assert "data-delete-site" in javascript
    assert "data-delete-action" in javascript
    assert 'id="deleteWorkflow"' in html


def test_saved_element_has_edit_control(client):
    javascript = client.get("/static/app.js").get_data(as_text=True)
    assert "data-edit-element" in javascript
    assert "openEditElement" in javascript
    assert "syncElementLocatorFromStrategy" in javascript
    assert "elementLocatorAlternatives" in javascript
    assert "elements.strategy.onchange" in javascript


def test_site_element_workflow_and_actions(client):
    site = client.post("/api/sites", json={"name": "Selenium", "url": "https://selenium.dev"}).get_json()["data"]
    element = client.post("/api/elements", json={
        "site_id": site["id"], "name": "Documentation", "strategy": "css selector",
        "locator": "a[href*='documentation']", "capture_preview": False,
        "alternatives": [{"strategy": "link text", "locator": "Documentation"}],
    }).get_json()["data"]
    workflow = client.post("/api/workflows", json={"site_id": site["id"], "name": "Test"}).get_json()["data"]
    response = client.post(f"/api/workflows/{workflow['id']}/actions", json={
        "action_type": "click", "element_id": element["id"], "parameters": {},
    })
    assert response.status_code == 201
    loaded = client.get(f"/api/workflows/{workflow['id']}").get_json()["data"]
    assert len(loaded["actions"]) == 1
    assert loaded["actions"][0]["element_id"] == element["id"]

    updated = client.put(f"/api/elements/{element['id']}", json={
        "site_id": site["id"], "name": "Dokumentace upravená", "strategy": "xpath",
        "locator": "//a[@href='/documentation']", "parent_id": None,
    }).get_json()["data"]
    assert updated["id"] == element["id"]
    assert updated["name"] == "Dokumentace upravená"
    loaded_again = client.get(f"/api/workflows/{workflow['id']}").get_json()["data"]
    assert loaded_again["actions"][0]["element_id"] == element["id"]


def test_encrypted_credential_profile_is_not_exposed(client):
    site = client.post("/api/sites", json={"name": "Login", "url": "https://example.com"}).get_json()["data"]
    username = client.post("/api/elements", json={"name": "User", "strategy": "id", "locator": "user", "capture_preview": False}).get_json()["data"]
    password = client.post("/api/elements", json={"name": "Password", "strategy": "id", "locator": "password", "capture_preview": False}).get_json()["data"]
    response = client.post("/api/credentials", json={
        "site_id": site["id"], "name": "Můj účet", "username": "secret-user",
        "password": "secret-password", "username_element_id": username["id"],
        "password_element_id": password["id"],
    })

    assert response.status_code == 201
    assert "secret" not in response.get_data(as_text=True)
    bootstrap = client.get("/api/bootstrap").get_json()["data"]
    assert bootstrap["credentials"][0]["name"] == "Můj účet"
    assert "password_cipher" not in bootstrap["credentials"][0]
    stored = client.application.extensions["automat_db"].one("SELECT * FROM credentials")
    assert b"secret-user" not in stored["username_cipher"]
    assert b"secret-password" not in stored["password_cipher"]

    credential = response.get_json()["data"]
    workflow = client.post("/api/workflows", json={"site_id": site["id"], "name": "Login backup"}).get_json()["data"]
    client.post(f"/api/workflows/{workflow['id']}/actions", json={
        "action_type": "auto_login", "parameters": {"credential_id": credential["id"]},
    })
    exported = client.get(f"/api/workflows/{workflow['id']}/export").get_json()
    exported_text = json.dumps(exported)
    assert "secret-user" not in exported_text
    assert "secret-password" not in exported_text
    assert exported["actions"][0]["parameters"] == {"credential_ref": "Můj účet"}


def test_credential_card_has_direct_login_control(client):
    javascript = client.get("/static/app.js").get_data(as_text=True)
    assert "data-login-credential" in javascript
    assert "/login`" in javascript


def test_credential_profile_can_be_updated_without_retyping_secret(client):
    username = client.post("/api/elements", json={"name": "User", "strategy": "id", "locator": "user", "capture_preview": False}).get_json()["data"]
    password = client.post("/api/elements", json={"name": "Password", "strategy": "id", "locator": "password", "capture_preview": False}).get_json()["data"]
    credential = client.post("/api/credentials", json={
        "name": "Původní", "username": "secret-user", "password": "secret-password",
        "username_element_id": username["id"], "password_element_id": password["id"],
    }).get_json()["data"]

    updated = client.put(f"/api/credentials/{credential['id']}", json={
        "site_id": None, "name": "Upravený", "username": "", "password": "",
        "username_element_id": username["id"], "password_element_id": password["id"],
        "submit_element_id": None,
    }).get_json()["data"]
    stored = client.application.extensions["automat_db"].one("SELECT * FROM credentials WHERE id=?", (credential["id"],))
    vault = client.application.extensions["automat_vault"]

    assert updated["name"] == "Upravený"
    assert "password_cipher" not in updated
    assert vault.decrypt(stored["username_cipher"]) == "secret-user"
    assert vault.decrypt(stored["password_cipher"]) == "secret-password"


def test_credential_profile_can_store_extra_login_actions(client):
    username = client.post("/api/elements", json={"name": "User", "strategy": "id", "locator": "user", "capture_preview": False}).get_json()["data"]
    password = client.post("/api/elements", json={"name": "Password", "strategy": "id", "locator": "password", "capture_preview": False}).get_json()["data"]
    checkbox = client.post("/api/elements", json={"name": "Remember", "strategy": "id", "locator": "remember", "capture_preview": False}).get_json()["data"]
    credential = client.post("/api/credentials", json={
        "name": "S kroky", "username": "secret-user", "password": "secret-password",
        "username_element_id": username["id"], "password_element_id": password["id"],
        "extra_actions": [{"action_type": "click", "element_id": checkbox["id"]}, {"action_type": "wait", "seconds": 2}],
    }).get_json()["data"]

    assert credential["extra_actions"] == [{"action_type": "click", "element_id": checkbox["id"]}, {"action_type": "wait", "seconds": 2.0}]
    bootstrap = client.get("/api/bootstrap").get_json()["data"]
    assert bootstrap["credentials"][0]["extra_actions"][0]["element_id"] == checkbox["id"]


def test_credential_export_and_import_roundtrip(client):
    site = client.post("/api/sites", json={"name": "Login", "url": "https://login.example"}).get_json()["data"]
    username = client.post("/api/elements", json={"site_id": site["id"], "name": "User", "strategy": "id", "locator": "user", "capture_preview": False}).get_json()["data"]
    password = client.post("/api/elements", json={"site_id": site["id"], "name": "Password", "strategy": "id", "locator": "password", "capture_preview": False}).get_json()["data"]
    submit = client.post("/api/elements", json={"site_id": site["id"], "name": "Submit", "strategy": "id", "locator": "submit", "capture_preview": False}).get_json()["data"]
    remember = client.post("/api/elements", json={"site_id": site["id"], "name": "Remember", "strategy": "id", "locator": "remember", "capture_preview": False}).get_json()["data"]
    credential = client.post("/api/credentials", json={
        "site_id": site["id"], "name": "Zalohovany profil", "username": "backup-user",
        "password": "backup-password", "username_element_id": username["id"],
        "password_element_id": password["id"], "submit_element_id": submit["id"],
        "extra_actions": [{"action_type": "click", "element_id": remember["id"]}],
    }).get_json()["data"]

    exported = client.get("/api/credentials/export")
    archive = exported.get_json()
    assert exported.status_code == 200
    assert exported.headers["Content-Disposition"].endswith('prihlasovaci-profily.automat.json"')
    assert archive["format"] == "automat-credentials"
    assert archive["credentials"][0]["username"] == "backup-user"
    assert archive["credentials"][0]["password"] == "backup-password"
    assert archive["credentials"][0]["username_element_ref"]
    assert archive["credentials"][0]["extra_actions"][0]["element_ref"]

    client.delete(f"/api/credentials/{credential['id']}")
    imported = client.post("/api/credentials/import", json=archive).get_json()["data"]
    stored = client.application.extensions["automat_db"].one("SELECT * FROM credentials WHERE name=?", ("Zalohovany profil",))
    vault = client.application.extensions["automat_vault"]

    assert imported["created"] == 1
    assert imported["updated"] == 0
    assert imported["total"] == 1
    assert vault.decrypt(stored["username_cipher"]) == "backup-user"
    assert vault.decrypt(stored["password_cipher"]) == "backup-password"
    assert stored["submit_element_id"] == submit["id"]
    assert stored["extra_actions"][0]["element_id"] == remember["id"]


def test_credential_backup_controls_are_visible(client):
    html = client.get("/").get_data(as_text=True)
    javascript = client.get("/static/app.js").get_data(as_text=True)

    assert 'id="credentialTools"' in html
    assert 'id="exportCredentials"' in html
    assert 'id="importCredentials"' in html
    assert 'id="credentialImportFile"' in html
    assert "/api/credentials/export" in javascript
    assert "/api/credentials/import" in javascript
    assert 'id="addCredentialAction"' in html
    assert 'id="credentialExtraActions"' in html
    assert "readCredentialExtraActions" in javascript


def test_new_continuous_action_types_are_available(client):
    action_types = client.get("/api/bootstrap").get_json()["data"]["action_types"]
    assert {"auto_login", "repeat_click", "repeat_until"} <= set(action_types)


def test_loop_controls_and_repeat_count_are_connected(client):
    html = client.get("/").get_data(as_text=True)
    javascript = client.get("/static/app.js").get_data(as_text=True)
    assert 'id="loopEnabled" type="checkbox" checked' in html
    assert 'id="loopCount"' in html
    assert 'id="loopCount" class="loop-count" type="number" min="0" value="0"' in html
    assert "{repeat_count}" in javascript


def test_workflow_export_and_import_preserves_element_links(client):
    site = client.post("/api/sites", json={"name": "Backup", "url": "https://example.com"}).get_json()["data"]
    source = client.post("/api/elements", json={"site_id": site["id"], "name": "Zdroj", "strategy": "id", "locator": "source", "capture_preview": False}).get_json()["data"]
    target = client.post("/api/elements", json={"site_id": site["id"], "name": "Cíl", "strategy": "css selector", "locator": ".target", "capture_preview": False}).get_json()["data"]
    workflow = client.post("/api/workflows", json={"site_id": site["id"], "name": "Záloha"}).get_json()["data"]
    client.post(f"/api/workflows/{workflow['id']}/actions", json={
        "action_type": "repeat_until", "element_id": source["id"],
        "parameters": {"target_element_id": target["id"], "operation": "click", "interval_seconds": 1},
    })

    exported = client.get(f"/api/workflows/{workflow['id']}/export")
    archive = exported.get_json()
    assert exported.status_code == 200
    assert exported.headers["Content-Disposition"].endswith('.automat.json"')
    assert archive["format"] == "automat-workflow"
    assert archive["actions"][0]["element_ref"]
    assert archive["actions"][0]["parameters"]["target_element_ref"]
    assert "target_element_id" not in archive["actions"][0]["parameters"]

    imported = client.post("/api/workflows/import", json=archive).get_json()["data"]
    loaded = client.get(f"/api/workflows/{imported['workflow']['id']}").get_json()["data"]
    assert loaded["name"] == "Záloha (import)"
    assert loaded["actions"][0]["element_id"] == source["id"]
    assert loaded["actions"][0]["parameters"]["target_element_id"] == target["id"]


def test_workflow_import_rejects_unknown_format(client):
    with pytest.raises(ValueError, match="supported Automat backup"):
        client.post("/api/workflows/import", json={"format": "something-else", "version": 1})


def test_workflow_backup_controls_are_visible(client):
    html = client.get("/").get_data(as_text=True)
    javascript = client.get("/static/app.js").get_data(as_text=True)
    assert 'id="exportWorkflow"' in html
    assert 'id="importWorkflow"' in html
    assert "/api/workflows/import" in javascript


def test_element_export_and_import_preserves_site_and_parent(client):
    site = client.post("/api/sites", json={"name": "Objekty", "url": "https://objects.example"}).get_json()["data"]
    parent = client.post("/api/elements", json={
        "site_id": site["id"], "name": "Rodič", "strategy": "id", "locator": "parent",
        "alternatives": [{"strategy": "css selector", "locator": "#parent"}], "capture_preview": False,
    }).get_json()["data"]
    child = client.post("/api/elements", json={
        "site_id": site["id"], "name": "Podobjekt", "strategy": "css selector", "locator": ".child",
        "parent_id": parent["id"], "metadata": {"tag": "button"}, "capture_preview": False,
    }).get_json()["data"]

    exported = client.get("/api/elements/export")
    archive = exported.get_json()
    assert exported.status_code == 200
    assert exported.headers["Content-Disposition"].endswith('objekty.automat.json"')
    assert archive["format"] == "automat-elements"
    assert len(archive["elements"]) == 2
    assert next(item for item in archive["elements"] if item["name"] == "Podobjekt")["parent_ref"]

    client.delete(f"/api/elements/{child['id']}")
    client.delete(f"/api/elements/{parent['id']}")
    imported = client.post("/api/elements/import", json=archive).get_json()["data"]
    values = client.get("/api/bootstrap").get_json()["data"]["elements"]
    imported_parent = next(item for item in values if item["name"] == "Rodič")
    imported_child = next(item for item in values if item["name"] == "Podobjekt")
    assert imported == {"created": 2, "reused": 0, "total": 2}
    assert imported_child["parent_id"] == imported_parent["id"]
    assert imported_child["metadata"] == {"tag": "button"}


def test_element_export_and_import_restores_preview_image(client):
    site = client.post("/api/sites", json={"name": "Preview", "url": "https://preview.example"}).get_json()["data"]
    element = client.post("/api/elements", json={
        "site_id": site["id"], "name": "Preview object", "strategy": "id", "locator": "preview",
        "capture_preview": False,
    }).get_json()["data"]
    browser = client.application.extensions["automat_browser"]
    db = client.application.extensions["automat_db"]
    preview_bytes = b"\x89PNG\r\n\x1a\npreview"
    preview_path = browser.screenshot_dir / f"element-{element['id']}.png"
    preview_path.write_bytes(preview_bytes)
    db.execute("UPDATE elements SET preview_path=? WHERE id=?", (f"/screenshots/{preview_path.name}", element["id"]))

    archive = client.get("/api/elements/export").get_json()
    exported = next(item for item in archive["elements"] if item["name"] == "Preview object")
    assert exported["preview"]["data"]

    client.delete(f"/api/elements/{element['id']}")
    preview_path.unlink()
    imported = client.post("/api/elements/import", json=archive).get_json()["data"]
    values = client.get("/api/bootstrap").get_json()["data"]["elements"]
    restored = next(item for item in values if item["name"] == "Preview object")
    restored_path = browser.screenshot_dir / Path(restored["preview_path"]).name

    assert imported == {"created": 1, "reused": 0, "total": 1}
    assert restored_path.read_bytes() == preview_bytes


def test_element_import_rejects_unknown_format(client):
    with pytest.raises(ValueError, match="object backup"):
        client.post("/api/elements/import", json={"format": "something-else", "version": 1})


def test_action_clipboard_and_gear_menus_are_connected(client):
    html = client.get("/").get_data(as_text=True)
    javascript = client.get("/static/app.js").get_data(as_text=True)
    assert 'id="workflowTools"' in html
    assert 'id="selectAllActions"' in html
    assert 'id="copyActions"' in html
    assert 'id="pasteActions"' in html
    assert 'id="insertPositionLabel"' in html
    assert 'id="actionContextMenu"' in html
    assert 'id="contextPasteBefore"' in html
    assert 'id="contextPasteAfter"' in html
    assert 'id="actionDialogTitle"' in html
    assert 'id="credentialDialogTitle"' in html
    assert 'id="importElements"' in html
    assert 'id="exportElements"' in html
    assert "selectedActions:new Set()" in javascript
    assert "data-edit-action" in javascript
    assert "data-edit-credential" in javascript
    assert "moveSelectedActionToPosition" in javascript
    assert "moveBuffer" in javascript
    assert 'key==="c"' in javascript
    assert 'key==="v"' in javascript
    assert 'key==="Enter"' in javascript
    assert "showActionContextMenu" in javascript
    assert "insert-before" in javascript
    assert "/api/elements/import" in javascript
    assert "/api/elements/export" in javascript


def test_rejects_unknown_locator_and_action(client):
    with pytest.raises(ValueError):
        client.post("/api/elements", json={"name": "Bad", "strategy": "magic", "locator": "x"})
    workflow = client.post("/api/workflows", json={"name": "Test"}).get_json()["data"]
    with pytest.raises(ValueError):
        client.post(f"/api/workflows/{workflow['id']}/actions", json={"action_type": "teleport"})
