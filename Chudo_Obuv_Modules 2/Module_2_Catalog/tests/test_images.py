import tempfile
import unittest
import unicodedata
from pathlib import Path
from unittest.mock import patch

from PIL import Image, UnidentifiedImageError
from interface.pictures import resolve_image, read_thumbnail, ImageStore


class ImagesTests(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.folder = Path(self.temporary.name)

    def test_regular_formats_preserve_aspect_ratio(self):
        for extension in ("png", "jpg", "webp", "gif", "bmp", "tiff"):
            with self.subTest(extension=extension):
                path = self.folder / f"фото товара.{extension}"
                Image.new("RGB", (400, 200), "green").save(path)
                self.assertEqual(read_thumbnail(path, (100, 100)).size, (100, 50))
                self.assertEqual(resolve_image(self.folder, path.name), path)

    def test_orientation_from_camera(self):
        path = self.folder / "portrait.jpg"
        exif = Image.Exif()
        exif[274] = 6
        Image.new("RGB", (120, 60)).save(path, exif=exif)
        self.assertEqual(read_thumbnail(path, (120, 120)).size, (60, 120))

    def test_cover_crops_to_panel_without_stretching(self):
        path = self.folder / "wide.png"
        Image.new("RGB", (400, 100), "red").save(path)
        self.assertEqual(read_thumbnail(path, (80, 80), "cover").size, (80, 80))
        self.assertEqual(read_thumbnail(path, (80, 80), "contain").size, (80, 20))
        with self.assertRaises(ValueError):
            ImageStore(None, self.folder, fit="stretch")

    def test_unicode_case_and_windows_paths(self):
        path = self.folder / "Фото café.PNG"
        Image.new("RGB", (10, 10)).save(path)
        value = unicodedata.normalize("NFD", "фото café.png")
        self.assertEqual(resolve_image(self.folder, value), path)
        self.assertEqual(
            resolve_image(self.folder, "C:\\old\\Images\\Фото café.PNG"), path
        )
        self.assertEqual(resolve_image(self.folder, "Images/Фото café.PNG"), path)

    def test_nested_paths_and_ambiguous_names(self):
        for directory in ("one", "two"):
            (self.folder / directory).mkdir()
            Image.new("RGB", (10, 10)).save(self.folder / directory / "model.png")
        self.assertEqual(
            resolve_image(self.folder, "one/model.png"), self.folder / "one/model.png"
        )
        self.assertIsNone(resolve_image(self.folder, "model.png"))
        self.assertIsNone(resolve_image(self.folder, "../model.png"))
        self.assertIsNone(resolve_image(self.folder, "https://example.com/model.png"))

    def test_missing_and_corrupt_images_have_status(self):
        store = ImageStore(None, self.folder)
        self.assertEqual(store.photo(None), (None, "Фото не указано"))
        self.assertEqual(store.photo("missing.png"), (None, "Файл фото не найден"))
        (self.folder / "broken.png").write_bytes(b"broken")
        self.assertEqual(store.photo("broken.png"), (None, "Не удалось открыть фото"))

    def test_cache_refreshes_after_file_change_and_is_bounded(self):
        path = self.folder / "model.png"
        Image.new("RGB", (100, 100)).save(path)
        store = ImageStore(None, self.folder, capacity=1)
        with patch(
            "interface.pictures.ImageTk.PhotoImage", side_effect=lambda *a, **kw: object()
        ):
            first, _ = store.photo(path.name)
            self.assertIs(store.photo(path.name)[0], first)
            Image.new("RGB", (300, 100), "blue").save(path)
            self.assertIsNot(store.photo(path.name)[0], first)
            store.photo(path.name, (50, 50))
            self.assertEqual(len(store.cache), 1)


if __name__ == "__main__":
    unittest.main()
