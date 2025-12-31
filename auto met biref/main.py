from datetime import datetime, timezone
from pathlib import Path

from collector.models import Briefing
from collector.providers.infared import InfraredProvider


def main():
    briefing = Briefing(
        generated_at_utc=datetime.now(timezone.utc)
    )

    provider = InfraredProvider()
    provider.collect(
        briefing=briefing,
        out_dir=Path("out/charts/satellite"),
    )

    print("=== BRIEFING SUMMARY ===")
    print(f"Generated at: {briefing.generated_at_utc}")
    print(f"Charts collected: {len(briefing.charts)}")
    print(f"Notes: {briefing.notes}")

    for chart in briefing.charts:
        print()
        print(f"Name: {chart.name}")
        print(f"Source URL: {chart.original_url}")
        print(f"Saved to: {chart.local_path}")


if __name__ == "__main__":
    main()
