from clang.cindex import TypeKind

class PointerOf:
    @property
    def kind(self):
        return TypeKind.POINTER

    def get_canonical(self):
        return PointerOf(self._type.get_canonical())

    def is_const_qualified(self):
        return False

    def is_volatile_qualified(self):
        return False

    def is_restrict_qualified(self):
        return False

    def get_pointee(self):
        return self._type

    def __init__(self, typ):
        self._type = typ

__all__ = ['PointerOf']

