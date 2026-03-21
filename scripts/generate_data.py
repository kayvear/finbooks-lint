"""
CLI wrapper for the DataGenPipeline.

Usage:
    python scripts/generate_data.py
    python scripts/generate_data.py --customers 100
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from finbooks.datagen.pipeline import main

if __name__ == "__main__":
    main()
