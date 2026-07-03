"""Baseball-style numeric formatting shared by stat modules."""


def fmt_avg(value):
    """Format a float as a baseball average string with no leading zero.

    Examples:
        0.333  -> ".333"
        1.000  -> "1.000"
        None   -> None
    """
    if value is None:
        return None
    s = f"{value:.3f}"
    return s[1:] if s.startswith("0.") else s
