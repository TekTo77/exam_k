import tkinter as tk
from tkinter import ttk, messagebox
from pathlib import Path
from typing import Callable

from design import (
    COLORS,
    LOGO_PATH,
    LOGO_SIZES,
    SPACING,
    WINDOW_ICON_PATH,
    ORDER_COLUMNS,
)
from PIL import Image, ImageTk
from interface.pictures import read_thumbnail
from interface.formatting import font, text


def configure_styles(root: tk.Tk) -> None:
    root.option_add("*Font", font())
    style = ttk.Style(root)
    try:
        style.theme_use("clam")
    except tk.TclError:
        pass
    style.configure("TFrame", background=COLORS["background"])
    style.configure("Surface.TFrame", background=COLORS["surface"])
    style.configure("Secondary.TFrame", background=COLORS["secondary"])
    style.configure(
        "TLabel",
        background=COLORS["background"],
        foreground=COLORS["text"],
        font=font("body"),
    )
    style.configure(
        "Title.TLabel",
        background=COLORS["background"],
        foreground=COLORS["text"],
        font=font("title", True),
    )
    style.configure(
        "SurfaceTitle.TLabel",
        background=COLORS["surface"],
        foreground=COLORS["text"],
        font=font("title", True),
    )
    style.configure(
        "Subtitle.TLabel",
        background=COLORS["background"],
        foreground=COLORS["muted"],
        font=font("body"),
    )
    style.configure(
        "SurfaceSubtitle.TLabel",
        background=COLORS["surface"],
        foreground=COLORS["muted"],
        font=font("body"),
    )
    style.configure("TButton", font=font("body"), padding=SPACING["button"])
    style.configure(
        "Accent.TButton",
        background=COLORS["accent"],
        foreground=COLORS["on_accent"],
        font=font("body", True),
        borderwidth=0,
    )
    style.map("Accent.TButton", background=[("active", COLORS["accent_dark"])])
    style.configure(
        "Danger.TButton",
        background=COLORS["danger"],
        foreground=COLORS["on_accent"],
        font=font("body", True),
        borderwidth=0,
    )
    style.map("Danger.TButton", background=[("active", COLORS["danger_dark"])])
    style.configure(
        "Soft.TButton",
        background=COLORS["secondary"],
        foreground=COLORS["accent_dark"],
        font=font("body", True),
        borderwidth=0,
    )
    style.map("Soft.TButton", background=[("active", COLORS["secondary_hover"])])
    style.configure("TEntry", font=font("body"), padding=5)
    style.configure("TCombobox", font=font("body"), padding=4)
    style.configure(
        "Treeview",
        background=COLORS["surface"],
        fieldbackground=COLORS["surface"],
        foreground=COLORS["text"],
        font=font("body"),
        rowheight=SPACING["table_row"],
        borderwidth=0,
    )
    style.map(
        "Treeview",
        background=[("selected", COLORS["secondary"])],
        foreground=[("selected", COLORS["text"])],
    )
    style.configure(
        "Treeview.Heading",
        background=COLORS["accent_dark"],
        foreground=COLORS["on_accent"],
        font=font("body", True),
        padding=(8, 8),
    )
    style.map("Treeview.Heading", background=[("active", COLORS["accent"])])
    style.configure(
        "TLabelframe", background=COLORS["background"], bordercolor=COLORS["border"]
    )
    style.configure(
        "TLabelframe.Label",
        background=COLORS["background"],
        foreground=COLORS["accent_dark"],
        font=font("body", True),
    )


def clear_frame(frame: ttk.Frame) -> None:
    for child in frame.winfo_children():
        child.destroy()


def order_table(parent, columns, widths):
    """Таблица с прокруткой."""
    area = ttk.Frame(parent)
    area.pack(fill="both", expand=True, padx=SPACING["page"], pady=(0, 10))
    area.rowconfigure(0, weight=1)
    area.columnconfigure(0, weight=1)
    tree = ttk.Treeview(
        area, columns=[key for key, _ in columns], show="headings", selectmode="browse"
    )
    for (key, title), width in zip(columns, widths):
        tree.heading(key, text=title)
        tree.column(
            key,
            width=width,
            minwidth=60,
            stretch=key in ("product", "client"),
            anchor="w" if key in ("product", "client") else "center",
        )
    vertical = ttk.Scrollbar(area, orient="vertical", command=tree.yview)
    horizontal = ttk.Scrollbar(area, orient="horizontal", command=tree.xview)
    tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
    tree.grid(row=0, column=0, sticky="nsew")
    vertical.grid(row=0, column=1, sticky="ns")
    horizontal.grid(row=1, column=0, sticky="ew")
    return tree


def configured_table(parent, name):
    columns = ORDER_COLUMNS[name]
    database = getattr(parent.winfo_toplevel(), "database", None)
    if database is not None and not database.variants_enabled:
        columns = [c for c in columns if c[0] not in {"size", "size_value", "size_id"}]
    return order_table(
        parent,
        [(key, title) for key, title, _ in columns],
        [width for _, _, width in columns],
    )


def insert_table_row(tree, values, **options):
    return tree.insert(
        "", "end", values=[values.get(key, "") for key in tree["columns"]], **options
    )


def _load_logo(master: tk.Misc, size=None):
    if LOGO_PATH is None:
        return None
    try:
        path = Path(LOGO_PATH)
        if not path.is_file():
            return None
        if isinstance(size, int):
            size = (size, size)
        return ImageTk.PhotoImage(
            read_thumbnail(path, size or LOGO_SIZES["header"]), master=master
        )
    except (OSError, ValueError, tk.TclError, Image.DecompressionBombError):
        return None


def set_window_icon(root):
    if WINDOW_ICON_PATH is None:
        return
    try:
        image = ImageTk.PhotoImage(
            read_thumbnail(Path(WINDOW_ICON_PATH), (128, 128)), master=root
        )
        root.iconphoto(True, image)
        root._window_icon = image
    except (OSError, ValueError, tk.TclError, Image.DecompressionBombError):
        pass


def add_logo(parent: tk.Misc, size=None, **pack_options):
    image = _load_logo(parent, size or LOGO_SIZES["login"])
    if image is None:
        return None
    label = tk.Label(parent, image=image, bg=COLORS["surface"], borderwidth=0)
    label.image = image
    label.pack(**pack_options)
    return label


def scrollable_form(parent):
    """Форма с прокруткой для большого числа полей."""
    area = ttk.Frame(parent)
    area.pack(fill="both", expand=True)
    canvas = tk.Canvas(area, bg=COLORS["background"], highlightthickness=0)
    bar = ttk.Scrollbar(area, orient="vertical", command=canvas.yview)
    bar.pack(side="right", fill="y")
    canvas.pack(side="left", fill="both", expand=True)
    canvas.configure(yscrollcommand=bar.set)
    body = ttk.Frame(canvas, padding=12)
    window = canvas.create_window((0, 0), window=body, anchor="nw")
    body.bind(
        "<Configure>", lambda event: canvas.configure(scrollregion=canvas.bbox("all"))
    )
    canvas.bind(
        "<Configure>", lambda event: canvas.itemconfigure(window, width=event.width)
    )
    return body


def make_header(
    parent: ttk.Frame,
    title: str,
    user_text: str = "",
    on_logout: Callable[[], None] | None = None,
) -> ttk.Frame:
    header = ttk.Frame(parent, style="Surface.TFrame")
    header.pack(
        fill="x",
        padx=SPACING["page"],
        pady=(SPACING["header_top"], SPACING["header_bottom"]),
    )
    logo = _load_logo(header, LOGO_SIZES["header"])
    if logo is not None:
        logo_label = tk.Label(header, image=logo, bg=COLORS["surface"], borderwidth=0)
        logo_label.image = logo
        logo_label.pack(side="left", padx=(0, 10))
    ttk.Label(header, text=title, style="SurfaceTitle.TLabel").pack(side="left")
    right = ttk.Frame(header, style="Surface.TFrame")
    right.pack(side="right")
    if user_text:
        ttk.Label(right, text=user_text, style="SurfaceSubtitle.TLabel").pack(
            side="left", padx=(0, 12)
        )
    if on_logout is not None:
        ttk.Button(
            right, text=text("logout"), style="Danger.TButton", command=on_logout
        ).pack(side="left")
    ttk.Separator(parent, orient="horizontal").pack(
        fill="x", padx=SPACING["page"], pady=(0, 12)
    )
    return header


def show_error(title: str, text: str) -> None:
    messagebox.showerror(title, text)


def show_info(title: str, text: str) -> None:
    messagebox.showinfo(title, text)


def show_warning(title: str, text: str) -> bool:
    return messagebox.askyesno(title, text, icon="warning")
