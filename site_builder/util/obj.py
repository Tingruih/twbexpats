"""Attribute-access dict used as the data carrier for Jinja templates."""


class Obj(dict):
    """Simple attribute-access dict used by Jinja templates."""

    def __getattr__(self, key):
        return self.get(key)

    def __setattr__(self, key, value):
        self[key] = value
