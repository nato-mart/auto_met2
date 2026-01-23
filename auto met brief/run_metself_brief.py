import sys
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, str(Path(__file__).resolve().parent))

from collector.models import Briefing
from collector.providers.metself_brief import MetSelfBriefProvider


def main():
    b = Briefing(generated_at_utc=datetime.now(timezone.utc))

    p = MetSelfBriefProvider(
    briefing_url="https://briefing.met.ie/custombriefing.php?id=35b36b9cc7030b98e7db8ce45edf2b5a",
    username="nathanmartin",
    password="Label.Curious.Scared.Five",
    headless=False,
    )

    p.collect(b, out_dir=Path("out"), station="EIME")
 
    print("Texts:", [t.local_path for t in b.texts])
    print("Charts:", len(b.charts))
    print("Notes:", b.notes)


if __name__ == "__main__":
    main()
