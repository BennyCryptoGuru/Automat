import os
import shutil
import subprocess
import threading
from io import BytesIO
from pathlib import Path
from urllib.parse import urlparse

from PIL import Image
from selenium import webdriver
from selenium.common.exceptions import NoSuchElementException, SessionNotCreatedException, WebDriverException
from selenium.webdriver.chrome.service import Service
from selenium.webdriver.common.by import By


BY_MAP = {
    "id": By.ID,
    "name": By.NAME,
    "class name": By.CLASS_NAME,
    "tag name": By.TAG_NAME,
    "css selector": By.CSS_SELECTOR,
    "xpath": By.XPATH,
    "link text": By.LINK_TEXT,
    "partial link text": By.PARTIAL_LINK_TEXT,
}

CUSTOM_LOCATOR_STRATEGIES = ("select by value", "select by text", "div text", "div partial text")
LOCATOR_STRATEGIES = [*BY_MAP, *CUSTOM_LOCATOR_STRATEGIES]


PICKER_SCRIPT = r"""
(() => {
  if (window.__automatPickerActive) return;
  window.__automatPickerActive = true;
  window.__automatSelection = null;
  const style = document.createElement('style');
  style.id = '__automat_picker_style';
  style.textContent = '.__automat-hover{outline:3px solid #7c5cff!important;outline-offset:2px!important;cursor:crosshair!important}';
  document.documentElement.appendChild(style);
  let hovered = null;
  const cssPath = (el) => {
    if (el.id) return '#' + CSS.escape(el.id);
    const parts = [];
    while (el && el.nodeType === 1 && parts.length < 7) {
      let part = el.tagName.toLowerCase();
      const siblings = el.parentElement ? [...el.parentElement.children].filter(x => x.tagName === el.tagName) : [];
      if (siblings.length > 1) part += `:nth-of-type(${siblings.indexOf(el) + 1})`;
      parts.unshift(part); el = el.parentElement;
    }
    return parts.join(' > ');
  };
  const xpath = (el) => {
    if (el.id) return `//*[@id=${JSON.stringify(el.id)}]`;
    const parts = [];
    while (el && el.nodeType === 1) {
      const peers = el.parentElement ? [...el.parentElement.children].filter(x => x.tagName === el.tagName) : [];
      parts.unshift(el.tagName.toLowerCase() + (peers.length > 1 ? `[${peers.indexOf(el)+1}]` : ''));
      el = el.parentElement;
    }
    return '/' + parts.join('/');
  };
  const over = e => { if (hovered) hovered.classList.remove('__automat-hover'); hovered=e.target; hovered.classList.add('__automat-hover'); e.stopPropagation(); };
  const click = e => {
    e.preventDefault(); e.stopPropagation(); e.stopImmediatePropagation();
    const el=e.target; el.classList.remove('__automat-hover');
    const rect=el.getBoundingClientRect();
    const alternatives=[];
    const addAlternative=(strategy,locator)=>{
      locator=String(locator||'').trim();
      if(!locator) return;
      if(alternatives.some(item=>item.strategy===strategy && item.locator===locator)) return;
      alternatives.push({strategy, locator});
    };
    const idValue=el.id||'';
    const nameValue=el.getAttribute('name')||'';
    const className=el.classList && el.classList.length ? el.classList[0] : '';
    const tagName=el.tagName.toLowerCase();
    const cssLocator=cssPath(el);
    const xpathLocator=xpath(el);
    addAlternative('id', idValue);
    addAlternative('name', nameValue);
    addAlternative('class name', className);
    addAlternative('tag name', tagName);
    addAlternative('css selector', cssLocator);
    addAlternative('xpath', xpathLocator);
    const link=el.closest('a');
    const linkText=link ? link.textContent.trim() : '';
    if(link && link.textContent.trim()) {
      addAlternative('link text', linkText);
      addAlternative('partial link text', linkText.slice(0,80));
    }
    const optionValue=el.tagName==='OPTION' ? el.value : '';
    const optionText=el.tagName==='OPTION' ? el.textContent.trim() : '';
    if(el.tagName==='OPTION') {
      addAlternative('select by value', optionValue);
      addAlternative('select by text', optionText);
    }
    const divText=el.tagName==='DIV' ? el.textContent.trim() : '';
    if(el.tagName==='DIV' && el.textContent.trim()) {
      addAlternative('div text', divText);
      addAlternative('div partial text', divText.slice(0,80));
    }
    const elementText=(el.innerText||el.value||el.textContent||'').trim().slice(0,160);
    window.__automatSelection={
      strategy: alternatives[0].strategy, locator: alternatives[0].locator, alternatives,
      tag:tagName, text:elementText, idValue, nameValue, className, cssLocator, xpathLocator,
      linkText:linkText.slice(0,160), optionValue, optionText:optionText.slice(0,160),
      divText:divText.slice(0,160),
      title:el.getAttribute('title')||'', ariaLabel:el.getAttribute('aria-label')||'',
      rect:{x:Math.round(rect.x),y:Math.round(rect.y),width:Math.round(rect.width),height:Math.round(rect.height)}
    };
    document.removeEventListener('mouseover',over,true); document.removeEventListener('click',click,true);
    style.remove(); window.__automatPickerActive=false;
  };
  document.addEventListener('mouseover',over,true); document.addEventListener('click',click,true);
})();
"""


class BrowserManager:
    def __init__(self, data_dir: Path):
        self.data_dir = data_dir
        self.profile_dir = None
        self.screenshot_dir = data_dir / "screenshots"
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        self.driver = None
        self.browser_name = None
        self.default_stealth = False
        self.stealth_run = False
        self.lock = threading.RLock()

    def set_stealth_run(self, enabled):
        with self.lock:
            self.default_stealth = bool(enabled)

    def start(self, preferred="chrome", url=None, stealth=None):
        with self.lock:
            stealth_run = self.default_stealth if stealth is None else bool(stealth)
            target_url = self.normalize_url(url) if url else None
            if self.driver:
                try:
                    _ = self.driver.current_url
                    if self.stealth_run != stealth_run:
                        self.driver.quit()
                        self.driver = None
                    else:
                        if target_url:
                            self.driver.get(target_url)
                        return self.status()
                except WebDriverException:
                    self.driver = None
            if self.driver:
                try:
                    if target_url:
                        self.driver.get(target_url)
                    return self.status()
                except WebDriverException:
                    self.driver = None

            errors = []
            for browser_name, binary in self._browser_candidates(preferred):
                self.browser_name = browser_name
                self.stealth_run = stealth_run
                try:
                    self.driver = webdriver.Chrome(
                        service=self._service(self.data_dir / "chromedriver.log", verbose=True),
                        options=self._options(binary, target_url, stealth_run),
                    )
                    if target_url and not self._is_at_target(target_url):
                        self.driver.get(target_url)
                    return self.status()
                except SessionNotCreatedException as exc:
                    self.driver = None
                    errors.append(f"{browser_name}: {self._error_message(exc)}")
                    break
                except WebDriverException as exc:
                    self.driver = None
                    errors.append(f"{browser_name}: {self._error_message(exc)}")
                    break

            detail = "; ".join(errors[-4:]) or "Selenium did not return error details"
            raise RuntimeError(
                "Chrome could not create a clean Selenium session. "
                "Automat uses only Chrome and no custom profile folders. "
                f"Last errors: {detail}"
            )

    def _options(self, binary, initial_url=None, stealth=False):
        options = webdriver.ChromeOptions()
        options.add_argument("--start-maximized")
        if stealth:
            options.add_argument("--headless=new")
            options.add_argument("--window-size=1920,1080")
            options.add_argument("--disable-gpu")
        options.add_argument("--disable-notifications")
        options.add_argument("--disable-background-mode")
        options.add_argument("--disable-background-networking")
        options.add_argument("--disable-default-apps")
        options.add_argument("--disable-logging")
        options.add_argument("--disable-sync")
        options.add_argument("--log-level=3")
        options.add_argument("--no-first-run")
        options.add_experimental_option("excludeSwitches", ["enable-automation", "enable-logging"])
        if binary:
            options.binary_location = str(binary)
        if initial_url:
            options.add_argument(initial_url)
        return options

    def _service(self, log_path=None, verbose=False):
        service = Service(
            log_output=str(log_path) if log_path else subprocess.DEVNULL,
            service_args=["--verbose"] if verbose else None,
        )
        if hasattr(subprocess, "CREATE_NO_WINDOW"):
            service.creation_flags = subprocess.CREATE_NO_WINDOW
        return service

    def _is_at_target(self, target_url):
        try:
            current = self.driver.current_url
        except WebDriverException:
            return False
        if not current or current == "data:,":
            return False
        return current.rstrip("/") == target_url.rstrip("/")

    def _browser_candidates(self, preferred):
        env = os.getenv("AUTOMAT_CHROME_BINARY") or os.getenv("AUTOMAT_BROWSER_BINARY")
        candidates = []
        if env:
            candidates.append(Path(env))
        local = Path(os.getenv("LOCALAPPDATA", ""))
        programs = Path(os.getenv("PROGRAMFILES", "C:/Program Files"))
        programs_x86 = Path(os.getenv("PROGRAMFILES(X86)", "C:/Program Files (x86)"))
        chrome = [programs / "Google/Chrome/Application/chrome.exe", programs_x86 / "Google/Chrome/Application/chrome.exe", local / "Google/Chrome/Application/chrome.exe"]
        candidates += chrome
        for command in ("chrome", "google-chrome"):
            found = shutil.which(command)
            if found:
                candidates.append(Path(found))

        result = []
        seen = set()
        for path in candidates:
            if not path or not path.is_file():
                continue
            resolved = str(path.resolve()).lower()
            if resolved in seen:
                continue
            seen.add(resolved)
            result.append(("Chrome", path))
        if not result:
            result.append(("Chrome", None))
        return result

    def _find_browser(self, preferred):
        return self._browser_candidates(preferred)[0][1]

    @staticmethod
    def _error_message(exc):
        return str(exc).splitlines()[0].strip() or type(exc).__name__

    def navigate(self, url):
        url = self.normalize_url(url)
        with self.lock:
            driver = self.require()
            driver.get(url)
            return self.status()

    @staticmethod
    def normalize_url(url):
        url = str(url or "").strip()
        if not url:
            raise ValueError("Enter a website address")
        if "://" not in url:
            url = "https://" + url
        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("Use a valid web address starting with http:// or https://")
        return url

    def status(self):
        with self.lock:
            if not self.driver:
                return {"running": False, "browser": self.browser_name, "url": "", "title": "", "stealth_run": self.default_stealth}
            try:
                return {"running": True, "browser": self.browser_name, "url": self.driver.current_url, "title": self.driver.title, "stealth_run": self.stealth_run}
            except WebDriverException:
                self.driver = None
                return {"running": False, "browser": self.browser_name, "url": "", "title": "", "stealth_run": self.default_stealth}

    def require(self):
        with self.lock:
            if not self.driver:
                self.start()
            return self.driver

    def begin_picker(self):
        with self.lock:
            self.require().execute_script(PICKER_SCRIPT)

    def picker_result(self):
        with self.lock:
            return self.require().execute_script("return window.__automatSelection || null")

    def capture_selected(self, selection, filename):
        with self.lock:
            element = self.find(selection["strategy"], selection["locator"])
            path = self.screenshot_dir / filename
            driver = self.require()
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
            screenshot = Image.open(BytesIO(driver.get_screenshot_as_png()))
            scale_x = screenshot.width / max(1, rect["viewportWidth"])
            scale_y = screenshot.height / max(1, rect["viewportHeight"])
            element_box = (
                rect["x"] * scale_x,
                rect["y"] * scale_y,
                (rect["x"] + rect["width"]) * scale_x,
                (rect["y"] + rect["height"]) * scale_y,
            )
            crop_box = self._preview_box(element_box, screenshot.size)
            preview = screenshot.crop(crop_box)
            if preview.mode not in ("RGB", "RGBA"):
                preview = preview.convert("RGB")
            preview.save(path, "PNG", optimize=True)
            return path

    @staticmethod
    def _preview_box(element_box, image_size, minimum=(240, 140), maximum=(760, 480)):
        image_width, image_height = image_size
        left, top, right, bottom = element_box
        element_width = max(1, right - left)
        element_height = max(1, bottom - top)
        padding = max(18, min(70, max(element_width, element_height) * 0.22))
        target_width = min(maximum[0], max(minimum[0], element_width + 2 * padding))
        target_height = min(maximum[1], max(minimum[1], element_height + 2 * padding))
        target_width = min(target_width, image_width)
        target_height = min(target_height, image_height)
        center_x = (left + right) / 2
        center_y = (top + bottom) / 2
        crop_left = max(0, min(image_width - target_width, center_x - target_width / 2))
        crop_top = max(0, min(image_height - target_height, center_y - target_height / 2))
        return (
            round(crop_left),
            round(crop_top),
            round(crop_left + target_width),
            round(crop_top + target_height),
        )

    def find(self, strategy, locator, alternatives=None):
        with self.lock:
            driver = self.require()
            attempts = [{"strategy": strategy, "locator": locator}] + list(alternatives or [])
            last_error = None
            for attempt in attempts:
                try:
                    by, value = self.locator_tuple(attempt["strategy"], attempt["locator"])
                    return driver.find_element(by, value)
                except (KeyError, NoSuchElementException) as exc:
                    last_error = exc
            raise NoSuchElementException(f"Element not found: {strategy}={locator}") from last_error

    @classmethod
    def locator_tuple(cls, strategy, locator):
        if strategy in BY_MAP:
            return BY_MAP[strategy], locator
        if strategy == "select by value":
            return By.XPATH, f"//option[@value={cls.xpath_literal(locator)}]"
        if strategy == "select by text":
            return By.XPATH, f"//option[normalize-space(.)={cls.xpath_literal(locator)}]"
        if strategy == "div text":
            return By.XPATH, f"//div[normalize-space(.)={cls.xpath_literal(locator)}]"
        if strategy == "div partial text":
            return By.XPATH, f"//div[contains(normalize-space(.), {cls.xpath_literal(locator)})]"
        raise KeyError(strategy)

    @staticmethod
    def xpath_literal(value):
        text = str(value or "")
        if '"' not in text:
            return f'"{text}"'
        if "'" not in text:
            return f"'{text}'"
        parts = text.split('"')
        return "concat(" + ', \'"\', '.join(f'"{part}"' for part in parts) + ")"

    def quit(self):
        with self.lock:
            if self.driver:
                try:
                    self.driver.quit()
                finally:
                    self.driver = None
