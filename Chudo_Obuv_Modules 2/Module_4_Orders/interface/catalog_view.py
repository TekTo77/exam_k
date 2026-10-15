"""Модуль 2: каталог товаров."""

from __future__ import annotations
import tkinter as tk
from tkinter import ttk

from config import COLORS, PRODUCT_CARD_LAYOUT, PRODUCT_CARD_MIN_WIDTH
from design import SPACING
from interface.formatting import text
from interface.components.product_tile import ProductCard
from interface.widgets import clear_frame, make_header


class CatalogFrame(ttk.Frame):
    def __init__(self, parent, app, order_mode: bool = False):
        super().__init__(parent)
        self.app = app
        self.order_mode = order_mode
        make_header(
            self,
            text("catalog"),
            app.user_text() if app.module_number >= 3 else "",
            app.logout if app.module_number >= 3 else None,
        )
        toolbar = ttk.Frame(self)
        toolbar.pack(fill="x", padx=SPACING["page"], pady=(0, 10))
        self.search = tk.StringVar()
        self.category = tk.StringVar(value="Все категории")
        self.sort = tk.StringVar(value="По возрастанию цены")
        ttk.Label(toolbar, text=text("search")).pack(side="left")
        search_entry = ttk.Entry(toolbar, textvariable=self.search, width=20)
        search_entry.pack(side="left", padx=(6, 16))
        ttk.Label(toolbar, text=text("category")).pack(side="left")
        categories = ["Все категории"] + app.database.categories()
        ttk.Combobox(
            toolbar,
            textvariable=self.category,
            values=categories,
            state="readonly",
            width=16,
        ).pack(side="left", padx=(6, 16))
        ttk.Label(toolbar, text=text("sort")).pack(side="left")
        ttk.Combobox(
            toolbar,
            textvariable=self.sort,
            values=["По возрастанию цены", "По убыванию цены"],
            state="readonly",
            width=18,
        ).pack(side="left", padx=6)
        if app.module_number == 2 or app.current_user is None:
            toolbar.pack_forget()
        actions = ttk.Frame(self)
        actions.pack(fill="x", padx=SPACING["page"], pady=(0, 10))
        ttk.Button(
            actions,
            text=text("data_settings"),
            command=lambda: app.show_data_settings(
                lambda: app.show_catalog(order_mode)
            ),
        ).pack(side="left")
        ttk.Button(actions, text=text("refresh"), command=self.reload).pack(
            side="left", padx=8
        )
        if app.can_order():
            ttk.Button(
                actions,
                text=text("cart_count", count=len(app.cart)),
                command=lambda: app.show_cart(order_mode),
            ).pack(side="right", padx=4)
        if app.can_order() and app.module_number >= 4:
            title = text("orders" if app.is_manager_or_admin() else "my_orders")
            ttk.Button(actions, text=title, command=app.show_orders).pack(
                side="right", padx=4
            )
        if app.database.mapping_warnings:
            ttk.Label(
                self,
                text=" ".join(app.database.mapping_warnings),
                wraplength=950,
                style="Subtitle.TLabel",
            ).pack(anchor="w", padx=SPACING["page"], pady=(0, 8))
        if order_mode:
            ttk.Label(
                self,
                text="Режим добавления заказа: выберите товары и оформите корзину.",
                style="Subtitle.TLabel",
            ).pack(anchor="w", padx=SPACING["page"], pady=(0, 8))
        self.canvas = tk.Canvas(
            self, background=COLORS["background"], highlightthickness=0
        )
        scrollbar = ttk.Scrollbar(self, orient="vertical", command=self.canvas.yview)
        self.content = ttk.Frame(self.canvas)
        self.content.bind(
            "<Configure>",
            lambda event: self.canvas.configure(scrollregion=self.canvas.bbox("all")),
        )
        self.content_window = self.canvas.create_window(
            (0, 0), window=self.content, anchor="nw"
        )
        self.canvas.bind("<Configure>", self.resize_catalog)
        self.canvas.bind("<MouseWheel>", self.scroll_catalog)
        self.content.bind("<MouseWheel>", self.scroll_catalog)
        if PRODUCT_CARD_LAYOUT not in {"grid", "list"}:
            raise ValueError(
                'PRODUCT_CARD_LAYOUT в design.py должен быть "grid" или "list".'
            )
        self.column_count = 1 if PRODUCT_CARD_LAYOUT == "list" else 3
        self.canvas.configure(yscrollcommand=scrollbar.set)
        self.canvas.pack(
            side="left",
            fill="both",
            expand=True,
            padx=(SPACING["page"], 0),
            pady=(0, 20),
        )
        scrollbar.pack(side="right", fill="y", padx=(0, 20), pady=(0, 20))
        self.search.trace_add("write", lambda *_: self.refresh())
        self.category.trace_add("write", lambda *_: self.refresh())
        self.sort.trace_add("write", lambda *_: self.refresh())
        self.refresh()

    def resize_catalog(self, event):
        self.canvas.itemconfigure(self.content_window, width=event.width)
        columns = (
            1
            if PRODUCT_CARD_LAYOUT == "list"
            else max(1, event.width // PRODUCT_CARD_MIN_WIDTH)
        )
        if columns != self.column_count:
            self.column_count = columns
            self.refresh()

    def scroll_catalog(self, event):
        delta = int(event.delta)
        step = (-1 if delta > 0 else 1) * max(1, abs(delta) // 120)
        self.canvas.yview_scroll(step, "units")

    def reload(self):
        self.app.database._refresh_domain_mapping()
        self.app.images.cache.clear()
        self.refresh()

    def refresh(self):
        clear_frame(self.content)
        try:
            products = self.app.database.products(
                self.search.get(), self.category.get(), self.sort.get()
            )
            prices = {
                str(p["product_id"]): self.app.database.discount_info(p["product_id"])
                for p in products
            }
        except Exception as error:
            ttk.Label(
                self.content,
                text=f"Не удалось прочитать каталог: {error}",
                wraplength=700,
            ).pack(pady=25)
            return
        if not products:
            ttk.Label(
                self.content,
                text=text("catalog_empty"),
                style="Subtitle.TLabel",
            ).pack(pady=30)
            return
        columns = self.column_count
        for index, product in enumerate(products):
            card = ProductCard(
                self.content,
                product,
                self.app.images,
                prices[str(product["product_id"])]["price"],
                on_open=(
                    (
                        lambda p=product: self.app.show_product(
                            p["product_id"], self.order_mode
                        )
                    )
                    if self.app.module_number >= 3
                    else None
                ),
                on_scroll=self.scroll_catalog,
                layout=PRODUCT_CARD_LAYOUT,
                discount=prices[str(product["product_id"])],
            )
            card.grid(
                row=index // columns,
                column=index % columns,
                padx=SPACING["card_gap"],
                pady=SPACING["card_gap"],
                sticky="nsew",
            )
        for column in range(max(columns, self.content.grid_size()[0])):
            self.content.columnconfigure(column, weight=1 if column < columns else 0)
