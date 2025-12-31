from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

from collector.models import Briefing, ChartAsset


@dataclass
class InfraredProvider:
    """
    Downloads the latest available Met Éireann Ireland IR satellite image by
    trying the deterministic image URLs and stepping back in 15-minute increments.
    """
    name: str = "met_ie_infrared"
    base_url: str = "https://www.met.ie/images/satellite"
    step_minutes: int = 15
    max_steps: int = 32          # 32 * 15min = 8 hours back-search
    timeout_s: int = 15

    def collect(self, briefing: Briefing, out_dir: Path) -> None:
        out_dir.mkdir(parents=True, exist_ok=True)
        now_utc = datetime.now(timezone.utc)

        # round down to nearest 15 minutes
        minute = (now_utc.minute // self.step_minutes) * self.step_minutes
        t = now_utc.replace(minute=minute, second=0, microsecond=0)

        session = requests.Session()

        last_error = None

        for _ in range(self.max_steps + 1):
            ymd = t.strftime("%Y%m%d")
            hm = t.strftime("%H%M")
            url = f"{self.base_url}/web17_sat_irl_ir_{ymd}{hm}.jpeg"

            asset = ChartAsset(
                name=f"Ireland IR Satellite {hm}Z (Latest Found)",
                kind="satellite",
                original_url=url,
                fetched_at_utc=now_utc,
                source=self.name,
                extras={"candidate_time_utc": t.isoformat()},
            )

            try:
                r = session.get(url, timeout=self.timeout_s, allow_redirects=True)
                if r.status_code == 404:
                    t -= timedelta(minutes=self.step_minutes)
                    continue

                r.raise_for_status()

                save_path = out_dir / f"ireland_ir_{ymd}_{hm}.jpeg"
                save_path.write_bytes(r.content)

                asset.local_path = str(save_path)
                asset.content_type = "image/jpeg"

                briefing.charts.append(asset)
                return  # success: stop after first valid image

            except Exception as e:
                last_error = e
                t -= timedelta(minutes=self.step_minutes)

        briefing.notes.append(
            f"{self.name}: no IR image found in last {self.max_steps*self.step_minutes} minutes"
            + (f" (last error: {last_error})" if last_error else "")
        )
