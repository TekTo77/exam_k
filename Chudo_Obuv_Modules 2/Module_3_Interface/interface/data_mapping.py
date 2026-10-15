"""Простой выбор таблиц и колонок. Папка фото настраивается в design.py."""

import tkinter as tk
from tkinter import messagebox, ttk

from config import COLORS, EXTRA_PRODUCT_FIELDS
from interface.widgets import scrollable_form
from preferences import read_settings, write_settings

FIELDS = {
    "products": {
        "product_id": "ID товара *",
        "product_name": "Название *",
        "price": "Цена *",
        "category": "Категория",
        "subcategory": "Подкатегория",
        "manufacturer": "Производитель",
        "description": "Описание",
        "composition": "Состав",
        "image_path": "Имя файла фото",
        "quantity_available": "Остаток в товаре",
    },
    "users": {
        "user_id": "ID пользователя *",
        "login": "Логин *",
        "last_name": "Фамилия",
        "first_name": "Имя",
        "middle_name": "Отчество",
        "role_name": "Роль (текст)",
        "role_id": "ID роли",
    },
}
FIELDS["products"].update(
    {key: value.get("label", key) for key, value in EXTRA_PRODUCT_FIELDS.items()}
)
REQUIRED = {
    "products": ("product_id", "product_name", "price"),
    "users": ("user_id", "login"),
}
EMPTY = "— Не используется —"


class DataSettings(tk.Toplevel):
    def __init__(self, app, on_saved):
        super().__init__(app)
        self.app, self.on_saved = app, on_saved
        self.title("Настройка данных")
        self.configure(bg=COLORS["background"])
        self.geometry("570x400")
        self.minsize(520, 380)
        self.transient(app)
        self.grab_set()
        self.tables, self.fields, self.boxes = {}, {}, {}
        self.optional_widgets = []
        self.show_optional = tk.BooleanVar(value=False)
        ttk.Label(
            self,
            text="Выбери таблицу и нужные колонки.\nКнопка «Авто» подберёт колонки по названиям.",
            style="Subtitle.TLabel",
        ).pack(anchor="w", padx=18, pady=(16, 8))
        notebook = ttk.Notebook(self)
        notebook.pack(fill="both", expand=True, padx=18, pady=8)
        for domain, title in (("products", "Товары"), ("users", "Пользователи")):
            page = ttk.Frame(notebook)
            notebook.add(page, text=title)
            tab = scrollable_form(page)
            tab.columnconfigure(1, weight=1)
            ttk.Label(tab, text="Таблица").grid(
                row=0, column=0, sticky="w", pady=(0, 10), padx=(0, 14)
            )
            table_var = tk.StringVar(value=app.database._domain_table(domain) or EMPTY)
            self.tables[domain] = table_var
            table_box = ttk.Combobox(
                tab,
                textvariable=table_var,
                state="readonly",
                values=[EMPTY] + app.database.available_tables,
            )
            table_box.grid(row=0, column=1, sticky="ew", pady=(0, 10))
            self.fields[domain], self.boxes[domain] = {}, {}
            for row, (field, label) in enumerate(FIELDS[domain].items(), 1):
                caption = ttk.Label(tab, text=label)
                caption.grid(row=row, column=0, sticky="w", pady=4, padx=(0, 14))
                variable = tk.StringVar(
                    value=app.database._domain_column(domain, field) or EMPTY
                )
                self.fields[domain][field] = variable
                box = ttk.Combobox(tab, textvariable=variable, state="readonly")
                box.grid(row=row, column=1, sticky="ew", pady=4)
                self.boxes[domain][field] = box
                if field not in REQUIRED[domain]:
                    self.optional_widgets.extend((caption, box))
            self.update_columns(domain, keep=True)
            table_box.bind(
                "<<ComboboxSelected>>", lambda event, d=domain: self.update_columns(d)
            )
        ttk.Checkbutton(
            self,
            text="Дополнительные поля",
            variable=self.show_optional,
            command=self.toggle_optional,
        ).pack(anchor="w", padx=18, pady=4)
        ttk.Label(
            self, text="* Обязательные поля выбранной таблицы.", style="Subtitle.TLabel"
        ).pack(anchor="w", padx=18)
        actions = ttk.Frame(self)
        actions.pack(fill="x", padx=18, pady=(12, 18))
        ttk.Button(actions, text="Авто", command=self.reset).pack(side="left")
        ttk.Button(actions, text="Отмена", command=self.destroy).pack(side="right")
        ttk.Button(
            actions, text="Сохранить", style="Accent.TButton", command=self.save
        ).pack(side="right", padx=8)
        self.toggle_optional()

    def toggle_optional(self):
        for widget in self.optional_widgets:
            widget.grid() if self.show_optional.get() else widget.grid_remove()
        self.geometry("570x650" if self.show_optional.get() else "570x400")

    def update_columns(self, domain, keep=False):
        table = self.tables[domain].get()
        columns = (
            sorted(self.app.database._table_columns(table)) if table != EMPTY else []
        )
        automatic = self.app.database.suggest_columns(domain, columns)
        for field, box in self.boxes[domain].items():
            box.configure(values=[EMPTY] + columns)
            if not keep:
                self.fields[domain][field].set(automatic.get(field) or EMPTY)

    def reset(self):
        # Ничего не записываем до нажатия «Сохранить».
        for domain in FIELDS:
            self.update_columns(domain)

    def save(self):
        mapping = {}
        for domain in FIELDS:
            table = self.tables[domain].get()
            if table == EMPTY:
                mapping[domain] = None
                continue
            fields = {
                field: (v.get() if v.get() != EMPTY else None)
                for field, v in self.fields[domain].items()
            }
            for field in REQUIRED[domain]:
                if not fields[field]:
                    messagebox.showerror(
                        "Не хватает поля",
                        f"Выберите колонку: {FIELDS[domain][field]}",
                        parent=self,
                    )
                    return
            columns = self.app.database._table_columns(table)
            if any(column and column not in columns for column in fields.values()):
                messagebox.showerror(
                    "Таблица изменилась",
                    "Обновите выбор таблицы и колонок.",
                    parent=self,
                )
                return
            mapping[domain] = {"table": table, "columns": fields}
        try:
            settings = read_settings()
            mappings = settings.setdefault("mappings", {})
            mappings[self.app.database.mapping_key] = {
                **mappings.get(self.app.database.mapping_key, {}),
                **mapping,
            }
            write_settings(settings)
            self.app.database._refresh_domain_mapping()
        except (OSError, ValueError) as error:
            messagebox.showerror("Настройки", str(error), parent=self)
            return
        self.destroy()
        self.on_saved()
