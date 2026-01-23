from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin
import random
import time

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


def _ext_from_url_or_type(url: str, content_type: str | None) -> str:
    ct = (content_type or "").split(";")[0].strip().lower()
    if ct == "image/png":
        return ".png"
    if ct == "image/jpeg":
        return ".jpg"
    if ct == "image/gif":
        return ".gif"
    u = url.lower()
    for ext in [".png", ".jpg", ".jpeg", ".gif", ".webp"]:
        if ext in u:
            return ".jpg" if ext == ".jpeg" else ext
    return ".bin"


@dataclass
class MetIeBriefingProvider:
    name: str = "metie_selfbrief"
    base_url: str = "https://briefing.met.ie/"
    briefing_url: str = "https://briefing.met.ie/custombriefing.php?id=35b36b9cc7030b98e7db8ce45edf2b5a"
    timeout_s: int = 30
    headless: bool = True

    # TEMPORARY: hardcoded credentials (remove later)
    username: str = "nathanmartin"
    password: str = "Label.Curious.Scared.Five"

    # Your provided XPaths
    metar_xpath: str = "/html/body/div/div[4]/table/tbody/tr[1]/td[2]"
    taf_xpath: str = "/html/body/div/div[6]/table/tbody/tr[1]/td[2]"
    sigwx_img_xpath: str = "/html/body/div/div[10]/table/tbody/tr[1]/td[2]/img"
    windtemp_img_xpath: str = "/html/body/div/div[11]/table/tbody/tr/td[2]/img"
    lowsigwx_img_xpath: str = "/html/body/div/div[12]/table/tbody/tr/td[2]/img"

    def collect(self, briefing: Briefing, out_dir: Path, station: str = "EIME") -> None:
        out_dir.mkdir(parents=True, exist_ok=True)
        now_utc = datetime.now(timezone.utc)

        charts_dir = out_dir / "charts" / self.name
        charts_dir.mkdir(parents=True, exist_ok=True)

        text_dir = out_dir / "text"
        text_dir.mkdir(parents=True, exist_ok=True)

        opts = Options()
        if self.headless:
            opts.add_argument("--headless")

        driver = webdriver.Firefox(
            service=Service(GeckoDriverManager().install()),
            options=opts,
        )

        try:
            wait = WebDriverWait(driver, self.timeout_s)

            # Go to briefing URL; if not logged in, page should show login form
            driver.get(self.briefing_url)

            # Login form (typical names); wait for presence
            user_el = wait.until(EC.presence_of_element_located((By.NAME, "username")))
            pass_el = wait.until(EC.presence_of_element_located((By.NAME, "password")))

            user_el.clear()
            _human_type(user_el, self.username)
            time.sleep(random.uniform(0.3, 0.8))

            pass_el.clear()
            _human_type(pass_el, self.password)
            time.sleep(random.uniform(0.4, 1.0))

            submit = wait.until(
                EC.element_to_be_clickable((By.XPATH, "//button[@type='submit'] | //input[@type='submit']"))
            )
            submit.click()

            # Return to the briefing page after login
            driver.get(self.briefing_url)

            # Wait for METAR field to exist (your XPath)
            metar_el = wait.until(EC.presence_of_element_located((By.XPATH, self.metar_xpath)))
            taf_el = wait.until(EC.presence_of_element_located((By.XPATH, self.taf_xpath)))

            metar_text = (metar_el.text or "").strip()
            taf_text = (taf_el.text or "").strip()

            # Write METAR/TAF to text file + TextAsset
            report = "\n".join([
                "Met Éireann Self Briefing",
                f"Generated (UTC): {now_utc.strftime('%Y-%m-%d %H:%M')}",
                f"Station: {station}",
                "",
                "METAR:",
                metar_text if metar_text else "(not found)",
                "",
                "TAF:",
                taf_text if taf_text else "(not found)",
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
                    extras={"station": station},
                )
            )

            # Build an authenticated requests session using Selenium cookies
            sess = requests.Session()
            for c in driver.get_cookies():
                sess.cookies.set(c["name"], c["value"])

            # Download charts by img XPath
            self._download_img_at_xpath(
                wait=wait,
                sess=sess,
                briefing=briefing,
                charts_dir=charts_dir,
                now_utc=now_utc,
                img_xpath=self.sigwx_img_xpath,
                display_name="SigWx Charts",
                kind="sigwx",
            )

            self._download_img_at_xpath(
                wait=wait,
                sess=sess,
                briefing=briefing,
                charts_dir=charts_dir,
                now_utc=now_utc,
                img_xpath=self.windtemp_img_xpath,
                display_name="Low Level Wind & Temp Charts",
                kind="wind_temp",
            )

            self._download_img_at_xpath(
                wait=wait,
                sess=sess,
                briefing=briefing,
                charts_dir=charts_dir,
                now_utc=now_utc,
                img_xpath=self.lowsigwx_img_xpath,
                display_name="Low Level Sig Weather Charts",
                kind="low_sigwx",
            )

        except Exception as e:
            briefing.notes.append(f"{self.name}: failed: {e}")

        finally:
            driver.quit()

    def _download_img_at_xpath(
        self,
        wait: WebDriverWait,
        sess: requests.Session,
        briefing: Briefing,
        charts_dir: Path,
        now_utc: datetime,
        img_xpath: str,
        display_name: str,
        kind: str,
    ) -> None:
        img_el = wait.until(EC.presence_of_element_located((By.XPATH, img_xpath)))
        src = img_el.get_attribute("src")
        if not src:
            briefing.notes.append(f"{self.name}: {display_name}: img src missing")
            return

        url = urljoin(self.base_url, src)

        try:
            r = sess.get(url, timeout=25)
            r.raise_for_status()
            content_type = r.headers.get("Content-Type", "")
            ext = _ext_from_url_or_type(url, content_type)
            filename = f"{kind}_{now_utc.strftime('%Y%m%d_%H%M%S')}{ext}"
            save_path = charts_dir / filename
            save_path.write_bytes(r.content)

            briefing.charts.append(
                ChartAsset(
                    name=display_name,
                    kind="chart",
                    original_url=url,
                    fetched_at_utc=now_utc,
                    local_path=str(save_path),
                    content_type=(content_type.split(";")[0].strip() or None),
                    source=self.name,
                    extras={"xpath": img_xpath},
                )
            )

        except Exception as e:
            briefing.notes.append(f"{self.name}: {display_name}: download failed: {e}")
