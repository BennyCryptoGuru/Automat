# Automat

A local studio for building and running browser automations. The backend is Python, the interface is HTML/CSS/JavaScript, data is stored in SQLite, and browser control is powered by Selenium WebDriver.

## Run

For a normal Windows installation, run:

```powershell
install.bat
start.bat
```

`start.bat` starts Automat hidden and opens the local web UI unless **Stealth run** is enabled.

For development, you can also run it manually:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py
```

The studio opens at `http://127.0.0.1:5000`. The **Start Chrome** button uses Google Chrome only. Selenium Manager automatically provides a compatible ChromeDriver. A custom Chrome binary can be set with `AUTOMAT_CHROME_BINARY`.

Automat does not pass a custom `--user-data-dir` to Chrome and does not use browser profile folders in `data`. Every controlled browser launch starts a clean Selenium session. `run.py` allows only one Automat instance to run at a time.

## Basic Workflow

1. Start the browser, enter a URL, and click **Go**.
2. Log in manually when needed. After the controlled Chrome window is closed, the next launch starts with a clean session again.
3. Click **Find object**, click an element in the controlled browser window, and save the object.
4. Create a workflow, add ordered actions, and start it with Play.
5. Pause stops the workflow between actions and during timed waits; Play resumes it and Stop ends the run.

## Supported Features

- Locators: ID, name, class name, tag name, CSS selector, XPath, link text, and partial link text.
- Multiple fallback locators for one object, subobject hierarchies, and iframe paths.
- Click, double click, right click, hover, focus, text input, keys, select, drag & drop, and mouse movement.
- Fixed and random waits, plus explicit waits for presence, visibility, clickability, or hidden state.
- **Wait** and **Wait randomly** show a live countdown in the active workflow; Pause freezes the countdown properly.
- Encrypted login profiles with Windows DPAPI and automatic filling of username, password, optional extra steps, and optional submit.
- A direct **Log in** button on each profile opens the assigned site and performs login without a workflow.
- Automatic login waits at least one second after activating each field and before submitting the form.
- Login fields can be saved directly as `INPUT/TEXTAREA` or through linked `LABEL` metadata (`for`, `control`, `aria-labelledby`).
- Continuous clicking with configurable clicks per second and duration; `0` means run until manually stopped.
- Repeat an action on Object 1 until Object 2 appears; both objects may be the same.
- Hover centers the object, uses its visible center, and falls back to precise Chrome DevTools mouse movement when needed.
- If a normal action cannot find its element or times out, Automat logs a warning, skips the step, and continues.
- Run the whole workflow in a finite loop or infinitely until Stop.
- Infinite loop (`0`) does not stop because of a single failed action or missing element; it logs the issue, skips the step, and continues until Stop.
- Workflow export/import as versioned `.automat.json`, including actions, site references, and used objects with automatic remapping.
- Navigation, history, refresh, tabs/windows, iframes, dialogs, upload, cookies, screenshots, and JavaScript execution.
- Context PNG previews for saved elements: the object is centered and cropped with a dynamic margin into a suitable square or rectangle.
- Frontend language switcher: English is the default UI language and Czech is available as a separate option.
- Lightweight stealth monitor at `http://127.0.0.1:5000/monitor`, built as a single self-contained HTML page with inline CSS/JS. It shows online/offline state, background mode, the last two log entries, and nearby workflow actions.
- Optional watchdog scripts can restart Automat only when Autorun is enabled. See `WATCHDOG_AUTORUN_GUIDE.txt`.
- `disable_stealth_run.bat` turns off Stealth run and restarts Automat with the visible UI.

## Security Notes

Automat listens only on `127.0.0.1`. Login profile values are encrypted in SQLite with Windows DPAPI and can be decrypted only under the same Windows user account. The **Run JavaScript** action is intentionally powerful and should be used only with your own or trusted code.

Design references: [Selenium locators](https://www.selenium.dev/documentation/webdriver/elements/locators/), [element finders](https://www.selenium.dev/documentation/webdriver/elements/finders/), [Actions API](https://www.selenium.dev/documentation/webdriver/actions_api/), and [waits](https://www.selenium.dev/documentation/webdriver/waits/).
