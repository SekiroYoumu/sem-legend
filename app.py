"""Launch with python app.py. No server, browser, or GPU required."""
import sys
from pathlib import Path

vendor = Path(__file__).resolve().parent / '.vendor'
if vendor.is_dir():
    sys.path.insert(0, str(vendor))

from semlegend.gui import main

if __name__ == '__main__':
    if '--self-test' in sys.argv:
        from semlegend.selftest import run
        run(Path(sys.argv[sys.argv.index('--self-test') + 1]))
    else:
        main()
