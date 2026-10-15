from __future__ import annotations
import tkinter as tk
from tkinter import messagebox, ttk
from datetime import date

from config import APP_TITLE, COLORS
from design import WINDOW
from storage.repository import Database
from preferences import read_settings, images_directory
from interface.pictures import ImageStore
from interface.data_mapping import DataSettings
from interface.widgets import (
    configure_styles,
    set_window_icon,
    clear_frame,
    show_error,
    show_warning,
)


from module_settings import MODULE_NUMBER
from interface.catalog_view import CatalogFrame
from interface.customer_views import LoginFrame, ProductFrame, CartFrame
from interface.order_views import OrdersFrame, OrderDetailFrame, OrderEditFrame


class Application(tk.Tk):
    def __init__(self, module_number=MODULE_NUMBER):
        super().__init__()
        self.module_number = module_number
        self.title(APP_TITLE)
        self.geometry("%dx%d" % WINDOW["size"])
        self.minsize(*WINDOW["minimum"])
        self.configure(bg=COLORS["background"])
        configure_styles(self)
        set_window_icon(self)
        self.database = None
        self.connection_error = ""
        try:
            self.database = Database()
        except Exception as error:
            self.connection_error = str(error)
        self.images = ImageStore(self, images_directory(read_settings()))
        self.current_user = None
        self.cart = []
        self.order_customer_id = None
        self.order_date_value = date.today().isoformat()
        self.navigation = ttk.Frame(self)
        self.navigation.pack(fill="both", expand=True)
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.show_login()

    def close(self):
        if self.database is not None:
            self.database.close()
        self.destroy()

    def show_connection_error(self):
        clear_frame(self.navigation)
        body = ttk.Frame(self.navigation, padding=30)
        body.pack(fill="both", expand=True)
        ttk.Label(
            body, text="Не удалось подключиться", style="Title.TLabel"
        ).pack(anchor="w", pady=12)
        ttk.Label(
            body, text=self.connection_error, wraplength=720, style="Subtitle.TLabel"
        ).pack(anchor="w", pady=12)

    def show_data_settings(self, on_saved=None):
        DataSettings(self, on_saved or self.show_login)

    def show_login(self):
        if self.database is None:
            self.show_connection_error()
            return
        if self.module_number == 2:
            self.current_user = None
            self.show_catalog()
            return
        clear_frame(self.navigation)
        LoginFrame(self.navigation, self).pack(fill="both", expand=True)

    def login(self, user):
        self.current_user = user
        self.cart = []
        self.show_catalog()

    def logout(self):
        self.current_user = None
        self.cart = []
        self.show_login()

    def show_catalog(self, order_mode: bool = False):
        clear_frame(self.navigation)
        CatalogFrame(self.navigation, self, order_mode=order_mode).pack(
            fill="both", expand=True
        )

    def show_product(self, product_id: int, order_mode: bool = False):
        if self.module_number < 3:
            return
        clear_frame(self.navigation)
        try:
            ProductFrame(self.navigation, self, product_id, order_mode=order_mode).pack(
                fill="both", expand=True
            )
        except Exception as error:
            show_error("Товар", str(error))
            self.show_catalog(order_mode)

    def show_cart(self, order_mode: bool = False):
        clear_frame(self.navigation)
        CartFrame(self.navigation, self, order_mode=order_mode).pack(
            fill="both", expand=True
        )

    def actor_id(self):
        return self.current_user.get("user_id") if self.current_user else None

    def start_order(self):
        if not self.is_manager_or_admin():
            show_error(
                "Доступ запрещён",
                "Создание заказа для клиента доступно менеджеру и администратору.",
            )
            return
        if self.cart and not show_warning(
            "Новый заказ", "Очистить текущую корзину и начать новый заказ?"
        ):
            return
        self.cart = []
        self.order_customer_id = None
        self.order_date_value = date.today().isoformat()
        self.show_catalog(order_mode=True)

    def _staff_page(self, frame, *args, admin=False):
        if not self.is_manager_or_admin() or (admin and not self.is_admin()):
            show_error("Доступ запрещён", "У вашей роли нет доступа к этому экрану.")
            return
        clear_frame(self.navigation)
        try:
            frame(self.navigation, self, *args).pack(fill="both", expand=True)
        except Exception as error:
            show_error("Заказы", str(error))
            self.show_catalog()

    def show_orders(self):
        if self.module_number < 4:
            return
        self._orders_page(OrdersFrame)

    def show_order_detail(self, order_id: int):
        self._orders_page(OrderDetailFrame, order_id)

    def _orders_page(self, frame, *args):
        if not self.current_user:
            show_error("Необходим вход", "Войдите, чтобы посмотреть свои заказы.")
            return
        clear_frame(self.navigation)
        try:
            frame(self.navigation, self, *args).pack(fill="both", expand=True)
        except Exception as error:
            show_error("Заказы", str(error))
            self.show_catalog()

    def show_order_edit(self, order_id: int):
        self._staff_page(OrderEditFrame, order_id, admin=True)

    def user_text(self):
        if not self.current_user:
            return "Гость"
        return " ".join(
            str(self.current_user.get(key) or "").strip()
            for key in ("last_name", "first_name", "middle_name")
        ).strip()

    def can_order(self):
        return (
            self.module_number >= 3
            and self.current_user is not None
            and self.database.orders_enabled
        )

    def is_manager_or_admin(self):
        return bool(
            self.module_number >= 4
            and self.current_user
            and str(self.current_user["role_name"]).strip()
            in ("Менеджер", "Администратор")
        )

    def is_admin(self):
        return bool(
            self.module_number >= 4
            and self.current_user
            and str(self.current_user["role_name"]).strip() == "Администратор"
        )
