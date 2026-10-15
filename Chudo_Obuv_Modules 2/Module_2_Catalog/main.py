"""Чудо Обувь: запуск приложения."""
from interface.application import Application


def main():
    try:
        app = Application()
    except Exception as error:
        print(f"Не удалось запустить приложение: {error}")
        return 1
    app.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
