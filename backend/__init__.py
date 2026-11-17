"""Agentic Policy Data Analytics Platform - Backend Root Package.

Automatically injects the backend directory into sys.path so that 'app'
and its submodules can be discovered and imported consistently from any working
directory or execution context.
"""

from __future__ import annotations

import sys
from pathlib import Path

# Dynamically resolve backend directory
_BACKEND_DIR = str(Path(__file__).resolve().parent)
if _BACKEND_DIR not in sys.path:
    sys.path.insert(0, _BACKEND_DIR)
