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

# Правила импорта находятся в Module_1_Database/config.py.

# Подстройка под другую тему. После изменения перезапусти приложение.
PRODUCT_VARIANTS_ENABLED = "auto"  # True: размеры/варианты, False: обычный товар.
STOCK_MODE = "auto"  # "separate", "product", "none" или "auto".
ORDERS_ENABLED = "auto"  # False: только каталог, без корзины и заказов.
CREATE_COMPATIBILITY_TABLES = False  # Не создавать пустые обувные таблицы.
DATABASE_LOOKUPS = {}  # Поля каталога из справочников; примеры в README.
INSERT_DEFAULTS = {}  # Дополнительные обязательные поля новых заказов.
DATE_INPUT_FORMATS = ("%d.%m.%Y", "%d.%m.%Y %H:%M:%S")

ROLE_ALIASES = {}  # Например {"директор": "Администратор"}.
