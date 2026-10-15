"""Простое окно подготовки таблиц перед импортом."""

from copy import deepcopy
import json
from pathlib import Path
from queue import Queue, Empty
import threading
import tkinter as tk
from tkinter import filedialog, messagebox, simpledialog, ttk

from .styles import configure_styles
from design import COLORS
from .model import Project, load_excel


class ExcelPreparationApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Подготовка Excel к базе данных")
        self.geometry("1120x740")
        self.minsize(880, 600)
        self.configure(bg=COLORS["background"])
        configure_styles(self)
        self.project = Project()
        self.saved_state = self.project.as_dict()
        self.current = None
        self.busy = False
        self.messages = Queue()
        self.protocol("WM_DELETE_WINDOW", self.close)
        self.build()
        self.poll_id = self.after(100, self.poll)

    def build(self):
        outer = ttk.Frame(self, padding=16)
        outer.pack(fill="both", expand=True)
        ttk.Label(outer, text="Подготовка Excel", style="Title.TLabel").pack(anchor="w")
        ttk.Label(
            outer,
            text="Откройте Excel. Повторяющиеся поля вынесите в таблицу, свяжите её по ID и сохраните результат.",
        ).pack(anchor="w", pady=(4, 10))
        top = ttk.Frame(outer)
        top.pack(fill="x")
        self.buttons = []

        def button(parent, label, action):
            b = ttk.Button(parent, text=label, command=action)
            b.pack(side="left", padx=(0, 6), pady=3)
            self.buttons.append(b)

        button(top, "1. Открыть", self.open_excel)
        button(top, "2. Разделить", self.extract_dialog)
        button(top, "3. Связать", self.relation_dialog)
        button(top, "4. Сохранить", self.export)
        self.header = tk.StringVar(value="1")
        self.append_files = tk.BooleanVar(value=False)
        self.schema_var = tk.StringVar(value="public")
        self.menubar = tk.Menu(self)
        self.configure(menu=self.menubar)
        for title, commands in (
            (
                "Файл",
                (
                    ("Параметры чтения", self.show_options),
                    ("Открыть проект", self.open_project),
                    ("Сохранить проект", self.save_project),
                ),
            ),
            (
                "Таблица",
                (
                    ("Переименовать", self.rename),
                    ("Первичный ключ", self.key_dialog),
                    ("Тип колонки", self.column_type),
                    ("Добавить колонку", self.add_column),
                    ("Удалить колонку", self.remove_column),
                    ("Добавить строку", self.add_row),
                    ("Удалить строки", self.remove_row),
                    ("Убрать таблицу", self.remove_table),
                ),
            ),
            (
                "Связи",
                (
                    ("Все отношения", self.relations_dialog),
                    ("Составной ключ", self.manual_relation_dialog),
                    ("Проверить структуру", self.check),
                ),
            ),
            ("Правка", (("Отменить шаг", self.undo),)),
            ("Помощь", (("Как пользоваться", self.help),)),
        ):
            menu = tk.Menu(self.menubar, tearoff=False)
            self.menubar.add_cascade(label=title, menu=menu)
            for label, command in commands:
                menu.add_command(label=label, command=command)
        self.bind("<Control-z>", lambda event: self.undo())
        self.bind("<Command-z>", lambda event: self.undo())
        self.status = tk.StringVar(
            value="Откройте файлы или сохранённый проект."
        )
        self.status_label = ttk.Label(outer, textvariable=self.status, wraplength=1000)
        self.status_label.pack(side="bottom", anchor="w", pady=(10, 0))
        self.bind(
            "<Configure>",
            lambda e: (
                self.status_label.configure(wraplength=max(400, e.width - 32))
                if e.widget is self
                else None
            ),
        )
        body = ttk.Panedwindow(outer, orient="horizontal")
        self.body = body
        body.pack(fill="both", expand=True)
        sidebar = ttk.Frame(body, padding=(0, 0, 10, 0))
        body.add(sidebar, weight=0)
        ttk.Label(sidebar, text="Таблицы").pack(anchor="w")
        self.tables = tk.Listbox(sidebar, width=24, height=6, exportselection=False)
        self.tables.pack(fill="x", pady=(4, 12))
        self.tables.bind("<<ListboxSelect>>", self.select_table)
        ttk.Label(sidebar, text="Колонки (Ctrl / Cmd / Shift)").pack(anchor="w")
        self.columns = tk.Listbox(
            sidebar, width=24, height=6, selectmode="extended", exportselection=False
        )
        self.columns.pack(fill="both", expand=True, pady=(4, 4))
        ttk.Label(sidebar, text="★ — ID строки\n→ — ссылка на таблицу").pack(anchor="w")
        preview = ttk.Frame(body)
        body.add(preview, weight=1)
        self.info = ttk.Label(preview, text="Выберите Excel-файлы.")
        self.info.pack(anchor="w", pady=(0, 5))
        ttk.Label(
            preview,
            text="Двойной щелчок по ячейке — изменить значение. Предпросмотр: первые 200 строк.",
        ).pack(side="bottom", anchor="w", pady=5)
        grid = ttk.Frame(preview)
        grid.pack(fill="both", expand=True)
        self.tree = ttk.Treeview(grid, show="headings", selectmode="extended")
        self.tree.grid(row=0, column=0, sticky="nsew")
        vertical = ttk.Scrollbar(grid, orient="vertical", command=self.tree.yview)
        vertical.grid(row=0, column=1, sticky="ns")
        horizontal = ttk.Scrollbar(grid, orient="horizontal", command=self.tree.xview)
        horizontal.grid(row=1, column=0, sticky="ew")
        self.tree.configure(yscrollcommand=vertical.set, xscrollcommand=horizontal.set)
        grid.rowconfigure(0, weight=1)
        grid.columnconfigure(0, weight=1)
        self.tree.bind("<Double-1>", self.edit_cell)

    def close(self):
        if self.busy:
            messagebox.showinfo(
                "Подождите", "Дождитесь окончания чтения или сохранения.", parent=self
            )
            return
        if self.project.as_dict() != self.saved_state and not messagebox.askyesno(
            "Выход",
            "Закрыть редактор? Несохранённые изменения будут потеряны.",
            parent=self,
        ):
            return
        self.destroy()

    def show_options(self):
        dialog, body = self.popup("Файлы и параметры", "550x260")
        ttk.Label(body, text="Строка заголовков Excel").pack(anchor="w")
        ttk.Spinbox(body, from_=1, to=10000, textvariable=self.header, width=8).pack(
            anchor="w", pady=6
        )
        ttk.Checkbutton(
            body, text="Добавлять файлы к уже открытым", variable=self.append_files
        ).pack(anchor="w", pady=8)
        ttk.Label(body, text="Схема PostgreSQL для SQL отношений").pack(anchor="w")
        ttk.Entry(body, textvariable=self.schema_var).pack(fill="x", pady=6)
        ttk.Button(body, text="Готово", command=dialog.destroy).pack(
            anchor="e", pady=10
        )

    def toggle_advanced(self):
        self.show_options()

    def destroy(self):
        if hasattr(self, "poll_id"):
            try:
                self.after_cancel(self.poll_id)
            except tk.TclError:
                pass
        super().destroy()

    def poll(self):
        try:
            result, callback, error = self.messages.get_nowait()
        except Empty:
            pass
        else:
            self.busy = False
            for b in self.buttons:
                b.configure(state="normal")
            for index in range(5):
                self.menubar.entryconfigure(index, state="normal")
            if error:
                self.error(error)
            else:
                callback(result)
        self.poll_id = self.after(100, self.poll)

    def worker(self, operation, callback):
        self.busy = True
        for b in self.buttons:
            b.configure(state="disabled")
        for index in range(5):
            self.menubar.entryconfigure(index, state="disabled")

        def run():
            try:
                self.messages.put((operation(), callback, None))
            except Exception as error:
                self.messages.put((None, callback, error))

        threading.Thread(target=run, daemon=True).start()

    def error(self, error):
        self.status.set(str(error))
        messagebox.showerror("Проверьте данные", str(error), parent=self)

    def replace_allowed(self):
        return not self.project.model.tables or messagebox.askyesno(
            "Открыть заново",
            "Текущий проект будет заменён. Сохраните его заранее, если он нужен. Продолжить?",
            parent=self,
        )

    def open_excel(self):
        paths = filedialog.askopenfilenames(
            parent=self,
            title="Выберите Excel-файлы",
            filetypes=[
                ("Excel / OpenDocument", "*.xlsx *.xls *.xlsb *.xlsm *.ods"),
                ("Все файлы", "*.*"),
            ],
        )
        append = self.append_files.get() and bool(self.project.model.tables)
        if not paths or (not append and not self.replace_allowed()):
            return
        try:
            header = int(self.header.get())
            if header < 1:
                raise ValueError("Номер строки заголовков должен быть от 1.")
        except ValueError as error:
            self.error(error)
            return
        self.status.set("Читаю Excel…")
        self.worker(
            lambda: Project(load_excel(paths, header)), lambda p: self.loaded(p, append)
        )

    def loaded(self, project, append=False):
        created = project.prepare_keys()
        if append:
            from .model import unique_name

            def merge():
                used = set(self.project.model.table_names())
                for table in project.model.tables:
                    table.name = unique_name(table.name, used)
                    self.project.model.tables.append(table)
                self.project.model.warnings.extend(project.model.warnings)

            self.project.change(merge)
        else:
            self.project, self.current = project, None
            self.saved_state = self.project.as_dict()
        self.refresh()
        self.status.set(
            "Готово. Для новой таблицы: «2. Разделить». Для готовых таблиц: «3. Связать»."
            + (f" Автоматически создано ID: {len(created)}." if created else "")
        )

    def open_project(self):
        path = filedialog.askopenfilename(
            parent=self, filetypes=[("Проект редактора", "*.json")]
        )
        if path and self.replace_allowed():
            try:
                self.loaded(
                    Project.from_dict(
                        json.loads(Path(path).read_text(encoding="utf-8"))
                    )
                )
            except Exception as error:
                self.error(error)

    def selected(self):
        if self.busy:
            return None
        if not self.current:
            self.error("Сначала откройте Excel и выберите таблицу.")
            return None
        return self.project.table(self.current)

    def selected_columns(self):
        table = self.project.table(self.current)
        return tuple(table.columns[i].name for i in self.columns.curselection())

    def refresh(self, chosen=None):
        self.current = chosen or self.current
        names = self.project.model.table_names()
        if self.current not in names:
            self.current = names[0] if names else None
        self.tables.delete(0, "end")
        for name in names:
            self.tables.insert("end", name)
        if self.current:
            self.tables.selection_set(names.index(self.current))
            self.show_table()
        else:
            self.columns.delete(0, "end")
            self.tree.delete(*self.tree.get_children())
            self.tree.configure(columns=())
            self.info.configure(text="Откройте Excel-файлы.")

    def select_table(self, _=None):
        selection = self.tables.curselection()
        if selection and not self.busy:
            self.current = self.project.model.tables[selection[0]].name
            self.show_table()

    def show_table(self):
        table = self.project.table(self.current)
        self.columns.delete(0, "end")
        fks = {c for fk in table.foreign_keys for c in fk.columns}
        for c in table.columns:
            self.columns.insert(
                "end",
                ("★ " if c.is_primary_key else "→ " if c.name in fks else "") + c.name,
            )
        self.tree.delete(*self.tree.get_children())
        self.tree.configure(columns=[c.name for c in table.columns])
        for c in table.columns:
            self.tree.heading(c.name, text=c.name)
            self.tree.column(c.name, width=155, stretch=False)
        for index, row in enumerate(table.rows[:200]):
            self.tree.insert(
                "",
                "end",
                iid=str(index),
                values=[
                    "" if row.get(c.name) is None else str(row[c.name])
                    for c in table.columns
                ],
            )
        self.info.configure(
            text=f"{table.name} · {len(table.rows)} строк · {len(table.columns)} колонок"
        )

    def apply(self, operation, *args, chosen=None, **kwargs):
        try:
            result = self.project.change(operation, *args, **kwargs)
            self.refresh(chosen)
            self.status.set(
                "Изменения в предпросмотре. Правка → Отменить шаг (Ctrl/Cmd+Z) возвращает прежние данные."
            )
            return True, result
        except Exception as error:
            self.error(error)
            return False, None

    def undo(self):
        if not self.busy:
            self.project.undo()
            self.refresh()

    def popup(self, title, size="640x520"):
        dialog = tk.Toplevel(self)
        dialog.title(title)
        dialog.geometry(size)
        dialog.transient(self)
        dialog.grab_set()
        body = ttk.Frame(dialog, padding=16)
        body.pack(fill="both", expand=True)
        return dialog, body

    @staticmethod
    def entry(body, label, default=""):
        ttk.Label(body, text=label).pack(anchor="w", pady=(6, 3))
        value = tk.StringVar(value=default)
        ttk.Entry(body, textvariable=value).pack(fill="x")
        return value

    @staticmethod
    def column_list(body, table, label, selected=(), height=6):
        ttk.Label(body, text=label).pack(anchor="w", pady=(8, 3))
        box = tk.Listbox(
            body, selectmode="extended", exportselection=False, height=height
        )
        box.pack(fill="both", expand=True)
        for index, c in enumerate(table.columns):
            box.insert("end", c.name)
            if c.name in selected:
                box.selection_set(index)
        return box

    @staticmethod
    def choices(box, table):
        return tuple(table.columns[i].name for i in box.curselection())

    def rename(self):
        table = self.selected()
        if table is None:
            return
        dialog, body = self.popup("Имена таблицы и колонок", "640x600")
        table_value = self.entry(body, "Имя таблицы (английскими буквами)", table.name)
        ttk.Label(
            body,
            text="Значения ячеек сохраняются. Например: производитель → manufacturer.",
        ).pack(anchor="w", pady=6)
        canvas = tk.Canvas(body, highlightthickness=0)
        canvas.pack(fill="both", expand=True)
        scroll = ttk.Scrollbar(canvas, command=canvas.yview)
        scroll.pack(side="right", fill="y")
        frame = ttk.Frame(canvas)
        window = canvas.create_window((0, 0), window=frame, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        frame.bind(
            "<Configure>", lambda _: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.bind(
            "<Configure>", lambda e: canvas.itemconfigure(window, width=e.width - 20)
        )
        values = {}
        for c in table.columns:
            row = ttk.Frame(frame)
            row.pack(fill="x", pady=3)
            ttk.Label(row, text=c.source_name, width=28).pack(side="left")
            values[c.name] = tk.StringVar(value=c.name)
            ttk.Entry(row, textvariable=values[c.name]).pack(
                side="left", fill="x", expand=True
            )

        def save():
            from .model import identifier

            def operation():
                names = {old: identifier(value.get()) for old, value in values.items()}
                if len(set(names.values())) != len(names):
                    raise ValueError("Имена колонок не должны повторяться.")
                # Временные имена позволяют поменять две колонки местами.
                temporary = {}
                for index, old in enumerate(names):
                    temp = f"_rename_{index}"
                    while temp in names or temp in names.values():
                        temp += "_"
                    self.project.rename_column(table.name, old, temp)
                    temporary[temp] = names[old]
                for old, new in temporary.items():
                    self.project.rename_column(table.name, old, new)
                self.project.rename_table(table.name, table_value.get())

            ok, _ = self.apply(operation, chosen=table_value.get().strip())
            if ok:
                dialog.destroy()

        ttk.Button(body, text="Сохранить имена", command=save).pack(anchor="e", pady=10)

    def key_dialog(self):
        table = self.selected()
        if table is None:
            return
        dialog, body = self.popup("Первичный ключ", "580x480")
        ttk.Label(
            body,
            text="Ключ однозначно определяет строку. Пустые значения и повторы запрещены.",
            wraplength=540,
        ).pack(anchor="w")
        columns = self.column_list(
            body,
            table,
            "Выбрать существующие колонки (можно несколько)",
            [c.name for c in table.primary_keys],
        )

        def use():
            if self.apply(
                self.project.set_key, table.name, self.choices(columns, table)
            )[0]:
                dialog.destroy()

        ttk.Button(body, text="Использовать выбранные как PK", command=use).pack(
            anchor="w", pady=8
        )
        name = self.entry(
            body, "Или создать новый числовой ID", table.name.rstrip("s") + "_id"
        )

        def create():
            if self.apply(self.project.add_id, table.name, name.get())[0]:
                dialog.destroy()

        ttk.Button(body, text="Создать ID 1, 2, 3…", command=create).pack(
            anchor="w", pady=8
        )

    def extract_dialog(self):
        table = self.selected()
        if table is None:
            return
        from .model import suggested_names, unique_name

        dialog, body = self.popup("Сделать отдельную таблицу", "680x520")
        ttk.Label(
            body,
            text="Отметьте поля, которые хотите хранить отдельно. Например, производитель повторяется у многих товаров — его можно вынести в справочник.",
            wraplength=640,
        ).pack(anchor="w")
        available = [c for c in table.columns if not c.is_primary_key]
        selected = set(self.selected_columns())
        manual = tk.BooleanVar(value=False)
        fields = {}
        field_area = ttk.Frame(body)
        field_area.pack(fill="x", pady=12)
        field_area.columnconfigure(0, weight=1)
        canvas = tk.Canvas(field_area, height=200, highlightthickness=0)
        canvas.grid(row=0, column=0, sticky="ew")
        scroll = ttk.Scrollbar(field_area, command=canvas.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.extract_canvas = canvas
        checkboxes = ttk.Frame(canvas)
        window = canvas.create_window((0, 0), window=checkboxes, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)
        checkboxes.bind(
            "<Configure>", lambda _: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        canvas.bind(
            "<Configure>", lambda e: canvas.itemconfigure(window, width=e.width - 20)
        )
        result = tk.StringVar()
        ttk.Label(body, textvariable=result, wraplength=640).pack(anchor="w", pady=6)
        advanced = ttk.Frame(body)
        target = tk.StringVar()
        key = tk.StringVar()
        match = tk.StringVar()
        for label, variable in (
            ("Имя новой таблицы", target),
            ("Имя нового ID", key),
            ("Совпадение по колонкам через запятую (пусто = все выбранные)", match),
        ):
            ttk.Label(advanced, text=label).pack(anchor="w", pady=(5, 2))
            ttk.Entry(advanced, textvariable=variable).pack(fill="x")

        def selected_fields():
            return tuple(c.name for c in available if fields[c.name].get())

        def update_result():
            columns = selected_fields()
            if not columns:
                result.set("Отметьте хотя бы одно поле. ID строки переносить не нужно.")
                return
            if not manual.get():
                new_table, new_key = suggested_names(table, columns)
                target.set(
                    unique_name(new_table, set(self.project.model.table_names()))
                )
                key.set(new_key)
                match.set("")
            result.set(
                f"Получится отдельная таблица {target.get()}.\nВ {table.name} выбранные поля заменятся ссылкой {key.get()}. ID и связь создаются автоматически."
            )

        for c in available:
            fields[c.name] = tk.BooleanVar(value=c.name in selected)
            original = c.source_name
            label = (
                c.name
                if original in {c.name, "(created)", "(generated)"}
                else f"{original} ({c.name})"
            )
            ttk.Checkbutton(
                checkboxes, text=label, variable=fields[c.name], command=update_result
            ).pack(anchor="w", pady=3)

        def toggle_parameters():
            if manual.get():
                advanced.pack(fill="x", before=actions, pady=(0, 8))
                dialog.geometry("680x710")
            else:
                advanced.pack_forget()
                dialog.geometry("680x520")
            update_result()

        ttk.Checkbutton(
            body,
            text="Задать имена и совпадения вручную",
            variable=manual,
            command=toggle_parameters,
        ).pack(anchor="w", pady=6)
        actions = ttk.Frame(body)
        actions.pack(side="bottom", fill="x", pady=(8, 0))
        self.extract_fields = fields

        def save():
            columns = selected_fields()
            if not columns:
                self.error("Отметьте поле, которое нужно вынести в отдельную таблицу.")
                return
            update_result()
            keys = tuple(c.strip() for c in match.get().split(",") if c.strip())
            if self.apply(
                self.project.extract, table.name, columns, target.get(), key.get(), keys
            )[0]:
                self.status.set(
                    f"Создана таблица {target.get()}. Можно вынести другие поля или нажать «Сохранить Excel»."
                )
                dialog.destroy()

        self.extract_create_button = ttk.Button(
            actions, text="Создать таблицу", style="Accent.TButton", command=save
        )
        self.extract_create_button.pack(side="right")
        ttk.Button(actions, text="Отмена", command=dialog.destroy).pack(side="left")
        update_result()

    def relation_dialog(self):
        if self.busy:
            return
        if len(self.project.model.tables) < 2:
            self.error(
                "Откройте как минимум две таблицы. Для добавления файлов: меню Таблица → Файлы и параметры."
            )
            return
        from .links import LinkWizard

        self.links_window = LinkWizard(self)

    def manual_relation_dialog(self):
        table = self.selected()
        if table is None:
            return
        dialog, body = self.popup("Связь с другой таблицей", "680x660")
        ttk.Label(
            body,
            text=f"Дочерняя таблица: {table.name}. Выберите родителя и колонки для сравнения.",
            wraplength=640,
        ).pack(anchor="w")
        mode = tk.StringVar(value="fk")
        ttk.Radiobutton(
            body,
            text="В колонках уже ID: создать внешний ключ",
            variable=mode,
            value="fk",
        ).pack(anchor="w", pady=5)
        ttk.Radiobutton(
            body,
            text="В колонках названия: получить ID по совпадению",
            variable=mode,
            value="lookup",
        ).pack(anchor="w")
        child_box = self.column_list(
            body,
            table,
            "Колонки дочерней таблицы (порядок сверху вниз)",
            self.selected_columns(),
            height=5,
        )
        parent_var = tk.StringVar(
            value=next(
                (n for n in self.project.model.table_names() if n != table.name),
                table.name,
            )
        )
        parent_box = ttk.Combobox(
            body,
            textvariable=parent_var,
            values=self.project.model.table_names(),
            state="readonly",
        )
        parent_box.pack(fill="x", pady=(12, 4))
        parent = self.project.table(parent_var.get())
        parent_columns = self.column_list(
            body,
            parent,
            "PK родителя или его поля для поиска совпадения",
            [c.name for c in parent.primary_keys],
            height=5,
        )

        def change_parent(_=None):
            parent_columns.delete(0, "end")
            p = self.project.table(parent_var.get())
            for index, c in enumerate(p.columns):
                parent_columns.insert("end", c.name)
                if c.is_primary_key:
                    parent_columns.selection_set(index)

        parent_box.bind("<<ComboboxSelected>>", change_parent)
        key = self.entry(
            body, "Новая колонка ID (только для поиска по названиям)", "reference_id"
        )
        ttk.Label(
            body,
            text="Совпадение точное, по значениям и типам. Неоднозначные имена и потерянные ссылки не связываются. Исходные названия при поиске остаются до ручного удаления колонки.",
            wraplength=640,
        ).pack(anchor="w", pady=8)

        def save():
            p = self.project.table(parent_var.get())
            child_cols = self.choices(child_box, table)
            parent_cols = self.choices(parent_columns, p)
            operation = (
                self.project.add_relation
                if mode.get() == "fk"
                else self.project.link_by_values
            )
            args = (table.name, child_cols, p.name, parent_cols)
            if mode.get() == "lookup":
                args += (key.get(),)
            if self.apply(operation, *args)[0]:
                dialog.destroy()

        ttk.Button(body, text="Проверить и создать связь", command=save).pack(
            anchor="e", pady=8
        )

    def relations_dialog(self):
        dialog, body = self.popup("Отношения таблиц", "800x420")
        entries = [
            (t.name, f) for t in self.project.model.tables for f in t.foreign_keys
        ]
        box = tk.Listbox(body, exportselection=False)
        box.pack(fill="both", expand=True)
        for name, fk in entries:
            box.insert(
                "end",
                f"{name} ({', '.join(fk.columns)}) → {fk.referenced_table} ({', '.join(fk.reference_columns)})",
            )
        if not entries:
            box.insert(
                "end",
                "Связей пока нет. Выделение справочника создаёт связь автоматически.",
            )

        def remove():
            if entries and box.curselection():
                name, fk = entries[box.curselection()[0]]
                self.apply(lambda: self.project.table(name).foreign_keys.remove(fk))
                dialog.destroy()

        ttk.Button(body, text="Удалить выбранную связь", command=remove).pack(
            anchor="e", pady=10
        )

    def column_type(self):
        table = self.selected()
        if table is None:
            return
        cols = self.selected_columns()
        if len(cols) != 1:
            self.error("Выберите одну колонку в списке слева.")
            return
        column = next(c for c in table.columns if c.name == cols[0])
        dialog, body = self.popup("Тип колонки", "550x260")
        ttk.Label(body, text=f"{table.name}.{column.name}: тип для PostgreSQL").pack(
            anchor="w"
        )
        value = tk.StringVar(value=column.pg_type)
        ttk.Combobox(
            body,
            textvariable=value,
            state="readonly",
            values=(
                "TEXT",
                "BIGINT",
                "NUMERIC",
                "BOOLEAN",
                "DATE",
                "TIMESTAMP",
                "UUID",
            ),
        ).pack(fill="x", pady=12)
        ttk.Label(
            body,
            text="TEXT сохраняет коды с ведущими нулями. Не назначайте числовой тип артикулам вроде 001.",
            wraplength=510,
        ).pack(anchor="w")

        def save():
            def operation():
                from excel2pg.rules import apply_table_rules

                apply_table_rules(
                    self.project.model,
                    {table.name: {"types": {column.name: value.get()}}},
                )

            if self.apply(operation)[0]:
                dialog.destroy()

        ttk.Button(body, text="Проверить и применить", command=save).pack(
            anchor="e", pady=12
        )

    def add_column(self):
        table = self.selected()
        if table is None:
            return
        name = simpledialog.askstring(
            "Новая колонка", "Имя английскими буквами:", parent=self
        )
        if name:

            def operation():
                from .model import identifier
                from excel2pg.entities import ColumnEntity

                actual = identifier(name)
                if actual in {c.name for c in table.columns}:
                    raise ValueError("Такая колонка уже есть.")
                table.columns.append(ColumnEntity(actual, actual, "TEXT"))
                for row in table.rows:
                    row[actual] = None

            self.apply(operation)

    def remove_column(self):
        table = self.selected()
        if table is None:
            return
        columns = self.selected_columns()
        if not columns:
            self.error("Выберите колонки слева.")
            return
        if not messagebox.askyesno(
            "Удаление колонок",
            "Убрать выбранные колонки из подготовленных файлов? Исходный Excel сохранится.",
            parent=self,
        ):
            return

        def operation():
            if any(
                c.is_primary_key and c.name in columns for c in table.columns
            ) or any(set(f.columns) & set(columns) for f in table.foreign_keys):
                raise ValueError(
                    "Сначала измените первичный ключ или удалите связь с этими колонками."
                )
            table.columns = [c for c in table.columns if c.name not in columns]
            for row in table.rows:
                for c in columns:
                    row.pop(c, None)

        self.apply(operation)

    def add_row(self):
        table = self.selected()
        if table is None:
            return

        def operation():
            row = {c.name: None for c in table.columns}
            if len(table.primary_keys) == 1:
                key = table.primary_key.name
                values = [r[key] for r in table.rows]
                if all(isinstance(v, int) and not isinstance(v, bool) for v in values):
                    row[key] = max(values, default=0) + 1
            table.rows.insert(0, row)

        self.apply(operation)

    def remove_table(self):
        table = self.selected()
        if table is None:
            return
        if not messagebox.askyesno(
            "Убрать таблицу",
            f"Не включать {table.name} в подготовленные файлы? Исходный Excel сохранится.",
            parent=self,
        ):
            return

        def operation():
            if any(
                f.referenced_table == table.name
                for t in self.project.model.tables
                if t is not table
                for f in t.foreign_keys
            ):
                raise ValueError(
                    "На таблицу есть ссылки. Сначала удалите их в окне «Связи»."
                )
            self.project.model.tables.remove(table)

        self.apply(operation)

    def remove_row(self):
        table = self.selected()
        if table is None:
            return
        rows = sorted((int(i) for i in self.tree.selection()), reverse=True)
        if rows and messagebox.askyesno(
            "Удаление строк",
            f"Удалить строк: {len(rows)}? Связи будут проверены перед сохранением.",
            parent=self,
        ):
            self.apply(lambda: [table.rows.pop(i) for i in rows])

    def edit_cell(self, event):
        if self.busy or not self.current:
            return
        table = self.project.table(self.current)
        item, column_id = self.tree.identify_row(event.y), self.tree.identify_column(
            event.x
        )
        if not item or not column_id:
            return
        column = table.columns[int(column_id[1:]) - 1]
        row = table.rows[int(item)]
        old = row.get(column.name)
        value = simpledialog.askstring(
            "Ячейка",
            f"{column.name} ({column.pg_type}). Пусто = NULL.\nДаты: ГГГГ-ММ-ДД; десятичные числа: через точку.",
            initialvalue="" if old is None else str(old),
            parent=self,
        )
        if value is None:
            return

        def operation():
            from excel2pg.rules import apply_table_rules

            row[column.name] = value if value != "" else None
            apply_table_rules(
                self.project.model,
                {table.name: {"types": {column.name: column.pg_type}}},
            )

        self.apply(operation)

    def check(self):
        if not self.project.model.tables:
            self.error("Сначала откройте Excel.")
            return
        errors = self.project.validate()
        hints = self.project.suggestions()
        dialog, body = self.popup("Проверка структуры", "800x600")
        output = tk.Text(body, wrap="word", padx=10, pady=10)
        output.pack(fill="both", expand=True)
        sections = [
            "Ошибки ключей и связей:\n" + "\n".join(errors or ["Ошибок не найдено."]),
            "Подсказки (решение принимает разработчик):\n"
            + "\n".join(hints or ["Нет повторяющихся текстовых полей."]),
            "3НФ: одно значение в ячейке; атрибуты зависят от всего ключа и не зависят друг от друга. Название производителя хранится в manufacturers, а в products — manufacturer_id. Повтор цены или имени сам по себе не доказывает нарушение 3НФ.",
            "Чтение исходников:\n" + "\n".join(self.project.model.warnings),
        ]
        output.insert("end", "\n\n".join(sections))
        output.configure(state="disabled")
        ttk.Button(body, text="Закрыть", command=dialog.destroy).pack(
            anchor="e", pady=10
        )

    def save_project(self):
        if not self.project.model.tables:
            return
        path = filedialog.asksaveasfilename(
            parent=self,
            initialfile="normalizer_project.json",
            defaultextension=".json",
            filetypes=[("Проект редактора", "*.json")],
        )
        if path:
            try:
                self.project.save_project(path)
                self.saved_state = self.project.as_dict()
                self.status.set(
                    "Проект сохранён. Его можно открыть и продолжить позже."
                )
            except Exception as error:
                self.error(error)

    def export(self):
        if any(not t.primary_keys for t in self.project.model.tables):
            if not self.apply(self.project.prepare_keys)[0]:
                return
        errors = self.project.validate()
        if errors or not self.project.model.tables:
            self.error("\n".join(errors or ["Нет таблиц."]))
            return
        directory = filedialog.askdirectory(
            parent=self, title="Где сохранить подготовленные файлы?"
        )
        if not directory:
            return
        schema = self.schema_var.get().strip() or "public"
        snapshot = Project(deepcopy(self.project.model))
        self.status.set("Сохраняю отдельную папку с Excel, настройками импорта и SQL…")

        def done(path):
            self.saved_state = snapshot.as_dict()
            self.status.set(f"Готово: {path}")
            messagebox.showinfo(
                "Файлы готовы",
                f"Файлы сохранены:\n{path}",
                parent=self,
            )

        self.worker(lambda: snapshot.export(directory, schema.strip()), done)

    def help(self):
        messagebox.showinfo(
            "Как пользоваться",
            "1. Откройте Excel.\n\n2. Чтобы вынести повторяющиеся поля: выберите таблицу и нажмите «Разделить».\n\n3. Чтобы соединить готовые таблицы: нажмите «Связать», выберите два поля и проверьте примеры будущих ID. Для ФИО из трёх колонок есть пункт «ФИО целиком».\n\n4. Сохраните результат. Исходные файлы останутся без изменений.\n\nИмена, ключи и правка строк — в меню «Таблица». Отмена шага — Ctrl/Cmd+Z. Создать связь с другой таблицей можно ещё раз тем же способом.",
            parent=self,
        )
