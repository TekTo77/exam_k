"""Отдельный импорт без входа: python import_db.py."""

import tkinter as tk

from interface.import_window import ExcelImportPanel
from interface.widgets import configure_styles, set_window_icon
from design import WINDOW
from config import APP_TITLE, COLORS


class ImportDatabaseApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Импорт Excel")
        self.geometry("%dx%d" % WINDOW["import_size"])
        self.minsize(*WINDOW["import_minimum"])
        self.configure(bg=COLORS["background"])
        configure_styles(self)
        set_window_icon(self)
        ExcelImportPanel(self).pack(fill="both", expand=True)


if __name__ == "__main__":
    ImportDatabaseApp().mainloop()
