import tkinter as tk

from design import CARD, CARD_FIELDS, COLORS, LOW_STOCK_THRESHOLD
from interface.pictures import image_panel
from interface.formatting import field_rows, font, product_context, render, text


class ProductCard(tk.Frame):
    """Карточка получает готовые данные и действия."""

    def __init__(
        self,
        parent,
        product,
        images,
        price,
        on_open,
        on_scroll=None,
        layout="grid",
        discount=None,
    ):
        options = CARD[layout]
        horizontal = layout == "list"
        quantity = product.get("total_quantity")
        low_stock = quantity is not None and quantity <= LOW_STOCK_THRESHOLD
        bg = COLORS["low_stock_background"] if low_stock else COLORS["surface"]
        super().__init__(
            parent,
            bg=bg,
            highlightthickness=1,
            highlightbackground=COLORS["low_stock"] if low_stock else COLORS["border"],
            width=options["width"],
        )
        padding = options["padding"]
        values = product_context(product, price, discount)
        self.product = product
        if options["show_image"]:
            photo = image_panel(
                self, images, product.get("image_path"), options["image"], bg
            )
            photo.pack(side="left" if horizontal else "top", padx=padding, pady=14)
        if horizontal:
            pricing = tk.Frame(self, bg=bg)
            pricing.pack(side="right", padx=padding, pady=16)
            body = tk.Frame(self, bg=bg)
            body.pack(side="left", fill="both", expand=True, pady=14)
        else:
            body = pricing = self
        labels = []

        def label(parent, value, foreground, role="body", bold=False, **kwargs):
            widget = tk.Label(
                parent,
                text=value,
                bg=bg,
                fg=foreground,
                font=font(role, bold),
                wraplength=options["wrap"],
                justify="left",
                **kwargs
            )
            widget.pack(anchor="w", padx=padding, pady=(2, 6))
            labels.append(widget)
            return widget

        if options["eyebrow"]:
            label(body, options["eyebrow"], COLORS["accent"], "small", True)
        title = label(
            body, render(options["title"], values), COLORS["text"], "card_title", True
        )
        if horizontal:
            title.pack_configure(anchor="w")
        for value, style in field_rows(CARD_FIELDS, values, layout):
            if style == "stock":
                widget = label(
                    body,
                    value,
                    COLORS["danger"] if low_stock else COLORS["accent_dark"],
                    "small",
                    True,
                    padx=8,
                    pady=3,
                )
                widget.configure(
                    bg=(
                        COLORS["low_stock_background"]
                        if low_stock
                        else COLORS["secondary"]
                    )
                )
            else:
                label(
                    body, value, COLORS["muted"] if style == "muted" else COLORS["text"]
                )
        if values["discount_applied"]:
            old_price = label(
                pricing, values["original_price_text"], COLORS["muted"], "small"
            )
            old_price.configure(font=font("small") + ("overstrike",))
            label(
                pricing, values["discount_text"], COLORS["accent_dark"], "small", True
            )
        label(
            pricing,
            text("price", price=values["price_text"]),
            COLORS["accent_dark"],
            "emphasis",
            True,
        )
        if on_open is not None:
            tk.Button(
                pricing,
                text=text("details"),
                bg=COLORS["accent"],
                fg=COLORS["on_accent"],
                activebackground=COLORS["accent_dark"],
                activeforeground=COLORS["on_accent"],
                relief="flat",
                cursor="hand2",
                font=font(bold=True),
                padx=12,
                pady=5,
                command=on_open,
            ).pack(anchor="w", padx=padding, pady=(2, 10))

        # Высота растёт, чтобы новые поля не обрезались.
        if options["minimum_height"]:
            self.pack_propagate(False)

            def fit_height(event):
                height = 0
                for child in self.winfo_children():
                    pady = child.pack_info().get("pady", 0)
                    gap = (
                        sum(map(int, pady))
                        if isinstance(pady, tuple)
                        else 2 * int(pady)
                    )
                    height += child.winfo_reqheight() + gap
                height = max(options["minimum_height"], height)
                if self.cget("height") != height:
                    self.configure(height=height)

            self.bind("<Configure>", fit_height)

        def resize_text(event):
            for widget in labels:
                if widget.master is body:
                    widget.configure(wraplength=max(80, event.width - 2 * padding))

        body.bind("<Configure>", resize_text, add="+")

        def bind_children(widget):
            if on_scroll:
                widget.bind("<MouseWheel>", on_scroll)
                widget.bind(
                    "<Button-4>",
                    lambda event: on_scroll(type("Scroll", (), {"delta": 120})()),
                )
                widget.bind(
                    "<Button-5>",
                    lambda event: on_scroll(type("Scroll", (), {"delta": -120})()),
                )
            if on_open is not None:
                widget.bind("<Double-Button-1>", lambda event: on_open())
            for child in widget.winfo_children():
                bind_children(child)

        bind_children(self)
