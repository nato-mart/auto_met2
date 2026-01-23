from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional
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

from collector.models import Briefing, ChartAsset


def _human_type(element, text: str, min_delay: float = 0.08, max_delay: float = 0.18) -> None:
    """
    Send keys character-by-character with random delays to reduce bot-like behaviour.
    """
    for ch in text:
        element.send_keys(ch)
        time.sleep(random.uniform(min_delay, max_delay))


@dataclass
class MetWebRadarProvider:
    """
    Logs in to metweb.ie and downloads the latest 5-min IRE radar image.
    """
    name: str = "metweb_radar_5min_ire"
    login_url: str = "https://www.metweb.ie/login"
    home_url: str = "https://www.metweb.ie/home-page"
    timeout_s: int = 25
    headless: bool = True

    # Credentials (pass in via collect() or set defaults). Prefer env vars in production.
    username: Optional[str] = None
    password: Optional[str] = None

    def collect(self, briefing: Briefing, out_dir: Path, username: str, password: str) -> None:
        out_dir.mkdir(parents=True, exist_ok=True)
        now_utc = datetime.now(timezone.utc)

        opts = Options()
        opts.headless = self.headless
        if self.headless:
            opts.add_argument("--headless")

        driver = webdriver.Firefox(
            service=Service(GeckoDriverManager().install()),
            options=opts,
        )

        try:
            wait = WebDriverWait(driver, self.timeout_s)

            # 1) Open login page
            driver.get(self.login_url)

            # 2) Wait for fields, then type slowly
            user_el = wait.until(EC.presence_of_element_located((By.NAME, "username")))
            pass_el = wait.until(EC.presence_of_element_located((By.NAME, "password")))

            user_el.clear()
            _human_type(user_el, username)

            # brief pause between fields
            time.sleep(random.uniform(0.3, 0.8))

            pass_el.clear()
            _human_type(pass_el, password)

            # pause before clicking login
            time.sleep(random.uniform(0.4, 1.0))

            # 3) Submit
            login_btn = wait.until(EC.element_to_be_clickable((By.XPATH, "//button[@type='submit']")))
            login_btn.click()

            # 4) Confirm login by navigating to home page and waiting for nav
            driver.get(self.home_url)
            wait.until(EC.presence_of_element_located((By.CSS_SELECTOR, "nav")))

            # 5) Navigate to Observations -> Radar -> (5min): IRE
            #
            # Your earlier script used XPaths; they work but are brittle.
            # If metweb changes markup, you may need to adjust selectors.
            #
            obs_xpath = "/html/body/div[2]/header/div/nav[2]/ul/li[2]/a"
            radar_xpath = "/html/body/div[2]/header/div/nav[2]/ul/li[2]/ul/li[3]"
            ire_xpath = "/html/body/div[2]/header/div/nav[2]/ul/li[2]/ul/li[3]/ul/li[1]/a"

            obs = wait.until(EC.element_to_be_clickable((By.XPATH, obs_xpath)))
            driver.execute_script("arguments[0].scrollIntoView(true);", obs)
            time.sleep(random.uniform(0.2, 0.6))
            driver.execute_script("arguments[0].click();", obs)

            radar = wait.until(EC.element_to_be_clickable((By.XPATH, radar_xpath)))
            driver.execute_script("arguments[0].scrollIntoView(true);", radar)
            time.sleep(random.uniform(0.2, 0.6))
            driver.execute_script("arguments[0].click();", radar)

            ire = wait.until(EC.element_to_be_clickable((By.XPATH, ire_xpath)))
            driver.execute_script("arguments[0].scrollIntoView(true);", ire)
            time.sleep(random.uniform(0.2, 0.6))
            driver.execute_script("arguments[0].click();", ire)

            # 6) Wait for the radar image
            # From your previous code: image element XPath below.
            image_xpath = "/html/body/div[2]/div[1]/div/div/div[2]/article/section/div[1]/img"
            img_el = wait.until(EC.presence_of_element_located((By.XPATH, image_xpath)))

            img_src = img_el.get_attribute("src")
            if not img_src:
                briefing.notes.append(f"{self.name}: radar img src not found")
                return

            # Normalize absolute URL
            if img_src.startswith("/"):
                img_url = "https://www.metweb.ie" + img_src
            else:
                img_url = img_src

            # 7) Download using requests session with Selenium cookies
            sess = requests.Session()
            for c in driver.get_cookies():
                sess.cookies.set(c["name"], c["value"])

            r = sess.get(img_url, timeout=20)
            r.raise_for_status()

            # 8) Save file and emit ChartAsset
            # Attempt to parse timestamp from URL; fallback to now_utc
            # URL often contains ..._YYYYMMDDHHMM_...png
            ts_hint = None
            try:
                parts = img_url.split("_")
                if len(parts) >= 2:
                    ts_hint = parts[-2]  # e.g. 202504021705
            except Exception:
                pass

            filename = "radar_5min_ire.png"
            if ts_hint and ts_hint.isdigit() and len(ts_hint) == 12:
                filename = f"radar_5min_ire_{ts_hint}.png"

            save_path = out_dir / filename
            save_path.write_bytes(r.content)

            briefing.charts.append(
                ChartAsset(
                    name="MetWeb Radar 5-min IRE (Latest)",
                    kind="radar",
                    original_url=img_url,
                    fetched_at_utc=now_utc,
                    local_path=str(save_path),
                    content_type="image/png",
                    source=self.name,
                    extras={"url_src": img_src, "timestamp_hint": ts_hint},
                )
            )

        except Exception as e:
            briefing.notes.append(f"{self.name}: failed: {e}")

        finally:
            driver.quit()
