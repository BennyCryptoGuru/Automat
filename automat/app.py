import atexit
import base64
import binascii
import json
import re
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from flask import Flask, jsonify, render_template, request, send_from_directory

from .browser import LOCATOR_STRATEGIES, BrowserManager
from .db import Database
from .runner import WorkflowRunner
from .secrets import SecretVault


ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


def create_app(test_config=None):
    app = Flask(__name__, static_folder="static", template_folder="templates")
    app.config.update(DATABASE=str(DATA / "automat.db"), TESTING=False, ENABLE_AUTORUN_MONITOR=False)
    if test_config:
        app.config.update(test_config)
    db = Database(Path(app.config["DATABASE"]))
    browser = BrowserManager(DATA)
    vault = SecretVault()
    runner = WorkflowRunner(browser, db, vault)
    app.extensions.update(automat_db=db, automat_browser=browser, automat_runner=runner, automat_vault=vault)

    def payload():
        return request.get_json(silent=True) or {}

    @app.after_request
    def allow_local_monitor_file(response):
        if request.path == "/api/monitor/status":
            response.headers["Access-Control-Allow-Origin"] = "*"
            response.headers["Access-Control-Allow-Methods"] = "GET, OPTIONS"
            response.headers["Access-Control-Allow-Headers"] = "Content-Type"
        return response

    def ok(data=None, status=200):
        return jsonify({"ok": True, "data": data}), status

    def credential_public_select():
        return "id,site_id,name,username_element_id,password_element_id,submit_element_id,extra_actions,created_at"

    def get_setting(key, default=None):
        row = db.one("SELECT value FROM settings WHERE key=?", (key,))
        if not row:
            return default
        try:
            return json.loads(row["value"])
        except (TypeError, json.JSONDecodeError):
            return default

    def set_setting(key, value):
        db.execute(
            "INSERT INTO settings(key,value) VALUES(?,?) ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, json.dumps(value)),
        )
        return value

    def export_element_preview(item):
        preview_path = item.get("preview_path")
        if not preview_path:
            return None
        filename = Path(str(preview_path).split("?", 1)[0]).name
        if not filename:
            return None
        path = browser.screenshot_dir / filename
        if not path.is_file():
            return None
        return {
            "filename": filename,
            "content_type": "image/png",
            "data": base64.b64encode(path.read_bytes()).decode("ascii"),
        }

    def import_element_preview(connection, item, element_id):
        preview = item.get("preview")
        if not isinstance(preview, dict) or not preview.get("data"):
            return
        try:
            content = base64.b64decode(str(preview["data"]), validate=True)
        except (binascii.Error, ValueError):
            raise ValueError("The object backup contains an invalid preview image") from None
        if len(content) > 5 * 1024 * 1024:
            raise ValueError("The object backup contains a preview image that is too large")
        browser.screenshot_dir.mkdir(parents=True, exist_ok=True)
        filename = f"element-{element_id}.png"
        path = browser.screenshot_dir / filename
        path.write_bytes(content)
        connection.execute("UPDATE elements SET preview_path=? WHERE id=?", (f"/screenshots/{filename}", element_id))

    def settings_payload():
        return {
            "autorun": bool(get_setting("autorun", False)),
            "stealth_run": bool(get_setting("stealth_run", False)),
        }

    browser.set_stealth_run(settings_payload()["stealth_run"])

    def normalize_element_alternatives(strategy, locator, raw_alternatives):
        values = []
        seen = set()

        def add(item_strategy, item_locator):
            item_locator = str(item_locator or "").strip()
            if item_strategy not in LOCATOR_STRATEGIES or not item_locator:
                return
            key = (item_strategy, item_locator)
            if key in seen:
                return
            seen.add(key)
            values.append({"strategy": item_strategy, "locator": item_locator})

        add(strategy, locator)
        if isinstance(raw_alternatives, list):
            for item in raw_alternatives:
                if isinstance(item, dict):
                    add(item.get("strategy"), item.get("locator"))
        return values

    def normalize_credential_actions(raw_actions):
        raw_actions = raw_actions or []
        if not isinstance(raw_actions, list) or len(raw_actions) > 100:
            raise ValueError("Extra login actions have an invalid structure")
        actions = []
        for index, item in enumerate(raw_actions, 1):
            if not isinstance(item, dict):
                raise ValueError(f"Extra login action {index} is invalid")
            action_type = item.get("action_type") or "click"
            if action_type not in CREDENTIAL_ACTION_TYPES:
                raise ValueError(f"Unsupported extra login action: {action_type}")
            action = {"action_type": action_type}
            if action_type == "wait":
                action["seconds"] = max(0, float(item.get("seconds") or 1))
            else:
                if not item.get("element_id"):
                    raise ValueError(f"Extra login action {index} requires an object")
                action["element_id"] = int(item["element_id"])
                if action_type in {"type", "key"}:
                    action["value"] = str(item.get("value") or "")
            actions.append(action)
        return actions

    @app.errorhandler(Exception)
    def error(exc):
        if app.config["TESTING"]:
            raise exc
        return jsonify({"ok": False, "error": str(exc), "type": type(exc).__name__}), 400

    @app.get("/")
    def index():
        return render_template("index.html", locator_strategies=LOCATOR_STRATEGIES, action_types=ACTION_TYPES)

    @app.get("/monitor")
    def monitor():
        return render_template("monitor.html")

    def monitor_action_item(action, active=False):
        parameters = action.get("parameters") or {}
        details = []
        if action.get("element_name"):
            details.append(action["element_name"])
        for value in parameters.values():
            if isinstance(value, (dict, list)) or value in (None, ""):
                continue
            details.append(str(value))
            if len(details) >= 3:
                break
        return {
            "id": action["id"],
            "position": action["position"],
            "type": action["action_type"],
            "label": ACTION_TYPES.get(action["action_type"], action["action_type"]),
            "details": " - ".join(details),
            "active": active,
        }

    def monitor_action_window(runner_state):
        workflow_id = runner_state.get("workflow_id")
        current = runner_state.get("current")
        if not workflow_id:
            return {"workflow": None, "previous": [], "current": None, "next": []}
        workflow = db.one("SELECT id,name FROM workflows WHERE id=?", (workflow_id,))
        actions = db.all(
            "SELECT a.*, e.name AS element_name FROM actions a "
            "LEFT JOIN elements e ON e.id=a.element_id "
            "WHERE a.workflow_id=? AND a.enabled=1 ORDER BY a.position,a.id",
            (workflow_id,),
        )
        if not actions:
            return {"workflow": workflow, "previous": [], "current": None, "next": []}
        current_index = current.get("index") if current else None
        if current_index is None or current_index < 0 or current_index >= len(actions):
            return {"workflow": workflow, "previous": [], "current": None, "next": [monitor_action_item(item) for item in actions[:2]]}
        repeat_forever = runner_state.get("repeat_count") == 0

        def pick(offsets):
            picked = []
            for offset in offsets:
                index = current_index + offset
                if repeat_forever:
                    index %= len(actions)
                if 0 <= index < len(actions) and index != current_index:
                    picked.append(monitor_action_item(actions[index]))
            return picked

        return {
            "workflow": workflow,
            "previous": pick([-2, -1]),
            "current": monitor_action_item(actions[current_index], True),
            "next": pick([1, 2]),
        }

    @app.get("/api/monitor/status")
    def monitor_status():
        runner_state = runner.snapshot()
        browser_state = browser.status()
        settings = settings_payload()
        action_window = monitor_action_window(runner_state)
        return ok({
            "online": True,
            "background": bool(settings.get("stealth_run") or browser_state.get("stealth_run")),
            "settings": settings,
            "browser": browser_state,
            "runner": runner_state,
            "logs": list(runner_state.get("logs", []))[-2:],
            "actions": action_window,
        })

    @app.get("/api/bootstrap")
    def bootstrap():
        return ok({
            "sites": db.all("SELECT * FROM sites ORDER BY updated_at DESC"),
            "elements": db.all("SELECT * FROM elements ORDER BY id DESC"),
            "workflows": db.all("SELECT * FROM workflows ORDER BY updated_at DESC"),
            "credentials": db.all(f"SELECT {credential_public_select()} FROM credentials ORDER BY id DESC"),
            "browser": browser.status(), "runner": runner.snapshot(),
            "settings": settings_payload(),
            "locator_strategies": LOCATOR_STRATEGIES, "action_types": ACTION_TYPES,
        })

    @app.get("/api/settings")
    def get_settings():
        return ok(settings_payload())

    @app.put("/api/settings")
    def update_settings():
        p = payload()
        if "autorun" in p:
            set_setting("autorun", bool(p["autorun"]))
            if p["autorun"] and app.config.get("ENABLE_AUTORUN_MONITOR"):
                threading.Thread(target=lambda: run_autorun("settings_enabled"), daemon=True).start()
        if "stealth_run" in p:
            browser.set_stealth_run(set_setting("stealth_run", bool(p["stealth_run"])))
        return ok(settings_payload())

    @app.post("/api/browser/start")
    def browser_start():
        p = payload()
        return ok(browser.start(p.get("preferred", "chrome"), p.get("url"), p.get("stealth_run")))

    @app.post("/api/browser/navigate")
    def browser_navigate():
        url = payload().get("url", "").strip()
        if not url:
            raise ValueError("Zadejte adresu webu")
        return ok(browser.navigate(url))

    @app.get("/api/browser/status")
    def browser_status():
        return ok(browser.status())

    @app.post("/api/browser/quit")
    def browser_quit():
        browser.quit()
        return ok(browser.status())

    @app.post("/api/picker/start")
    def picker_start():
        p = payload()
        click_count = p.get("click_count", 1)
        browser.begin_picker(click_count)
        try:
            click_count = max(1, int(click_count or 1))
        except (TypeError, ValueError):
            click_count = 1
        return ok({"active": True, "click_count": click_count})

    @app.get("/api/picker/result")
    def picker_result():
        return ok(browser.picker_result())

    @app.post("/api/elements")
    def create_element():
        p = payload()
        if p.get("strategy") not in LOCATOR_STRATEGIES:
            raise ValueError("Invalid locator strategy")
        if not p.get("name") or not p.get("locator"):
            raise ValueError("Name and locator are required")
        alternatives = normalize_element_alternatives(p["strategy"], p["locator"], p.get("alternatives", []))
        element_id = db.execute(
            "INSERT INTO elements(site_id,name,strategy,locator,alternatives,frame_path,parent_id,metadata) VALUES(?,?,?,?,?,?,?,?)",
            (p.get("site_id"), p["name"].strip(), p["strategy"], p["locator"], json.dumps(alternatives), json.dumps(p.get("frame_path", [])), p.get("parent_id"), json.dumps(p.get("metadata", {}))),
        )
        preview = None
        if p.get("capture_preview", True):
            try:
                filename = f"element-{element_id}.png"
                browser.capture_selected(p, filename)
                preview = f"/screenshots/{filename}"
                db.execute("UPDATE elements SET preview_path=? WHERE id=?", (preview, element_id))
            except Exception:
                preview = None
        return ok(db.one("SELECT * FROM elements WHERE id=?", (element_id,)), 201)

    @app.get("/api/elements/export")
    def export_elements():
        elements = db.all("SELECT * FROM elements ORDER BY id")
        site_ids = {item["site_id"] for item in elements if item.get("site_id")}
        sites = [db.one("SELECT id,name,url FROM sites WHERE id=?", (site_id,)) for site_id in sorted(site_ids)]
        site_refs = {site["id"]: f"site-{index + 1}" for index, site in enumerate(sites) if site}
        element_refs = {item["id"]: f"element-{index + 1}" for index, item in enumerate(elements)}
        archive = {
            "format": "automat-elements", "version": 1,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "sites": [{"ref": site_refs[site["id"]], "name": site["name"], "url": site["url"]} for site in sites if site],
            "elements": [{
                "ref": element_refs[item["id"]], "site_ref": site_refs.get(item.get("site_id")),
                "name": item["name"], "strategy": item["strategy"], "locator": item["locator"],
                "alternatives": item.get("alternatives", []), "frame_path": item.get("frame_path", []),
                "metadata": item.get("metadata", {}), "parent_ref": element_refs.get(item.get("parent_id")),
                "preview": export_element_preview(item),
            } for item in elements],
        }
        response = app.response_class(json.dumps(archive, ensure_ascii=False, indent=2), mimetype="application/json")
        response.headers["Content-Disposition"] = 'attachment; filename="objekty.automat.json"'
        return response

    @app.post("/api/elements/import")
    def import_elements():
        archive = payload()
        if archive.get("format") != "automat-elements" or archive.get("version") != 1:
            raise ValueError("The file is not a supported Automat object backup")
        sites = archive.get("sites", [])
        elements = archive.get("elements", [])
        if not isinstance(sites, list) or not isinstance(elements, list) or len(sites) > 10000 or len(elements) > 10000:
            raise ValueError("The object backup has an invalid or too large structure")
        site_ref_values = [item.get("ref") for item in sites]
        element_ref_values = [item.get("ref") for item in elements]
        if any(not ref for ref in site_ref_values) or len(set(site_ref_values)) != len(site_ref_values):
            raise ValueError("The object backup contains invalid site references")
        if any(not ref for ref in element_ref_values) or len(set(element_ref_values)) != len(element_ref_values):
            raise ValueError("The object backup contains duplicate references")
        known_sites = set(site_ref_values)
        known_elements = set(element_ref_values)
        if any(item.get("site_ref") and item["site_ref"] not in known_sites for item in elements):
            raise ValueError("The backup references a missing site")
        if any(item.get("parent_ref") and item["parent_ref"] not in known_elements for item in elements):
            raise ValueError("The backup references a missing parent object")
        created_count = 0
        reused_count = 0
        with db.connect() as connection:
            site_refs = {}
            for item in sites:
                if not item.get("ref") or not str(item.get("url", "")).strip():
                    raise ValueError("The backup contains an invalid site")
                row = connection.execute("SELECT id FROM sites WHERE url=?", (item["url"],)).fetchone()
                site_refs[item["ref"]] = row["id"] if row else connection.execute(
                    "INSERT INTO sites(name,url) VALUES(?,?)", (item.get("name") or item["url"], item["url"]),
                ).lastrowid
            element_refs = {}
            created_refs = set()
            for item in elements:
                if not item.get("ref") or item.get("strategy") not in LOCATOR_STRATEGIES or not str(item.get("locator", "")).strip():
                    raise ValueError("The backup contains an invalid object")
                site_id = site_refs.get(item.get("site_ref"))
                row = connection.execute(
                    "SELECT id FROM elements WHERE site_id IS ? AND strategy=? AND locator=?",
                    (site_id, item["strategy"], item["locator"]),
                ).fetchone()
                if row:
                    element_id = row["id"]
                    reused_count += 1
                else:
                    element_id = connection.execute(
                        "INSERT INTO elements(site_id,name,strategy,locator,alternatives,frame_path,metadata) VALUES(?,?,?,?,?,?,?)",
                        (site_id, item.get("name") or "Imported object", item["strategy"], item["locator"],
                         json.dumps(item.get("alternatives", [])), json.dumps(item.get("frame_path", [])),
                         json.dumps(item.get("metadata", {}))),
                    ).lastrowid
                    created_refs.add(item["ref"])
                    created_count += 1
                element_refs[item["ref"]] = element_id
                import_element_preview(connection, item, element_id)
            for item in elements:
                if item.get("parent_ref") and item["ref"] in created_refs:
                    parent_id = element_refs.get(item["parent_ref"])
                    if not parent_id:
                        raise ValueError("The backup references a missing parent object")
                    connection.execute("UPDATE elements SET parent_id=? WHERE id=?", (parent_id, element_refs[item["ref"]]))
        return ok({"created": created_count, "reused": reused_count, "total": len(elements)}, 201)

    @app.put("/api/elements/<int:item_id>")
    def update_element(item_id):
        p = payload()
        if p.get("strategy") not in LOCATOR_STRATEGIES:
            raise ValueError("Invalid locator strategy")
        if not str(p.get("name", "")).strip() or not str(p.get("locator", "")).strip():
            raise ValueError("Name and locator are required")
        alternatives = normalize_element_alternatives(p["strategy"], p["locator"], p.get("alternatives", []))
        db.execute(
            "UPDATE elements SET site_id=?,name=?,strategy=?,locator=?,alternatives=?,parent_id=?,metadata=? WHERE id=?",
            (p.get("site_id"), p["name"], p["strategy"], p["locator"], json.dumps(alternatives), p.get("parent_id"), json.dumps(p.get("metadata", {})), item_id),
        )
        if p.get("capture_preview"):
            try:
                filename = f"element-{item_id}.png"
                browser.capture_selected(p, filename)
                db.execute("UPDATE elements SET preview_path=? WHERE id=?", (f"/screenshots/{filename}", item_id))
            except Exception:
                pass
        return ok(db.one("SELECT * FROM elements WHERE id=?", (item_id,)))

    @app.delete("/api/elements/<int:item_id>")
    def delete_element(item_id):
        db.execute("DELETE FROM elements WHERE id=?", (item_id,))
        return ok({"id": item_id})

    @app.get("/screenshots/<path:filename>")
    def screenshots(filename):
        return send_from_directory(browser.screenshot_dir, filename)

    @app.post("/api/sites")
    def create_site():
        p = payload()
        if not p.get("name") or not p.get("url"):
            raise ValueError("Name and URL are required")
        item_id = db.execute("INSERT INTO sites(name,url) VALUES(?,?)", (p["name"].strip(), p["url"].strip()))
        return ok(db.one("SELECT * FROM sites WHERE id=?", (item_id,)), 201)

    @app.delete("/api/sites/<int:item_id>")
    def delete_site(item_id):
        db.execute("DELETE FROM sites WHERE id=?", (item_id,))
        return ok({"id": item_id})

    @app.post("/api/credentials")
    def create_credential():
        p = payload()
        required = ("name", "username", "password", "username_element_id", "password_element_id")
        if any(p.get(key) in (None, "") for key in required):
            raise ValueError("Fill in the name, values, and both login objects")
        extra_actions = normalize_credential_actions(p.get("extra_actions", []))
        item_id = db.execute(
            "INSERT INTO credentials(site_id,name,username_element_id,password_element_id,submit_element_id,extra_actions,username_cipher,password_cipher) VALUES(?,?,?,?,?,?,?,?)",
            (p.get("site_id"), p["name"].strip(), p["username_element_id"], p["password_element_id"], p.get("submit_element_id"), json.dumps(extra_actions), vault.encrypt(p["username"]), vault.encrypt(p["password"])),
        )
        item = db.one(f"SELECT {credential_public_select()} FROM credentials WHERE id=?", (item_id,))
        return ok(item, 201)

    @app.put("/api/credentials/<int:item_id>")
    def update_credential(item_id):
        p = payload()
        if not db.one("SELECT id FROM credentials WHERE id=?", (item_id,)):
            raise ValueError("Login profile does not exist")
        required = ("name", "username_element_id", "password_element_id")
        if any(p.get(key) in (None, "") for key in required):
            raise ValueError("Fill in the name and both login objects")
        extra_actions = normalize_credential_actions(p.get("extra_actions", []))
        values = [
            p.get("site_id"), p["name"].strip(), p["username_element_id"],
            p["password_element_id"], p.get("submit_element_id"), json.dumps(extra_actions),
        ]
        assignments = "site_id=?,name=?,username_element_id=?,password_element_id=?,submit_element_id=?,extra_actions=?"
        if p.get("username"):
            assignments += ",username_cipher=?"
            values.append(vault.encrypt(p["username"]))
        if p.get("password"):
            assignments += ",password_cipher=?"
            values.append(vault.encrypt(p["password"]))
        values.append(item_id)
        db.execute(f"UPDATE credentials SET {assignments} WHERE id=?", values)
        return ok(db.one(
            f"SELECT {credential_public_select()} FROM credentials WHERE id=?",
            (item_id,),
        ))

    @app.delete("/api/credentials/<int:item_id>")
    def delete_credential(item_id):
        db.execute("DELETE FROM credentials WHERE id=?", (item_id,))
        return ok({"id": item_id})

    @app.post("/api/credentials/<int:item_id>/login")
    def login_credential(item_id):
        return ok(runner.login(item_id))

    @app.get("/api/credentials/export")
    def export_credentials():
        credentials = db.all("SELECT * FROM credentials ORDER BY id")
        element_ids = set()
        site_ids = set()
        for item in credentials:
            if item.get("site_id"):
                site_ids.add(item["site_id"])
            for key in ("username_element_id", "password_element_id", "submit_element_id"):
                if item.get(key):
                    element_ids.add(item[key])
            for action in item.get("extra_actions", []):
                if action.get("element_id"):
                    element_ids.add(action["element_id"])
        elements = []
        pending = list(element_ids)
        while pending:
            element_id = pending.pop()
            if any(item["id"] == element_id for item in elements):
                continue
            element = db.one("SELECT * FROM elements WHERE id=?", (element_id,))
            if not element:
                continue
            elements.append(element)
            if element.get("site_id"):
                site_ids.add(element["site_id"])
            if element.get("parent_id"):
                pending.append(element["parent_id"])
        sites = [db.one("SELECT id,name,url FROM sites WHERE id=?", (site_id,)) for site_id in sorted(site_ids)]
        sites = [site for site in sites if site]
        site_refs = {site["id"]: f"site-{index + 1}" for index, site in enumerate(sites)}
        element_refs = {item["id"]: f"element-{index + 1}" for index, item in enumerate(elements)}
        archive = {
            "format": "automat-credentials", "version": 1,
            "exported_at": datetime.now(timezone.utc).isoformat(),
            "warning": "Soubor obsahuje prihlasovaci jmena a password v citelne podobe. Uchovejte ho bezpecne.",
            "sites": [{"ref": site_refs[site["id"]], "name": site["name"], "url": site["url"]} for site in sites],
            "elements": [{
                "ref": element_refs[item["id"]], "site_ref": site_refs.get(item.get("site_id")),
                "name": item["name"], "strategy": item["strategy"], "locator": item["locator"],
                "alternatives": item.get("alternatives", []), "frame_path": item.get("frame_path", []),
                "metadata": item.get("metadata", {}), "parent_ref": element_refs.get(item.get("parent_id")),
            } for item in elements],
            "credentials": [{
                "name": item["name"], "site_ref": site_refs.get(item.get("site_id")),
                "username_element_ref": element_refs.get(item.get("username_element_id")),
                "password_element_ref": element_refs.get(item.get("password_element_id")),
                "submit_element_ref": element_refs.get(item.get("submit_element_id")),
                "extra_actions": [{
                    **{key: value for key, value in action.items() if key != "element_id"},
                    "element_ref": element_refs.get(action.get("element_id")) if action.get("element_id") else None,
                } for action in item.get("extra_actions", [])],
                "username": vault.decrypt(item["username_cipher"]),
                "password": vault.decrypt(item["password_cipher"]),
            } for item in credentials],
        }
        response = app.response_class(json.dumps(archive, ensure_ascii=False, indent=2), mimetype="application/json")
        response.headers["Content-Disposition"] = 'attachment; filename="prihlasovaci-profily.automat.json"'
        return response

    @app.post("/api/credentials/import")
    def import_credentials():
        archive = payload()
        if archive.get("format") != "automat-credentials" or archive.get("version") != 1:
            raise ValueError("This file is not a supported Automat login profile backup")
        sites = archive.get("sites", [])
        elements = archive.get("elements", [])
        credentials = archive.get("credentials", [])
        if (
            not isinstance(sites, list) or not isinstance(elements, list) or not isinstance(credentials, list)
            or len(sites) > 10000 or len(elements) > 10000 or len(credentials) > 10000
        ):
            raise ValueError("The login profile backup has an invalid or too large structure")
        site_ref_values = [item.get("ref") for item in sites]
        element_ref_values = [item.get("ref") for item in elements]
        if any(not ref for ref in site_ref_values) or len(set(site_ref_values)) != len(site_ref_values):
            raise ValueError("The backup contains invalid site references")
        if any(not ref for ref in element_ref_values) or len(set(element_ref_values)) != len(element_ref_values):
            raise ValueError("The backup contains invalid object references")
        known_sites = set(site_ref_values)
        known_elements = set(element_ref_values)
        if any(item.get("site_ref") and item["site_ref"] not in known_sites for item in elements):
            raise ValueError("The backup references a missing site")
        if any(item.get("parent_ref") and item["parent_ref"] not in known_elements for item in elements):
            raise ValueError("The backup references a missing parent object")
        for item in credentials:
            refs = [item.get("username_element_ref"), item.get("password_element_ref")]
            if item.get("submit_element_ref"):
                refs.append(item.get("submit_element_ref"))
            for action in item.get("extra_actions", []) or []:
                if not isinstance(action, dict) or action.get("action_type") not in CREDENTIAL_ACTION_TYPES:
                    raise ValueError("The backup contains an invalid extra login action")
                if action.get("action_type") != "wait":
                    refs.append(action.get("element_ref"))
            if item.get("site_ref") and item["site_ref"] not in known_sites:
                raise ValueError("The profile backup references a missing site")
            if any(not ref or ref not in known_elements for ref in refs):
                raise ValueError("The profile backup references a missing object")
            if not str(item.get("name", "")).strip() or item.get("username") is None or item.get("password") is None:
                raise ValueError("The backup contains an invalid login profile")
        created_count = 0
        updated_count = 0
        reused_elements = 0
        created_elements = 0
        with db.connect() as connection:
            site_refs = {}
            for item in sites:
                if not str(item.get("url", "")).strip():
                    raise ValueError("The backup contains an invalid site")
                row = connection.execute("SELECT id FROM sites WHERE url=?", (item["url"],)).fetchone()
                site_refs[item["ref"]] = row["id"] if row else connection.execute(
                    "INSERT INTO sites(name,url) VALUES(?,?)", (item.get("name") or item["url"], item["url"]),
                ).lastrowid
            element_refs = {}
            created_refs = set()
            for item in elements:
                if item.get("strategy") not in LOCATOR_STRATEGIES or not str(item.get("locator", "")).strip():
                    raise ValueError("The backup contains an invalid object")
                site_id = site_refs.get(item.get("site_ref"))
                row = connection.execute(
                    "SELECT id FROM elements WHERE site_id IS ? AND strategy=? AND locator=?",
                    (site_id, item["strategy"], item["locator"]),
                ).fetchone()
                if row:
                    element_id = row["id"]
                    reused_elements += 1
                else:
                    element_id = connection.execute(
                        "INSERT INTO elements(site_id,name,strategy,locator,alternatives,frame_path,metadata) VALUES(?,?,?,?,?,?,?)",
                        (site_id, item.get("name") or "Imported object", item["strategy"], item["locator"],
                         json.dumps(item.get("alternatives", [])), json.dumps(item.get("frame_path", [])),
                         json.dumps(item.get("metadata", {}))),
                    ).lastrowid
                    created_refs.add(item["ref"])
                    created_elements += 1
                element_refs[item["ref"]] = element_id
            for item in elements:
                if item.get("parent_ref") and item["ref"] in created_refs:
                    connection.execute("UPDATE elements SET parent_id=? WHERE id=?", (element_refs[item["parent_ref"]], element_refs[item["ref"]]))
            for item in credentials:
                extra_actions = []
                for action in item.get("extra_actions", []) or []:
                    action_type = action.get("action_type") or "click"
                    normalized = {"action_type": action_type}
                    if action_type == "wait":
                        normalized["seconds"] = max(0, float(action.get("seconds") or 1))
                    else:
                        normalized["element_id"] = element_refs[action["element_ref"]]
                        if action_type in {"type", "key"}:
                            normalized["value"] = str(action.get("value") or "")
                    extra_actions.append(normalized)
                values = (
                    site_refs.get(item.get("site_ref")),
                    item["name"].strip(),
                    element_refs[item["username_element_ref"]],
                    element_refs[item["password_element_ref"]],
                    element_refs.get(item.get("submit_element_ref")),
                    json.dumps(extra_actions),
                    vault.encrypt(item["username"]),
                    vault.encrypt(item["password"]),
                )
                row = connection.execute("SELECT id FROM credentials WHERE name=?", (item["name"].strip(),)).fetchone()
                if row:
                    connection.execute(
                        "UPDATE credentials SET site_id=?,name=?,username_element_id=?,password_element_id=?,submit_element_id=?,extra_actions=?,username_cipher=?,password_cipher=? WHERE id=?",
                        values + (row["id"],),
                    )
                    updated_count += 1
                else:
                    connection.execute(
                        "INSERT INTO credentials(site_id,name,username_element_id,password_element_id,submit_element_id,extra_actions,username_cipher,password_cipher) VALUES(?,?,?,?,?,?,?,?)",
                        values,
                    )
                    created_count += 1
        return ok({
            "created": created_count, "updated": updated_count, "total": len(credentials),
            "created_elements": created_elements, "reused_elements": reused_elements,
        }, 201)

    @app.post("/api/workflows")
    def create_workflow():
        p = payload()
        if not p.get("name"):
            raise ValueError("Workflow name is required")
        item_id = db.execute("INSERT INTO workflows(site_id,name,description) VALUES(?,?,?)", (p.get("site_id"), p["name"].strip(), p.get("description", "")))
        return ok(db.one("SELECT * FROM workflows WHERE id=?", (item_id,)), 201)

    @app.get("/api/workflows/<int:item_id>")
    def get_workflow(item_id):
        workflow = db.one("SELECT * FROM workflows WHERE id=?", (item_id,))
        if not workflow:
            raise ValueError("Workflow does not exist")
        workflow["actions"] = db.all("SELECT * FROM actions WHERE workflow_id=? ORDER BY position,id", (item_id,))
        return ok(workflow)

    @app.get("/api/workflows/<int:item_id>/export")
    def export_workflow(item_id):
        workflow = db.one("SELECT * FROM workflows WHERE id=?", (item_id,))
        if not workflow:
            raise ValueError("Workflow does not exist")
        actions = db.all("SELECT * FROM actions WHERE workflow_id=? ORDER BY position,id", (item_id,))
        site = db.one("SELECT name,url FROM sites WHERE id=?", (workflow.get("site_id"),)) if workflow.get("site_id") else None
        element_ids = set()
        for action in actions:
            if action.get("element_id"):
                element_ids.add(action["element_id"])
            for key, value in action.get("parameters", {}).items():
                if key.endswith("element_id") and value:
                    element_ids.add(int(value))
        elements = []
        pending = list(element_ids)
        while pending:
            element_id = pending.pop()
            if any(item["id"] == element_id for item in elements):
                continue
            element = db.one("SELECT * FROM elements WHERE id=?", (element_id,))
            if not element:
                continue
            elements.append(element)
            if element.get("parent_id"):
                pending.append(element["parent_id"])
        refs = {element["id"]: f"element-{index + 1}" for index, element in enumerate(elements)}
        exported_elements = [{
            "ref": refs[element["id"]], "name": element["name"], "strategy": element["strategy"],
            "locator": element["locator"], "alternatives": element.get("alternatives", []),
            "frame_path": element.get("frame_path", []), "metadata": element.get("metadata", {}),
            "parent_ref": refs.get(element.get("parent_id")),
        } for element in elements]
        exported_actions = []
        for action in actions:
            parameters = dict(action.get("parameters", {}))
            for key in list(parameters):
                if key.endswith("element_id"):
                    parameters[key.removesuffix("_id") + "_ref"] = refs.get(int(parameters.pop(key)))
            if "credential_id" in parameters:
                credential = db.one("SELECT name FROM credentials WHERE id=?", (parameters.pop("credential_id"),))
                parameters["credential_ref"] = credential["name"] if credential else None
            exported_actions.append({
                "action_type": action["action_type"], "element_ref": refs.get(action.get("element_id")),
                "parameters": parameters, "enabled": action["enabled"],
            })
        archive = {
            "format": "automat-workflow", "version": 1, "exported_at": datetime.now(timezone.utc).isoformat(),
            "workflow": {"name": workflow["name"], "description": workflow["description"]},
            "site": site, "elements": exported_elements, "actions": exported_actions,
        }
        filename = re.sub(r"[^A-Za-z0-9._-]+", "-", workflow["name"]).strip("-") or "workflow"
        response = app.response_class(json.dumps(archive, ensure_ascii=False, indent=2), mimetype="application/json")
        response.headers["Content-Disposition"] = f'attachment; filename="{filename}.automat.json"'
        return response

    @app.post("/api/workflows/import")
    def import_workflow():
        archive = payload()
        if archive.get("format") != "automat-workflow" or archive.get("version") != 1:
            raise ValueError("The file is not a supported Automat backup")
        elements = archive.get("elements", [])
        actions = archive.get("actions", [])
        if not isinstance(elements, list) or not isinstance(actions, list) or len(elements) > 10000 or len(actions) > 10000:
            raise ValueError("The backup has an invalid or too large structure")
        workflow_data = archive.get("workflow") or {}
        if not str(workflow_data.get("name", "")).strip():
            raise ValueError("The backup does not contain a workflow name")
        warnings = []
        with db.connect() as connection:
            site_id = None
            site_data = archive.get("site")
            if site_data and site_data.get("url"):
                row = connection.execute("SELECT id FROM sites WHERE url=?", (site_data["url"],)).fetchone()
                site_id = row["id"] if row else connection.execute("INSERT INTO sites(name,url) VALUES(?,?)", (site_data.get("name") or site_data["url"], site_data["url"])).lastrowid
            name = workflow_data["name"].strip()
            if connection.execute("SELECT 1 FROM workflows WHERE name=?", (name,)).fetchone():
                name += " (import)"
            workflow_id = connection.execute("INSERT INTO workflows(site_id,name,description) VALUES(?,?,?)", (site_id, name, workflow_data.get("description", ""))).lastrowid
            refs = {}
            created = {}
            for item in elements:
                if item.get("strategy") not in LOCATOR_STRATEGIES or not item.get("ref") or not item.get("locator"):
                    raise ValueError("The backup contains an invalid object")
                row = connection.execute("SELECT id FROM elements WHERE site_id IS ? AND strategy=? AND locator=?", (site_id, item["strategy"], item["locator"])).fetchone()
                if row:
                    element_id = row["id"]
                else:
                    element_id = connection.execute(
                        "INSERT INTO elements(site_id,name,strategy,locator,alternatives,frame_path,metadata) VALUES(?,?,?,?,?,?,?)",
                        (site_id, item.get("name") or "Imported object", item["strategy"], item["locator"], json.dumps(item.get("alternatives", [])), json.dumps(item.get("frame_path", [])), json.dumps(item.get("metadata", {}))),
                    ).lastrowid
                    created[item["ref"]] = element_id
                refs[item["ref"]] = element_id
            for item in elements:
                if item.get("parent_ref") and item["ref"] in created:
                    connection.execute("UPDATE elements SET parent_id=? WHERE id=?", (refs.get(item["parent_ref"]), created[item["ref"]]))
            for position, action in enumerate(actions, 1):
                if action.get("action_type") not in ACTION_TYPES:
                    warnings.append(f"Unknown action {action.get('action_type')} was skipped")
                    continue
                parameters = dict(action.get("parameters") or {})
                for key in list(parameters):
                    if key.endswith("element_ref"):
                        parameters[key.removesuffix("_ref") + "_id"] = refs.get(parameters.pop(key))
                enabled = bool(action.get("enabled", True))
                credential_ref = parameters.pop("credential_ref", None)
                if credential_ref is not None:
                    row = connection.execute("SELECT id FROM credentials WHERE name=?", (credential_ref,)).fetchone()
                    if row:
                        parameters["credential_id"] = row["id"]
                    else:
                        enabled = False
                        warnings.append(f"Auto-login action was disabled: missing profile „{credential_ref}“")
                element_id = refs.get(action.get("element_ref"))
                if action.get("element_ref") and not element_id:
                    enabled = False
                    warnings.append(f"Action {position} was disabled: its object is missing")
                connection.execute(
                    "INSERT INTO actions(workflow_id,position,action_type,element_id,parameters,enabled) VALUES(?,?,?,?,?,?)",
                    (workflow_id, position, action["action_type"], element_id, json.dumps(parameters), int(enabled)),
                )
        return ok({"workflow": db.one("SELECT * FROM workflows WHERE id=?", (workflow_id,)), "warnings": warnings}, 201)

    @app.delete("/api/workflows/<int:item_id>")
    def delete_workflow(item_id):
        db.execute("DELETE FROM workflows WHERE id=?", (item_id,))
        return ok({"id": item_id})

    @app.post("/api/workflows/<int:item_id>/actions")
    def create_action(item_id):
        p = payload()
        if p.get("action_type") not in ACTION_TYPES:
            raise ValueError("Invalid action type")
        next_position = db.one("SELECT COALESCE(MAX(position),0)+1 AS value FROM actions WHERE workflow_id=?", (item_id,))["value"]
        action_id = db.execute("INSERT INTO actions(workflow_id,position,action_type,element_id,parameters) VALUES(?,?,?,?,?)", (item_id, next_position, p["action_type"], p.get("element_id"), json.dumps(p.get("parameters", {}))))
        return ok(db.one("SELECT * FROM actions WHERE id=?", (action_id,)), 201)

    @app.put("/api/workflows/<int:item_id>/actions")
    def replace_actions(item_id):
        actions = payload().get("actions", [])
        with db.connect() as connection:
            connection.execute("DELETE FROM actions WHERE workflow_id=?", (item_id,))
            for position, action in enumerate(actions, 1):
                if action.get("action_type") not in ACTION_TYPES:
                    raise ValueError("Invalid action type")
                connection.execute("INSERT INTO actions(workflow_id,position,action_type,element_id,parameters,enabled) VALUES(?,?,?,?,?,?)", (item_id, position, action["action_type"], action.get("element_id"), json.dumps(action.get("parameters", {})), int(action.get("enabled", True))))
        return get_workflow(item_id)

    @app.post("/api/runner/start/<int:workflow_id>")
    def runner_start(workflow_id): return ok(runner.start(workflow_id, payload().get("repeat_count", 1)))

    @app.post("/api/runner/pause")
    def runner_pause(): return ok(runner.pause())

    @app.post("/api/runner/resume")
    def runner_resume(): return ok(runner.resume())

    @app.post("/api/runner/stop")
    def runner_stop(): return ok(runner.stop())

    @app.get("/api/runner/status")
    def runner_status(): return ok(runner.snapshot())

    autorun_lock = threading.Lock()

    def configured_credential_element_ids(profile):
        element_ids = [
            profile.get("username_element_id"),
            profile.get("password_element_id"),
            profile.get("submit_element_id"),
        ]
        element_ids.extend(action.get("element_id") for action in profile.get("extra_actions", []) if action.get("element_id"))
        return [element_id for element_id in element_ids if element_id]

    def element_is_present(element_id):
        item = db.one("SELECT * FROM elements WHERE id=?", (element_id,))
        if not item:
            return False
        try:
            with browser.lock:
                browser.find(item["strategy"], item["locator"], item.get("alternatives"))
            return True
        except Exception:
            return False

    def credential_is_present(profile):
        return any(element_is_present(element_id) for element_id in configured_credential_element_ids(profile))

    def autorun_credentials_for_site(site_id):
        profiles = db.all("SELECT * FROM credentials ORDER BY id DESC")
        matching = [item for item in profiles if item.get("site_id") == site_id]
        fallback = [item for item in profiles if item.get("site_id") != site_id]
        return matching + fallback

    def stop_running_workflow_for_autorun():
        thread = runner.thread
        if not thread or not thread.is_alive():
            return True
        runner.stop()
        thread.join(timeout=5)
        return not (runner.thread and runner.thread.is_alive())

    def run_autorun(reason):
        if not get_setting("autorun", False):
            return
        if not autorun_lock.acquire(blocking=False):
            return
        try:
            if runner.thread and runner.thread.is_alive():
                if reason != "browser_closed" or not stop_running_workflow_for_autorun():
                    return
            site = db.one("SELECT * FROM sites ORDER BY updated_at DESC, id LIMIT 1")
            workflow = db.one("SELECT * FROM workflows ORDER BY updated_at DESC, id LIMIT 1")
            if not site or not workflow:
                runner._log("warning", "Autorun: saved site or workflow is missing")
                return
            browser.start("chrome", site["url"])
            time.sleep(1)
            for profile in autorun_credentials_for_site(site["id"]):
                if credential_is_present(profile):
                    runner._log("info", f"Autorun: logging in profile {profile['name']}")
                    runner._auto_login(profile["id"])
                    time.sleep(1)
                    break
            runner._log("info", "Autorun: starting the first workflow in an infinite loop")
            runner.start(workflow["id"], 0)
        except Exception as exc:
            runner._log("error", f"Autorun failed: {type(exc).__name__}: {exc}")
        finally:
            autorun_lock.release()

    def autorun_monitor():
        time.sleep(1.5)
        if get_setting("autorun", False):
            run_autorun("startup")
        last_running = browser.status()["running"]
        while True:
            time.sleep(3)
            if not get_setting("autorun", False):
                last_running = browser.status()["running"]
                continue
            status = browser.status()
            if last_running and not status["running"]:
                run_autorun("browser_closed")
                status = browser.status()
            last_running = status["running"]

    if not app.config["TESTING"]:
        atexit.register(browser.quit)
    if not app.config["TESTING"] and app.config.get("ENABLE_AUTORUN_MONITOR"):
        threading.Thread(target=autorun_monitor, daemon=True).start()
    return app


CREDENTIAL_ACTION_TYPES = {"click", "double_click", "hover", "focus", "type", "key", "wait"}


ACTION_TYPES = {
    "auto_login": "Auto login", "repeat_click": "Continuous clicking",
    "repeat_until": "Act until object appears",
    "click": "Click", "double_click": "Double click", "context_click": "Right click",
    "hover": "Hover", "focus": "Focus", "type": "Type text", "clear": "Clear",
    "submit": "Submit form", "select": "Select from dropdown", "key": "Press key",
    "scroll_to": "Scroll to element", "scroll_by": "Scroll page", "mouse_move": "Move mouse",
    "drag_to": "Drag to", "wait": "Wait", "wait_random": "Wait randomly", "wait_for": "Wait for element state",
    "navigate": "Go to URL", "back": "Back", "forward": "Forward", "refresh": "Refresh",
    "switch_frame": "Switch to iframe", "default_content": "Main document", "switch_window": "Switch window",
    "new_tab": "New tab", "close_tab": "Close tab", "alert_accept": "Accept dialog",
    "alert_dismiss": "Dismiss dialog", "upload": "Upload file", "screenshot": "Element screenshot",
    "script": "Run JavaScript", "cookie_set": "Set cookie",
}
