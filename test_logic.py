"""Compatibility entry point. Run isolated regression tests with pytest."""
import subprocess
import sys
from pathlib import Path

if __name__ == '__main__':
    raise SystemExit(subprocess.call([sys.executable, '-m', 'pytest', '-q'], cwd=Path(__file__).parent))
