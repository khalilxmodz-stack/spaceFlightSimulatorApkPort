import json
from math import cos, pi, sin, sqrt
from typing import Tuple, TypedDict

import pyglet

constants = json.load(open("constants.json"))
G = constants["G"]


# ==========================================
# STATIC FUNCTIONS
# ==========================================
def create_gradient_ring(
    x: float,
    y: float,
    inner_radius: float,
    outer_radius: float,
    inner_color: tuple[int, int, int, int],
    outer_color: tuple[int, int, int, int],
    batch: pyglet.graphics.Batch,
    segments=256,
):
    """
    Creates a gradient ring (donut shape) used for atmospheric visual effects.
    This approximates a smooth circle using a series of connected triangle strips.
    A higher 'segments' argument will increase rendering fidelity at the cost of performance.
    """
    vertices = []
    colors = []

    for i in range(segments + 1):
        angle = 2 * pi * i / segments
        c = cos(angle)
        s = sin(angle)

        # Inner vertex
        vertices.extend((x + inner_radius * c, y + inner_radius * s))
        colors.extend(inner_color)

        # Outer vertex
        vertices.extend((x + outer_radius * c, y + outer_radius * s))
        colors.extend(outer_color)

    count = len(vertices) // 2
    program = pyglet.shapes.get_default_shader()

    return program.vertex_list(
        count,
        pyglet.gl.GL_TRIANGLE_STRIP,
        batch=batch,
        position=("f", vertices),
        colors=("Bn", colors),
    )


# ==========================================
# ATMOSPHERE CLASS
# ==========================================
class AtmosphereData(TypedDict):
    number_of_layers: int
    colours: Tuple[Tuple[int, int, int, int], ...]
    outer_radius: float


class Atmosphere:
    """
    Constructs volumetric visual layers surrounding planetary objects.
    Each layer renders sequentially outward using dynamic color palettes to create depth.
    """

    def __init__(
        self,
        x: float,
        y: float,
        number_of_layers: int,
        colours: Tuple[Tuple[int, int, int, int], ...],
        inner_radius: float,
        outer_radius: float,
        batch: pyglet.graphics.Batch,
    ):
        self.batch = batch
        self.layers = []
        for i in range(number_of_layers):
            layer = create_gradient_ring(
                x=x,
                y=y,
                inner_radius=inner_radius
                + (outer_radius - inner_radius) * i / number_of_layers,
                outer_radius=inner_radius
                + (outer_radius - inner_radius) * (i + 1) / number_of_layers,
                inner_color=colours[i],
                outer_color=colours[i + 1],
                batch=self.batch,
            )
            self.layers.append(layer)

    def draw(self):
        self.batch.draw()


# ==========================================
# BODY (CELESTIAL OBJECT) CLASS
# ==========================================
class Body(pyglet.shapes.Circle):
    """
    Subclasses the Pyglet Circle class to represent celestial bodies like Earth or the Moon.
    This structure encapsulates positional state alongside physical metrics like mass and
    radius to enable accurate orbital integrations. Modify 'mass' and 'radius' variables in
    Game.py or constants.json to change gameplay physics dynamically.
    """

    def __init__(
        self,
        x: float,
        y: float,
        radius: float,
        color: tuple[int, int, int, int],
        mass: float,
        name: str,
        atmosphere: None | AtmosphereData = None,
        body_to_orbit: "None | Body" = None,
        orbit_radius: None | float = None,
    ):
        super().__init__(
            x, y, radius, color=color, segments=256, batch=pyglet.graphics.Batch()
        )

        self.angle = 0.0  # Initial angle for orbital rotation, if applicable

        assert (
            self.batch is not None
        ), "Batch must be initialised in the parent Circle class"

        self._mass = mass
        self._name = name
        self._atmosphere_data: AtmosphereData = (
            atmosphere
            if atmosphere
            else {
                "number_of_layers": 2,
                "colours": ((159, 215, 249, 255), (13, 139, 217, 255), (0, 0, 0, 255)),
                "outer_radius": radius + 100000.0,
            }
        )
        self._atmosphere = (
            Atmosphere(x, y, inner_radius=radius, batch=self.batch, **atmosphere)
            if atmosphere
            else None
        )
        self._body_to_orbit = None
        self._orbit_radius = None
        self._angular_velocity = 0.0
        self._orbit_path = None

        self.physics_x = self.x
        self.physics_y = self.y

        if body_to_orbit and orbit_radius:
            self._body_to_orbit = body_to_orbit
            self._orbit_radius = orbit_radius
            self._angular_velocity = sqrt(
                G * self._body_to_orbit.mass / self._orbit_radius**3
            )
            self._orbit_path = pyglet.shapes.Arc(
                self._body_to_orbit.x,
                self._body_to_orbit.y,
                self._orbit_radius,
                color=(255, 255, 255, 100),
                batch=self.batch,
                segments=256,
                thickness=50000,
            )

    @property
    def mass(self):
        return self._mass

    @property
    def centre(self):
        return (self.x, self.y)

    @property
    def has_atmosphere(self):
        return self._atmosphere is not None

    @has_atmosphere.setter
    def has_atmosphere(self, val: bool):
        if val and not self._atmosphere:
            assert self.batch is not None
            self._atmosphere = Atmosphere(
                self.x,
                self.y,
                inner_radius=self.radius,
                batch=self.batch,
                **self._atmosphere_data
            )
        elif not val and self._atmosphere:
            for layer in self._atmosphere.layers:
                layer.delete()
            self._atmosphere = None

    @property
    def atmosphere_thickness(self) -> float:
        return self._atmosphere_data["outer_radius"] - self.radius

    @atmosphere_thickness.setter
    def atmosphere_thickness(self, new_thickness: float):
        self._atmosphere_data["outer_radius"] = self.radius + new_thickness
        if self._atmosphere:
            assert self.batch is not None
            for layer in self._atmosphere.layers:
                layer.delete()
            self._atmosphere = Atmosphere(
                self.x,
                self.y,
                inner_radius=self.radius,
                batch=self.batch,
                **self._atmosphere_data
            )

    @property
    def orbit_path(self):
        return self._orbit_path

    @property
    def soi_radius(self):
        if self._body_to_orbit:
            return self._orbit_radius * (self.mass / self._body_to_orbit.mass) ** (
                2 / 5
            )
        return None

    @property
    def orbit_radius(self):
        return self._orbit_radius

    @property
    def is_orbiting(self):
        return self._body_to_orbit is not None

    @property
    def parent_body(self):
        return self._body_to_orbit

    # self.radius is already provide by parent Circle class

    @property
    def angular_velocity(self):
        return self._angular_velocity

    def __str__(self):
        return self._name

    def draw(self):
        assert self.batch is not None
        self.batch.draw()

    def shift(self, dx: float, dy: float):
        # Allow the native Pyglet properties to shift the circle coordinates directly
        self.x += dx
        self.y += dy

        if self._atmosphere:
            for layer in self._atmosphere.layers:
                # Batch shift X (even indices) and Y (odd indices) simultaneously
                positions = layer.position
                layer.position = [
                    pos + (dx if i % 2 == 0 else dy) for i, pos in enumerate(positions)
                ]

        # The orbit path should always remain centered on the parent body,
        # rather than moving blindly with the moon's local displacement.
        if self._orbit_path:
            if self._body_to_orbit:
                self._orbit_path.x = self._body_to_orbit.x
                self._orbit_path.y = self._body_to_orbit.y
            else:
                # Fallback if there is no linked orbit body
                self._orbit_path.x += dx
                self._orbit_path.y += dy
