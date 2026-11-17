import json
import random
import sys
from math import atan2, degrees, pi, sqrt, sin, cos, exp

import pyglet
from pyglet.math import Mat4, Vec3

from dataclasses import dataclass
from typing import Callable, Any

from Body import Body
from Rocket import Rocket, PhysicsState

# ==========================================
# SIMULATION CONSTANTS & CONFIGURATION
# ==========================================
# Load physical constants from an external JSON document.
# This separates logic from data, allowing non-programmers to easily tweak simulation values
constants = json.load(open("constants.json", encoding="utf-8"))
EARTH_MASS = constants[
    "earth_mass"
]  # Adjust this value in constants.json to change Earth's gravitational pull
EARTH_RADIUS = constants[
    "earth_radius"
]  # Modifying this radius will alter surface collision boundaries
KARMAN_LINE = constants[
    "karman_line"
]  # Boundary representing the edge of space, measured in metres
MOON_MASS = constants[
    "moon_mass"
]  # Adjust this value to alter the Moon's gravitational strength
MOON_RADIUS = constants[
    "moon_radius"
]  # Modifying this will alter lunar collision boundaries
EARTH_MOON_DISTANCE = constants[
    "earth_moon_distance"
]  # Average distance between Earth and Moon, measured in metres
FLOATING_ORIGIN_THRESHOLD = 1e6  # Distance from center at which coordinate system shifts to maintain float precision


# ==========================================
# WINDOW INITIALIZATION & GRAPHICS SETUP
# ==========================================
class Modal:
    def __init__(self, title, content_text, width=600, height=300, buttons=None):
        self._width = width
        self._height = height
        self.buttons = buttons if buttons else []
        self.batch = pyglet.graphics.Batch()

        # Semi-transparent overlay
        self.overlay = pyglet.shapes.Rectangle(
            x=0,
            y=0,
            width=window.width,
            height=window.height,
            color=(0, 0, 0, 180),
            batch=self.batch,
        )

        # Modal Background
        self.bg = pyglet.shapes.Rectangle(
            x=window.width // 2 - width // 2,
            y=window.height // 2 - height // 2,
            width=width,
            height=height,
            color=(40, 40, 40, 255),
            batch=self.batch,
        )

        # Title
        self.title_label = pyglet.text.Label(
            title,
            font_name="a Astro Space",
            font_size=24,
            x=window.width // 2,
            y=window.height // 2 + height // 2 - 40,
            anchor_x="center",
            anchor_y="center",
            color=(255, 165, 0, 255),
            batch=self.batch,
        )

        # Content
        self.content_text = pyglet.text.Label(
            content_text,
            font_name="a Astro Space",
            font_size=16,
            x=window.width // 2,
            y=window.height // 2,
            anchor_x="center",
            anchor_y="center",
            multiline=True,
            width=width - 80,
            batch=self.batch,
        )

        self._visible = False
        self.resize(window.width, window.height)

    @property
    def visible(self):
        return self._visible

    @visible.setter
    def visible(self, value):
        self._visible = value

    def resize(self, w, h):
        self.overlay.width = w
        self.overlay.height = h

        self.bg.x = w // 2 - self._width // 2
        self.bg.y = h // 2 - self._height // 2

        self.title_label.x = w // 2
        self.title_label.y = h // 2 + self._height // 2 - 40

        self.content_text.x = w // 2
        self.content_text.y = h // 2 - 20

        if self.buttons:
            btn_w = self.buttons[0].width
            btn_h = self.buttons[0].height
            gap = 20
            total_w = len(self.buttons) * btn_w + (len(self.buttons) - 1) * gap
            start_x = w // 2 - total_w // 2

            for i, btn in enumerate(self.buttons):
                btn.x = start_x + i * (btn_w + gap)
                btn.y = h // 2 - self._height // 2 + 20
                btn.text.x = btn.x + btn_w // 2
                btn.text.y = btn.y + btn_h // 2

    def draw(self):
        if self._visible:
            # We don't want the modal to be affected by the camera
            old_view = window.view
            window.view = Mat4()
            self.batch.draw()
            for btn in self.buttons:
                btn.draw()
            window.view = old_view


# Initialise the graphics window.
# Alter the 'width' and 'height' integer parameters here to adjust the application's default testing resolution.
window = pyglet.window.Window(
    width=1024,
    height=768,
    caption="Skypiercer",
)

# Set the OpenGL clear colour (the backdrop) to deep space black.
# Modifying the first three RGB floats (0.0 to 1.0) will alter the base background colour of the simulation.
pyglet.gl.glClearColor(0, 0, 0, 1)

# Load a custom TrueType font for the heads-up display (HUD). Ensure the asset exists at this directory path.
pyglet.font.add_file("assets/astrospace.ttf")

PAUSE_LOCATION = window.height - 100
ACHIEVEMENT_LOCATION = window.height - 150
WARN_LOCATION = window.height - 200

WARN_COLOUR = (255, 165, 0, 255)
ERROR_COLOUR = (255, 0, 0, 255)
ACHIEVEMENT_COLOUR = (0, 255, 255, 255)
SUCCESS_COLOUR = (0, 255, 0, 255)
INFO_COLOUR = (255, 255, 0, 255)

# Game progression state
game_state = "MENU"  # "MENU" or "PLAYING"
tutorial: bool | None = (
    None  # None = ask modal, True = show tutorial, False = skip tutorial
)


# ==========================================
# MAIN MENU COMPONENTS
# ==========================================
class Star:
    def __init__(self, width, height):
        self.x = random.randint(0, width)
        self.y = random.randint(0, height)
        self.speed = random.uniform(0.5, 2.0)
        self.size = random.uniform(1.0, 3.0)
        self.shape = pyglet.shapes.Circle(
            self.x, self.y, self.size, color=(255, 255, 255)
        )

    def update(self, dt, width):
        self.x -= self.speed * 60 * dt
        if self.x < 0:
            self.x = width
            self.y = random.randint(
                0, int(self.shape.y) * 2 if self.shape.y > 0 else 600
            )
        self.shape.x = self.x


class Button(pyglet.shapes.Rectangle):
    def __init__(self, x, y, width, height, text):
        super().__init__(x, y, width, height, color=(50, 50, 200))
        self.text = pyglet.text.Label(
            text,
            font_name="a Astro Space",
            font_size=height // 2,
            x=x + width // 2,
            y=y + height // 2,
            anchor_x="center",
            anchor_y="center",
            color=(255, 255, 255),
        )

    def draw(self):
        super().draw()
        self.text.draw()


class Menu:
    def __init__(self):
        cx = window.width // 2
        cy = window.height // 2

        self.stars = [Star(window.width, window.height) for _ in range(100)]
        self.buttons = [
            Button(cx - 100, cy, 200, 50, "Play"),
            Button(cx - 100, cy - 100, 200, 50, "Exit"),
        ]

        self.title = pyglet.text.Label(
            "Skypiercer",
            font_name="a Astro Space",
            font_size=50,
            x=cx,
            y=cy + 200,
            anchor_x="center",
            anchor_y="center",
            color=(255, 255, 255),
        )

    def update(self, dt):
        for star in self.stars:
            star.update(dt, window.width)

    def draw(self):
        for star in self.stars:
            star.shape.draw()
        for button in self.buttons:
            button.draw()
        self.title.draw()

    def resize(self, width, height):
        cx = width // 2
        cy = height // 2
        self.title.x = cx
        self.title.y = cy + 200


main_menu = Menu()


@dataclass
class CheatParam:
    name: str
    getter: Callable[[], str]
    setter: Callable[[Any], None]
    validator: Callable[[Any], bool]
    ptype: str


class CheatMenu:
    def __init__(self, window):
        self.visible = False
        self.selected_param = 0
        self.input_text = ""
        self.error_text = ""

        self.tabs = ["Rocket", "Bodies"]
        self.current_tab = 0

        self.params = {
            "Rocket": [
                CheatParam(
                    "Fuel (kg)",
                    lambda: f"{rocket.fuel:.2f}",
                    lambda v: setattr(rocket, "_fuel", float(v)),
                    lambda v: float(v) >= 0,
                    "float",
                ),
                CheatParam(
                    "Dry Mass (kg)",
                    lambda: f"{rocket._dry_mass:.2f}",
                    lambda v: setattr(rocket, "_dry_mass", float(v)),
                    lambda v: float(v) > 0,
                    "float",
                ),
                CheatParam(
                    "Thrust (N)",
                    lambda: f"{rocket._engine_thrust:.2f}",
                    lambda v: setattr(rocket, "_engine_thrust", float(v)),
                    lambda v: float(v) >= 0,
                    "float",
                ),
                CheatParam(
                    "Drag Coeff",
                    lambda: f"{rocket._drag_coefficient:.2f}",
                    lambda v: setattr(rocket, "_drag_coefficient", float(v)),
                    lambda v: float(v) >= 0,
                    "float",
                ),
                CheatParam(
                    "Cross-Sect Area (m^2)",
                    lambda: f"{rocket._cross_sectional_area:.2f}",
                    lambda v: setattr(rocket, "_cross_sectional_area", float(v)),
                    lambda v: float(v) > 0,
                    "float",
                ),
                CheatParam(
                    "Temperature (K)",
                    lambda: f"{rocket.temperature:.2f}",
                    lambda v: setattr(rocket, "temperature", float(v)),
                    lambda v: float(v) >= 0,
                    "float",
                ),
                CheatParam(
                    "Inf Fuel",
                    lambda: (
                        "Yes" if getattr(rocket, "cheat_infinite_fuel", False) else "No"
                    ),
                    lambda v: setattr(rocket, "cheat_infinite_fuel", v),
                    lambda v: isinstance(v, bool),
                    "bool",
                ),
                CheatParam(
                    "No Drag",
                    lambda: "Yes" if getattr(rocket, "cheat_no_drag", False) else "No",
                    lambda v: setattr(rocket, "cheat_no_drag", v),
                    lambda v: isinstance(v, bool),
                    "bool",
                ),
                CheatParam(
                    "No Collisions",
                    lambda: (
                        "Yes" if getattr(rocket, "cheat_no_collisions", False) else "No"
                    ),
                    lambda v: setattr(rocket, "cheat_no_collisions", v),
                    lambda v: isinstance(v, bool),
                    "bool",
                ),
                CheatParam(
                    "No Heat Damage",
                    lambda: "Yes" if getattr(rocket, "cheat_no_heat", False) else "No",
                    lambda v: setattr(rocket, "cheat_no_heat", v),
                    lambda v: isinstance(v, bool),
                    "bool",
                ),
            ],
            "Bodies": [
                CheatParam(
                    "Earth Mass (kg)",
                    lambda: f"{earth.mass:.4e}",
                    lambda v: setattr(earth, "_mass", float(v)),
                    lambda v: float(v) > 0,
                    "float",
                ),
                CheatParam(
                    "Earth Radius (m)",
                    lambda: f"{earth.radius:.2f}",
                    lambda v: setattr(earth, "radius", float(v)),
                    lambda v: float(v) > 0,
                    "float",
                ),
                CheatParam(
                    "Moon Mass (kg)",
                    lambda: f"{moon.mass:.4e}",
                    lambda v: setattr(moon, "_mass", float(v)),
                    lambda v: float(v) > 0,
                    "float",
                ),
                CheatParam(
                    "Moon Radius (m)",
                    lambda: f"{moon.radius:.2f}",
                    lambda v: setattr(moon, "radius", float(v)),
                    lambda v: float(v) > 0,
                    "float",
                ),
                CheatParam(
                    "Earth Atm",
                    lambda: "Yes" if earth.has_atmosphere else "No",
                    lambda v: setattr(earth, "has_atmosphere", v),
                    lambda v: isinstance(v, bool),
                    "bool",
                ),
                CheatParam(
                    "Earth Atm Thick (m)",
                    lambda: f"{earth.atmosphere_thickness:.2f}",
                    lambda v: setattr(earth, "atmosphere_thickness", float(v)),
                    lambda v: float(v) > 0,
                    "float",
                ),
                CheatParam(
                    "Moon Atm",
                    lambda: "Yes" if moon.has_atmosphere else "No",
                    lambda v: setattr(moon, "has_atmosphere", v),
                    lambda v: isinstance(v, bool),
                    "bool",
                ),
                CheatParam(
                    "Moon Atm Thick (m)",
                    lambda: f"{moon.atmosphere_thickness:.2f}",
                    lambda v: setattr(moon, "atmosphere_thickness", float(v)),
                    lambda v: float(v) > 0,
                    "float",
                ),
            ],
        }

        self.batch = pyglet.graphics.Batch()
        self.bg = pyglet.shapes.Rectangle(
            x=window.width // 2 - 400,
            y=window.height // 2 - 280,
            width=800,
            height=560,
            color=(30, 30, 30, 240),
            batch=self.batch,
        )
        self.title_label = pyglet.text.Label(
            "CHEAT MODE",
            font_name="a Astro Space",
            font_size=24,
            x=window.width // 2,
            y=window.height // 2 + 240,
            anchor_x="center",
            anchor_y="center",
            batch=self.batch,
        )
        self.tab_label = pyglet.text.Label(
            "< ROCKET >",
            font_name="a Astro Space",
            font_size=20,
            x=window.width // 2,
            y=window.height // 2 + 190,
            anchor_x="center",
            anchor_y="center",
            color=(200, 200, 255, 255),
            batch=self.batch,
        )
        self.instructions = pyglet.text.Label(
            "UP/DOWN: Select | L/R: Tabs | ENTER: Save/Toggle | BACKSPACE: Clear | C: Close",
            font_name="Arial",
            font_size=12,
            x=window.width // 2,
            y=window.height // 2 + 150,
            anchor_x="center",
            anchor_y="center",
            batch=self.batch,
        )
        self.error_label = pyglet.text.Label(
            "",
            font_name="Arial",
            font_size=12,
            x=window.width // 2,
            y=window.height // 2 - 260,
            anchor_x="center",
            anchor_y="center",
            color=(255, 50, 50, 255),
            batch=self.batch,
        )

        self.labels = []
        for i in range(10):  # max items per tab
            y = window.height // 2 + 100 - i * 36
            lbl = pyglet.text.Label(
                "",
                font_name="Arial",
                font_size=16,
                x=window.width // 2 - 350,
                y=y,
                anchor_x="left",
                anchor_y="center",
                batch=self.batch,
            )
            self.labels.append(lbl)

    def update_labels(self):
        current_params = self.params[self.tabs[self.current_tab]]
        self.tab_label.text = f"< {self.tabs[self.current_tab].upper()} >"

        for i in range(len(self.labels)):
            if i < len(current_params):
                param = current_params[i]
                if i == self.selected_param:
                    prefix = "> "
                    color = (0, 255, 0, 255)
                    val_str = (
                        self.input_text if self.input_text != "" else param.getter()
                    )
                else:
                    prefix = "  "
                    color = (255, 255, 255, 255)
                    val_str = param.getter()

                self.labels[i].text = f"{prefix}{param.name}: {val_str}"
                self.labels[i].color = color
            else:
                self.labels[i].text = ""

        self.error_label.text = self.error_text

    def handle_key(self, symbol, modifiers):
        global modal_lock, time_mult_index
        if not self.visible:
            return False

        current_params = self.params[self.tabs[self.current_tab]]

        match symbol:
            case pyglet.window.key.LEFT:
                self.current_tab = max(0, self.current_tab - 1)
                self.selected_param = 0
                self.input_text = ""
            case pyglet.window.key.RIGHT:
                self.current_tab = min(len(self.tabs) - 1, self.current_tab + 1)
                self.selected_param = 0
                self.input_text = ""
            case pyglet.window.key.UP:
                self.selected_param = max(0, self.selected_param - 1)
                self.input_text = ""
            case pyglet.window.key.DOWN:
                self.selected_param = min(
                    len(current_params) - 1, self.selected_param + 1
                )
                self.input_text = ""
            case pyglet.window.key.ENTER:
                param = current_params[self.selected_param]
                if param.ptype == "bool":
                    current_val = param.getter() == "Yes"
                    try:
                        if not param.validator(not current_val):
                            raise ValueError("Invalid bool.")
                        param.setter(not current_val)
                        self.error_text = "Boolean toggled successfully."
                    except ValueError as e:
                        self.error_text = f"Invalid Data: {str(e)}"
                elif self.input_text != "":
                    try:
                        val = float(self.input_text)
                        if not param.validator(val):
                            raise ValueError("Range/Boundary error (invalid value).")

                        if param.name.startswith("Dry Mass") and val == 0:
                            raise ValueError("Division by 0 error (Mass cannot be 0).")

                        param.setter(val)
                        self.input_text = ""
                        self.error_text = "Value updated successfully."
                    except ValueError as e:
                        self.error_text = f"Invalid Data: {str(e)}"
            case pyglet.window.key.BACKSPACE:
                self.input_text = self.input_text[:-1]
            case pyglet.window.key.C:
                self.visible = False
                self.error_text = ""
                if modal_lock == self:
                    modal_lock = None
                    time_mult_index = 0

        self.update_labels()
        return True

    def handle_text(self, text):
        if self.visible:
            if text.lower() == "c":
                return False

            current_params = self.params[self.tabs[self.current_tab]]
            param = current_params[self.selected_param]
            if param.ptype == "bool":
                return False

            if text in "0123456789.eE+-":
                self.input_text += text
                self.update_labels()
            return True
        return False

    def draw(self):
        if self.visible:
            old_view = window.view
            window.view = pyglet.math.Mat4()
            self.update_labels()
            self.batch.draw()
            window.view = old_view


cheat_menu = CheatMenu(window)


# ==========================================
# HELPER FUNCTIONS
# ==========================================


def hex_to_rgba(code) -> tuple[int, int, int, int]:
    """
    Helper function to convert hex colour strings (e.g. 'FF0000') into RGBA integers.
    Modify this if alpha-channel transparency changes are required.
    """
    r = int(code[0:2], 16)
    g = int(code[2:4], 16)
    b = int(code[4:6], 16)
    return (r, g, b, 255)


def format_altitude(meters: float):
    if meters < 1000:
        return f"{meters:.1f} m"
    if meters < 1_000_000:
        return f"{meters / 1000:.1f} km"
    return f"{meters / 1_000_000:.2f} Mm"


def set_arrows(
    rocket: Rocket,
    resultant_force_x: float,
    resultant_force_y: float,
):
    global camera_angle

    if not rocket.visible:
        # If the rocket is not visible (e.g., destroyed), hide all arrows and labels to prevent confusion.
        arrow_group_x.visible = False
        arrow_group_y.visible = False
        arrow_group_accel.visible = False
        return

    c = cos(camera_angle)
    s = sin(camera_angle)

    # Calculate the nearest body's instantaneous velocity
    body = rocket.dominant_body
    if body.is_orbiting:
        # Tangential velocity components: v_x = -r * w * sin(theta), v_y = r * w * cos(theta)
        assert body.orbit_radius is not None
        r = body.orbit_radius
        w = body.angular_velocity
        angle = body.angle

        body_v_x = -r * w * sin(angle)
        body_v_y = r * w * cos(angle)
    else:
        body_v_x = 0
        body_v_y = 0

    # Calculate relative velocity
    relative_rocket_v_x = rocket.velocity_x - body_v_x
    relative_rocket_v_y = rocket.velocity_y - body_v_y

    # 3. Rotate this relative velocity into screen/camera space
    rel_v_x = relative_rocket_v_x * c - relative_rocket_v_y * s
    rel_v_y = relative_rocket_v_x * s + relative_rocket_v_y * c

    rel_f_x = resultant_force_x * c - resultant_force_y * s
    rel_f_y = resultant_force_x * s + resultant_force_y * c

    # Determine directions (1 for positive, -1 for negative movement)
    direction_x = 1 if rel_v_x >= 0 else -1
    direction_y = 1 if rel_v_y >= 0 else -1

    offset = 120  # Pixels out from the rocket
    line_length = 40  # Length of the arrow line
    head_size = 18  # Size of the triangle arrow head

    # Use screen-space center coordinates instead of rocket.x/rocket.y
    base_x = window.width // 2
    base_y = window.height // 2

    # --- Horizontal Arrow (X) ---
    # Positioned to the left/right of the model
    start_x = base_x + (offset * direction_x)
    start_y = base_y
    end_x = start_x + (line_length * direction_x)

    arrow_x.x, arrow_x.y = start_x, start_y
    arrow_x.x2, arrow_x.y2 = end_x, start_y

    # Point the triangle head along the axis
    arrow_head_x.x, arrow_head_x.y = end_x, start_y
    arrow_head_x.x2, arrow_head_x.y2 = end_x - (head_size * direction_x), start_y + (
        head_size / 2
    )
    arrow_head_x.x3, arrow_head_x.y3 = end_x - (head_size * direction_x), start_y - (
        head_size / 2
    )

    # --- Vertical Arrow (Y) ---
    # Positioned above/below the model
    start_x_yline = base_x
    start_y_yline = base_y + (offset * direction_y)
    end_y = start_y_yline + (line_length * direction_y)

    arrow_y.x, arrow_y.y = start_x_yline, start_y_yline
    arrow_y.x2, arrow_y.y2 = start_x_yline, end_y

    # Point the triangle head along the axis
    arrow_head_y.x, arrow_head_y.y = start_x_yline, end_y
    arrow_head_y.x2, arrow_head_y.y2 = start_x_yline - (head_size / 2), end_y - (
        head_size * direction_y
    )
    arrow_head_y.x3, arrow_head_y.y3 = start_x_yline + (head_size / 2), end_y - (
        head_size * direction_y
    )

    arrow_label_x.x = start_x + ((line_length * direction_x) / 2)
    arrow_label_x.y = start_y - 15
    arrow_label_y.x = start_x_yline - 15
    arrow_label_y.y = start_y_yline + ((line_length * direction_y) / 2)

    # Format label and place it just below the arrow
    arrow_label_x.text = f"{abs(rel_v_x):.1f} m/s"
    arrow_label_y.text = f"{abs(rel_v_y):.1f} m/s"

    arrow_group_x.visible = False if round(rel_v_x) == 0 else True
    arrow_group_y.visible = False if round(rel_v_y) == 0 else True

    # --- Acceleration Arrow (Top Left) ---
    accel_base_x = 50
    accel_base_y = window.height - 60

    # Calculate vector direction directly from forces
    # Avoid div by 0 if forces are somehow 0
    if rel_f_x == 0 and rel_f_y == 0:
        accel_dir_x = 0
        accel_dir_y = 1
        accel_angle = 0
        accel_mag = 0.0
    else:
        # Get purely directional unit vector by normalizing forces
        total_force_mag = sqrt(rel_f_x**2 + rel_f_y**2)
        accel_dir_x = rel_f_x / total_force_mag
        accel_dir_y = rel_f_y / total_force_mag
        # Calculate acceleration magnitude (a = F/m)
        accel_mag = total_force_mag / rocket.wet_mass

        # Calculate the angle of the resultant vector in radians for rendering
        # Math atan2 usually takes (Y, X), but Pyglet rotation requires specific offset matching
        # Pyglet 0 deg = Up (0, 1), 90 deg = Right (1, 0)
        accel_angle = degrees(atan2(accel_dir_x, accel_dir_y))

    arrow_accel.x, arrow_accel.y = accel_base_x, accel_base_y
    arrow_accel.x2 = accel_base_x + (line_length * accel_dir_x)
    arrow_accel.y2 = accel_base_y + (line_length * accel_dir_y)

    arrow_head_accel.x = arrow_accel.x2
    arrow_head_accel.y = arrow_accel.y2
    arrow_head_accel.rotation = accel_angle

    # Move label further right to not overlap the dynamic arrowhead
    arrow_label_accel.x = accel_base_x + 50
    arrow_label_accel.y = accel_base_y
    arrow_label_accel.text = f"{accel_mag:.1f} m/s^2"

    arrow_group_accel.visible = round(accel_mag, 1) != 0.0


def clear_event_notice(_dt):
    event_notice_label.text = ""


def show_temporary_notice(text, color=(255, 255, 0, 255), duration=2.0, y=None):
    event_notice_label.text = text
    event_notice_label.color = color
    if y is not None:
        event_notice_label.y = y
    pyglet.clock.unschedule(clear_event_notice)
    pyglet.clock.schedule_once(clear_event_notice, duration)


# ==========================================
# GAME ENTITIES & ENVIRONMENT SETUP
# ==========================================

# Defines the drawing batch and colour layers of the atmospheric skybox.
skybox = pyglet.graphics.Batch()

# Colour palette for atmospheric effects. Change these hex values to alter planetary atmosphere visuals.
light_blue = hex_to_rgba("9fd7f9")
deep_blue = hex_to_rgba("0d8bd9")
black = (0, 0, 0, 255)

# Earth definition
earth = Body(
    x=window.width // 2,
    y=283 - EARTH_RADIUS,
    radius=EARTH_RADIUS,
    color=(34, 139, 34, 255),  # Modify static untextured planet colour here
    mass=EARTH_MASS,
    name="Earth",
    atmosphere={
        "number_of_layers": 2,  # Expand layers to create smoother gradient transitions
        "colours": (light_blue, deep_blue, black),
        "outer_radius": EARTH_RADIUS + KARMAN_LINE,
    },
)

# Moon definition
moon = Body(
    x=earth.x + EARTH_MOON_DISTANCE,
    y=earth.y,
    radius=MOON_RADIUS,
    color=(169, 169, 169, 255),  # Adjust lunar surface colour
    mass=MOON_MASS,
    name="The Moon",
    body_to_orbit=earth,
    orbit_radius=EARTH_MOON_DISTANCE,
)

# Determines the edge of meaningful orbital interactions for physics checks
ALTITUDE_THRESHOLDS = {
    earth: KARMAN_LINE,
    moon: 15000,
}

# ==========================================
# ROCKET INITIALIZATION
# ==========================================
# Instantiate the primary spacecraft passed into physics simulations
rocket = Rocket(bodies=[earth, moon])

# Static marker used when zoomed out far enough that the detailed sprite becomes sub-pixel
rocket_marker = pyglet.shapes.Triangle(0, 0, 20, 0, 10, 25, color=(255, 255, 255))
rocket_marker.anchor_x = 10
rocket_marker.anchor_y = 12.5

# ==========================================
# UI COMPONENTS & HUD
# ==========================================

modal_lock = None  # Global lock to prevent multiple modals from overlapping or conflicting, None for no lock, or set to the modal instance that should be locked in place
pause_modal = Modal(
    title="PAUSED",
    content_text="",
    buttons=[Button(0, 0, 150, 40, "Resume"), Button(0, 0, 150, 40, "Menu")],
)
tutorial_ask_modal = Modal(
    title="Welcome to Skypiercer!",
    content_text="Would you like to enable tutorial hints on this run?",
    buttons=[Button(0, 0, 150, 40, "Yes"), Button(0, 0, 150, 40, "No")],
)

tutorial_step = 0
tutorial_modals = [
    Modal(
        title="Tutorial: Takeoff",
        content_text="Engage engine (SPACE). Wait for your apoapsis to reach about 12km, then turn 45 deg clockwise. Wait until the apoapsis is above 33km. Zoom in and out with the scroll wheel and press M to reset zoom.",
        buttons=[Button(0, 0, 150, 40, "Got it")],
    ),
    Modal(
        title="Tutorial: Reach LEO",
        content_text="Guide your ship into reaching low Earth orbit (LEO) by time warping to the apoapsis (PERIOD to increase, COMMA to decrease) and burning prograde (facing the direction of travel). Stop burning when the trajectory goes around the Earth.",
        buttons=[Button(0, 0, 150, 40, "Got it")],
    ),
    Modal(
        title="Tutorial: TLI",
        content_text="Time warp to the TLI marker and burn prograde to intercept the Moon. Fine control your thrust with Q and E. The value next to the marker shows how much more speed (delta-v) you need until you should stop. Once the marker disappears, stop burning and time warp.",
        buttons=[Button(0, 0, 150, 40, "Got it")],
    ),
    Modal(
        title="Tutorial: Lunar Landing",
        content_text="Press ENTER to activate the next stage (decreases mass and max thrust). Burn retrograde (facing opposite to direction of travel) until landing safely on the surface. Touch down less than 15 m/s.",
        buttons=[Button(0, 0, 150, 40, "Got it")],
    ),
    Modal(
        title="Tutorial: Lunar Orbit",
        content_text="Similar to LEO, take off and turn clockwise until the apoapsis is around 15km. Then, time warp to the apoapsis and burn prograde until the trajectory goes around the Moon.",
        buttons=[Button(0, 0, 150, 40, "Got it")],
    ),
    Modal(
        title="Tutorial: TEI",
        content_text="Time warp to the TEI marker and burn prograde until the marker disappears to return to Earth. Fine control your thrust with Q and E.",
        buttons=[Button(0, 0, 150, 40, "Got it")],
    ),
    Modal(
        title="Tutorial: Re-entry",
        content_text="Press ENTER to stage. Make sure the descent is shallow and not perpendicular ton the surface to not burn up. Deploy your parachute (P) to land gently when you're travelling less than 250 m/s.",
        buttons=[Button(0, 0, 150, 40, "Got it")],
    ),
]

# Text labels for telemetry rendering
# Adjust 'x' and 'y' positions or 'font_size' to reposition these elements on custom aspect ratios.
status_text = pyglet.text.Label(
    "Press SPACE to Engage Engine",
    font_name="a Astro Space",
    font_size=window.width // 40,
    x=window.width // 2,
    y=110,
    anchor_x="center",
    anchor_y="center",
)

event_notice_label = pyglet.text.Label(
    "",
    font_name="a Astro Space",
    font_size=window.width // 50,
    x=window.width // 2,
    y=window.height - 150,
    anchor_x="center",
    anchor_y="center",
    color=(255, 255, 0, 255),
)


time_mult_text = pyglet.text.Label(
    font_name="a Astro Space",
    font_size=window.width // 50,
    x=window.width - 30,
    y=window.height - 30,
    anchor_x="right",
    anchor_y="top",
)
telemetry_text = pyglet.text.Label(
    font_name="a Astro Space",
    font_size=window.width // 50,
    x=window.width // 2,
    y=50,
    anchor_x="center",
    anchor_y="center",
)
temp_text = pyglet.text.Label(
    font_name="a Astro Space",
    font_size=window.width // 60,
    x=window.width - 180,
    y=window.height - 100,
    anchor_x="left",
    anchor_y="center",
)

arrow_batch_x = pyglet.graphics.Batch()
arrow_batch_y = pyglet.graphics.Batch()
arrow_batch_accel = pyglet.graphics.Batch()
arrow_group_x = pyglet.graphics.Group()
arrow_group_y = pyglet.graphics.Group()
arrow_group_accel = pyglet.graphics.Group()

# Create white lines and triangles to represent the vector arrows
arrow_x = pyglet.shapes.Line(
    0,
    0,
    0,
    0,
    thickness=2,
    color=(255, 255, 255),
    batch=arrow_batch_x,
    group=arrow_group_x,
)
arrow_y = pyglet.shapes.Line(
    0,
    0,
    0,
    0,
    thickness=2,
    color=(255, 255, 255),
    batch=arrow_batch_y,
    group=arrow_group_y,
)
arrow_accel = pyglet.shapes.Line(
    0,
    0,
    0,
    0,
    thickness=2,
    color=(255, 255, 255),
    batch=arrow_batch_accel,
    group=arrow_group_accel,
)

arrow_head_x = pyglet.shapes.Triangle(
    0, 0, 0, 0, 0, 0, color=(255, 255, 255), batch=arrow_batch_x, group=arrow_group_x
)
arrow_head_y = pyglet.shapes.Triangle(
    0, 0, 0, 0, 0, 0, color=(255, 255, 255), batch=arrow_batch_y, group=arrow_group_y
)
arrow_head_accel = pyglet.shapes.Triangle(
    0,
    0,
    -9,
    -18,
    9,
    -18,
    color=(255, 255, 255),
    batch=arrow_batch_accel,
    group=arrow_group_accel,
)

# Labels for the exact readout next to the arrows
arrow_label_x = pyglet.text.Label(
    font_name="a Astro Space",
    font_size=window.width // 60,
    anchor_x="center",
    anchor_y="top",
    batch=arrow_batch_x,
    group=arrow_group_x,
)
arrow_label_y = pyglet.text.Label(
    font_name="a Astro Space",
    font_size=window.width // 60,
    anchor_x="right",
    anchor_y="center",
    batch=arrow_batch_y,
    group=arrow_group_y,
)
arrow_label_accel = pyglet.text.Label(
    font_name="a Astro Space",
    font_size=window.width // 60,
    anchor_x="left",
    anchor_y="center",
    batch=arrow_batch_accel,
    group=arrow_group_accel,
)

# ==========================================
# CAMERA & GLOBAL STATE CONFIGURATION
# ==========================================
# Track and manipulate viewport coordinates or zoom levels
camera_angle = 0  # Initial camera angle in radians. Can be modified by logic that locks view to horizon.
zoom_mult = 1.0  # Scales projection for zooming in and out. Lower numbers = zoomed out.

# Simulation speed multiplier array
# Add new integer step sizes here to allow faster or slower time warps.
time_mult_steps = [
    1,  # Real-time baseline (1x)
    2,
    3,
    5,
    25,
    50,
    100,
    500,
    2500,
    10000,
    50000,
    250000,
    0,  # Pause state placeholder
]
time_mult_index = 0

# Floating origin tracking metrics
origin_x = 0.0
origin_y = 0.0

# ==========================================
# ORBIT PROJECTION & TELEMETRY
# ==========================================
# Configuration and rendering groups for elliptical orbit drawing
trajectory_batch = pyglet.graphics.Batch()
trajectory_group = pyglet.graphics.Group()
MAX_TRAJECTORY_LINES = (
    2000  # Cap to prevent out-of-memory errors when projecting long paths
)

trajectory_lines = [
    pyglet.shapes.Line(
        0,
        0,
        0,
        0,
        thickness=1,
        color=(255, 255, 255, 120),  # Slightly transparent
        batch=trajectory_batch,
        group=trajectory_group,
    )
    for _ in range(MAX_TRAJECTORY_LINES)
]

apoapsis_marker = pyglet.shapes.Circle(
    0,
    0,
    radius=1,
    color=(255, 200, 0, 255),
    batch=trajectory_batch,
    group=trajectory_group,
)
apoapsis_marker.visible = False
apoapsis_label = pyglet.text.Label(
    "",
    font_name="a Astro Space",
    font_size=window.width // 60,
    color=(255, 200, 0, 255),
    group=trajectory_group,
)

tli_marker = pyglet.shapes.Circle(
    0,
    0,
    radius=1,
    color=(255, 0, 255, 255),
    batch=trajectory_batch,
    group=trajectory_group,
)
tli_marker.visible = False
tli_label = pyglet.text.Label(
    "",
    font_name="a Astro Space",
    font_size=window.width // 60,
    color=(255, 0, 255, 255),
    group=trajectory_group,
)


def reset_game():
    global earth, moon, rocket, ALTITUDE_THRESHOLDS
    global camera_angle, zoom_mult, time_mult_index, origin_x, origin_y
    global tutorial, tutorial_step

    # Re-initialize Earth
    earth = Body(
        x=window.width // 2,
        y=283 - EARTH_RADIUS,
        radius=EARTH_RADIUS,
        color=(34, 139, 34, 255),
        mass=EARTH_MASS,
        name="Earth",
        atmosphere={
            "number_of_layers": 2,
            "colours": (light_blue, deep_blue, black),
            "outer_radius": EARTH_RADIUS + KARMAN_LINE,
        },
    )

    # Re-initialize Moon
    moon = Body(
        x=earth.x + EARTH_MOON_DISTANCE,
        y=earth.y,
        radius=MOON_RADIUS,
        color=(169, 169, 169, 255),
        mass=MOON_MASS,
        name="The Moon",
        body_to_orbit=earth,
        orbit_radius=EARTH_MOON_DISTANCE,
    )

    ALTITUDE_THRESHOLDS = {
        earth: KARMAN_LINE,
        moon: 15000,
    }

    rocket = Rocket(bodies=[earth, moon])

    rocket_marker.x = rocket.x
    rocket_marker.y = rocket.y
    rocket_marker.rotation = rocket.rotation

    camera_angle = 0
    zoom_mult = 1.0
    time_mult_index = 0

    origin_x = 0.0
    origin_y = 0.0

    tutorial = None
    tutorial_step = 0

    for line in trajectory_lines:
        line.visible = False
    apoapsis_marker.visible = False
    apoapsis_label.visible = False
    tli_marker.visible = False
    tli_label.visible = False

    status_text.text = "Press SPACE to Engage Engine"


# ==========================================
# EVENT HANDLERS & GRAPHICAL PIPELINE
# ==========================================
def draw_notices():
    """
    Renders on-screen events (Landings, crash reports, altitude notices).
    Tweak colour tuples for text alerts or positional `_LOCATION` values
    below to move text up or down the HUD.
    """
    global modal_lock, tutorial_step, time_mult_index

    if time_mult_index == -1 and (modal_lock is None or modal_lock == pause_modal):
        modal_lock = pause_modal
        pause_modal.visible = True
        pause_modal.draw()
    else:
        pause_modal.visible = False

    if (
        tutorial is None
        and game_state == "PLAYING"
        and (modal_lock is None or modal_lock == tutorial_ask_modal)
    ):
        modal_lock = tutorial_ask_modal
        tutorial_ask_modal.visible = True
        tutorial_ask_modal.draw()
        time_mult_index = -1
    else:
        tutorial_ask_modal.visible = False

    # Tutorial hints
    if tutorial and tutorial_step < len(tutorial_modals):
        current_tut_modal = tutorial_modals[tutorial_step]
        if modal_lock is None and not current_tut_modal.visible:
            should_show = False
            alt = rocket.distance_from_object(earth.centre) - earth.radius

            match tutorial_step:
                case 0:
                    should_show = True
                case 1:
                    if alt >= 25000:
                        should_show = True
                case 2:
                    if rocket.dominant_body == earth and tli_marker.visible:
                        should_show = True
                case 3:
                    if rocket.dominant_body == moon:
                        should_show = True
                case 4:
                    if (
                        rocket.dominant_body == moon
                        and rocket.distance_from_object(moon.centre) - moon.radius == 0
                    ):
                        should_show = True
                case 5:
                    if rocket.dominant_body == moon and tli_marker.visible:
                        should_show = True
                case 6:
                    if (
                        rocket.dominant_body == earth
                        and rocket.distance_from_object(earth.centre) - earth.radius
                        < KARMAN_LINE
                    ):
                        should_show = True

            if should_show:
                modal_lock = current_tut_modal
                current_tut_modal.visible = True
                # Force time warp to -1 to pause the game but do not show pause menu
                time_mult_index = -1

        if current_tut_modal.visible:
            current_tut_modal.draw()

    nearest_body = rocket.nearest_body

    angle_from_centre = atan2(rocket.y - nearest_body.y, rocket.x - nearest_body.x)
    segment_angle = pi / 128
    alpha = (angle_from_centre % segment_angle) - (segment_angle / 2)
    polygon_radius_scalar = cos(segment_angle / 2) / cos(alpha)
    effective_radius = nearest_body.radius * polygon_radius_scalar

    # Render a notification if the payload has safely landed or destructively crashed.
    if rocket.distance_from_object(nearest_body.centre) - effective_radius <= 0.1:
        land_notice = pyglet.text.Label(
            f"Landed on {nearest_body}!",
            font_name="a Astro Space",
            font_size=window.width // 50,
            x=window.width // 2,
            y=ACHIEVEMENT_LOCATION,
            anchor_x="center",
            anchor_y="center",
            color=SUCCESS_COLOUR,  # Render text in green indicating success
        )

        # A survival logic check. The rocket is 'destroyed' at a predefined impact speed.
        if rocket.speed >= rocket.max_impact_speed:
            land_notice.text = f"Crashed on {nearest_body}!"
            land_notice.color = (
                ERROR_COLOUR  # Render text in red indicating destruction
            )
            land_notice.draw()
        else:
            land_notice.draw()

    # Notice for passing the Karman Line (edge of space).
    if KARMAN_LINE == rocket.distance_from_object((earth.x, earth.y)) - EARTH_RADIUS:
        show_temporary_notice(
            "Passing the Karman Line!",
            color=INFO_COLOUR,
            duration=3.0,
            y=ACHIEVEMENT_LOCATION,
        )

    # Steering is artificially locked at high time-warps to prevent instability and loss of control.
    if time_mult_index > 3 and (
        keys[pyglet.window.key.LEFT] or keys[pyglet.window.key.RIGHT]
    ):
        show_temporary_notice(
            "Cannot rotate while time warping!",
            color=WARN_COLOUR,
            duration=1.0,
            y=WARN_LOCATION,
        )

    # Time warp altitude and thrust locks. These are safety measures to prevent players from accidentally skipping past critical flight phases.
    altitude = (
        rocket.distance_from_object(rocket.nearest_body.centre)
        - rocket.nearest_body.radius
    )
    if time_mult_index == 2 and keys[pyglet.window.key.PERIOD]:
        if altitude <= ALTITUDE_THRESHOLDS[rocket.nearest_body]:
            show_temporary_notice(
                f"Cannot time warp past 3x below {ALTITUDE_THRESHOLDS[rocket.nearest_body] // 1000}km!",
                color=WARN_COLOUR,
                duration=1.0,
                y=WARN_LOCATION,
            )
        elif rocket.engaged:
            show_temporary_notice(
                "Can't time warp past 3x while engine is engaged!",
                color=WARN_COLOUR,
                duration=1.0,
                y=WARN_LOCATION,
            )

    if event_notice_label.text:
        event_notice_label.draw()


@window.event
def on_mouse_press(x, y, _button, _modifiers):
    global game_state, time_mult_index, modal_lock, tutorial, tutorial_step
    if game_state == "MENU":
        for btn in main_menu.buttons:
            if btn.x <= x <= btn.x + btn.width and btn.y <= y <= btn.y + btn.height:
                match btn.text.text:
                    case "Exit":
                        pyglet.app.exit()
                    case "Play":
                        reset_game()
                        game_state = "PLAYING"
        return pyglet.event.EVENT_HANDLED

    if pause_modal.visible:
        for btn in pause_modal.buttons:
            if btn.x <= x <= btn.x + btn.width and btn.y <= y <= btn.y + btn.height:
                match btn.text.text:
                    case "Resume":
                        time_mult_index = 0  # Assuming 0 is 1x speed
                        modal_lock = None
                        pause_modal.visible = False
                    case "Menu":
                        game_state = "MENU"
                        time_mult_index = 0
                        modal_lock = None
                        pause_modal.visible = False
        return pyglet.event.EVENT_HANDLED

    if tutorial_ask_modal.visible:
        for btn in tutorial_ask_modal.buttons:
            if btn.x <= x <= btn.x + btn.width and btn.y <= y <= btn.y + btn.height:
                match btn.text.text:
                    case "Yes":
                        tutorial = True
                        tutorial_step = 0
                        modal_lock = None
                        tutorial_ask_modal.visible = False
                        time_mult_index = 0
                    case "No":
                        tutorial = False
                        modal_lock = None
                        tutorial_ask_modal.visible = False
                        time_mult_index = 0
        return pyglet.event.EVENT_HANDLED

    if tutorial and tutorial_step < len(tutorial_modals):
        current_tut = tutorial_modals[tutorial_step]
        if current_tut.visible:
            for btn in current_tut.buttons:
                if btn.x <= x <= btn.x + btn.width and btn.y <= y <= btn.y + btn.height:
                    current_tut.visible = False
                    tutorial_step += 1
                    modal_lock = None
                    time_mult_index = 0
            return pyglet.event.EVENT_HANDLED

    return pyglet.event.EVENT_UNHANDLED


@window.event
def on_mouse_motion(x, y, dx, dy):
    if game_state == "MENU":
        for btn in main_menu.buttons:
            if btn.x <= x <= btn.x + btn.width and btn.y <= y <= btn.y + btn.height:
                btn.color = (70, 70, 220)
            else:
                btn.color = (50, 50, 200)
        return pyglet.event.EVENT_HANDLED

    if pause_modal.visible:
        for btn in pause_modal.buttons:
            if btn.x <= x <= btn.x + btn.width and btn.y <= y <= btn.y + btn.height:
                btn.color = (70, 70, 220)
            else:
                btn.color = (50, 50, 200)
        return pyglet.event.EVENT_HANDLED

    if tutorial_ask_modal.visible:
        for btn in tutorial_ask_modal.buttons:
            if btn.x <= x <= btn.x + btn.width and btn.y <= y <= btn.y + btn.height:
                btn.color = (70, 70, 220)
            else:
                btn.color = (50, 50, 200)
        return pyglet.event.EVENT_HANDLED

    if (
        tuple(globals().keys())
        and "tutorial_step" in globals()
        and tutorial
        and tutorial_step < len(tutorial_modals)
    ):
        current_tut = tutorial_modals[tutorial_step]
        if current_tut.visible:
            for btn in current_tut.buttons:
                if btn.x <= x <= btn.x + btn.width and btn.y <= y <= btn.y + btn.height:
                    btn.color = (70, 70, 220)
                else:
                    btn.color = (50, 50, 200)
            return pyglet.event.EVENT_HANDLED

    return pyglet.event.EVENT_UNHANDLED


@window.event
def on_draw():
    """
    Main Pyglet rendering callback. Fires every frame to composite the visual output.
    Contains logic for camera movement, object ordering, label positions, and
    transform scaling. Adjust rendering order here to layer elements properly.
    """
    global camera_angle

    window.clear()

    if game_state == "MENU":
        old_view = window.view
        window.view = Mat4()
        main_menu.draw()
        window.view = old_view
        return

    altitude = (
        rocket.distance_from_object(rocket.nearest_body.centre)
        - rocket.nearest_body.radius
    )

    # Flatten the camera's orientation to the planetary surface normal inside the atmosphere
    # Disable or uncomment this clause to allow free-rotation inside gravity wells
    if altitude < ALTITUDE_THRESHOLDS[rocket.nearest_body]:
        camera_angle = pi / 2 - atan2(
            rocket.y - rocket.nearest_body.y, rocket.x - rocket.nearest_body.x
        )

    # Camera System
    # Translates logical world coordinates to the center of pixel space, applies zoom,
    # and counter-rotates based on the calculated 'camera_angle'.
    # Modify view matrix components to change focus (e.g. tracking a moon instead of the rocket)
    # Tweak: `zoom_mult` affects the `Mat4.from_scale` and the final visual size of all UI vs world scaling.
    window.view = (
        Mat4.from_translation(Vec3(window.width / 2, window.height / 2, 0))
        @ Mat4.from_scale(Vec3(zoom_mult, zoom_mult, 1))
        @ Mat4.from_rotation(camera_angle, Vec3(0, 0, 1))
        @ Mat4.from_translation(Vec3(-rocket.x, -rocket.y, 0))
    )

    # Sequence defines draw priority. Later elements paint on top of earlier ones.
    skybox.draw()
    earth.draw()
    moon.draw()

    if moon.orbit_path:
        moon.orbit_path.visible = (
            zoom_mult < 5e-5
        )  # Only show orbit path when zoomed out enough to prevent clutter

    # Adjust trajectory line thickness based on zoom
    trajectory_thickness = int(zoom_mult**-1 * 2)
    for line in trajectory_lines:
        if line.visible:
            line.thickness = trajectory_thickness

    trajectory_batch.draw()

    if zoom_mult >= 0.05:
        rocket.draw()
    else:
        window.view = (
            Mat4.from_translation(Vec3(window.width / 2, window.height / 2, 0))
            @ Mat4.from_rotation(camera_angle, Vec3(0, 0, 1))
            @ Mat4.from_translation(Vec3(-rocket.x, -rocket.y, 0))
        )
        rocket_marker.x = rocket.x
        rocket_marker.y = rocket.y
        rocket_marker.rotation = rocket.rotation
        rocket_marker.draw()

    # Reset view matrix to draw UI elements in screen space (fixed position)
    window.view = Mat4()

    thickness = int(zoom_mult**-1 * 3)
    c = cos(camera_angle)
    s = sin(camera_angle)

    # Convert apoapsis position to screen space for label placement, factoring in camera rotation
    apoapsis_marker.radius = thickness
    if apoapsis_label.visible:
        apo_dx = apoapsis_marker.x - rocket.x
        apo_dy = apoapsis_marker.y - rocket.y
        rot_apo_dx = apo_dx * c - apo_dy * s
        rot_apo_dy = apo_dx * s + apo_dy * c

        apoapsis_label.x = window.width / 2 + rot_apo_dx * zoom_mult
        apoapsis_label.y = window.height / 2 + rot_apo_dy * zoom_mult + 12
        apoapsis_label.draw()

    # Convert TLI position to screen space for label placement, factoring in camera rotation
    tli_marker.radius = thickness
    if tli_label.visible:
        tli_dx = tli_marker.x - rocket.x
        tli_dy = tli_marker.y - rocket.y
        rot_tli_dx = tli_dx * c - tli_dy * s
        rot_tli_dy = tli_dx * s + tli_dy * c

        tli_label.x = window.width / 2 + rot_tli_dx * zoom_mult
        tli_label.y = window.height / 2 + rot_tli_dy * zoom_mult + 12
        tli_label.draw()

    if zoom_mult >= 0.05:
        arrow_batch_x.draw()
        arrow_batch_y.draw()

    arrow_batch_accel.draw()

    # Draw static HUD logic that disregards camera transformations
    if rocket.visible:
        status_text.draw()

        # Calculates altitude dynamically.
        # Change max() default floor to allow sub-surface heights (for debugging)
        # Modify the format_altitude parameter if parsing different metrics
        nearest_body = rocket.nearest_body

        angle_from_centre = atan2(rocket.y - nearest_body.y, rocket.x - nearest_body.x)
        segment_angle = pi / 128
        alpha = (angle_from_centre % segment_angle) - (segment_angle / 2)
        polygon_radius_scalar = cos(segment_angle / 2) / cos(alpha)
        effective_radius = nearest_body.radius * polygon_radius_scalar

        altitude = format_altitude(
            max(
                0,
                (rocket.distance_from_object(nearest_body.centre) - effective_radius),
            )
        )

        telemetry_text.text = f"Fuel: {rocket.fuel:.0f} kg ({rocket.fuel_percentage}%) | Speed: {rocket.speed:.0f} m/s | Altitude: {altitude}"

        temp_text.text = f"Temp: {rocket.temperature:.0f}K"

        # Color warning if getting close to destruction
        if rocket.temperature > rocket.max_safe_temperature * 0.8:
            temp_text.color = ERROR_COLOUR
        elif rocket.temperature > rocket.max_safe_temperature * 0.5:
            temp_text.color = WARN_COLOUR
        else:
            temp_text.color = (255, 255, 255, 255)

        altitude = (
            rocket.distance_from_object(rocket.nearest_body.centre)
            - rocket.nearest_body.radius
        )
        telemetry_text.draw()
        if (
            rocket.nearest_body.has_atmosphere
            and altitude <= ALTITUDE_THRESHOLDS[rocket.nearest_body]
        ):
            temp_text.draw()

        time_mult_text.text = f"{time_mult_steps[time_mult_index]}x"
        time_mult_text.draw()

    draw_notices()
    if cheat_menu.visible:
        cheat_menu.draw()


@window.event
def on_text(text):
    if cheat_menu.visible:
        cheat_menu.handle_text(text)
        return pyglet.event.EVENT_HANDLED


@window.event
def on_key_press(symbol, modifiers):
    """Handles single key press events."""
    global time_mult_index, game_state, modal_lock

    if game_state == "MENU":
        return pyglet.event.EVENT_HANDLED

    altitude = (
        rocket.distance_from_object(rocket.nearest_body.centre)
        - rocket.nearest_body.radius
    )

    if cheat_menu.visible:
        cheat_menu.handle_key(symbol, modifiers)
        return pyglet.event.EVENT_HANDLED

    if symbol == pyglet.window.key.C:
        modal_lock = cheat_menu
        cheat_menu.visible = True
        cheat_menu.update_labels()
        time_mult_index = -1
        return pyglet.event.EVENT_HANDLED

    if time_mult_index == -1 or modal_lock is not None:
        # If currently paused ignore all other inputs to prevent unintended time warp changes or engine toggling while paused.
        # Change keybinds in the condition above to modify the allowed inputs during the paused state.
        return pyglet.event.EVENT_HANDLED

    match symbol:
        case pyglet.window.key.SPACE:
            # Toggle engine if visible and has fuel
            if rocket.fuel > 0 and rocket.visible:
                rocket.engaged = not rocket.engaged
                status_text.text = (
                    f"Engine Engaged: {rocket.thrust_level * 100:.0f}%"
                    if rocket.engaged
                    else "Press SPACE to Engage Engine"
                )
        case pyglet.window.key.M:
            # Reset zoom to default with M key
            global zoom_mult
            zoom_mult = 1.0
        case pyglet.window.key.ENTER:
            if rocket.jettison_stage():
                show_temporary_notice(
                    "Stage jettisoned!",
                    color=ACHIEVEMENT_COLOUR,
                    duration=2.0,
                    y=ACHIEVEMENT_LOCATION,
                )
            else:
                show_temporary_notice(
                    "No more stages to jettison!",
                    color=WARN_COLOUR,
                    duration=2.0,
                    y=WARN_LOCATION,
                )
        case pyglet.window.key.P:
            if rocket.parachute_deployed is None:
                show_temporary_notice(
                    "Parachute has already been cut!",
                    color=WARN_COLOUR,
                    duration=1.0,
                    y=WARN_LOCATION,
                )
            elif rocket.parachute_deployed:
                show_temporary_notice(
                    "Parachute has already been deployed!",
                    color=ERROR_COLOUR,
                    duration=3.0,
                    y=ACHIEVEMENT_LOCATION,
                )
            elif not (
                rocket.nearest_body.has_atmosphere
                and altitude <= ALTITUDE_THRESHOLDS[rocket.nearest_body]
            ):
                show_temporary_notice(
                    "Can't deploy parachute in a vacuum!",
                    color=WARN_COLOUR,
                    duration=1.0,
                    y=WARN_LOCATION,
                )
            elif rocket.speed > 250:
                show_temporary_notice(
                    "Can't deploy parachute above 250 m/s!",
                    color=WARN_COLOUR,
                    duration=1.0,
                    y=WARN_LOCATION,
                )
            else:
                rocket.deploy_parachute()
                show_temporary_notice(
                    "Parachute deployed!",
                    color=ACHIEVEMENT_COLOUR,
                    duration=3.0,
                    y=ACHIEVEMENT_LOCATION,
                )
        case pyglet.window.key.PERIOD:
            # Time warp control: increase multiplier with PERIOD key. Safety checks prevent warping past critical flight phases (e.g., re-entry below 30km or while engine is active).
            if time_mult_index == len(time_mult_steps) - 2:
                return
            if altitude <= ALTITUDE_THRESHOLDS[rocket.nearest_body] or rocket.engaged:
                time_mult_index = min(time_mult_index + 1, 2)  # Limit to 3x below 30km
            elif (
                altitude > ALTITUDE_THRESHOLDS[rocket.nearest_body]
                and time_mult_index < 3
            ):
                time_mult_index = 3
            else:
                time_mult_index = min(time_mult_index + 1, len(time_mult_steps) - 2)

        case pyglet.window.key.COMMA:
            # Time warp control: decrease multiplier with COMMA key. Safety checks prevent unintended warping into critical flight phases (e.g., re-entry below 30km).
            if time_mult_index == 0:
                return
            if (
                altitude > ALTITUDE_THRESHOLDS[rocket.nearest_body]
                and time_mult_index == 3
            ):
                time_mult_index = 0
            time_mult_index = max(time_mult_index - 1, 0)

        case pyglet.window.key.ESCAPE:
            # Pause / Reset time warp
            time_mult_index = (
                -1 if time_mult_index != -1 else 0
            )  # Toggle between PAUSED and real-time
            return pyglet.event.EVENT_HANDLED


@window.event
def on_mouse_scroll(_x, _y, _scroll_x, scroll_y):
    """Handles mouse scroll for zooming the camera."""
    global zoom_mult
    # Zoom in/out by 10% per scroll tick
    zoom_mult *= 1.1**scroll_y

    # Limit max zoom level to 2x (closer)
    zoom_mult = min(zoom_mult, 2.0)


def update_trajectory(_dt):
    """
    Renders the projected orbital path derived from the Keplerian forecast in Rocket.py.
    This function manages object pooling of Pyglet lines to avoid memory reallocations.
    To improve performance for deeply complex orbital projections, consider reducing
    'MAX_TRAJECTORY_LINES' in the configuration rather than changing logic here.
    """
    if time_mult_index == -1 or game_state == "MENU":
        return

    apoapsis_marker.visible = False
    apoapsis_label.visible = False
    tli_marker.visible = False
    tli_label.visible = False

    if rocket.dominant_body == earth:
        transfer_body = moon
    else:
        transfer_body = earth

    trajectory = rocket.calculate_trajectory(
        transfer_body=transfer_body, transfer_distance=EARTH_MOON_DISTANCE
    )
    altitude = (
        rocket.distance_from_object(rocket.nearest_body.centre)
        - rocket.nearest_body.radius
    )
    if not trajectory or altitude <= 0:
        for line in trajectory_lines:
            line.visible = False
        return

    path, apoapsis_pos, tli_pos, delta_v = trajectory

    draw_count = min(len(path) - 1, MAX_TRAJECTORY_LINES)
    for i in range(draw_count):
        trajectory_lines[i].x = path[i][0]
        trajectory_lines[i].y = path[i][1]
        trajectory_lines[i].x2 = path[i + 1][0]
        trajectory_lines[i].y2 = path[i + 1][1]
        trajectory_lines[i].visible = True

    # Turn OFF unused leftover lines from previous longer orbits
    for i in range(draw_count, MAX_TRAJECTORY_LINES):
        trajectory_lines[i].visible = False

    if len(path) > 1:
        if apoapsis_pos:
            apoapsis_marker.x, apoapsis_marker.y = apoapsis_pos
            apoapsis_marker.visible = True
            apoapsis_label.visible = True
            global global_apo_dist
            global_apo_dist = (
                sqrt(
                    (apoapsis_pos[0] - rocket.nearest_body.x) ** 2
                    + (apoapsis_pos[1] - rocket.nearest_body.y) ** 2
                )
                - rocket.nearest_body.radius
            )
            apo_alt = format_altitude(global_apo_dist)
            apoapsis_label.text = apo_alt

        if delta_v >= 0:
            tli_marker.x = tli_pos[0]
            tli_marker.y = tli_pos[1]
            tli_marker.visible = True

            if transfer_body == moon:
                tli_label.text = f"TLI: {delta_v:.0f} m/s"
            else:
                tli_label.text = f"TEI: {delta_v:.0f} m/s"
            tli_label.visible = True


def update(dt):
    """
    Main physics integration loop (utilising RK4 mathematics).
    This routine is scheduled to execute repetitively (e.g. 100 times per second).
    'dt' (delta time) is the real time passed since the last tick in seconds.
    Adjust substeps in this function if the game feels 'floaty' or tunnelling (objects
    clipping through planets at high velocities) occurs. Be aware increased substeps
    reduces performance at high time-warp multipliers.
    """
    global time_mult_index, origin_x, origin_y

    if game_state == "MENU":
        main_menu.update(dt)
        return

    if time_mult_index == -1:
        return

    # Throttle control (E to increase, Q to decrease)
    # The multiplier (0.5) dictates throttle responsiveness.
    # Increase this scalar to allow players to throttle up/down much faster.
    if keys[pyglet.window.key.E]:
        rocket.thrust_level += 0.5 * dt
    if keys[pyglet.window.key.Q]:
        rocket.thrust_level -= 0.5 * dt

    if rocket.engaged:
        status_text.text = f"Engine Engaged: {rocket.thrust_level * 100:.0f}%"

    # Enforce safe temporal thresholds to prevent logic breaking.
    altitude = (
        rocket.distance_from_object(rocket.nearest_body.centre)
        - rocket.nearest_body.radius
    )
    if altitude <= ALTITUDE_THRESHOLDS[rocket.nearest_body] and time_mult_index > 2:
        time_mult_index = 0  # Revert immediately to 1x time warp when re-entering thick atmosphere (below 30km)
    if time_mult_index >= 3 and rocket.engaged:
        time_mult_index = (
            2  # Hard limit time warp to 3x whilst the main engine is actively burning
        )

    # Apply time warp and physics substepping.
    # Substepping divides a single visual frame into several smaller physics calculation ticks.
    # This radically improves simulation accuracy, preventing tunnelling and ensuring stable orbital behaviour.
    # Note: If adjusting the 1000 max substeps limit, you'll need to re-benchmark performance on low-end hardware.

    # Calculate how many steps to take based on the initial state of this frame
    max_substep_dt = 1
    initial_time_mult = time_mult_steps[time_mult_index]
    total_simulated_time = dt * initial_time_mult
    substeps = min(int(total_simulated_time / max_substep_dt) + 1, 1000)

    # The real-time chunk per substep is fixed
    real_dt = dt / substeps

    resultant_force_x = 0.0
    resultant_force_y = 0.0

    for _ in range(substeps):
        # Calculate angle dynamically relative to the exact mathematical bounds
        abs_rocket_x = window.width // 2 + rocket.displacement_x - origin_x
        abs_rocket_y = 283 + rocket.displacement_y - origin_y

        dx = abs_rocket_x - rocket.nearest_body.physics_x
        dy = abs_rocket_y - rocket.nearest_body.physics_y
        exact_distance = sqrt(dx**2 + dy**2)
        angle_from_centre = atan2(dy, dx)

        # Dynamically calculate the exact scalar to perfectly map to the 256 straight edges of Pyglet's polygon
        segment_angle = pi / 128  # 2 * pi / 256 segments
        alpha = (angle_from_centre % segment_angle) - (segment_angle / 2)
        polygon_radius_scalar = cos(segment_angle / 2) / cos(alpha)
        effective_radius = rocket.nearest_body.radius * polygon_radius_scalar

        altitude = exact_distance - effective_radius

        # Dynamically calculate THIS substep's simulated delta-time based on the current time warp
        current_time_mult = time_mult_steps[time_mult_index]
        sub_dt = real_dt * current_time_mult

        # Predictive threshold check: if we are above 30km, but our current speed * sub_dt would throw us below 30km,
        # drop the warp speed BEFORE we calculate the physics for this step.
        if altitude > ALTITUDE_THRESHOLDS[rocket.nearest_body] and time_mult_index > 2:
            # Compute radial velocity — positive means moving away, negative means falling toward body
            dx = rocket.x - rocket.nearest_body.x
            dy = rocket.y - rocket.nearest_body.y
            dist = sqrt(dx**2 + dy**2)
            radial_vel = (
                rocket.velocity_x * dx + rocket.velocity_y * dy
            ) / dist  # m/s toward/away

            # Only drop warp if we're actually approaching AND would breach the threshold this substep
            if (
                radial_vel < 0
                and altitude + radial_vel * sub_dt
                <= ALTITUDE_THRESHOLDS[rocket.nearest_body]
            ):
                time_mult_index = 0
                sub_dt = real_dt * time_mult_steps[time_mult_index]

        # Standard safety check if we are already inside the atmosphere boundaries
        # Automatically throttles warp to baseline to ensure responsive player controls during re-entry
        if altitude <= ALTITUDE_THRESHOLDS[rocket.nearest_body] and time_mult_index > 2:
            time_mult_index = 0
            sub_dt = real_dt * time_mult_steps[time_mult_index]

        # Ground collision logic overrides physics stepping when touching down or destroying the ship
        is_landed = False
        if altitude <= 0 and not getattr(rocket, "cheat_no_collisions", False):
            if rocket.speed >= rocket.max_impact_speed:
                # Fatal crash logic: hide visual components rather than destroying the object.
                rocket.visible = False
                rocket.thrust.visible = False
                trajectory_group.visible = False

                time_mult_index = (
                    -1 if time_mult_index != -1 else 0
                )  # Toggle between PAUSED and real-time
                time_mult_text.visible = (
                    time_mult_index != -1
                )  # Hide time warp text when paused

                break
            # Safe landing logic: manually kill velocity to prevent unwanted jitter near ground.

            body = rocket.nearest_body
            if body.is_orbiting:
                assert (
                    body.orbit_radius is not None
                ), "Orbiting bodies must have an orbit path defined."
                body_v_x = -body.orbit_radius * body.angular_velocity * sin(body.angle)
                body_v_y = body.orbit_radius * body.angular_velocity * cos(body.angle)
                rocket.velocity_x = body_v_x
                rocket.velocity_y = body_v_y
            else:
                rocket.velocity_x = 0
                rocket.velocity_y = 0

            rocket.angular_velocity = 0

            is_landed = True

            # Use displacement for exact math instead of visual x/y
            abs_x = window.width // 2 + rocket.displacement_x - origin_x
            abs_y = 283 + rocket.displacement_y - origin_y

            angle_from_centre = atan2(
                abs_y - rocket.nearest_body.y, abs_x - rocket.nearest_body.x
            )

            # Apply identical dynamic radius scalar here to fix rendering gap dynamically across entire shape
            segment_angle = pi / 128
            alpha = (angle_from_centre % segment_angle) - (segment_angle / 2)
            polygon_radius_scalar = cos(segment_angle / 2) / cos(alpha)
            effective_radius = rocket.nearest_body.radius * polygon_radius_scalar

            target_abs_x = rocket.nearest_body.x + effective_radius * cos(
                angle_from_centre
            )
            target_abs_y = rocket.nearest_body.y + effective_radius * sin(
                angle_from_centre
            )

            rocket.displacement_x += target_abs_x - abs_x
            rocket.displacement_y += target_abs_y - abs_y

            # Immediately sync visual coordinates so RK4 calculates gravity from the surface, not beneath it
            rocket.x = window.width // 2 + rocket.displacement_x - origin_x
            rocket.y = 283 + rocket.displacement_y - origin_y

        if rocket.fuel <= 0:
            rocket.engaged = False
            status_text.text = "Out of Fuel"

        # Cut parachute if deployed and too fast
        if rocket.parachute_deployed and rocket.speed > 250:
            rocket.cut_parachute()
            show_temporary_notice(
                "Parachute cut due to excessive speed!",
                color=WARN_COLOUR,
                duration=1.0,
                y=WARN_LOCATION,
            )

        torque = 0

        # Steering control: apply torque based on user input (LEFT and RIGHT arrow keys).
        # Hardcoded to only allow inputs whilst at safe time warp levels (< 3x).
        if altitude > 0 and time_mult_index <= 2:
            if keys[pyglet.window.key.LEFT]:
                torque = -(rocket.torque_strength * rocket.length)
            if keys[pyglet.window.key.RIGHT]:
                torque = rocket.torque_strength * rocket.length
            # Gimballed engines multiply available rotational torque. Modify this scalar to adjust gimbal strength.
            if rocket.engaged:
                torque *= 2

        # --- Physics Integration (RK4 Method) ---

        current_state = PhysicsState(
            velocity_x=rocket.velocity_x,
            velocity_y=rocket.velocity_y,
            angular_velocity=rocket.angular_velocity,
            displacement_x=rocket.displacement_x,
            displacement_y=rocket.displacement_y,
            rotation=rocket.rotation,
        )

        k1 = rocket.evaluate_derivative(current_state, 0, torque)

        # Use k1 for forces to get instantaneous acceleration for the arrows, rather than the more accurate but less intuitive k4 which is calculated at the end of the substep.
        resultant_force_x = k1.velocity_x * rocket.wet_mass
        resultant_force_y = k1.velocity_y * rocket.wet_mass

        # k2 = t + sub_dt / 2
        moon.angle += moon.angular_velocity * (sub_dt / 2)
        moon.physics_x = earth.physics_x + cos(moon.angle) * EARTH_MOON_DISTANCE
        moon.physics_y = earth.physics_y + sin(moon.angle) * EARTH_MOON_DISTANCE
        k2 = rocket.evaluate_derivative(current_state, sub_dt / 2, torque, k1)

        # k3 = t + sub_dt / 2 (Angle is already at sub_dt/2, so just evaluate)
        k3 = rocket.evaluate_derivative(current_state, sub_dt / 2, torque, k2)

        # k4 = t + sub_dt
        moon.angle += moon.angular_velocity * (sub_dt / 2)  # Add the remaining half
        moon.physics_x = earth.physics_x + cos(moon.angle) * EARTH_MOON_DISTANCE
        moon.physics_y = earth.physics_y + sin(moon.angle) * EARTH_MOON_DISTANCE
        k4 = rocket.evaluate_derivative(current_state, sub_dt, torque, k3)

        # 4. Calculate proposed state changes (v = u + at)
        # Uses explicit Runge-Kutta weights (1/6, 1/3, 1/3, 1/6) on the computed k-derivates
        dv_x = (
            (1.0 / 6.0)
            * (k1.velocity_x + 2 * k2.velocity_x + 2 * k3.velocity_x + k4.velocity_x)
            * sub_dt
        )
        dv_y = (
            (1.0 / 6.0)
            * (k1.velocity_y + 2 * k2.velocity_y + 2 * k3.velocity_y + k4.velocity_y)
            * sub_dt
        )
        dp_x = (
            (1.0 / 6.0)
            * (
                k1.displacement_x
                + 2 * k2.displacement_x
                + 2 * k3.displacement_x
                + k4.displacement_x
            )
            * sub_dt
        )
        dp_y = (
            (1.0 / 6.0)
            * (
                k1.displacement_y
                + 2 * k2.displacement_y
                + 2 * k3.displacement_y
                + k4.displacement_y
            )
            * sub_dt
        )
        da_v = (
            (1.0 / 6.0)
            * (
                k1.angular_velocity
                + 2 * k2.angular_velocity
                + 2 * k3.angular_velocity
                + k4.angular_velocity
            )
            * sub_dt
        )
        d_rot = degrees(
            (1.0 / 6.0)
            * (k1.rotation + 2 * k2.rotation + 2 * k3.rotation + k4.rotation)
            * sub_dt
        )

        # Normal Force Calculation: If landed, we evaluate if gravity is trying to pull us downward
        if is_landed:
            angle_from_centre = atan2(
                rocket.y - rocket.nearest_body.y, rocket.x - rocket.nearest_body.x
            )
            normal_x, normal_y = cos(angle_from_centre), sin(angle_from_centre)

            # Dot product evaluates if the resulting velocity vector is pushing AWAY from the planet (>0)
            if (dv_x * normal_x + dv_y * normal_y) <= 0:
                # Gravity is winning; cancel all position and velocity updates perfectly
                dv_x, dv_y = 0, 0
                dp_x = rocket.velocity_x * sub_dt
                dp_y = rocket.velocity_y * sub_dt
                da_v, d_rot = 0, 0

                resultant_force_x = 0
                resultant_force_y = 0

                # Instantly kill any residual rotational energy
                rocket.angular_velocity = 0
                # 90 degrees offset converts the Pyglet rotational plane to mathematical radians facing UP
                rocket.rotation = 90 - degrees(angle_from_centre)

        # Apply final properties
        rocket.velocity_x += dv_x
        rocket.velocity_y += dv_y
        rocket.displacement_x += dp_x
        rocket.displacement_y += dp_y
        rocket.angular_velocity += da_v
        rocket.rotation += d_rot

        # Apply artificial dampening to rotational speed to mimic gyroscopic reaction wheels,
        # otherwise spacecraft rotation never naturally halts. Change 0.99 to alter control tightness.
        rocket.angular_velocity *= 0.99

        # Floating Origin system to handle 32/64-bit coordinate space floating point drift / precision loss.
        # Repositions the entire 'Universe' back towards [0,0] when zooming far out rather than shifting the ship continuously.
        if (
            abs(rocket.displacement_x - origin_x) > FLOATING_ORIGIN_THRESHOLD
            or abs(rocket.displacement_y - origin_y) > FLOATING_ORIGIN_THRESHOLD
        ):
            shift_x = rocket.displacement_x - origin_x
            shift_y = rocket.displacement_y - origin_y

            origin_x += shift_x
            origin_y += shift_y

            earth.shift(-shift_x, -shift_y)
            earth.physics_x -= shift_x
            earth.physics_y -= shift_y

            moon.shift(-shift_x, -shift_y)
            moon.physics_x -= shift_x
            moon.physics_y -= shift_y

            for line in trajectory_lines:
                line.x -= shift_x
                line.y -= shift_y
                line.x2 -= shift_x
                line.y2 -= shift_y

            apoapsis_marker.x -= shift_x
            apoapsis_marker.y -= shift_y
            tli_marker.x -= shift_x
            tli_marker.y -= shift_y

        # Update visual position
        rocket.x = window.width // 2 + rocket.displacement_x - origin_x
        rocket.y = 283 + rocket.displacement_y - origin_y

        rocket.calculate_fuel(sub_dt)
        rocket.update_temperature(current_state, altitude, sub_dt)

        if rocket.temperature > rocket.max_safe_temperature and not getattr(
            rocket, "cheat_no_heat", False
        ):
            rocket.visible = False
            rocket.thrust.visible = False
            trajectory_group.visible = False
            time_mult_index = -1 if time_mult_index != -1 else 0
            time_mult_text.visible = time_mult_index != -1
            show_temporary_notice(
                "Rocket burned up on re-entry!",
                color=ERROR_COLOUR,
                duration=5.0,
                y=ACHIEVEMENT_LOCATION,
            )
            break

    set_arrows(
        rocket,
        resultant_force_x,
        resultant_force_y,
    )

    # Calculate exact lunar displacement this frame
    moon_dx = moon.physics_x - moon.x
    moon_dy = moon.physics_y - moon.y

    # Slide the orbit projections to perfectly glue them to the moving Moon between trajectory ticks
    if rocket.dominant_body == moon and time_mult_index != -1:
        for line in trajectory_lines:
            if not line.visible:
                continue
            line.x += moon_dx
            line.y += moon_dy
            line.x2 += moon_dx
            line.y2 += moon_dy

        if apoapsis_marker.visible:
            apoapsis_marker.x += moon_dx
            apoapsis_marker.y += moon_dy
        if tli_marker.visible:
            tli_marker.x += moon_dx
            tli_marker.y += moon_dy

    # Apply visual Pyglet geometry shift
    moon.shift(moon_dx, moon_dy)


keys = pyglet.window.key.KeyStateHandler()
window.push_handlers(keys)
# Schedule update to run 100 times per second
# Adjust the second argument (0.01) to increase or decrease the frequency of physics updates.
pyglet.clock.schedule_interval(update, 0.01)

# Schedule the trajectory projection rendering to run 5 times per second
pyglet.clock.schedule_interval(update_trajectory, 0.2)

# Only call pyglet.app.run() if this script is executed directly. This allows for modular imports without side effects.
if __name__ == "__main__":
    pyglet.app.run()
