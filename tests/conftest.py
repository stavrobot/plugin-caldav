import sys
from pathlib import Path

# helpers.py lives in the plugin root, one level above tests/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
