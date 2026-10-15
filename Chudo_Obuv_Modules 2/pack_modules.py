"""Собирает самостоятельные модули задания."""
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED

root = Path(__file__).resolve().parent
output = root / "dist"
output.mkdir(exist_ok=True)
for folder in ("Module_1_Database", "Module_2_Catalog", "Module_3_Interface", "Module_4_Orders", "Module_5_Analytics"):
    source = root / folder
    with ZipFile(output / (folder + ".zip"), "w", ZIP_DEFLATED) as archive:
        for path in sorted(source.rglob("*")):
            if not path.is_file() or any(part in {".venv", "__pycache__", ".git"} for part in path.parts) or path.suffix in {".pyc", ".pyo"} or path.name == ".DS_Store" or path.name.startswith("._"):
                continue
            archive.write(path, Path(folder) / path.relative_to(source))
        if folder != "Module_5_Analytics":
            archive.write(root / "postgres_connection.json", Path(folder) / "postgres_connection.json")
        archive.write(root / "INSTRUCTION.md", Path(folder) / "INSTRUCTION.md")
    print(output / (folder + ".zip"))
