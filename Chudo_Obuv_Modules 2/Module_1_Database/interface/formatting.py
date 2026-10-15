from design import FONT_FAMILY, FONT_SIZES

def font(role="body", bold=False):
    value = (FONT_FAMILY, FONT_SIZES[role])
    return value + ("bold",) if bold else value
