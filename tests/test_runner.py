import threading
import time

import automat.runner as runner_module
from automat.runner import WorkflowRunner
from selenium.common.exceptions import NoSuchElementException, TimeoutException


class FakeBrowser:
    def __init__(self):
        self.lock = threading.RLock()


class LoopDatabase:
    def all(self, sql, values=()):
        return [{"id": 1, "action_type": "click", "element_id": 7, "parameters": {}, "enabled": True}]

    def one(self, sql, values=()):
        return {"value": 1}


class LoginBrowser(FakeBrowser):
    def __init__(self):
        super().__init__()
        self.urls = []

    def navigate(self, url):
        self.urls.append(url)
        return self.status()

    def status(self):
        return {"running": True, "browser": "Brave", "url": self.urls[-1] if self.urls else "", "title": "Login"}


class LoginDatabase:
    def one(self, sql, values=()):
        return {"id": values[0], "site_url": "https://example.com/login"}


class SkipDatabase:
    def all(self, sql, values=()):
        return [
            {"id": 1, "action_type": "click", "element_id": 7, "parameters": {}, "enabled": True},
            {"id": 2, "action_type": "wait", "element_id": None, "parameters": {}, "enabled": True},
        ]


class FakeElement:
    def __init__(self, tag="div", attributes=None, children=None, displayed=True, enabled=True):
        self.tag_name = tag
        self.attributes = attributes or {}
        self.children = children or []
        self.displayed = displayed
        self.enabled = enabled

    def get_attribute(self, name):
        return self.attributes.get(name)

    def find_elements(self, by, selector):
        return self.children

    def is_displayed(self):
        return self.displayed

    def is_enabled(self):
        return self.enabled

    def click(self):
        self.attributes["clicked"] = True


class LinkedFieldDriver:
    def __init__(self, fields):
        self.fields = fields

    def find_element(self, by, value):
        return self.fields[value]

    def execute_script(self, script, element):
        return None


def make_runner():
    runner = WorkflowRunner(FakeBrowser(), None, None)
    runner.pause_event.set()
    return runner


def test_repeat_click_respects_frequency_and_duration(monkeypatch):
    runner = make_runner()
    operations = []
    times = iter([0.0, 0.0, 2.0])
    monkeypatch.setattr(runner_module.time, "monotonic", lambda: next(times))
    runner._perform_operation = lambda element_id, operation, value="": operations.append((element_id, operation))
    runner._sleep = lambda seconds: None
    runner._repeat_click({"id": 1, "element_id": 7, "parameters": {"clicks_per_second": 2, "duration_seconds": 1}})
    assert operations == [(7, "click")]


def test_repeat_until_uses_object_one_until_object_two_appears():
    runner = make_runner()
    visibility = iter([False, False, True])
    operations = []
    runner._is_visible = lambda element_id: next(visibility)
    runner._perform_operation = lambda element_id, operation, value="": operations.append((element_id, operation))
    runner._sleep = lambda seconds: None
    runner._repeat_until({"id": 2, "element_id": 10, "parameters": {"target_element_id": 20, "operation": "click", "interval_seconds": 0.1}})
    assert operations == [(10, "click"), (10, "click")]


def test_repeat_until_same_object_waits_then_runs_once():
    runner = make_runner()
    runner._is_visible = lambda element_id: True
    operations = []
    runner._perform_operation = lambda element_id, operation, value="": operations.append((element_id, operation))
    runner._repeat_until({"id": 3, "element_id": 10, "parameters": {"target_element_id": 10, "operation": "double_click"}})
    assert operations == [(10, "double_click")]


def test_workflow_repeats_requested_number_of_cycles():
    runner = WorkflowRunner(FakeBrowser(), LoopDatabase(), None)
    runner.pause_event.set()
    runner.repeat_count = 3
    executed = []
    runner._execute = lambda action: executed.append(action["id"])

    runner._run(5)

    assert executed == [1, 1, 1]
    assert runner.state["cycle"] == 3
    assert runner.state["status"] == "completed"


def test_missing_element_skips_action_and_continues_workflow():
    runner = WorkflowRunner(FakeBrowser(), SkipDatabase(), None)
    runner.pause_event.set()
    runner.repeat_count = 1
    executed = []

    def execute(action):
        if action["id"] == 1:
            raise NoSuchElementException("nenalezen testovací element")
        executed.append(action["id"])

    runner._execute = execute
    runner._run(5)

    assert executed == [2]
    assert runner.state["status"] == "completed"
    assert any("skipped" in log["message"] for log in runner.state["logs"])


def test_infinite_loop_survives_arbitrary_action_errors_until_stop():
    runner = WorkflowRunner(FakeBrowser(), LoopDatabase(), None)
    runner.pause_event.set()
    runner.repeat_count = 0
    calls = []

    def execute(action):
        calls.append(action["id"])
        if len(calls) == 3:
            runner.stop_event.set()
        raise RuntimeError("testovací chyba akce")

    def interruptible_sleep(seconds):
        if runner.stop_event.is_set():
            raise InterruptedError

    runner._execute = execute
    runner._sleep = interruptible_sleep
    runner._run(5)

    assert calls == [1, 1, 1]
    assert runner.state["errors"] == 3
    assert runner.state["status"] == "stopped"
    assert not any(runner.state["status"] == value for value in ("failed", "completed"))


def test_infinite_loop_survives_missing_elements_until_stop():
    runner = WorkflowRunner(FakeBrowser(), LoopDatabase(), None)
    runner.pause_event.set()
    runner.repeat_count = 0
    calls = 0

    def execute(action):
        nonlocal calls
        calls += 1
        if calls == 3:
            runner.stop_event.set()
        raise NoSuchElementException("element nenalezen")

    def interruptible_sleep(seconds):
        if runner.stop_event.is_set():
            raise InterruptedError

    runner._execute = execute
    runner._sleep = interruptible_sleep
    runner._run(5)

    assert calls == 3
    assert runner.state["skipped"] == 3
    assert runner.state["status"] == "stopped"


def test_finite_loop_still_fails_on_non_element_error():
    runner = WorkflowRunner(FakeBrowser(), LoopDatabase(), None)
    runner.pause_event.set()
    runner.repeat_count = 2
    runner._execute = lambda action: (_ for _ in ()).throw(ValueError("neplatná akce"))

    runner._run(5)

    assert runner.state["status"] == "failed"


def test_infinite_runner_log_is_bounded():
    runner = make_runner()

    for index in range(1500):
        runner._log("info", f"záznam {index}")

    assert len(runner.state["logs"]) <= 1000
    assert runner.state["logs"][-1]["message"] == "záznam 1499"


def test_wait_and_random_wait_enable_countdown(monkeypatch):
    runner = make_runner()
    calls = []
    runner._sleep = lambda seconds, countdown=False: calls.append((seconds, countdown))
    monkeypatch.setattr(runner_module.random, "uniform", lambda minimum, maximum: 2.7)

    runner._execute({"action_type": "wait", "parameters": {"seconds": 3}})
    runner._execute({"action_type": "wait_random", "parameters": {"min": 1, "max": 4}})

    assert calls == [(3.0, True), (2.7, True)]


def test_countdown_descends_and_is_cleared(monkeypatch):
    runner = make_runner()
    updates = []
    original_set_countdown = runner._set_countdown

    def capture(total=None, remaining=None):
        updates.append((total, remaining))
        original_set_countdown(total, remaining)

    runner._set_countdown = capture
    monkeypatch.setattr(runner_module.time, "sleep", lambda seconds: None)
    runner._sleep(0.25, countdown=True)

    numeric = [remaining for total, remaining in updates if total is not None]
    assert numeric[0] == 0.25
    assert numeric[-1] == 0
    assert all(left >= right for left, right in zip(numeric, numeric[1:]))
    assert updates[-1] == (None, None)
    assert runner.state["countdown"] is None


def test_wait_for_element_state_zero_timeout_waits_until_condition(monkeypatch):
    runner = make_runner()
    attempts = iter([False, False, FakeElement(displayed=True)])
    sleeps = []
    times = iter([0, 1, 2])
    monkeypatch.setattr(runner_module.time, "sleep", lambda seconds: sleeps.append(seconds))
    monkeypatch.setattr(runner_module.time, "monotonic", lambda: next(times, 2))
    runner._wait_for_element = lambda _item, _condition: next(attempts)

    result = runner._wait_for_element_state({"id": 1}, "visible", 0)

    assert result.is_displayed()
    assert sleeps == [0.2, 0.2]


def test_wait_for_element_state_positive_timeout_expires(monkeypatch):
    runner = make_runner()
    times = iter([0, 0.3, 0.6])
    monkeypatch.setattr(runner_module.time, "sleep", lambda _seconds: None)
    monkeypatch.setattr(runner_module.time, "monotonic", lambda: next(times, 0.6))
    runner._wait_for_element = lambda _item, _condition: False

    try:
        runner._wait_for_element_state({"id": 1}, "visible", 0.5)
        raise AssertionError("TimeoutException was not raised")
    except TimeoutException:
        pass


def test_pause_freezes_countdown():
    runner = make_runner()
    worker = threading.Thread(target=runner._sleep, args=(0.5, True))
    worker.start()
    deadline = time.time() + 1
    while runner.state["countdown"] is None and time.time() < deadline:
        time.sleep(0.01)
    runner.pause_event.clear()
    time.sleep(0.15)
    paused_remaining = runner.state["countdown"]["remaining"]
    time.sleep(0.25)
    still_paused_remaining = runner.state["countdown"]["remaining"]
    runner.pause_event.set()
    worker.join(timeout=2)

    assert abs(paused_remaining - still_paused_remaining) <= 0.1
    assert not worker.is_alive()
    assert runner.state["countdown"] is None


def test_direct_login_opens_assigned_site_and_fills_profile():
    browser = LoginBrowser()
    runner = WorkflowRunner(browser, LoginDatabase(), None)
    used_profiles = []
    runner._auto_login = lambda credential_id: used_profiles.append(credential_id)

    result = runner.login(9)

    assert browser.urls == ["https://example.com/login"]
    assert used_profiles == [9]
    assert result["credential_id"] == 9
    assert "password" not in result


def test_login_field_can_be_found_inside_saved_wrapper():
    input_element = FakeElement("input", {"type": "text"})
    wrapper = FakeElement("div", children=[input_element])

    assert WorkflowRunner._editable_from(wrapper) is input_element


def test_login_field_follows_label_for_attribute():
    input_element = FakeElement("input", {"type": "email"})
    label = FakeElement("label", {"for": "loginUsername"})
    driver = LinkedFieldDriver({"loginUsername": input_element})

    assert WorkflowRunner._editable_from(label, driver) is input_element


def test_login_field_rejects_hidden_readonly_and_disabled_inputs():
    hidden = FakeElement("input", {"type": "hidden"})
    readonly = FakeElement("input", {"readonly": "true"})
    disabled = FakeElement("input", enabled=False)

    assert WorkflowRunner._editable_from(hidden) is None
    assert WorkflowRunner._editable_from(readonly) is None
    assert WorkflowRunner._editable_from(disabled) is None


def test_login_field_is_clicked_before_typing():
    class FocusDriver:
        def execute_script(self, script, element):
            return bool(element.attributes.get("clicked")) if script.startswith("return") else None

    class FocusBrowser(FakeBrowser):
        def require(self):
            return FocusDriver()

    runner = WorkflowRunner(FocusBrowser(), None, None)
    field = FakeElement("input")

    runner._activate_login_field(field)

    assert field.attributes["clicked"] is True


def test_login_delay_is_at_least_one_second(monkeypatch):
    runner = WorkflowRunner(FakeBrowser(), None, None)
    delays = []
    monkeypatch.setattr(runner_module.time, "sleep", lambda seconds: delays.append(seconds))

    runner._login_delay(0.1)

    assert delays == [1.0]


def test_hover_point_uses_visible_part_of_partially_clipped_element():
    point = WorkflowRunner._visible_center({
        "x": -100, "y": 20, "width": 300, "height": 40,
        "viewportWidth": 1200, "viewportHeight": 800,
    })
    assert point == (100, 40)


def test_hover_point_rejects_element_outside_viewport():
    import pytest

    with pytest.raises(ValueError, match="visible part"):
        WorkflowRunner._visible_center({
            "x": 1300, "y": 20, "width": 100, "height": 40,
            "viewportWidth": 1200, "viewportHeight": 800,
        })
