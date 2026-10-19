"""Separate bundled resources from the portable app's writable directory."""
import sys
from pathlib import Path

RESOURCE_ROOT = Path(__file__).resolve().parent.parent
ROOT = Path(sys.executable).resolve().parent if getattr(sys, 'frozen', False) else RESOURCE_ROOT
