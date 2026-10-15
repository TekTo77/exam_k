from pathlib import Path
from PIL import Image, ImageOps
from design import IMAGE_FIT

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
