"""Minimal Vec3 / Mat4 matching the parts of pyglet.math that Skypiercer uses.

Column-vector convention: (A @ B) applies B first, exactly like pyglet.
"""
import math as _m


class Vec3:
    __slots__ = ("x", "y", "z")

    def __init__(self, x=0.0, y=0.0, z=0.0):
        self.x, self.y, self.z = float(x), float(y), float(z)

    def __iter__(self):
        return iter((self.x, self.y, self.z))


def _identity():
    return ((1.0, 0.0, 0.0, 0.0), (0.0, 1.0, 0.0, 0.0), (0.0, 0.0, 1.0, 0.0), (0.0, 0.0, 0.0, 1.0))


class Mat4:
    __slots__ = ("m", "_aff")

    def __init__(self, m=None):
        self.m = m if m is not None else _identity()
        self._aff = None

    @classmethod
    def from_translation(cls, v):
        x, y, z = tuple(v)
        return cls(((1.0, 0.0, 0.0, x), (0.0, 1.0, 0.0, y), (0.0, 0.0, 1.0, z), (0.0, 0.0, 0.0, 1.0)))

    @classmethod
    def from_scale(cls, v):
        x, y, z = tuple(v)
        return cls(((x, 0.0, 0.0, 0.0), (0.0, y, 0.0, 0.0), (0.0, 0.0, z, 0.0), (0.0, 0.0, 0.0, 1.0)))

    @classmethod
    def from_rotation(cls, angle, vector):
        """Counter-clockwise rotation (radians) about an axis (Rodrigues)."""
        x, y, z = tuple(vector)
        n = _m.sqrt(x * x + y * y + z * z) or 1.0
        x, y, z = x / n, y / n, z / n
        c, s = _m.cos(angle), _m.sin(angle)
        t = 1.0 - c
        return cls((
            (t * x * x + c, t * x * y - s * z, t * x * z + s * y, 0.0),
            (t * x * y + s * z, t * y * y + c, t * y * z - s * x, 0.0),
            (t * x * z - s * y, t * y * z + s * x, t * z * z + c, 0.0),
            (0.0, 0.0, 0.0, 1.0),
        ))

    def __matmul__(self, other):
        a, b = self.m, other.m
        return Mat4(tuple(
            tuple(sum(a[i][k] * b[k][j] for k in range(4)) for j in range(4))
            for i in range(4)
        ))

    def affine2d(self):
        """(a, b, c, d, tx, ty) so that x' = a*x + c*y + tx and y' = b*x + d*y + ty."""
        if self._aff is None:
            m = self.m
            self._aff = (m[0][0], m[1][0], m[0][1], m[1][1], m[0][3], m[1][3])
        return self._aff
