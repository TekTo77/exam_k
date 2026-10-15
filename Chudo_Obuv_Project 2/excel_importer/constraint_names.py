def _constraint_name(table, fk):
    import hashlib

    name = f"fk_{table.name}_{'_'.join(fk.columns)}"
    # PostgreSQL ограничивает имена 63 байтами, а не 63 символами.
    if len(name.encode()) > 63:
        prefix = name.encode()[:45].decode("utf-8", errors="ignore")
        name = prefix + "_" + hashlib.sha256(name.encode()).hexdigest()[:12]
    return name
