"""CLI wrapper for canonical website enrichment."""

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
AGENT_ROOT = ROOT / "agent"
if str(AGENT_ROOT) not in sys.path:
    sys.path.insert(0, str(AGENT_ROOT))

from canonical.website_enrichment import main  # noqa: E402


if __name__ == "__main__":
    main()
