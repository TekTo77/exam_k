from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from storage.repository import Database

if __name__ == "__main__":
    database = Database()
    print("Подключение к PostgreSQL успешно. Таблицы доступны.")
    database.close()
