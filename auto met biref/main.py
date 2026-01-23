from datetime import datetime, timezone
from pathlib import Path

from collector.models import Briefing
from collector.providers.infared import InfraredProvider
from collector.providers.surface_pressure_provider import SurfacePressureProvider
from collector.providers.metweb_radar_provider import MetWebRadarProvider
from collector.providers.metie_briefing_provider import MetIeBriefingProvider





def main():
    briefing = Briefing(
        generated_at_utc=datetime.now(timezone.utc)
    )

    provider = InfraredProvider()
    provider.collect(
        briefing=briefing,
        out_dir=Path("out/charts/satellite"),
    )
    
    SurfacePressureProvider().collect(
        briefing=briefing,
        out_dir=Path("out/charts/surface_pressure"),
    )
    
    MetWebRadarProvider(headless=True).collect(
        briefing=briefing,
        out_dir=Path("out/charts/radar_ire_5min"),
        username="FTSOPS",
        password="FTSWX",
       
    )
    
    MetIeBriefingProvider(headless=True).collect(
        briefing=briefing,
        out_dir=Path("out"),
        station="EIME",
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
        
        print("Text assets:", [t.local_path for t in briefing.texts])
        print("Charts:", [c.local_path for c in briefing.charts])
        print("Notes:", briefing.notes)


if __name__ == "__main__":
    main()
