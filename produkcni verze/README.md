# Automat

Lokální studio pro tvorbu a spouštění automatizací webového prohlížeče. Backend je v Pythonu, rozhraní v HTML/CSS/JavaScriptu, data v SQLite a prohlížeč ovládá Selenium WebDriver.

## Spuštění

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python run.py
```

Studio se otevře na `http://127.0.0.1:5000`. Tlačítko **Spustit Chrome** používá pouze Google Chrome. Selenium Manager automaticky zajistí kompatibilní ChromeDriver. Vlastní cestu ke Chromu lze nastavit proměnnou `AUTOMAT_CHROME_BINARY`.

Automat nepředává Chromu žádný vlastní `--user-data-dir` a nepoužívá profilové složky v `data`. Každé spuštění řízeného prohlížeče začíná čistou Selenium relací. `run.py` současně dovolí běžet pouze jedné instanci Automatu.

## Základní postup

1. Spusťte prohlížeč, vložte URL a klikněte na **Přejít**.
2. Přihlaste se ručně podle potřeby. Po ukončení řízeného Chromu další spuštění začíná znovu čistou relací.
3. Klikněte na **Najít objekt**, poté přímo na element v řízeném okně a objekt uložte.
4. Vytvořte workflow, přidejte seřazené akce a spusťte je tlačítkem Play.
5. Pause pozastaví workflow mezi akcemi i během časových čekání; Play pokračuje a Stop běh ukončí.

## Podporované možnosti

- Lokátory: ID, name, class name, tag name, CSS selector, XPath, link text a partial link text.
- Více alternativních lokátorů pro jeden objekt, hierarchie podobjektů a cesta přes iframe.
- Kliknutí, dvojklik, pravé tlačítko, hover, focus, text, klávesy, select, drag & drop a pohyb myši.
- Pevné a náhodné čekání, explicitní čekání na přítomnost, viditelnost, kliknutelnost nebo skrytí.
- Akce **Čekat** a **Čekat náhodně** zobrazují v aktivním workflow živý odpočet a průběh; Pause odpočet skutečně zmrazí.
- Šifrované přihlašovací profily (Windows DPAPI) a automatické vyplnění uživatele, hesla a volitelné odeslání.
- Přímé tlačítko **Přihlásit** u profilu otevře přiřazenou stránku a okamžitě provede přihlášení i bez workflow.
- Automatické přihlášení po aktivaci každého pole čeká nejméně jednu sekundu před zápisem a před odesláním formuláře.
- Přihlašovací pole lze uložit přímo jako `INPUT/TEXTAREA` nebo přes propojený `LABEL` (`for`, `control`, `aria-labelledby`).
- Kontinuální klikání s nastavitelným počtem kliknutí za sekundu a dobou běhu; `0` znamená běh do ručního zastavení.
- Opakování akce na Objektu 1 do zobrazení Objektu 2; oba objekty mohou být stejné.
- Hover vycentruje objekt, používá jeho viditelný střed a při chybě hranic využije přesný pohyb myši přes Chrome DevTools.
- Pokud běžná akce nenajde svůj element nebo vyprší čekání, zapíše varování, krok přeskočí a pokračuje další akcí.
- Spuštění celého workflow ve smyčce s přesným počtem cyklů nebo nekonečně do stisknutí Stop.
- Nekonečný Loop (`0`) se nezastaví kvůli chybě jednotlivé akce ani nenalezenému elementu; chybu zapíše, krok přeskočí a běží až do Stop.
- Export workflow do verzovaného `.automat.json` včetně akcí, stránky a používaných objektů a následný import s automatickým přemapováním vazeb.
- Navigace, historie, refresh, karty/okna, iframe, dialogy, upload, cookies, screenshoty a JavaScript.
- Kontextové PNG náhledy uložených elementů: objekt se vycentruje a snímek se ořízne s dynamickým okrajem na přiměřený čtvercový nebo obdélníkový formát.

## Poznámky k bezpečnosti

Automat běží pouze na `127.0.0.1`. Hodnoty přihlašovacích profilů jsou v SQLite šifrované pomocí Windows DPAPI a lze je dešifrovat pouze pod stejným uživatelským účtem Windows. Akce **Spustit JavaScript** je záměrně mocná a měla by se používat jen s vlastním nebo důvěryhodným kódem.

Oficiální zdroje návrhu: [Selenium locators](https://www.selenium.dev/documentation/webdriver/elements/locators/), [element finders](https://www.selenium.dev/documentation/webdriver/elements/finders/), [Actions API](https://www.selenium.dev/documentation/webdriver/actions_api/) a [waits](https://www.selenium.dev/documentation/webdriver/waits/).
