"""Фото из папки по имени файла из БД."""

from collections import OrderedDict
from pathlib import Path
import unicodedata

from PIL import Image, ImageOps, ImageTk, UnidentifiedImageError
from design import IMAGE_CACHE_SIZE, IMAGE_FIT, PLACEHOLDER_PATH


def _normalized(value):
    return unicodedata.normalize("NFC", value).casefold()


def resolve_image(folder: Path, value) -> Path | None:
    """Ищем фото в папке. Совпадение должно быть однозначным."""
    if value is None or not str(value).strip() or not folder.is_dir():
        return None
    text = str(value).strip().replace("\\", "/")
    if "://" in text:
        return None
    root = folder.resolve()
    relative = Path(text)
    if ".." in relative.parts:
        return None
    candidate = (root / relative).resolve()
    if candidate.is_relative_to(root) and candidate.is_file():
        return candidate
    # Сначала ищем точный путь, затем одно совпадение по имени.
    try:
        files = [
            p
            for p in root.rglob("*")
            if p.is_file() and p.resolve().is_relative_to(root)
        ]
    except OSError:
        return None
    exact = [
        p
        for p in files
        if _normalized(p.relative_to(root).as_posix()) == _normalized(text)
    ]
    if len(exact) == 1:
        return exact[0]
    matches = [p for p in files if _normalized(p.name) == _normalized(relative.name)]
    return matches[0] if len(matches) == 1 else None


def read_thumbnail(path: Path, size, fit="contain"):
    """Уменьшаем фото с учётом поворота камеры."""
    with Image.open(path) as source:
        image = ImageOps.exif_transpose(source).convert("RGBA")
        if fit == "cover":
            return ImageOps.fit(image, size, method=Image.Resampling.LANCZOS)
        if fit != "contain":
            raise ValueError('IMAGE_FIT должен быть "contain" или "cover".')
        image.thumbnail(size, Image.Resampling.LANCZOS)
        return image.copy()


class ImageStore:
    def __init__(self, master, folder: Path, capacity=IMAGE_CACHE_SIZE, fit=IMAGE_FIT):
        if fit not in {"contain", "cover"}:
            raise ValueError('IMAGE_FIT должен быть "contain" или "cover".')
        self.master = master
        self.folder = Path(folder)
        self.capacity = capacity
        self.fit = fit
        self.cache = OrderedDict()

    def photo(self, filename, size=(270, 170)):
        try:
            path = resolve_image(self.folder, filename)
            if path is None:
                return None, (
                    "Фото не указано" if not filename else "Файл фото не найден"
                )
            stat = path.stat()
            key = (str(path), stat.st_mtime_ns, stat.st_size, size, self.fit)
            if key in self.cache:
                self.cache.move_to_end(key)
                return self.cache[key], ""
            image = ImageTk.PhotoImage(
                read_thumbnail(path, size, self.fit), master=self.master
            )
            self.cache[key] = image
            while len(self.cache) > self.capacity:
                self.cache.popitem(last=False)
            return image, ""
        except (
            OSError,
            ValueError,
            UnidentifiedImageError,
            Image.DecompressionBombError,
        ):
            return None, "Не удалось открыть фото"


def image_panel(parent, store, filename, size, background):
    import tkinter as tk
    from config import COLORS
    from interface.formatting import font

    frame = tk.Frame(parent, width=size[0], height=size[1], bg=background)
    frame.pack_propagate(False)
    image, status = store.photo(filename, size)
    if image is None and PLACEHOLDER_PATH is not None:
        try:
            image = ImageTk.PhotoImage(read_thumbnail(Path(PLACEHOLDER_PATH), size), master=parent)
            status = ""
        except (OSError, ValueError, tk.TclError, Image.DecompressionBombError):
            pass
    label = tk.Label(
        frame,
        image=image,
        text=status,
        bg=background,
        fg=COLORS["muted"],
        font=font(),
        wraplength=size[0] - 20,
    )
    label.image = image  # Сохраняем ссылку, чтобы фото не исчезло.
    label.pack(expand=True)
    return frame
