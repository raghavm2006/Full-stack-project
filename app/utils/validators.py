"""Small, reusable input-validation helpers (rule #10)."""


class ValidationError(Exception):
    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


def parse_pagination(args, default_per_page=20, max_per_page=100):
    """Reads/validates ?page= and ?per_page= from a Flask request.args."""
    try:
        page = int(args.get("page", 1))
        per_page = int(args.get("per_page", default_per_page))
    except (TypeError, ValueError):
        raise ValidationError("page and per_page must be integers")

    if page < 1:
        raise ValidationError("page must be >= 1")
    if per_page < 1 or per_page > max_per_page:
        raise ValidationError(f"per_page must be between 1 and {max_per_page}")

    return page, per_page


def parse_bool_param(args, name):
    """Returns True/False/None for an optional ?<name>=true|false query param."""
    raw = args.get(name)
    if raw is None:
        return None
    if raw.lower() in ("true", "1", "yes"):
        return True
    if raw.lower() in ("false", "0", "no"):
        return False
    raise ValidationError(f"{name} must be a boolean (true/false)")
