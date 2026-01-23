from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import random
import time
from urllib.parse import urljoin

import requests
from selenium import webdriver
from selenium.webdriver.common.by import By
from selenium.webdriver.firefox.options import Options
from selenium.webdriver.firefox.service import Service
from selenium.webdriver.support.ui import WebDriverWait
from selenium.webdriver.support import expected_conditions as EC
from webdriver_manager.firefox import GeckoDriverManager

from collector.models import Briefing, ChartAsset, TextAsset


def _human_type(el, text: str, min_delay: float = 0.08, max_delay: float = 0.18) -> None:
    for ch in text:
        el.send_keys(ch)
        time.sleep(random.uniform(min_delay, max_delay))


@dataclass
class MetSelfBriefProvider:
    name: str = "metie_custombrief"
    base_url: str = "https://briefing.met.ie/"
    briefing_url: str = ""  # set in constructor or call
    timeout_s: int = 35
    headless: bool = False  # start non-headless for debugging

    # TEMP ONLY: hardcode during bring-up
    username: str = ""
    password: str = ""

    def _debug_dump(self, driver, out_dir: Path, tag: str) -> None:
        debug_dir = out_dir / "debug"
        debug_dir.mkdir(parents=True, exist_ok=True)
        (debug_dir / f"{tag}.html").write_text(driver.page_source, encoding="utf-8")
        driver.save_screenshot(str(debug_dir / f"{tag}.png"))
        try:
            body_text = driver.find_element(By.TAG_NAME, "body").text
            (debug_dir / f"{tag}_body.txt").write_text(body_text, encoding="utf-8")
        except Exception:
            pass

    def _safe_get(self, driver, url: str, attempts: int = 3, base_sleep: float = 1.5) -> None:
        """
        Navigate with retries. Treat Firefox about:neterror pages as failures.
        """
        last_err = None
        for i in range(1, attempts + 1):
            try:
                driver.get(url)
                if driver.current_url.startswith("about:neterror"):
                    raise RuntimeError(f"Firefox error page: {driver.current_url}")
                return
            except Exception as e:
                last_err = e
                time.sleep(base_sleep * i)
        raise last_err

    def collect(self, briefing: Briefing, out_dir: Path, station: str = "EIME") -> None:
        out_dir.mkdir(parents=True, exist_ok=True)
        now_utc = datetime.now(timezone.utc)

        charts_dir = out_dir / "charts" / self.name
        charts_dir.mkdir(parents=True, exist_ok=True)

        text_dir = out_dir / "text"
        text_dir.mkdir(parents=True, exist_ok=True)

        debug_dir = out_dir / "debug"
        debug_dir.mkdir(parents=True, exist_ok=True)

        opts = Options()
        if self.headless:
            opts.add_argument("--headless")

        driver = webdriver.Firefox(
            service=Service(GeckoDriverManager().install()),
            options=opts,
        )

        try:
            wait = WebDriverWait(driver, self.timeout_s)

            # 1) Go to briefing URL (should redirect to login if not authenticated)
            driver.get(self.briefing_url)

            # Navigate to briefing URL (will redirect to login if needed)
            self._safe_get(driver, self.briefing_url, attempts=3)
            self._debug_dump(driver, out_dir, "01_after_get_briefing_url")
            
            # If we see a login form, log in
            def on_login_page(d) -> bool:
                html = d.page_source.lower()
                return ("name=\"username\"" in html or "name='username'" in html) and ("name=\"password\"" in html or "name='password'" in html)
            
            if on_login_page(driver):
                # Try multiple selectors for robustness
                user_el = wait.until(lambda d: d.find_element(By.CSS_SELECTOR, "input[name='username'], input#username"))
                pass_el = wait.until(lambda d: d.find_element(By.CSS_SELECTOR, "input[name='password'], input#password"))
            
                user_el.clear()
                _human_type(user_el, self.username)
                time.sleep(random.uniform(0.3, 0.8))
            
                pass_el.clear()
                _human_type(pass_el, self.password)
                time.sleep(random.uniform(0.4, 1.0))
            
                # Submit: try button[type=submit] first, then input[type=submit]
                submit = wait.until(lambda d: d.find_element(By.CSS_SELECTOR, "button[type='submit'], input[type='submit']"))
                driver.execute_script("arguments[0].scrollIntoView(true);", submit)
                time.sleep(random.uniform(0.2, 0.5))
                submit.click()
            
                # Wait for login to complete: either we leave login page, or we see the briefing URL loaded
                def login_complete(d) -> bool:
                    # if still login form present, not complete
                    if on_login_page(d):
                        return False
                    # if we have the custom briefing page, great
                    return ("custombriefing.php" in d.current_url.lower()) or ("briefing" in d.current_url.lower())
            
                wait.until(login_complete)
                self._debug_dump(driver, out_dir, "02_after_login_submit")
            
            # Now ensure we are on the briefing page
            self._safe_get(driver, self.briefing_url, attempts=3)
            self._debug_dump(driver, out_dir, "03_after_get_briefing_url_post_login")


            # 5) Extract METAR and TAF for station from rendered body text
            wait.until(lambda d: any(
                (el.get_attribute("textContent") or "").strip().upper().startswith("METAR")
                for el in d.find_elements(By.CSS_SELECTOR, "td.briefingText")
            ))

            metar_text, taf_text = self._extract_metar_taf_from_sections(
                driver=driver,
                wait=wait,
                station=station,   # "EIME"
            )

            report = "\n".join([
                "Met Éireann Custom Briefing",
                f"Generated (UTC): {now_utc.strftime('%Y-%m-%d %H:%M')}",
                f"Station: {station}",
                "",
                "METAR:",
                metar or "(not found)",
                "",
                "TAF:",
                taf or "(not found)",
                "",
            ])

            txt_path = text_dir / f"metar_taf_{station.lower()}_{now_utc.strftime('%Y%m%d_%H%M%S')}.txt"
            txt_path.write_text(report, encoding="utf-8")

            briefing.texts.append(
                TextAsset(
                    name=f"METAR/TAF {station}",
                    kind="metar_taf",
                    generated_at_utc=now_utc,
                    local_path=str(txt_path),
                    source=self.name,
                )
            )

            # 6) Download charts by finding <img> and links near the section headings
            # Placeholder: we’ll implement once we confirm the markup in debug HTML.
            # briefing.notes.append("TODO: chart download not yet implemented in fresh provider")

        except Exception as e:
            briefing.notes.append(f"{self.name}: failed: {e}")

            # capture debug on error too
            try:
                (debug_dir / "error_page.html").write_text(driver.page_source, encoding="utf-8")
                driver.save_screenshot(str(debug_dir / "error_page.png"))
            except Exception:
                pass

        finally:
            driver.quit()


def _extract_metar_taf_from_sections(self, driver, wait, station: str = "EIME") -> tuple[str | None, str | None]:
    station_u = station.upper().strip()

    metar_section_xpath = "/html/body/div/div[4]"
    taf_section_xpath = "/html/body/div/div[6]"

    def wait_section_has_text(section_xpath: str, must_start: str) -> None:
        must_start_u = must_start.upper()
        def _ready(d):
            section = d.find_element(By.XPATH, section_xpath)
            cells = section.find_elements(By.CSS_SELECTOR, "td.briefingText")
            for c in cells:
                txt = (c.get_attribute("textContent") or "").strip()
                if txt and txt.upper().startswith(must_start_u):
                    return True
            return False
        wait.until(_ready)

    def pick_from_section(section_xpath: str, prefix: str) -> str | None:
        section = driver.find_element(By.XPATH, section_xpath)
        cells = section.find_elements(By.CSS_SELECTOR, "td.briefingText")
        texts = [(c.get_attribute("textContent") or "").strip() for c in cells]
        texts = [t for t in texts if t]

        pref_u = prefix.upper()

        # Prefer station match
        for t in texts:
            up = t.upper()
            if up.startswith(pref_u) and station_u in up:
                return t

        # Fallback: Casement name (in case station shown as name)
        for t in texts:
            up = t.upper()
            if up.startswith(pref_u) and "CASEMENT" in up:
                return t

        # Fallback: first METAR/TAF in that section
        for t in texts:
            if t.upper().startswith(pref_u):
                return t

        return None

    # Wait until the sections are populated
    wait_section_has_text(metar_section_xpath, "METAR")
    wait_section_has_text(taf_section_xpath, "TAF")

    metar = pick_from_section(metar_section_xpath, "METAR")
    taf = pick_from_section(taf_section_xpath, "TAF")
    return metar, taf
