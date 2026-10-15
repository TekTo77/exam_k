"""Запускает импорт из модуля 1."""
from pathlib import Path
import runpy
import sys

folder = Path(__file__).resolve().parent / "Module_1_Database"
sys.path.insert(0, str(folder))
if __name__ == "__main__":
    runpy.run_path(str(folder / "main.py"), run_name="__main__")
