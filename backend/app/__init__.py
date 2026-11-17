"""Agentic Policy Data Analytics Platform backend package.

Automatically ensures that the backend root directory (parent of app) is in
sys.path so that absolute imports within the 'app' hierarchy ('from app.xxx import yyy')
resolve seamlessly regardless of current working directory or entry point.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Dynamically resolve backend directory (parent of app)
_BACKEND_DIR = str(Path(__file__).resolve().parent.parent)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)
