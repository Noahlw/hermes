"""``python -m hermes_agent`` entrypoint."""

from __future__ import annotations

import sys

from hermes_agent.main import main

if __name__ == "__main__":
    sys.exit(main())