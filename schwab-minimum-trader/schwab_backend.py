"""Compatibility entry point; the integrated backend is maintained in data_service."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from data_service import schwab_backend as backend

if __name__ == '__main__':
    backend.main()
else:
    sys.modules[__name__] = backend
