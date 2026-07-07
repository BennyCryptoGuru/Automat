import random
import threading
import time
import traceback

from selenium.common.exceptions import InvalidElementStateException, MoveTargetOutOfBoundsException, NoSuchElementException, TimeoutException, WebDriverException
from selenium.webdriver import ActionChains, Keys
from selenium.webdriver.common.by import By
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import Select, WebDriverWait

from .browser import BY_MAP


KEYS = {name.lower(): value for name, value in vars(Keys).items() if name.isupper()}


class WorkflowRunner:
    def __init__(self, browser, db, vault):
        self.browser = browser
        self.db = db
        self.vault = vault
        self.thread = None
        self.pause_event = threading.Event()
        self.stop_event = threading.Event()
        self.lock = threading.RLock()
        self.repeat_count = 1
        self.state = self._empty_state()

    @staticmethod
    def _empty_state():
        return {"status": "idle", "workflow_id": None, "current": None, "countdown": None, "message": "Připraveno", "errors": 0, "skipped": 0, "logs": []}

    def start(self, workflow_id, repeat_count=1):
        with self.lock:
            if self.thread and self.thread.is_alive():
                raise RuntimeError("Jiné workflow právě běží")
            try:
                repeat_count = int(repeat_count)
            except (TypeError, ValueError) as exc:
                raise ValueError("Počet cyklů musí být celé číslo") from exc
            if repeat_count < 0:
                raise ValueError("Počet cyklů nesmí být záporný")
            action_count = self.db.one("SELECT COUNT(*) AS value FROM actions WHERE workflow_id=? AND enabled=1", (workflow_id,))
            if not action_count or not action_count["value"]:
                raise ValueError("Workflow neobsahuje žádné aktivní akce")
            self.repeat_count = repeat_count
            self.pause_event.set()
            self.stop_event.clear()
            self.state = {"status": "running", "workflow_id": workflow_id, "current": None, "countdown": None, "cycle": 0, "repeat_count": repeat_count, "message": "Spouštím", "errors": 0, "skipped": 0, "logs": []}
            self.thread = threading.Thread(target=self._run, args=(workflow_id,), daemon=True)
            self.thread.start()
            return self.snapshot()

    def pause(self):
        if self.state["status"] == "running":
            self.pause_event.clear()
            self.state["status"] = "paused"
            self.state["message"] = "Pozastaveno"
        return self.snapshot()

    def resume(self):
        if self.state["status"] == "paused":
            self.state["status"] = "running"
            self.state["message"] = "Pokračuji"
            self.pause_event.set()
        return self.snapshot()

    def stop(self):
        self.stop_event.set()
        self.pause_event.set()
        self.state["message"] = "Zastavuji"
        return self.snapshot()

    def login(self, credential_id):
        with self.lock:
            if self.thread and self.thread.is_alive():
                raise RuntimeError("Přímé přihlášení nelze spustit během běžícího workflow")
        profile = self.db.one(
            "SELECT c.id, s.url AS site_url FROM credentials c LEFT JOIN sites s ON s.id=c.site_id WHERE c.id=?",
            (credential_id,),
        )
        if not profile:
            raise ValueError("Přihlašovací profil neexistuje")
        if profile.get("site_url"):
            self.browser.navigate(profile["site_url"])
        elif not self.browser.status()["running"]:
            raise ValueError("Profil nemá přiřazenou stránku. Nejdříve otevřete cílový web.")
        self._auto_login(credential_id)
        return {"credential_id": credential_id, "browser": self.browser.status()}

    def snapshot(self):
        with self.lock:
            return {**self.state, "logs": list(self.state["logs"][-100:])}

    def _log(self, level, message, action_id=None):
        entry = {"time": time.strftime("%H:%M:%S"), "level": level, "message": message, "action_id": action_id}
        with self.lock:
            self.state["logs"].append(entry)
            if len(self.state["logs"]) > 1000:
                del self.state["logs"][:-750]
            self.state["message"] = message

    def _checkpoint(self):
        while not self.pause_event.wait(0.1):
            if self.stop_event.is_set():
                raise InterruptedError
        if self.stop_event.is_set():
            raise InterruptedError

    def _set_countdown(self, total=None, remaining=None):
        with self.lock:
            self.state["countdown"] = None if total is None else {
                "total": round(max(0, float(total)), 1),
                "remaining": round(max(0, float(remaining)), 1),
            }

    def _sleep(self, seconds, countdown=False):
        total = max(0, float(seconds))
        remaining = total
        if countdown:
            self._set_countdown(total, remaining)
        try:
            while remaining > 0:
                self._checkpoint()
                step = min(0.1, remaining)
                time.sleep(step)
                remaining = max(0, remaining - step)
                if countdown:
                    self._set_countdown(total, remaining)
        finally:
            if countdown:
                self._set_countdown()

    def _run(self, workflow_id):
        try:
            actions = self.db.all("SELECT * FROM actions WHERE workflow_id=? AND enabled=1 ORDER BY position, id", (workflow_id,))
            mode = "nekonečná smyčka" if self.repeat_count == 0 else f"{self.repeat_count} cyklů"
            self._log("info", f"Workflow spuštěno: {len(actions)} akcí, {mode}")
            cycle = 0
            while self.repeat_count == 0 or cycle < self.repeat_count:
                self._checkpoint()
                cycle += 1
                cycle_had_error = False
                with self.lock:
                    self.state["cycle"] = cycle
                self._log("info", f"Cyklus {cycle} spuštěn")
                for index, action in enumerate(actions):
                    self._checkpoint()
                    with self.lock:
                        self.state["current"] = {"index": index, "total": len(actions), "cycle": cycle, "action_id": action["id"], "type": action["action_type"]}
                    self._log("info", f"{index + 1}/{len(actions)} · {action['action_type']}", action["id"])
                    try:
                        if action["action_type"] in {"wait", "wait_random", "repeat_click", "repeat_until"}:
                            self._execute(action)
                        else:
                            with self.browser.lock:
                                self._execute(action)
                    except (NoSuchElementException, TimeoutException) as exc:
                        cycle_had_error = True
                        detail = str(exc).splitlines()[0] or "element nebyl nalezen"
                        with self.lock:
                            self.state["skipped"] += 1
                        self._log(
                            "warning",
                            f"Akce {index + 1} přeskočena: {detail}",
                            action["id"],
                        )
                        continue
                    except InterruptedError:
                        raise
                    except Exception as exc:
                        if self.repeat_count != 0:
                            raise
                        cycle_had_error = True
                        detail = str(exc).splitlines()[0] or type(exc).__name__
                        with self.lock:
                            self.state["errors"] += 1
                        self._log(
                            "error",
                            f"Akce {index + 1} selhala, nekonečný Loop pokračuje: {type(exc).__name__}: {detail}",
                            action["id"],
                        )
                        self._sleep(0.5)
                        continue
                if cycle_had_error:
                    self._log("warning", f"Cyklus {cycle} dokončen s přeskočenými nebo chybnými akcemi")
                else:
                    self._log("success", f"Cyklus {cycle} dokončen")
                if self.repeat_count == 0:
                    self._sleep(0.1)
            with self.lock:
                self.state["status"] = "completed"
                self.state["current"] = None
            self._log("success", "Workflow dokončeno")
        except InterruptedError:
            with self.lock:
                self.state["status"] = "stopped"
                self.state["current"] = None
            self._log("warning", "Workflow zastaveno")
        except Exception as exc:
            with self.lock:
                self.state["status"] = "failed"
            self._log("error", f"{type(exc).__name__}: {exc}")
            self._log("debug", traceback.format_exc())

    def _element(self, action):
        if not action.get("element_id"):
            raise ValueError("Akce vyžaduje element")
        item = self.db.one("SELECT * FROM elements WHERE id=?", (action["element_id"],))
        if not item:
            raise ValueError("Uložený element neexistuje")
        driver = self.browser.require()
        driver.switch_to.default_content()
        for frame in item.get("frame_path", []):
            driver.switch_to.frame(driver.find_element(BY_MAP[frame["strategy"]], frame["locator"]))
        return self.browser.find(item["strategy"], item["locator"], item.get("alternatives"))

    def _element_by_id(self, element_id):
        return self._element({"element_id": element_id})

    def _is_visible(self, element_id):
        try:
            with self.browser.lock:
                return self._element_by_id(element_id).is_displayed()
        except Exception:
            return False

    def _perform_operation(self, element_id, operation, value=""):
        with self.browser.lock:
            driver = self.browser.require()
            element = self._element_by_id(element_id)
            if operation == "click":
                element.click()
            elif operation == "double_click":
                ActionChains(driver).double_click(element).perform()
            elif operation == "context_click":
                ActionChains(driver).context_click(element).perform()
            elif operation == "hover":
                self._hover_element(element)
            elif operation == "type":
                element.send_keys(value)
            elif operation == "key":
                element.send_keys(KEYS.get(str(value or "ENTER").lower(), value or Keys.ENTER))
            else:
                raise ValueError(f"Nepodporovaná opakovaná akce: {operation}")

    def _repeat_click(self, action):
        p = action["parameters"]
        frequency = float(p.get("clicks_per_second", 1))
        if frequency <= 0:
            raise ValueError("Frekvence klikání musí být větší než nula")
        interval = 1.0 / frequency
        duration = float(p.get("duration_seconds", 0))
        if duration < 0:
            raise ValueError("Doba klikání nesmí být záporná")
        started = time.monotonic()
        clicks = 0
        while duration == 0 or time.monotonic() - started < duration:
            self._checkpoint()
            self._perform_operation(action["element_id"], "click")
            clicks += 1
            if clicks == 1 or clicks % 25 == 0:
                self._log("info", f"Kontinuální klikání: {clicks} kliknutí", action["id"])
            self._sleep(interval)
        self._log("success", f"Kontinuální klikání dokončeno: {clicks} kliknutí", action["id"])

    def _repeat_until(self, action):
        p = action["parameters"]
        target_id = int(p.get("target_element_id") or action["element_id"])
        source_id = int(action["element_id"])
        operation = p.get("operation", "click")
        value = p.get("value", "")
        interval = max(0.05, float(p.get("interval_seconds", 0.5)))
        timeout = max(0, float(p.get("timeout_seconds", 0)))
        started = time.monotonic()
        repetitions = 0
        while True:
            self._checkpoint()
            if self._is_visible(target_id):
                if target_id == source_id:
                    self._perform_operation(source_id, operation, value)
                    repetitions += 1
                self._log("success", f"Cílový objekt se objevil; opakování: {repetitions}", action["id"])
                return
            if timeout and time.monotonic() - started >= timeout:
                raise TimeoutError("Cílový objekt se ve stanoveném čase neobjevil")
            if target_id != source_id:
                self._perform_operation(source_id, operation, value)
                repetitions += 1
            self._sleep(interval)

    def _auto_login(self, credential_id):
        profile = self.db.one("SELECT * FROM credentials WHERE id=?", (credential_id,))
        if not profile:
            raise ValueError("Přihlašovací profil neexistuje")
        username = self.vault.decrypt(profile["username_cipher"])
        password = self.vault.decrypt(profile["password_cipher"])
        with self.browser.lock:
            self._fill_login_field(profile["username_element_id"], username, "uživatelského jména")
            self._fill_login_field(profile["password_element_id"], password, "hesla")
            for action in profile.get("extra_actions", []):
                self._perform_login_action(action)
            if profile.get("submit_element_id"):
                self._click_login_button(profile["submit_element_id"])

    def _perform_login_action(self, action):
        kind = action.get("action_type", "click")
        if kind == "wait":
            seconds = max(0, float(action.get("seconds", 1)))
            if self.thread and self.thread.is_alive():
                self._sleep(seconds)
            else:
                time.sleep(seconds)
            return
        element_id = action.get("element_id")
        if not element_id:
            raise ValueError("Dodatecna prihlasovaci akce vyzaduje objekt")
        self._login_delay()
        if kind == "focus":
            element = self._element_by_id(element_id)
            self.browser.require().execute_script("arguments[0].scrollIntoView({block:'center',inline:'center'})", element)
            self._activate_login_field(element)
        elif kind in {"click", "double_click", "hover", "type", "key"}:
            self._perform_operation(element_id, kind, action.get("value", ""))
        else:
            raise ValueError(f"Nepodporovana dodatecna prihlasovaci akce: {kind}")

    @staticmethod
    def _editable_from(root, driver=None):
        tag = root.tag_name.lower()
        candidates = [root] if tag in {"input", "textarea"} or root.get_attribute("contenteditable") == "true" else []
        candidates.extend(root.find_elements(By.CSS_SELECTOR, "input:not([type='hidden']), textarea, [contenteditable='true']"))
        if driver is not None:
            try:
                linked_id = root.get_attribute("for")
                if linked_id:
                    candidates.append(driver.find_element(By.ID, linked_id))
            except WebDriverException:
                pass
            try:
                associated = driver.execute_script(
                    "const el=arguments[0];"
                    "if(el.control)return el.control;"
                    "if(!el.id)return null;"
                    "return document.querySelector('[aria-labelledby~=\"'+CSS.escape(el.id)+'\"]');",
                    root,
                )
                if associated:
                    candidates.append(associated)
            except WebDriverException:
                pass
        for element in candidates:
            try:
                hidden_input = element.tag_name.lower() == "input" and (element.get_attribute("type") or "text").lower() == "hidden"
                readonly = element.get_attribute("readonly") is not None
                if not hidden_input and not readonly and element.is_displayed() and element.is_enabled():
                    return element
            except WebDriverException:
                continue
        return None

    def _wait_editable(self, element_id, label, timeout=12):
        driver = self.browser.require()

        def locate(_driver):
            try:
                return self._editable_from(self._element_by_id(element_id), driver) or False
            except WebDriverException:
                return False

        try:
            return WebDriverWait(driver, timeout, poll_frequency=0.2).until(locate)
        except Exception as exc:
            raise ValueError(
                f"Objekt pro {label} není editovatelné pole. Uložte přímo INPUT/TEXTAREA, ne jeho obal."
            ) from exc

    def _fill_login_field(self, element_id, value, label):
        element = self._wait_editable(element_id, label)
        driver = self.browser.require()
        driver.execute_script("arguments[0].scrollIntoView({block:'center',inline:'center'})", element)
        try:
            self._activate_login_field(element)
            self._login_delay()
            try:
                element.clear()
            except InvalidElementStateException:
                element.send_keys(Keys.CONTROL, "a")
                element.send_keys(Keys.BACKSPACE)
            element.send_keys(value)
        except WebDriverException as exc:
            raise ValueError(f"Pole {label} bylo nalezeno, ale nelze do něj psát. Zkontrolujte uložený objekt.") from exc

    def _login_delay(self, seconds=1.0):
        seconds = max(1.0, float(seconds))
        if self.thread and self.thread.is_alive():
            self._sleep(seconds)
        else:
            time.sleep(seconds)

    def _activate_login_field(self, element):
        driver = self.browser.require()
        try:
            element.click()
        except WebDriverException:
            try:
                ActionChains(driver).move_to_element(element).click().perform()
            except WebDriverException:
                driver.execute_script("arguments[0].focus(); arguments[0].click()", element)
        if not driver.execute_script("return document.activeElement === arguments[0]", element):
            driver.execute_script("arguments[0].focus()", element)

    @staticmethod
    def _visible_center(rect):
        left = max(0, float(rect["x"]))
        top = max(0, float(rect["y"]))
        right = min(float(rect["viewportWidth"]), float(rect["x"]) + float(rect["width"]))
        bottom = min(float(rect["viewportHeight"]), float(rect["y"]) + float(rect["height"]))
        if right <= left or bottom <= top:
            raise ValueError("Objekt není ve viditelné části stránky")
        return (left + right) / 2, (top + bottom) / 2

    def _hover_element(self, element):
        driver = self.browser.require()
        driver.execute_script(
            "arguments[0].scrollIntoView({behavior:'instant',block:'center',inline:'center'})",
            element,
        )
        rect = driver.execute_script(
            "const r=arguments[0].getBoundingClientRect();"
            "return {x:r.x,y:r.y,width:r.width,height:r.height,"
            "viewportWidth:window.innerWidth,viewportHeight:window.innerHeight}",
            element,
        )
        x, y = self._visible_center(rect)
        try:
            ActionChains(driver).move_to_element(element).perform()
        except MoveTargetOutOfBoundsException:
            try:
                if driver.execute_script("return window === window.top"):
                    driver.execute_cdp_cmd("Input.dispatchMouseEvent", {"type": "mouseMoved", "x": x, "y": y})
                else:
                    driver.execute_script(
                        "const e=arguments[0],x=arguments[1],y=arguments[2];"
                        "for(const type of ['mouseover','mouseenter','mousemove'])"
                        "e.dispatchEvent(new MouseEvent(type,{view:window,bubbles:true,clientX:x,clientY:y}));",
                        element, x, y,
                    )
            except WebDriverException as exc:
                raise ValueError("Na objekt nelze přejet myší ani po jeho posunutí do viditelné oblasti") from exc

    def _click_login_button(self, element_id, timeout=12):
        driver = self.browser.require()

        def locate(_driver):
            try:
                root = self._element_by_id(element_id)
                tag = root.tag_name.lower()
                candidates = []
                if tag in {"button", "a"} or root.get_attribute("role") == "button" or (tag == "input" and (root.get_attribute("type") or "").lower() in {"submit", "button"}):
                    candidates.append(root)
                candidates.extend(root.find_elements(By.CSS_SELECTOR, "button, input[type='submit'], input[type='button'], [role='button'], a"))
                return next((item for item in candidates if item.is_displayed() and item.is_enabled()), False)
            except WebDriverException:
                return False

        try:
            button = WebDriverWait(driver, timeout, poll_frequency=0.2).until(locate)
            driver.execute_script("arguments[0].scrollIntoView({block:'center',inline:'center'})", button)
            self._login_delay()
            button.click()
        except Exception as exc:
            raise ValueError("Přihlašovací tlačítko nebylo kliknutelné. Zkontrolujte uložený objekt tlačítka.") from exc

    def _execute(self, action):
        p = action["parameters"]
        kind = action["action_type"]
        if kind == "wait":
            self._sleep(float(p.get("seconds", 1)), countdown=True)
            return
        if kind == "wait_random":
            self._sleep(random.uniform(float(p.get("min", 1)), float(p.get("max", 4))), countdown=True)
            return
        if kind == "repeat_click":
            self._repeat_click(action)
            return
        if kind == "repeat_until":
            self._repeat_until(action)
            return
        if kind == "auto_login":
            self._auto_login(int(p.get("credential_id")))
            return
        driver = self.browser.require()
        element = None
        element_kinds = {"click", "double_click", "context_click", "hover", "type", "clear", "submit", "select", "scroll_to", "drag_to", "key", "wait_for", "upload", "screenshot", "focus"}
        if kind in element_kinds:
            element = self._element(action)
        if kind == "click": element.click()
        elif kind == "double_click": ActionChains(driver).double_click(element).perform()
        elif kind == "context_click": ActionChains(driver).context_click(element).perform()
        elif kind == "hover": self._hover_element(element)
        elif kind == "focus": driver.execute_script("arguments[0].focus()", element)
        elif kind == "type":
            if p.get("clear", False): element.clear()
            element.send_keys(p.get("text", ""))
        elif kind == "clear": element.clear()
        elif kind == "submit": element.submit()
        elif kind == "select":
            select = Select(element)
            mode, value = p.get("by", "text"), p.get("value", "")
            {"text": select.select_by_visible_text, "value": select.select_by_value, "index": lambda v: select.select_by_index(int(v))}[mode](value)
        elif kind == "scroll_to": driver.execute_script("arguments[0].scrollIntoView({behavior:'smooth',block:'center'})", element)
        elif kind == "scroll_by": driver.execute_script("window.scrollBy(arguments[0],arguments[1])", int(p.get("x", 0)), int(p.get("y", 400)))
        elif kind == "drag_to":
            target = self.db.one("SELECT * FROM elements WHERE id=?", (p.get("target_element_id"),))
            if not target: raise ValueError("Cílový element neexistuje")
            target_el = self.browser.find(target["strategy"], target["locator"], target.get("alternatives"))
            ActionChains(driver).drag_and_drop(element, target_el).perform()
        elif kind == "mouse_move": ActionChains(driver).move_by_offset(int(p.get("x", 0)), int(p.get("y", 0))).perform()
        elif kind == "key":
            key = KEYS.get(str(p.get("key", "ENTER")).lower(), p.get("key", ""))
            element.send_keys(key)
        elif kind == "wait_for":
            timeout = float(p.get("timeout", 10)); condition = p.get("condition", "visible")
            item = self.db.one("SELECT * FROM elements WHERE id=?", (action["element_id"],))
            locator = (BY_MAP[item["strategy"]], item["locator"])
            expected = {"present": EC.presence_of_element_located, "visible": EC.visibility_of_element_located, "clickable": EC.element_to_be_clickable, "hidden": EC.invisibility_of_element_located}[condition]
            WebDriverWait(driver, timeout).until(expected(locator))
        elif kind == "navigate": self.browser.navigate(p.get("url", ""))
        elif kind == "back": driver.back()
        elif kind == "forward": driver.forward()
        elif kind == "refresh": driver.refresh()
        elif kind == "switch_frame": driver.switch_to.frame(self._element(action))
        elif kind == "default_content": driver.switch_to.default_content()
        elif kind == "switch_window": driver.switch_to.window(driver.window_handles[int(p.get("index", -1))])
        elif kind == "new_tab": driver.switch_to.new_window("tab")
        elif kind == "close_tab": driver.close()
        elif kind == "alert_accept": driver.switch_to.alert.accept()
        elif kind == "alert_dismiss": driver.switch_to.alert.dismiss()
        elif kind == "upload": element.send_keys(p.get("path", ""))
        elif kind == "screenshot": element.screenshot(str(self.browser.screenshot_dir / p.get("filename", f"action-{action['id']}.png")))
        elif kind == "script": driver.execute_script(p.get("script", ""))
        elif kind == "cookie_set": driver.add_cookie({"name": p.get("name", ""), "value": p.get("value", "")})
        else: raise ValueError(f"Neznámý typ akce: {kind}")
