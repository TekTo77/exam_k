"""Запускает полную версию из модуля 4."""
from pathlib import Path
import runpy
import sys

folder = Path(__file__).resolve().parent / "Module_4_Orders"
sys.path.insert(0, str(folder))
if __name__ == "__main__":
    runpy.run_path(str(folder / "main.py"), run_name="__main__")
