"""Мастер связи двух таблиц с проверкой совпадений."""

import tkinter as tk
from tkinter import ttk

from .model import singular_name, english_name


def field_choices(table):
    choices = {}
    for c in table.columns:
        original = c.source_name
        label = (
            c.name
            if original in {c.name, "(created)", "(generated)", "(resolved reference)"}
            else f"{original} ({c.name})"
        )
        choices[label] = (c.name,)
    by_name = {
        english_name(alias): c.name
        for c in table.columns
        for alias in (c.name, c.source_name)
    }
    parts = []
    for aliases in (
        ("last_name", "surname", "фамилия"),
        ("first_name", "имя"),
        ("middle_name", "отчество", "отчетсво"),
    ):
        match = next(
            (by_name[english_name(n)] for n in aliases if english_name(n) in by_name),
            None,
        )
        if match:
            parts.append(match)
    if len(parts) >= 2:
        choices["ФИО целиком: " + " + ".join(parts)] = tuple(parts)
    if len(parts) == 3:
        choices["Фамилия и имя: " + " + ".join(parts[:2])] = tuple(parts[:2])
    return choices


class LinkWizard(tk.Toplevel):
    def __init__(self, app):
        super().__init__(app)
        self.app = app
        self.title("Связать таблицы")
        self.geometry("720x650")
        self.minsize(660, 610)
        self.transient(app)
        self.grab_set()
        names = app.project.model.table_names()
        self.child = tk.StringVar(value=app.current or names[0])
        others = [n for n in names if n != self.child.get()]
        self.parent = tk.StringVar(
            value=next(
                (n for n in others if n == "users" or n.startswith("users_")),
                others[0] if others else names[0],
            )
        )
        self.child_field = tk.StringVar()
        self.parent_field = tk.StringVar()
        self.reference = tk.StringVar()
        self.mode = tk.StringVar(value="text")
        self.allow_missing = tk.BooleanVar(value=False)
        self.replace_existing = tk.BooleanVar(value=False)
        self.normalize = tk.BooleanVar(value=True)
        self.summary = tk.StringVar()
        body = ttk.Frame(self, padding=16)
        body.pack(fill="both", expand=True)
        ttk.Label(
            body,
            text="Выберите поля, которые обозначают одно и то же",
            style="Title.TLabel",
            wraplength=680,
        ).pack(anchor="w")
        ttk.Label(
            body,
            text="Например: ФИО в заказах → ФИО пользователя. В заказы будет записан ID найденного пользователя.",
            wraplength=680,
        ).pack(anchor="w", pady=(5, 12))
        selectors = ttk.Frame(body)
        selectors.pack(fill="x")
        selectors.columnconfigure(0, weight=1)
        selectors.columnconfigure(1, weight=1)
        self.boxes = {}
        for i, (title, table_var, field_var, side) in enumerate(
            (
                ("1. Где нужна ссылка", self.child, self.child_field, "child"),
                ("2. На какую таблицу", self.parent, self.parent_field, "parent"),
            )
        ):
            panel = ttk.Frame(selectors, padding=(0, 0, 12 if i == 0 else 0, 0))
            panel.grid(row=0, column=i, sticky="nsew")
            ttk.Label(panel, text=title).pack(anchor="w")
            box = ttk.Combobox(
                panel, textvariable=table_var, values=names, state="readonly"
            )
            box.pack(fill="x", pady=(4, 10))
            box.bind("<<ComboboxSelected>>", self.reset_fields)
            ttk.Label(panel, text="Поле для совпадения").pack(anchor="w")
            field = ttk.Combobox(
                panel, textvariable=field_var, state="readonly", width=30
            )
            field.pack(fill="x", pady=(4, 6))
            field.bind("<<ComboboxSelected>>", self.fields_changed)
            self.boxes[side] = field
        row = ttk.Frame(body)
        row.pack(fill="x", pady=8)
        ttk.Label(row, text="Сравнивать:").pack(side="left")
        ttk.Radiobutton(
            row, text="ID", variable=self.mode, value="id", command=self.refresh_preview
        ).pack(side="left", padx=8)
        ttk.Radiobutton(
            row,
            text="Название / ФИО",
            variable=self.mode,
            value="text",
            command=self.refresh_preview,
        ).pack(side="left")
        ttk.Label(body, text="ID будет записан в поле:").pack(anchor="w", pady=(4, 0))
        ttk.Label(body, textvariable=self.reference, style="Title.TLabel").pack(
            anchor="w"
        )
        self.summary_label = ttk.Label(body, textvariable=self.summary, wraplength=680)
        self.summary_label.pack(anchor="w", pady=(4, 8))
        self.details = tk.Text(body, height=6, wrap="word", state="disabled")
        self.details.pack(fill="both", expand=True)
        self.options = ttk.Frame(body)
        advanced = tk.BooleanVar(value=False)

        def toggle_options():
            if advanced.get():
                self.options.pack(fill="x", before=actions, pady=(4, 8))
                self.geometry("720x770")
            else:
                self.options.pack_forget()
                self.geometry("720x650")

        ttk.Checkbutton(
            body,
            text="Дополнительные параметры",
            variable=advanced,
            command=toggle_options,
        ).pack(anchor="w", pady=8)
        ttk.Label(
            self.options, text="Колонка для ссылки (создастся или заполнится)"
        ).pack(anchor="w")
        ttk.Entry(self.options, textvariable=self.reference).pack(fill="x", pady=4)
        ttk.Checkbutton(
            self.options,
            text="Игнорировать регистр и лишние пробелы в тексте",
            variable=self.normalize,
            command=self.refresh_preview,
        ).pack(anchor="w")
        ttk.Checkbutton(
            self.options,
            text="Разрешить изменение уже заполненных ID",
            variable=self.replace_existing,
            command=self.refresh_preview,
        ).pack(anchor="w")
        ttk.Checkbutton(
            body,
            text="Ненайденные и неоднозначные оставить без ссылки",
            variable=self.allow_missing,
            command=self.refresh_preview,
        ).pack(anchor="w", pady=(0, 6))
        actions = ttk.Frame(body)
        actions.pack(fill="x", pady=(4, 0))
        ttk.Button(actions, text="Отмена", command=self.destroy).pack(side="left")
        self.create_button = ttk.Button(
            actions, text="Создать связь", style="Accent.TButton", command=self.create
        )
        self.create_button.pack(side="right")
        self.reference.trace_add(
            "write",
            lambda *_: (
                self.refresh_preview() if hasattr(self, "child_choices") else None
            ),
        )
        self.reset_fields()

    def reset_fields(self, _=None):
        project = self.app.project
        if self.parent.get() == self.child.get():
            others = [n for n in project.model.table_names() if n != self.child.get()]
            if others:
                self.parent.set(
                    next(
                        (n for n in others if n == "users" or n.startswith("users_")),
                        others[0],
                    )
                )
        child, parent = project.table(self.child.get()), project.table(
            self.parent.get()
        )
        self.child_choices, self.parent_choices = field_choices(child), field_choices(
            parent
        )
        self.boxes["child"].configure(values=list(self.child_choices))
        self.boxes["parent"].configure(values=list(self.parent_choices))
        child_names = {c.name for c in child.columns}
        parent_pk = parent.primary_key.name if parent.primary_key else ""
        fio_aliases = {
            "client_name",
            "full_name",
            "fio",
            "фио",
            "фио_клиента",
            "customer_name",
            "покупатель",
        }
        child_fio = next(
            (
                label
                for label, fields in self.child_choices.items()
                if len(fields) == 1
                and any(
                    english_name(n) in {english_name(a) for a in fio_aliases}
                    for c in child.columns
                    if c.name == fields[0]
                    for n in (c.name, c.source_name)
                )
            ),
            None,
        )
        parent_fio = next(
            (label for label, fields in self.parent_choices.items() if len(fields) > 1),
            None,
        )
        if parent_fio is None:
            parent_fio = next(
                (
                    label
                    for label, fields in self.parent_choices.items()
                    if len(fields) == 1
                    and any(
                        english_name(n) in {english_name(a) for a in fio_aliases}
                        for c in parent.columns
                        if c.name == fields[0]
                        for n in (c.name, c.source_name)
                    )
                ),
                None,
            )
        if parent_pk in child_names:
            self.child_field.set(
                next(
                    label
                    for label, fields in self.child_choices.items()
                    if fields == (parent_pk,)
                )
            )
            self.parent_field.set(
                next(
                    label
                    for label, fields in self.parent_choices.items()
                    if fields == (parent_pk,)
                )
            )
        elif child_fio and parent_fio:
            self.child_field.set(child_fio)
            self.parent_field.set(parent_fio)
        else:
            first = next(
                (
                    label
                    for label, fields in self.child_choices.items()
                    if not any(
                        c.is_primary_key and c.name in fields for c in child.columns
                    )
                ),
                next(iter(self.child_choices), ""),
            )
            self.child_field.set(first)
            selected = self.child_choices.get(first)
            self.parent_field.set(
                next(
                    (
                        label
                        for label, fields in self.parent_choices.items()
                        if fields == selected
                    ),
                    next(iter(self.parent_choices), ""),
                )
            )
        # Если ID пока пусты, ФИО полезнее пустой колонки.
        selected = self.child_choices.get(self.child_field.get(), ())
        if (
            child_fio
            and parent_fio
            and selected
            and all(
                all(r.get(n) is None or r.get(n) == "" for n in selected)
                for r in child.rows
            )
        ):
            self.child_field.set(child_fio)
            self.parent_field.set(parent_fio)
        self.fields_changed()

    def fields_changed(self, _=None):
        parent = self.app.project.table(self.parent.get())
        child = self.app.project.table(self.child.get())
        refs = self.parent_choices.get(self.parent_field.get(), ())
        self.mode.set(
            "id" if refs == tuple(c.name for c in parent.primary_keys) else "text"
        )
        name = singular_name(parent.name)[:45] + "_id"
        pk = parent.primary_key.name if parent.primary_key else name
        if pk.endswith("_id") and not pk.startswith("__"):
            name = pk
        if name in {c.name for c in child.primary_keys}:
            name = singular_name(parent.name)[:40] + "_ref_id"
        self.reference.set(name)
        self.refresh_preview()

    def arguments(self):
        cols = self.child_choices.get(self.child_field.get(), ())
        refs = self.parent_choices.get(self.parent_field.get(), ())
        return dict(
            child_name=self.child.get(),
            columns=cols,
            parent_name=self.parent.get(),
            match_columns=refs,
            reference_column=self.reference.get(),
            mode=self.mode.get(),
            combine=self.mode.get() == "text" and (len(cols) > 1 or len(refs) > 1),
            normalize=self.normalize.get(),
            replace_existing=self.replace_existing.get(),
        )

    def refresh_preview(self):
        if not hasattr(self, "child_choices"):
            return
        try:
            report = self.app.project.preview_link(**self.arguments())
            unresolved = report["missing"] + report["ambiguous"]
            self.summary.set(
                f"{self.child.get()}.{self.reference.get()} → {self.parent.get()}\nНайдено: {report['matched']}; сохранено готовых ID: {report['kept']}; пустых: {report['empty']}; без совпадения: {unresolved}; конфликтов ID: {report['conflicts']}."
            )
            args = self.arguments()
            child = self.app.project.table(args["child_name"])
            lines = []
            for row, result in list(zip(child.rows, report["values"]))[:5]:
                original = " ".join(str(row.get(c) or "") for c in args["columns"])
                lines.append(
                    f"{original or '(пусто)'}  →  {self.reference.get()} = {result if result is not None else 'NULL'}"
                )
            lines.extend(report["issues"][:5])
            if not lines:
                lines = ["В таблице пока нет строк."]
            if unresolved and self.allow_missing.get():
                lines = [
                    "Ненайденные ссылки станут NULL. Такие заказы не будут привязаны к покупателю.",
                    *lines,
                ]
            allowed = not report["conflicts"] and (
                not unresolved or self.allow_missing.get()
            )
            self.create_button.configure(state="normal" if allowed else "disabled")
        except Exception as error:
            self.summary.set(str(error))
            lines = [
                "Выберите две таблицы и подходящие поля. Для ФИО выберите готовый вариант из списка."
            ]
            self.create_button.configure(state="disabled")
        self.details.configure(state="normal")
        self.details.delete("1.0", "end")
        self.details.insert("end", "\n".join(lines))
        self.details.configure(state="disabled")

    def create(self):
        ok, report = self.app.apply(
            self.app.project.connect_tables,
            **self.arguments(),
            allow_missing=self.allow_missing.get(),
            chosen=self.child.get(),
        )
        if ok:
            self.app.status.set(
                f"Связь создана: {self.child.get()}.{self.reference.get()} → {self.parent.get()}. Найдено {report['matched']}, сохранено {report['kept']} готовых ID."
            )
            self.destroy()
