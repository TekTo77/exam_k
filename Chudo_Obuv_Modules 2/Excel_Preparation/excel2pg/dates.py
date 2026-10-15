from datetime import date, datetime

def as_date(value):
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        text = str(value).strip()
        return datetime.fromisoformat(text.replace("Z", "+00:00")).date()
    except (ValueError, TypeError) as error:
        from config import DATE_INPUT_FORMATS

        for fmt in DATE_INPUT_FORMATS:
            try:
                return datetime.strptime(str(value).strip(), fmt).date()
            except ValueError:
                pass
        raise ValueError(
            f"Не удалось прочитать дату {value!r}. Используйте ГГГГ-ММ-ДД или настройте DATE_INPUT_FORMATS."
        ) from error
