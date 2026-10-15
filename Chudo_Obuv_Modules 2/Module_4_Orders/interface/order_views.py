"""Модуль 4: список, состав и редактирование заказов."""

from __future__ import annotations
import tkinter as tk
from tkinter import ttk
from decimal import Decimal
from storage.order_operations import size_text

from config import COLORS
from design import SPACING
from interface.formatting import font, text, money
from interface.widgets import (
    make_header,
    show_error,
    show_info,
    show_warning,
    configured_table,
    insert_table_row,
)


class OrdersFrame(ttk.Frame):
    def __init__(self, parent, app):
        super().__init__(parent)
        self.app = app
        make_header(
            self,
            text("orders_list" if app.is_manager_or_admin() else "my_orders"),
            app.user_text(),
            app.logout,
        )
        actions = ttk.Frame(self)
        actions.pack(fill="x", padx=SPACING["page"], pady=(0, 10))
        ttk.Button(actions, text=text("back_catalog"), command=app.show_catalog).pack(
            side="left"
        )
        if app.is_manager_or_admin():
            ttk.Button(
                actions,
                text=text("new_order"),
                style="Accent.TButton",
                command=app.start_order,
            ).pack(side="right")
        self.tree = configured_table(self, "orders")
        self.tree.bind("<Double-1>", lambda event: self.open_selected())
        bottom = ttk.Frame(self)
        bottom.pack(side="bottom", fill="x", padx=SPACING["page"], pady=(0, 20))
        ttk.Button(bottom, text=text("open_order"), command=self.open_selected).pack(
            side="left"
        )
        if app.is_manager_or_admin():
            ttk.Button(
                bottom, text=text("delete_order"), command=self.delete_selected
            ).pack(side="left", padx=8)
        ttk.Button(actions, text=text("refresh"), command=self.refresh).pack(
            side="left", padx=8
        )
        self.count_label = ttk.Label(bottom, text="", style="Subtitle.TLabel")
        self.count_label.pack(side="right")
        self.refresh()

    def refresh(self):
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.order_ids = {}
        try:
            orders = self.app.database.orders(actor_id=self.app.actor_id())
        except Exception as error:
            show_error("Не удалось прочитать заказы", str(error))
            return
        for order in orders:
            self.order_ids[str(order["order_id"])] = order["order_id"]
            insert_table_row(
                self.tree,
                {
                    "id": order["order_id"],
                    "date": order["order_date"],
                    "client": order["client_name"],
                    "total": money(order["total_sum"]),
                },
                iid=str(order["order_id"]),
            )

        self.count_label.configure(text=f"Заказов: {len(self.order_ids)}")

    def selected_id(self):
        selected = self.tree.selection()
        if not selected:
            show_error("Заказ не выбран", "Выберите заказ в списке.")
            return None
        return self.order_ids[selected[0]]

    def open_selected(self):
        order_id = self.selected_id()
        if order_id is not None:
            self.app.show_order_detail(order_id)

    def delete_selected(self):
        order_id = self.selected_id()
        if order_id is None:
            return
        if not show_warning(
            "Удаление заказа",
            "Заказ будет удалён, а товары возвращены в доступный остаток. Продолжить?",
        ):
            return
        try:
            self.app.database.delete_order(order_id, actor_id=self.app.actor_id())
        except Exception as error:
            show_error("Ошибка удаления", f"Заказ не удалось удалить: {error}")
            return
        show_info("Заказ удалён", "Заказ и его состав удалены.")
        self.refresh()


class OrderDetailFrame(ttk.Frame):
    def __init__(self, parent, app, order_id: int):
        super().__init__(parent)
        self.app = app
        self.order_id = order_id
        order = app.database.order(order_id, actor_id=app.actor_id())
        if not order:
            raise ValueError("Заказ больше не найден. Обновите список.")
        make_header(
            self, text("order_detail", order_id=order_id), app.user_text(), app.logout
        )
        ttk.Label(
            self, text=f"Дата: {order['order_date']}    Клиент: {order['client_name']}"
        ).pack(anchor="w", padx=30, pady=(0, 12))
        actions = ttk.Frame(self)
        actions.pack(side="bottom", fill="x", padx=30, pady=20)
        self.total_label = ttk.Label(self, text="", font=font("card_title", True))
        self.total_label.pack(side="bottom", anchor="e", padx=30, pady=8)
        self.item_text = ttk.Label(
            self,
            text=text("order_selection_hint"),
            wraplength=1000,
            style="Subtitle.TLabel",
        )
        self.item_text.pack(side="bottom", fill="x", padx=30, pady=5)
        self.tree = configured_table(self, "items")
        self.tree.bind(
            "<<TreeviewSelect>>",
            lambda event: (
                self.item_text.configure(
                    text=self.tree.set(self.tree.selection()[0], "product")
                )
                if self.tree.selection() and "product" in self.tree["columns"]
                else None
            ),
        )
        total = Decimal("0.00")
        for item in app.database.order_items(order_id, actor_id=app.actor_id()):
            total += item["line_total"]
            insert_table_row(
                self.tree,
                {
                    "product": f"{item['product_name']} — {item['manufacturer']}",
                    "size": size_text(item["size_value"]),
                    "quantity": item["quantity"],
                    "price": money(item["unit_price"]),
                    "total": money(item["line_total"]),
                },
            )
        self.total_label.configure(text=text("total", price=money(total)))
        ttk.Button(actions, text=text("back_orders"), command=app.show_orders).pack(
            side="left"
        )
        if app.is_admin():
            ttk.Button(
                actions,
                text=text("edit_order"),
                style="Accent.TButton",
                command=lambda: app.show_order_edit(order_id),
            ).pack(side="right")


class OrderEditFrame(ttk.Frame):
    def __init__(self, parent, app, order_id: int):
        super().__init__(parent)
        self.app = app
        self.order_id = order_id
        order = app.database.order(order_id, actor_id=app.actor_id())
        if not order:
            raise ValueError("Заказ больше не найден. Обновите список.")
        make_header(
            self, text("order_edit", order_id=order_id), app.user_text(), app.logout
        )
        form = ttk.Frame(self)
        form.pack(fill="x", padx=30, pady=10)
        ttk.Label(form, text="Дата заказа (ГГГГ-ММ-ДД):").pack(side="left")
        self.date_value = tk.StringVar(value=order["order_date"])
        ttk.Entry(form, textvariable=self.date_value, width=18).pack(
            side="left", padx=10
        )
        ttk.Label(
            self,
            text="Измените количество. Чтобы удалить позицию целиком, снимите отметку:",
            style="Subtitle.TLabel",
        ).pack(anchor="w", padx=30, pady=(15, 5))
        actions = ttk.Frame(self)
        actions.pack(side="bottom", fill="x", padx=30, pady=25)
        canvas = tk.Canvas(self, background=COLORS["background"], highlightthickness=0)
        scrollbar = ttk.Scrollbar(self, command=canvas.yview)
        scrollbar.pack(side="right", fill="y", padx=(0, 24), pady=10)
        canvas.pack(fill="both", expand=True, padx=(30, 10), pady=10)
        rows = ttk.Frame(canvas)
        window = canvas.create_window((0, 0), window=rows, anchor="nw")
        rows.bind(
            "<Configure>",
            lambda event: canvas.configure(scrollregion=canvas.bbox("all")),
        )
        canvas.bind(
            "<Configure>", lambda event: canvas.itemconfigure(window, width=event.width)
        )
        canvas.configure(yscrollcommand=scrollbar.set)
        self.item_vars = {}
        self.quantity_vars = {}
        self.original_quantities = {}
        self.edit_total = tk.StringVar()
        ttk.Label(actions, textvariable=self.edit_total, style="Subtitle.TLabel").pack(
            side="left", padx=16
        )
        items = app.database.order_items(order_id, actor_id=app.actor_id())
        self.items = items
        for item in items:
            variable = tk.BooleanVar(value=True)
            key = item["order_item_id"]
            self.item_vars[key] = variable
            self.original_quantities[key] = item["quantity"]
            quantity = tk.StringVar(value=str(item["quantity"]))
            self.quantity_vars[key] = quantity
            row = ttk.Frame(rows)
            row.pack(fill="x", padx=30, pady=4)
            tk.Checkbutton(
                row,
                bg=COLORS["background"],
                fg=COLORS["text"],
                font=font("body"),
                wraplength=570,
                justify="left",
                anchor="w",
                text=text(
                    "item_variant",
                    name=item["product_name"],
                    manufacturer=item["manufacturer"],
                    value=size_text(item["size_value"]),
                )
                + f" · {money(item['unit_price'])} за единицу",
                variable=variable,
            ).pack(side="left", fill="x", expand=True)
            ttk.Spinbox(row, from_=1, to=999999, textvariable=quantity, width=8).pack(
                side="right", padx=(8, 0)
            )
            ttk.Label(row, text=text("quantity")).pack(side="right", padx=(8, 0))
            quantity.trace_add("write", lambda *_: self.refresh_total())
            variable.trace_add("write", lambda *_: self.refresh_total())
        self.items = items
        self.refresh_total()
        ttk.Button(
            actions, text=text("back"), command=lambda: app.show_order_detail(order_id)
        ).pack(side="left")
        ttk.Button(
            actions,
            text=text("save_changes"),
            style="Accent.TButton",
            command=self.save,
        ).pack(side="right")

    def chosen_quantities(self):
        result = {}
        for key, variable in self.quantity_vars.items():
            if not self.item_vars[key].get():
                continue
            try:
                quantity = int(variable.get().strip())
            except ValueError as error:
                raise ValueError(
                    "Количество должно быть положительным целым числом."
                ) from error
            if quantity <= 0:
                raise ValueError(
                    "Количество должно быть больше нуля. Для удаления снимите отметку."
                )
            result[key] = quantity
        return result

    def refresh_total(self):
        try:
            quantities = self.chosen_quantities()
            total = sum(
                (
                    item["unit_price"] * quantities.get(item["order_item_id"], 0)
                    for item in self.items
                ),
                Decimal("0"),
            )
            self.edit_total.set(text("total", price=money(total)))
        except ValueError:
            self.edit_total.set("Проверьте количество")

    def save(self):
        try:
            from datetime import datetime

            datetime.strptime(self.date_value.get().strip(), "%Y-%m-%d")
        except ValueError:
            show_error(
                "Ошибка даты", "Введите дату в формате ГГГГ-ММ-ДД, например 2026-10-02."
            )
            return
        removed = [
            item_id
            for item_id, variable in self.item_vars.items()
            if not variable.get()
        ]
        try:
            quantities = self.chosen_quantities()
        except ValueError as error:
            show_error("Ошибка количества", str(error))
            return
        if removed and not show_warning(
            "Удаление позиций",
            "Позиции без отметки будут удалены из заказа, а их количество вернётся на склад. Продолжить?",
        ):
            return
        try:
            self.app.database.update_order(
                self.order_id,
                self.date_value.get().strip(),
                removed,
                actor_id=self.app.actor_id(),
                quantities=quantities,
                expected_quantities=self.original_quantities,
            )
        except Exception as error:
            show_error("Ошибка сохранения", str(error))
            return
        show_info("Изменения сохранены", "Заказ обновлён.")
        self.app.show_orders()
