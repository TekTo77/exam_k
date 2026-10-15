"""Настройки оформления. Примеры и запуск — в README.md."""

from pathlib import Path

PROJECT_DIR = Path(__file__).resolve().parent
APP_TITLE = "Чудо Обувь — система оформления заказов"
BRAND_NAME = "ЧУДО ОБУВЬ"
FONT_FAMILY = "Calibri"
FONT_SIZES = {
    "small": 9,
    "body": 10,
    "emphasis": 11,
    "card_title": 12,
    "login_title": 15,
    "title": 18,
    "brand": 20,
}
WINDOW = {
    "size": (1120, 760),
    "minimum": (900, 620),
    "import_size": (940, 700),
    "import_minimum": (820, 560),
}
SPACING = {
    "page": 24,
    "card_gap": 10,
    "header_top": 18,
    "header_bottom": 12,
    "login_x": 42,
    "login_y": 32,
    "button": (12, 7),
    "table_row": 36,
}
COLORS = {
    "background": "#F4F8F7",
    "surface": "#FFFFFF",
    "secondary": "#E2F4EC",
    "secondary_hover": "#CBEBDD",
    "accent": "#3E8C78",
    "accent_dark": "#286B5B",
    "on_accent": "#FFFFFF",
    "border": "#D8E6E0",
    "danger": "#C65757",
    "danger_dark": "#A83F3F",
    "low_stock": "#FF8080",
    "low_stock_background": "#FFF0F0",
    "text": "#1F2933",
    "muted": "#667085",
}

# Логотип и иконка. None убирает изображение.
LOGO_PATH = PROJECT_DIR / "assets" / "logo.png"
WINDOW_ICON_PATH = None  # например PROJECT_DIR / "assets" / "icon.png"
LOGO_SIZES = {"login": (150, 100), "header": (42, 42)}
DEFAULT_IMAGES_FOLDER = "images"
IMAGE_FIT = "contain"  # contain — целиком; cover — обрезать до размеров панели
IMAGE_CACHE_SIZE = 96

CURRENCY = "₽"  # Это подпись, не конвертация цен в БД.
QUANTITY_UNIT = "пар"
VARIANT_LABEL = "Размер"
LOW_STOCK_THRESHOLD = 3

# Только настройка разработчика: переключателя в приложении нет.
PRODUCT_CARD_LAYOUT = "list"  # "grid" — плитки; "list" — строки
PRODUCT_CARD_MIN_WIDTH = 325
CARD = {
    "grid": {
        "width": 310,
        "minimum_height": 475,
        "image": (270, 170),
        "wrap": 270,
        "padding": 18,
        "show_image": True,
        "eyebrow": "МОДЕЛЬ ОБУВИ",
        "title": "{product_name}",
    },
    "list": {
        "width": 800,
        "minimum_height": 0,
        "image": (190, 145),
        "wrap": 420,
        "padding": 18,
        "show_image": True,
        "eyebrow": "",
        "title": "{manufacturer} | {product_name}",
    },
}
# Строки карточек по порядку. Новые поля объявляются в config.py.
CARD_FIELDS = (
    {
        "template": "{category} · {manufacturer}",
        "fields": ("category", "manufacturer"),
        "layout": "grid",
        "style": "muted",
        "hide_empty": True,
    },
    {
        "template": "Категория: {category}",
        "fields": ("category",),
        "layout": "list",
        "style": "muted",
        "hide_empty": True,
    },
    {
        "template": "Осталось: {total_quantity} {unit}",
        "layout": "grid",
        "style": "stock",
    },
    {
        "template": "Количество: {total_quantity} {unit}",
        "layout": "list",
        "style": "stock",
    },
    {
        "template": "Состав: {composition}",
        "fields": ("composition",),
        "layout": "list",
        "style": "muted",
        "hide_empty": True,
    },
)
DETAIL_FIELDS = (
    {
        "template": "Производство: {manufacturer}",
        "fields": ("manufacturer",),
        "hide_empty": True,
    },
    {
        "template": "Категория: {category} / {subcategory}",
        "fields": ("category", "subcategory"),
        "hide_empty": True,
    },
    {
        "template": "Состав: {composition}",
        "fields": ("composition",),
        "hide_empty": True,
    },
    {
        "template": "Описание: {description}",
        "fields": ("description",),
        "hide_empty": True,
    },
    {"template": "Цена: {price_text}"},
)
DETAIL_IMAGE_SIZE = (280, 280)
DETAIL_TEXT_WIDTH = 480

# (ключ данных экрана, подпись, ширина). Можно менять порядок/убирать колонки.
ORDER_COLUMNS = {
    "orders": (
        ("id", "№", 70),
        ("date", "Дата заказа", 145),
        ("client", "ФИО клиента", 420),
        ("total", "Итого", 160),
    ),
    "items": (
        ("product", "Модель и производство", 410),
        ("size", VARIANT_LABEL, 80),
        ("quantity", QUANTITY_UNIT.capitalize(), 70),
        ("price", "Цена за единицу", 165),
        ("total", "Сумма", 150),
    ),
}

# Подписи экранов и кнопок.
TEXTS = {
    "login_title": "Вход в систему",
    "login_hint": "Введите логин из списка пользователей. Пароль не требуется.",
    "login_source": "Пользователи и роли загружаются из подключённой базы данных.",
    "login": "Войти",
    "guest": "Продолжить без входа",
    "logout": "Выйти",
    "catalog": "Каталог обуви",
    "product": "Карточка товара",
    "details": "Подробнее",
    "data_settings": "Настройка данных…",
    "refresh": "Обновить",
    "search": "Поиск:",
    "category": "Категория:",
    "sort": "Сортировка:",
    "cart": "Корзина",
    "cart_count": "Корзина ({count})",
    "orders": "Заказы",
    "my_orders": "Мои заказы",
    "orders_list": "Список заказов",
    "new_order": "Новый заказ",
    "order_detail": "Состав заказа №{order_id}",
    "order_edit": "Редактирование заказа №{order_id}",
    "back": "Назад",
    "back_catalog": "Назад к каталогу",
    "back_orders": "Назад к заказам",
    "add_order": "Добавить в заказ",
    "cancel_order": "Отменить заказ",
    "confirm_order": "Подтвердить заказ",
    "open_order": "Открыть состав",
    "delete_order": "Удалить заказ",
    "edit_order": "Редактировать заказ",
    "save": "Сохранить",
    "delete": "Удалить",
    "save_changes": "Сохранить изменения",
    "price": "Цена: {price}",
    "total": "Итого: {price}",
    "quantity": "Количество ({unit}):",
    "variants": "{variant}: доступные варианты и количество",
    "select_variant": "Выберите доступный вариант: {variant}.",
    "item_variant": "{name} — {manufacturer} · {variant} {value}",
    "item_edit": "{name} — {manufacturer}, {variant} {value}, {quantity} {unit} по {price}",
    "order_selection_hint": "Выберите позицию, чтобы увидеть полное название модели.",
    "catalog_empty": "Товары не найдены. Проверьте поиск и выбор таблицы в «Данные и фото».",
}

# Изображение при отсутствии фотографии товара.
PLACEHOLDER_PATH = PROJECT_DIR / "assets" / "picture.png"
