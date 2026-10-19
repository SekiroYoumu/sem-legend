"""Keep the full regression corpus separate from the curated GUI examples."""
from pathlib import Path
from .paths import ROOT

ARCHIVE=ROOT/'example_archive'/'original_user_examples'
ORIGINAL_EXAMPLES=ARCHIVE if ARCHIVE.is_dir() else ROOT/'example'
