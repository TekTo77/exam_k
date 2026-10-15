from __future__ import annotations

import threading
import queue
import tkinter as tk
from pathlib import Path
from interface.formatting import font
from design import WINDOW
from tkinter import filedialog, messagebox, ttk
from excel_importer.profile import read_import_profile


class ExcelImportPanel(ttk.Frame):
    """Самостоятельная панель импорта Excel в PostgreSQL."""

    def __init__(self, parent: tk.Misc):
        super().__init__(parent)
        self.files: list[str] = []
        self.model = None
        self.profile = None
        self.results = queue.Queue()
        self._build_ui()

    def _build_ui(self) -> None:
        root = ttk.Frame(self, padding=16)
        root.pack(fill="both", expand=True)
        ttk.Label(
            root, text="Импорт Excel", font=font("title", True)
        ).pack(anchor="w")
        file_box = ttk.LabelFrame(root, text="1. Excel-файлы", padding=10)
        file_box.pack(fill="x")
        self.files_label = ttk.Label(file_box, text="Файлы ещё не выбраны")
        self.files_label.pack(side="left", fill="x", expand=True)
        ttk.Button(file_box, text="Выбрать файлы", command=self.choose_files).pack(
            side="right"
        )

        options = ttk.Frame(root)
        options.pack(fill="x", pady=(0, 8))
        ttk.Label(options, text="Строка заголовков:").pack(side="left")
        self.header_entry = ttk.Entry(options, width=5)
        self.header_entry.insert(0, "1")
        self.header_entry.pack(side="left", padx=(5, 14))
        self.replace_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(
            options, text="Пересоздать таблицы", variable=self.replace_var
        ).pack(side="left")

        actions = ttk.Frame(root)
        actions.pack(fill="x")
        ttk.Button(actions, text="Проверить Excel", command=self.preview).pack(
            side="left"
        )
        ttk.Button(actions, text="Сохранить schema.sql", command=self.save_sql).pack(
            side="left", padx=8
        )
        ttk.Button(actions, text="Правила редактора", command=self.choose_profile).pack(
            side="left"
        )
        self.import_button = ttk.Button(
            actions, text="Импортировать", command=self.start_import
        )
        self.import_button.pack(side="right")

        from config import COLORS

        self.output = tk.Text(
            root,
            height=18,
            wrap="word",
            state="disabled",
            bg=COLORS["surface"],
            fg=COLORS["text"],
            insertbackground=COLORS["text"],
        )
        self.output.pack(fill="both", expand=True, pady=(12, 0))
        self.log("Выбери Excel-файлы для импорта.")

    def log(self, text: str) -> None:
        self.output.configure(state="normal")
        self.output.insert("end", text + "\n")
        self.output.see("end")
        self.output.configure(state="disabled")

    def choose_files(self) -> None:
        selected = filedialog.askopenfilenames(
            parent=self,
            title="Выберите Excel-файлы",
            filetypes=[
                ("Excel и OpenDocument", "*.xlsx *.xls *.xlsb *.xlsm *.ods"),
                ("Все файлы", "*.*"),
            ],
        )
        if selected:
            self.files = list(selected)
            self.profile = None
            self.files_label.configure(text=f"Выбрано файлов: {len(self.files)}")
            self.log("Выбраны файлы:")
            for file in self.files:
                self.log(f"  • {Path(file).name}")
            folders = {Path(file).parent for file in self.files}
            if len(folders) == 1:
                profile_path = next(iter(folders)) / "import_profile.json"
                if profile_path.is_file():
                    try:
                        self.profile = read_import_profile(profile_path, self.files)
                        self.log(
                            "Правила импорта загружены."
                        )
                    except Exception as error:
                        self.log(f"Профиль редактора не загружен: {error}")
                        messagebox.showerror("Профиль импорта", str(error), parent=self)
                        # Не импортируем подготовленные файлы с ошибочным профилем.
                        self.files = []
                        self.files_label.configure(
                            text="Выберите файлы с корректным профилем"
                        )

    def choose_profile(self):
        path = filedialog.askopenfilename(
            parent=self,
            title="Настройки подготовленных Excel",
            filetypes=[("Профиль редактора", "*.json")],
        )
        if path:
            try:
                self.profile = read_import_profile(path, self.files)
                self.log("Правила импорта загружены.")
            except Exception as error:
                messagebox.showerror("Профиль импорта", str(error), parent=self)

    def _parse(self):
        if not self.files:
            messagebox.showwarning(
                "Нет файлов", "Сначала выбери Excel-файлы.", parent=self
            )
            return None
        try:
            header_row = int(self.header_entry.get())
            if header_row < 1:
                raise ValueError
        except ValueError:
            messagebox.showerror(
                "Ошибка",
                "Строка заголовков должна быть целым числом от 1.",
                parent=self,
            )
            return None
        try:
            from excel_importer.parser import parse_excel_files
            from config import (
                IMPORT_REFERENCE_RULES,
                IMPORT_TABLE_RULES,
                IMPORT_FOREIGN_KEYS,
                IMPORT_AUTO_FOREIGN_KEYS,
                IMPORT_HEADER_ROWS,
            )

            profile = self.profile
            if profile:
                if not {Path(f).name for f in self.files} <= set(profile["files"]):
                    raise ValueError(
                        "Выбранные файлы не принадлежат загруженному профилю редактора."
                    )
                header_row = 1
            self.model = parse_excel_files(
                self.files,
                header_row=header_row,
                reference_rules=(
                    profile["reference_rules"] if profile else IMPORT_REFERENCE_RULES
                ),
                table_rules=profile["table_rules"] if profile else IMPORT_TABLE_RULES,
                foreign_keys=(
                    profile["foreign_keys"] if profile else IMPORT_FOREIGN_KEYS
                ),
                auto_foreign_keys=False if profile else IMPORT_AUTO_FOREIGN_KEYS,
                header_rows={} if profile else IMPORT_HEADER_ROWS,
            )
            return self.model
        except ImportError as error:
            messagebox.showerror(
                "Не хватает библиотеки",
                f"Установи зависимости из requirements.txt.\n\n{error}",
                parent=self,
            )
            return None
        except Exception as error:
            messagebox.showerror("Ошибка чтения Excel", str(error), parent=self)
            return None

    def preview(self) -> None:
        model = self._parse()
        if model is None:
            return
        self.log(f"\nНайдено таблиц: {len(model.tables)}")
        for table in model.tables:
            primary_key = ", ".join(c.name for c in table.primary_keys) or "нет"
            self.log(f"{table.name}: {len(table.rows)} строк, PK: {primary_key}")
            for foreign_key in table.foreign_keys:
                status = (
                    "готова"
                    if foreign_key.enabled
                    else f"пропущена, сирот: {foreign_key.orphan_count}"
                )
                self.log(
                    f"  связь: {table.name} ({', '.join(foreign_key.columns)}) → {foreign_key.referenced_table} ({', '.join(foreign_key.reference_columns)}) ({status})"
                )
        for warning in model.warnings:
            self.log(f"Предупреждение: {warning}")

    def save_sql(self) -> None:
        model = self._parse()
        if model is None:
            return
        path = filedialog.asksaveasfilename(
            parent=self,
            defaultextension=".sql",
            initialfile="schema.sql",
            filetypes=[("SQL", "*.sql")],
        )
        if path:
            from excel_importer.postgres import create_schema_sql

            from storage.connection import read_connection_settings

            try:
                schema = read_connection_settings()["schema"]
            except ValueError as error:
                messagebox.showerror("Подключение", str(error), parent=self)
                return
            Path(path).write_text(
                create_schema_sql(model, schema, self.replace_var.get()),
                encoding="utf-8",
            )
            self.log(f"SQL-схема сохранена: {path}")

    def start_import(self) -> None:
        model = self._parse()
        if model is None:
            return
        from storage.connection import read_connection_config

        try:
            settings = read_connection_config()
        except Exception as error:
            messagebox.showerror("Подключение", str(error), parent=self)
            return
        self.import_button.configure(state="disabled")
        self.log("\nСоздаю таблицы и загружаю строки...")
        threading.Thread(
            target=self._import_worker,
            args=(model, settings["dsn"], settings["schema"], self.replace_var.get()),
            daemon=True,
        ).start()
        self.after(100, self._poll_import)

    def _import_worker(self, model, conninfo, schema, replace):
        try:
            from excel_importer.postgres import import_model

            result = import_model(model, conninfo, schema, replace=replace)
            self.results.put((True, result))
        except Exception as error:
            self.results.put((False, error))

    def _poll_import(self):
        try:
            ok, result = self.results.get_nowait()
        except queue.Empty:
            self.after(100, self._poll_import)
            return
        if ok:
            self._import_done(result)
        else:
            self._import_failed(result)

    def _import_done(self, result) -> None:
        self.import_button.configure(state="normal")
        self.log(
            f"Готово: таблиц {result.tables_created}, строк {result.rows_inserted}, внешних ключей {result.foreign_keys_added}."
        )
        for warning in result.warnings:
            self.log(f"Предупреждение: {warning}")
        messagebox.showinfo(
            "Импорт завершён", "Данные загружены.", parent=self
        )

    def _import_failed(self, error: Exception) -> None:
        self.import_button.configure(state="normal")
        self.log(f"Ошибка импорта: {error}")
        messagebox.showerror("Ошибка импорта", str(error), parent=self)


class ExcelImportWindow(tk.Toplevel):
    """Совместимое отдельное окно для запуска панели импорта."""

    def __init__(self, parent: tk.Misc):
        super().__init__(parent)
        self.title("Импорт Excel")
        self.geometry("%dx%d" % WINDOW["import_size"])
        self.minsize(*WINDOW["import_minimum"])
        self.transient(parent)
        self.grab_set()
        ExcelImportPanel(self).pack(fill="both", expand=True)
