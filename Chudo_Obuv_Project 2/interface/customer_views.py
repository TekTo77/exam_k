"""Модуль 3: вход, товар и корзина."""

from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from datetime import date
from decimal import Decimal
from storage.order_operations import size_text, as_date

from config import COLORS
from design import (
    BRAND_NAME,
    SPACING,
    LOGO_SIZES,
    DETAIL_FIELDS,
    DETAIL_IMAGE_SIZE,
    DETAIL_TEXT_WIDTH,
)
from interface.formatting import font, text, money, field_rows, product_context
from interface.pictures import image_panel
from interface.widgets import (
    clear_frame,
    add_logo,
    make_header,
    show_error,
    show_info,
    show_warning,
)


from interface.row_helpers import row_value


class LoginFrame(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        wrapper = tk.Frame(
            self,
            bg=COLORS["surface"],
            highlightbackground=COLORS["border"],
            highlightthickness=1,
            padx=SPACING["login_x"],
            pady=SPACING["login_y"],
        )
        wrapper.place(relx=0.5, rely=0.5, anchor="center")
        add_logo(wrapper, LOGO_SIZES["login"], pady=(0, 14))
        tk.Label(
            wrapper,
            text=BRAND_NAME,
            bg=COLORS["surface"],
            fg=COLORS["accent_dark"],
            font=font("brand", True),
        ).pack(pady=(0, 4))
        tk.Label(
            wrapper,
            text=text("login_title"),
            bg=COLORS["surface"],
            fg=COLORS["text"],
            font=font("login_title", True),
        ).pack(pady=(0, 6))
        tk.Label(
            wrapper,
            text=text("login_hint"),
            bg=COLORS["surface"],
            fg=COLORS["muted"],
            font=font("body"),
            wraplength=330,
        ).pack(pady=(0, 16))
        self.login_value = tk.StringVar()
        entry = ttk.Entry(wrapper, textvariable=self.login_value, width=34)
        entry.pack(pady=5)
        entry.focus_set()
        ttk.Button(
            wrapper, text=text("login"), style="Accent.TButton", command=self.submit
        ).pack(fill="x", pady=(10, 6))
        ttk.Button(wrapper, text=text("guest"), command=self.guest).pack(fill="x")
        ttk.Button(
            wrapper, text=text("data_settings"), command=app.show_data_settings
        ).pack(fill="x", pady=(12, 0))
        entry.bind("<Return>", lambda event: self.submit())

    def submit(self):
        login = self.login_value.get().strip()
        if not login:
            show_error("Ошибка входа", "Введите логин пользователя.")
            return
        try:
            user = self.app.database.find_user_by_login(login)
        except Exception as error:
            show_error(
                "Ошибка базы данных", f"Не удалось проверить пользователя:\n{error}"
            )
            return
        if not user:
            show_error(
                "Ошибка входа",
                "Пользователь с таким логином не найден. Проверьте написание и попробуйте снова.",
            )
            return
        self.app.login(user)

    def guest(self):
        self.app.login(None)


class ProductFrame(ttk.Frame):
    def __init__(self, parent, app, product_id: int, order_mode: bool = False):
        super().__init__(parent)
        self.app = app
        self.product_id = product_id
        self.order_mode = order_mode
        product = app.database.product(product_id)
        if not product:
            show_error("Ошибка", "Товар не найден в базе данных.")
            app.show_catalog(order_mode)
            return
        make_header(self, text("product"), app.user_text(), app.logout)
        actions = ttk.Frame(self)
        actions.pack(side="bottom", fill="x", padx=30, pady=20)
        canvas = tk.Canvas(self, bg=COLORS["background"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=canvas.yview)
        scrollbar.pack(side="right", fill="y", padx=(0, 20), pady=10)
        canvas.pack(fill="both", expand=True, padx=(30, 8), pady=10)
        canvas.configure(yscrollcommand=scrollbar.set)
        body = ttk.Frame(canvas)
        window = canvas.create_window((0, 0), window=body, anchor="nw")
        body.bind(
            "<Configure>",
            lambda event: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.bind(
            "<Configure>", lambda event: canvas.itemconfigure(window, width=event.width)
        )
        left = ttk.Frame(body)
        left.pack(side="left", anchor="n", padx=(0, 24))
        image_panel(
            left,
            app.images,
            row_value(product, "image_path"),
            DETAIL_IMAGE_SIZE,
            COLORS["surface"],
        ).pack()
        right = ttk.Frame(body)
        right.pack(side="left", fill="both", expand=True)
        ttk.Label(
            right,
            text=product["product_name"],
            style="Title.TLabel",
            wraplength=DETAIL_TEXT_WIDTH,
        ).pack(anchor="w")
        discount = app.database.discount_info(product_id)
        values = product_context(product, discount["price"], discount)
        for value, _ in field_rows(DETAIL_FIELDS, values):
            ttk.Label(right, text=value, wraplength=DETAIL_TEXT_WIDTH).pack(
                anchor="w", pady=5
            )
        if discount["applied"]:
            ttk.Label(
                right,
                text=f"Без скидки: {values['original_price_text']} · {values['discount_text']}",
                wraplength=DETAIL_TEXT_WIDTH,
            ).pack(anchor="w", pady=5)
        ttk.Label(
            right,
            text=discount["reason"],
            style="Subtitle.TLabel",
            wraplength=DETAIL_TEXT_WIDTH,
        ).pack(anchor="w", pady=(5, 10))
        if app.database.variants_enabled:
            ttk.Label(right, text=text("variants"), font=font("emphasis", True)).pack(
                anchor="w", pady=(15, 5)
            )
        self.size_value = tk.StringVar()
        sizes = app.database.product_sizes(product_id)
        size_values = [
            f"{size_text(row['size_value'])}"
            + (
                f" (доступно: {row['quantity_available']})"
                if row["quantity_available"] is not None
                else ""
            )
            for row in sizes
            if row["quantity_available"] is None or row["quantity_available"] > 0
        ]
        self.size_rows = [
            row
            for row in sizes
            if row["quantity_available"] is None or row["quantity_available"] > 0
        ]
        self.size_box = ttk.Combobox(
            right,
            textvariable=self.size_value,
            values=size_values,
            state="readonly",
            width=32,
        )
        if app.database.variants_enabled:
            self.size_box.pack(anchor="w")
        if len(self.size_rows) == 1:
            self.size_box.current(0)
        if not app.database.variants_enabled and self.size_rows:
            available = self.size_rows[0]["quantity_available"]
            if available is not None:
                ttk.Label(right, text=f"Доступно: {available}").pack(anchor="w")
        ttk.Label(right, text=text("quantity")).pack(anchor="w", pady=(10, 2))
        self.quantity_value = tk.StringVar(value="1")
        ttk.Spinbox(
            right, from_=1, to=999, textvariable=self.quantity_value, width=8
        ).pack(anchor="w")
        ttk.Button(
            actions, text=text("back"), command=lambda: app.show_catalog(order_mode)
        ).pack(side="left")
        if app.can_order():
            ttk.Button(
                actions,
                text=text("add_order"),
                style="Accent.TButton",
                command=self.add_to_cart,
            ).pack(side="right")

        def scroll(event):
            if event.delta:
                canvas.yview_scroll(-1 if event.delta > 0 else 1, "units")

        def bind_scroll(widget):
            widget.bind("<MouseWheel>", scroll)
            for child in widget.winfo_children():
                bind_scroll(child)

        bind_scroll(body)
        canvas.bind("<MouseWheel>", scroll)

    def add_to_cart(self):
        if self.app.database.variants_enabled and not self.size_value.get():
            show_error("Ошибка выбора", text("select_variant"))
            return
        try:
            quantity = int(self.quantity_value.get())
        except ValueError:
            show_error(
                "Ошибка количества",
                "Количество должно быть положительным целым числом.",
            )
            return
        if quantity <= 0:
            show_error("Ошибка количества", "Количество должно быть больше нуля.")
            return
        index = self.size_box.current() if self.app.database.variants_enabled else 0
        row = self.size_rows[index] if 0 <= index < len(self.size_rows) else None
        size_value = row["size_value"] if row else None
        if not row or (
            row["quantity_available"] is not None
            and quantity > row["quantity_available"]
        ):
            show_error(
                "Недостаточно товара",
                "Введите количество, которое не превышает доступный остаток выбранного размера.",
            )
            return
        for item in self.app.cart:
            if (
                item["product_id"] == self.product_id
                and item["size_id"] == row["size_id"]
            ):
                if (
                    row["quantity_available"] is not None
                    and item["quantity"] + quantity > row["quantity_available"]
                ):
                    show_error(
                        "Недостаточно товара",
                        "Общее количество этой позиции в корзине превышает остаток.",
                    )
                    return
                item["quantity"] += quantity
                break
        else:
            self.app.cart.append(
                {
                    "product_id": self.product_id,
                    "size_id": row["size_id"],
                    "size_value": size_value,
                    "quantity": quantity,
                    "product_name": self.app.database.product(self.product_id)[
                        "product_name"
                    ],
                    "unit_price": self.app.database.discounted_price(self.product_id),
                    "manufacturer": row_value(
                        self.app.database.product(self.product_id), "manufacturer"
                    ),
                }
            )
        show_info(
            "Товар добавлен",
            "Позиция добавлена в заказ. Можно продолжить выбор товаров или открыть корзину.",
        )
        self.app.show_catalog(self.order_mode)


class CartFrame(ttk.Frame):
    def __init__(self, parent, app, order_mode: bool = False):
        super().__init__(parent)
        self.app = app
        self.order_mode = order_mode
        make_header(
            self,
            text("new_order" if order_mode else "cart"),
            app.user_text(),
            app.logout,
        )
        self.client_ids = {}
        self.client_value = tk.StringVar()
        self.date_value = tk.StringVar(value=app.order_date_value)
        if order_mode and app.is_manager_or_admin():
            form = ttk.Frame(self)
            form.pack(fill="x", padx=30, pady=(0, 10))
            ttk.Label(form, text="Клиент:").grid(row=0, column=0, sticky="w")
            clients = app.database.clients(app.actor_id())
            self.client_ids = {
                f"{c['client_name']} · {c['login']} [ID {c['user_id']}]": c["user_id"]
                for c in clients
            }
            selected = next(
                (
                    label
                    for label, key in self.client_ids.items()
                    if key == app.order_customer_id
                ),
                "",
            )
            self.client_value.set(selected)
            form.columnconfigure(1, weight=1)
            box = ttk.Combobox(
                form,
                textvariable=self.client_value,
                values=list(self.client_ids),
                state="readonly",
            )
            box.grid(row=0, column=1, sticky="ew", padx=10)
            box.bind(
                "<<ComboboxSelected>>",
                lambda event: setattr(
                    app, "order_customer_id", self.client_ids[self.client_value.get()]
                ),
            )
            ttk.Label(form, text="Дата (ГГГГ-ММ-ДД):").grid(row=0, column=2)
            ttk.Entry(form, textvariable=self.date_value, width=14).grid(
                row=0, column=3, padx=(10, 0)
            )
            self.date_value.trace_add(
                "write",
                lambda *_: setattr(app, "order_date_value", self.date_value.get()),
            )
        self.total_label = ttk.Label(self, text="", font=font("card_title", True))
        self.total_label.pack(side="bottom", anchor="e", padx=30, pady=8)
        actions = ttk.Frame(self)
        actions.pack(side="bottom", fill="x", padx=30, pady=20)
        ttk.Button(
            actions,
            text=text("back_catalog"),
            command=lambda: app.show_catalog(order_mode),
        ).pack(side="left")
        ttk.Button(actions, text=text("cancel_order"), command=self.cancel).pack(
            side="left", padx=8
        )
        ttk.Button(
            actions,
            text=text("confirm_order"),
            style="Accent.TButton",
            command=self.confirm,
        ).pack(side="right")
        canvas = tk.Canvas(self, background=COLORS["background"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, command=canvas.yview)
        scrollbar.pack(side="right", fill="y", padx=(0, 24), pady=10)
        canvas.pack(fill="both", expand=True, padx=(30, 10), pady=10)
        self.rows_frame = ttk.Frame(canvas)
        window = canvas.create_window((0, 0), window=self.rows_frame, anchor="nw")
        self.rows_frame.bind(
            "<Configure>",
            lambda event: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.bind(
            "<Configure>", lambda event: canvas.itemconfigure(window, width=event.width)
        )
        canvas.configure(yscrollcommand=scrollbar.set)
        self.date_value.trace_add("write", lambda *_: self.refresh())
        self.refresh()

    def refresh(self):
        clear_frame(self.rows_frame)
        if not self.app.cart:
            ttk.Label(
                self.rows_frame,
                text="Корзина пуста. Вернитесь в каталог и добавьте товар.",
                style="Subtitle.TLabel",
            ).pack(pady=30)
            self.total_label.configure(text=text("total", price=money(0)))
            return
        try:
            price_date = (
                as_date(self.date_value.get()) if self.order_mode else date.today()
            )
        except ValueError:
            price_date = date.today()
        total = Decimal("0.00")
        for index, item in enumerate(self.app.cart):
            item["unit_price"] = self.app.database.discounted_price(
                item["product_id"], on_date=price_date
            )
            row = ttk.Frame(self.rows_frame)
            row.pack(fill="x", pady=5)
            ttk.Label(
                row,
                text=text(
                    "item_variant",
                    name=item["product_name"],
                    manufacturer=item.get("manufacturer", ""),
                    value=size_text(item["size_value"]),
                ),
                wraplength=380,
                width=42,
            ).pack(side="left")
            ttk.Label(row, text=money(item["unit_price"]), width=15).pack(side="left")
            quantity = tk.StringVar(value=str(item["quantity"]))
            ttk.Entry(row, textvariable=quantity, width=7).pack(side="left", padx=5)
            ttk.Button(
                row,
                text=text("save"),
                command=lambda i=index, q=quantity: self.change_quantity(i, q),
            ).pack(side="left")
            ttk.Button(
                row, text=text("delete"), command=lambda i=index: self.remove(i)
            ).pack(side="left", padx=5)
            total += Decimal(str(item["unit_price"])) * item["quantity"]
        self.total_label.configure(text=text("total", price=money(total)))

    def change_quantity(self, index: int, value: tk.StringVar):
        try:
            quantity = int(value.get())
        except ValueError:
            show_error(
                "Ошибка количества",
                "Количество должно быть положительным целым числом.",
            )
            return
        if quantity <= 0:
            show_error("Ошибка количества", "Количество должно быть больше нуля.")
            return
        item = self.app.cart[index]
        try:
            available = self.app.database.available_quantity(
                item["product_id"], item["size_id"]
            )
        except Exception as error:
            show_error("Остатки", str(error))
            return
        if available is not None and quantity > available:
            show_error(
                "Недостаточно товара",
                "Количество не может превышать доступный остаток.",
            )
            return
        item["quantity"] = quantity
        self.refresh()

    def remove(self, index: int):
        self.app.cart.pop(index)
        self.refresh()

    def cancel(self):
        self.app.cart = []
        self.app.order_customer_id = None
        self.app.show_orders() if self.order_mode else self.app.show_catalog()

    def confirm(self):
        if not self.app.cart:
            show_error("Пустой заказ", "Добавьте хотя бы одну товарную позицию.")
            return
        client_id = self.app.actor_id()
        day = date.today().isoformat()
        if self.order_mode:
            client_id = self.client_ids.get(self.client_value.get())
            if client_id is None:
                show_error(
                    "Клиент не выбран",
                    "Выберите клиента, для которого оформляется заказ.",
                )
                return
            day = self.date_value.get().strip()
        try:
            as_date(day)
        except ValueError as error:
            show_error("Дата заказа", str(error))
            return
        if not show_warning(
            "Подтверждение заказа",
            "После подтверждения заказ будет сохранён, а остатки товара уменьшатся. Продолжить?",
        ):
            return
        try:
            order_id = self.app.database.create_order(
                client_id, self.app.cart, order_date=day, actor_id=self.app.actor_id()
            )
        except Exception as error:
            show_error("Не удалось оформить заказ", str(error))
            return
        self.app.cart = []
        show_info("Заказ оформлен", f"Заказ №{order_id} успешно сохранён.")
        self.app.order_customer_id = None
        self.app.show_orders() if self.order_mode else self.app.show_catalog()
