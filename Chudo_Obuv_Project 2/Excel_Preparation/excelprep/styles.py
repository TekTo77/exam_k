import tkinter as tk
from tkinter import ttk
from design import COLORS, FONT_FAMILY, FONT_SIZES, SPACING


def font(role="body", bold=False):
    value = (FONT_FAMILY, FONT_SIZES[role])
    return value + ("bold",) if bold else value


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
