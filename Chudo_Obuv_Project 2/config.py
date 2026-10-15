from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
# Оформление редактируется в design.py.
from design import (
    APP_TITLE,
    COLORS,
    FONT_FAMILY,
    LOGO_PATH,
    PRODUCT_CARD_LAYOUT,
    PRODUCT_CARD_MIN_WIDTH,
)

# Новые поля каталога. Пример с автором книги — в README.md.
EXTRA_PRODUCT_FIELDS = {}

# Скидка без заказов за прошлый месяц. "0" отключает её.
NEW_PRODUCT_DISCOUNT = "0.25"

# Свои таблицы и колонки. Неуказанные поля определяются автоматически.
DATABASE_MAPPINGS = {}

# Правила импорта Excel.
IMPORT_REFERENCE_RULES = (
    {
        "parent_table": "users",
        "child_table": "orders",
        "column": "user_id",
        "parent_fields": (
            ("last_name", "фамилия"),
            ("first_name", "имя"),
            ("middle_name", "отчетсво", "отчество"),
        ),
        "child_fields": (("client_name", "фио", "фио_клиента", "покупатель"),),
        "existing_columns": (
            "user_id",
            "id_user",
            "idusers",
            "клиент_id",
            "пользователь_id",
        ),
    },
)


IMPORT_TABLE_RULES = {}

IMPORT_FOREIGN_KEYS = ()

IMPORT_AUTO_FOREIGN_KEYS = True

IMPORT_HEADER_ROWS = {}


# Подстройка под другую тему. После изменения перезапусти приложение.
PRODUCT_VARIANTS_ENABLED = "auto"  # True: размеры/варианты, False: обычный товар.
STOCK_MODE = "auto"  # "separate", "product", "none" или "auto".
ORDERS_ENABLED = "auto"  # False: только каталог, без корзины и заказов.
CREATE_COMPATIBILITY_TABLES = False  # Не создавать пустые обувные таблицы.
DATABASE_LOOKUPS = {}  # Поля каталога из справочников; примеры в README.
INSERT_DEFAULTS = {}  # Дополнительные обязательные поля новых заказов.
DATE_INPUT_FORMATS = ("%d.%m.%Y", "%d.%m.%Y %H:%M:%S")

ROLE_ALIASES = {}  # Например {"директор": "Администратор"}.
