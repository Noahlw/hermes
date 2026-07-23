"""Project pytest configuration."""
import sys
from pathlib import Path

# Make `orchestrator` importable as a package for tests without installing.
_PROJECT_ROOT = Path(__file__).resolve().parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))
