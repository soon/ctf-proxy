class Ref:
    """Deferred id placeholder: filled in when its row is bulk-inserted."""

    __slots__ = ("value", "resolved")

    def __init__(self):
        self.value = None
        self.resolved = False
