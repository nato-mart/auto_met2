from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from collector.models import Briefing, ChartAsset


@dataclass
class SurfacePressureProvider:
    name: str = "metoffice_surface_pressure"
    page_url: str = "https://weather.metoffice.gov.uk/maps-and-charts/surface-pressure"
    timeout_s: int = 20
    user_agent: str = "Mozilla/5.0"
    max_charts: int = 8  # chartColour0..chartColour7

    def collect(self, briefing: Briefing, out_dir: Path) -> None:
        out_dir.mkdir(parents=True, exist_ok=True)

        headers = {"User-Agent": self.user_agent}
        now_utc = datetime.now(timezone.utc)

        try:
            page = requests.get(self.page_url, headers=headers, timeout=self.timeout_s)
            page.raise_for_status()
            soup = BeautifulSoup(page.text, "html.parser")
        except Exception as e:
            briefing.notes.append(f"{self.name}: failed to fetch page: {e}")
            return

        downloaded = 0

        for i in range(self.max_charts):
            li = soup.find("li", id=f"chartColour{i}")
            if not li:
                continue

            img = li.find("img")
            if not img:
                continue

            src = img.get("src") or img.get("data-src")
            if not src:
                continue

            img_url = urljoin(self.page_url, src)

            asset = ChartAsset(
                name=f"Surface Pressure Chart {i}",
                kind="analysis",
                original_url=img_url,
                fetched_at_utc=now_utc,
                source=self.name,
                extras={"chart_index": i},
            )

            try:
                r = requests.get(img_url, headers=headers, timeout=self.timeout_s)
                r.raise_for_status()

                content_type = (r.headers.get("Content-Type", "").split(";")[0].strip() or "image/gif")
                ext = ".gif"
                if content_type == "image/jpeg":
                    ext = ".jpg"
                elif content_type == "image/png":
                    ext = ".png"
                elif content_type == "image/webp":
                    ext = ".webp"

                save_path = out_dir / f"spc_{i}{ext}"
                save_path.write_bytes(r.content)

                asset.local_path = str(save_path)
                asset.content_type = content_type
                downloaded += 1

            except Exception as e:
                briefing.notes.append(f"{self.name}: failed chart {i}: {e}")

            briefing.charts.append(asset)

        if downloaded == 0:
            briefing.notes.append(f"{self.name}: no charts downloaded (page structure may have changed)")
