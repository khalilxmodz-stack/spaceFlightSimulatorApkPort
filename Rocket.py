import json
from dataclasses import dataclass
from math import cos, exp, radians, sin, sqrt, atan2, pi, acos

import pyglet

from Body import Body

constants = json.load(open("constants.json"))
G = constants["G"]


@dataclass
class PhysicsState:
    velocity_x: float = 0.0  # m/s
    velocity_y: float = 0.0  # m/s
    angular_velocity: float = 0.0  # rad/s
    displacement_x: float = 0.0  # m
    displacement_y: float = 0.0  # m
    rotation: float = 0.0  # degrees


@dataclass
class Stage:
    dry_mass: float  # kg
    fuel_mass: float  # kg
    engine_thrust: float  # N
    engine_efficiency: float  # ISP in seconds
    length: float = 10.0  # m, default length for moment of inertia calculations
    cross_sectional_area: float = 20.0  # m^2, default for drag calculations
    color: tuple[int, int, int] = (200, 50, 50)  # Default color


# ==========================================
# ROCKET PHYSICAL DEFINITION & SIMULATION
# ==========================================
class Rocket(pyglet.shapes.Triangle):
    """
    Subclasses Pyglet's Triangle class to blend rendering rendering with internal physics.
    Responsible for orbital force projections, aerodynamic drag, engine handling, and mass properties.
    """

    def __init__(
        self,
        bodies: list[Body],
    ):
        if not bodies:
            raise ValueError(
                "Rocket must be initialised with at least one celestial body for gravity calculations."
            )

        # Base sprite initialisation
        # Modify the relative triangle vertices entirely to change the spacecraft's underlying collider and visual size
        super().__init__(
            0,
            0,
            100,
            0,
            50,
            100,
            color=(200, 50, 50),
        )
        # Shift pivot point of rotations for aerodynamic torque steering.
        self.anchor_x = 50
        self.anchor_y = 0

        # Define engine plume visual parameters
        # Adjust 'y' to make thrust trail artificially wider or shorter
        self.thrust = pyglet.shapes.Triangle(
            0,
            0,
            40,
            0,
            20,
            -50,
            color=(255, 100, 100),
        )
        self.thrust.anchor_x = 20
        self.thrust.anchor_y = 0

        # ==========================================
        # PHYSICS STATE TRACKING
        # ==========================================
        # Dynamic property vectors managed strictly by RK4 integration steps in Game.py
        # Adjust these ONLY for teleporation/debugging or specific setup scenarios (e.g., spawning on a moon)
        self.velocity_x = 0.0  # (m/s) Real space vector movement
        self.velocity_y = 0.0  # (m/s) Real space vector movement
        self.angular_velocity = 0.0  # (rad/s) Rate of spin
        self.displacement_x = (
            0.0  # (m) Delta offset tracking for floating origin shifts
        )
        self.displacement_y = (
            0.0  # (m) Delta offset tracking for floating origin shifts
        )
        self.rotation = 0  # Absolute angle (degrees)
        self.engaged = False  # Track engine firing state

        self._bodies = bodies

        self._stages = [
            Stage(
                dry_mass=37.2 * 1000,
                fuel_mass=153 * 1000,
                engine_thrust=3 * 120 * 9.81 * 1000,
                engine_efficiency=240,
                length=28.5,
                cross_sectional_area=3 * pi,
                color=(200, 50, 30),  # Red
            ),
            Stage(
                dry_mass=7.3 * 1000,
                fuel_mass=9 * 1000,
                engine_thrust=15 * 9.81 * 1000,
                engine_efficiency=260,
                length=6.5,
                cross_sectional_area=pi,
                color=(255, 120, 0),  # Orange
            ),
            Stage(
                dry_mass=4.4 * 1000,
                fuel_mass=0,
                engine_thrust=0,
                engine_efficiency=0,
                length=2.5,
                cross_sectional_area=pi,
                color=(255, 230, 50),  # Yellow
            ),
        ]

        self.color = self._stages[0].color

        # ==========================================
        # SPACECRAFT DESIGN METRICS
        # ==========================================
        # Hard limits and operational characteristics for the spacecraft.
        # Major game-feel changes should occur here (e.g. fuel mass ratio, torque logic)
        self._length = self._stages[
            0
        ].length  # Chassis metric (meters), scales moment of inertia natively
        self._dry_mass = self._stages[
            0
        ].dry_mass  # Chassis hull mass in kg (affects TWR significantly)
        self._torque_strength = (
            50000  # Raw rotational input strength (N m). Adjust for twitchier controls.
        )
        self._engine_efficiency = self._stages[
            0
        ].engine_efficiency  # ISP. Higher value = lower fuel consumption rate.
        self._engine_thrust = self._stages[
            0
        ].engine_thrust  # Max thrust (N). Base multiplier calculates actual acceleration.
        self._thrust_level = 1.0  # Engine throttle percentage (0.0 - 1.0)
        self._drag_coefficient = 1.2  # Atmospheric resistance mapping coefficient. Decrease to fall through air faster.
        self._cross_sectional_area = self._stages[
            0
        ].cross_sectional_area  # Aerodynamic footprint (m^2) influencing thick atmosphere deceleration
        self._initial_fuel = self._stages[
            0
        ].fuel_mass  # Total starting fuel mass pool (kg). Scales wet_mass on launch.
        self._fuel = self._initial_fuel
        self._max_impact_speed = 15  # Crash threshold velocity (m/s). Raise to make landings much more forgiving.
        self._parachute_deployed = (
            False  # Track parachute state for visual and physics adjustments
        )
        self.temperature = 300.0  # Kelvin (ambient baseline)
        self.max_safe_temperature = 2000.0  # Kelvin (structural failure point)
        self.heat_capacity = 25000.0  # J/K

    # ==========================================
    # PROPERTIES & COMPUTED STATE
    # ==========================================
    # Exposing internal physics properties securely to prevent external clobbering while reading.
    @property
    def length(self):
        return self._length

    @property
    def max_impact_speed(self):
        return self._max_impact_speed

    # Calculates continuous kinetic velocity via Pythagorean theorem.
    @property
    def speed(self):
        body = self.dominant_body
        if body.is_orbiting:
            # Calculate the nearest body's instantaneous velocity
            assert body.orbit_radius is not None
            r = body.orbit_radius
            w = body.angular_velocity
            angle = body.angle

            body_v_x = -r * w * sin(angle)
            body_v_y = r * w * cos(angle)

            rel_v_x = self.velocity_x - body_v_x
            rel_v_y = self.velocity_y - body_v_y

            return sqrt(rel_v_x**2 + rel_v_y**2)  # m/s

        return sqrt(self.velocity_x**2 + self.velocity_y**2)  # m/s

    @property
    def fuel(self):
        return self._fuel

    # Wet mass = dry mass + fuel mass which changes during flight as fuel is consumed, so it's a dynamic property
    @property
    def wet_mass(self):
        return self._dry_mass + self._fuel  # kg

    @property
    def thrust_level(self):
        return self._thrust_level

    @property
    def moment_of_inertia(self):
        return 1 / 12 * self._length**2 * self.wet_mass  # kg m^2

    @property
    def torque_strength(self):
        # Dynamically scale torque with mass to prevent the last payload from spinning out of control
        # Increased base multiplier to make the first stage significantly easier to turn
        base_torque = 150000 * (self.wet_mass / 190000.0)
        return max(15000, base_torque)  # N m

    @property
    def fuel_percentage(self):
        if self._initial_fuel == 0:
            return 0
        return round(self._fuel / self._initial_fuel * 100)

    @property
    def nearest_body(self):
        nearest = None
        min_distance = float("inf")
        for body in self._bodies:
            distance = self.distance_from_object((body.x, body.y))
            if distance < min_distance:
                min_distance = distance
                nearest = body
        assert nearest is not None
        return nearest

    @property
    def dominant_body(self):
        # Use the body.soi_radius property
        for body in self._bodies:
            if not body.soi_radius:
                continue
            soi = body.soi_radius
            dist = sqrt((self.x - body.x) ** 2 + (self.y - body.y) ** 2)
            if dist < soi:
                return body
        return max(self._bodies, key=lambda b: b.mass)

    @property
    def parachute_deployed(self):
        return self._parachute_deployed

    # Throttle setter with clamping to ensure values remain within the valid range of 0.0 to 1.0.
    @thrust_level.setter
    def thrust_level(self, value: float):
        if self._engine_thrust != 0:
            self._thrust_level = max(0.0, min(1.0, value))
            # Update mass flow rate based on the new thrust level and engine efficiency.
            self._mass_flow_rate = (
                self._engine_thrust
                * self._thrust_level
                / (self._engine_efficiency * 9.81)
            )

    def get_state_speed(self, state: PhysicsState):
        return sqrt(state.velocity_x**2 + state.velocity_y**2)

    # Utility method to calculate the distance from the rocket to a given object's centre, used for gravity and collision calculations.
    def distance_from_object(self, object_centre: tuple[float, float]):
        distance_vector_x = self.x - object_centre[0]
        distance_vector_y = self.y - object_centre[1]
        distance_magnitude = sqrt(distance_vector_x**2 + distance_vector_y**2)
        return distance_magnitude

    def draw(self):
        super().draw()
        if self.engaged and self._fuel > 0 and self.thrust_level > 0:
            self.thrust.x = self.x
            self.thrust.y = self.y
            self.thrust.rotation = self.rotation
            self.thrust.draw()

    # ==========================================
    # PHYSICS SIMULATION METHODS (RK4 Engine)
    # ==========================================
    # These functions calculate the continuous derivative changes in state for movement forecasting.
    # Altering these directly changes exactly how forces map to vector movement.

    def calculate_thrust(self, state: PhysicsState):
        """
        Derives x/y engine output based on current absolute orientation.
        """
        if self.engaged and self._fuel > 0:
            thrust_y = (
                self._engine_thrust * cos(radians(state.rotation)) * self._thrust_level
            )
            thrust_x = (
                self._engine_thrust * sin(radians(state.rotation)) * self._thrust_level
            )
        else:
            thrust_y = 0
            thrust_x = 0

        return thrust_x, thrust_y

    def calculate_drag(self, state: PhysicsState, distance_from_surface: int | float):
        if getattr(self, "cheat_no_drag", False):
            return 0.0, 0.0, 0.0

        if self.get_state_speed(state) == 0 and state.angular_velocity == 0:
            return 0.0, 0.0, 0.0

        if not self.nearest_body.has_atmosphere:
            return 0.0, 0.0, 0.0

        # Terminate drag coefficient processing outside the thick atmosphere (> 30km)
        # to save CPU cycles, as air density is negligible in a vacuum.
        if distance_from_surface > self.nearest_body.atmosphere_thickness:
            return 0.0, 0.0, 0.0

        # Calculates atmospheric density logarithmically.
        # Scales dynamically with the atmosphere thickness bounds relative to the 30km baseline
        scale_height = 4000 * (self.nearest_body.atmosphere_thickness / 30000)
        air_density = 1.225 * exp(
            -distance_from_surface / scale_height
        )  # Measured in kg/m^3

        heading_x = sin(radians(self.rotation))
        heading_y = cos(radians(self.rotation))

        cos_aoa = abs(
            (state.velocity_x * heading_x + state.velocity_y * heading_y)
            / self.get_state_speed(state)
        )
        sin_aoa = sqrt(1 - cos_aoa**2)

        effective_area = (self._cross_sectional_area * cos_aoa) + (
            self._length * 8 * sin_aoa
        )

        drag_magnitude = (
            0.5
            * air_density
            * self.get_state_speed(state) ** 2
            * self._drag_coefficient
            * effective_area
        )  # Measured in Newtons (N)

        # Custom drag integration: dynamically scales rotational resistance based on geometric inertia.
        damping_strength = self.moment_of_inertia * 0.5 / 1.225 * 3

        # Drag dynamically opposes the component velocity vectors.
        # Normalise vectors (v_x/v_mag, v_y/v_mag) and multiply by magnitude.
        # A negative scalar is applied because drag always opposes the current direction of travel.
        if self.get_state_speed(state) == 0:
            drag_x = 0
            drag_y = 0
        else:
            drag_x = -drag_magnitude * (state.velocity_x / self.get_state_speed(state))
            drag_y = -drag_magnitude * (state.velocity_y / self.get_state_speed(state))
        rotational_drag = (
            -damping_strength * state.angular_velocity * air_density
        )  # Measured in Newton-metres (N m)

        return drag_x, drag_y, rotational_drag

    def calculate_weight(self, absolute_pos: tuple[float, float]):
        # Calculates reactive ground-force negation.
        # If landed on the planet, gravity is functionally cancelled out by ground reaction force.
        if not getattr(self, "cheat_no_collisions", False):
            for body in self._bodies:
                distance_vector_x = absolute_pos[0] - body.physics_x
                distance_vector_y = absolute_pos[1] - body.physics_y
                distance_magnitude = sqrt(distance_vector_x**2 + distance_vector_y**2)
                distance_from_surface = distance_magnitude - body.radius
                if distance_from_surface <= 0:
                    return 0.0, 0.0

        net_g_x = 0.0
        net_g_y = 0.0

        for body in self._bodies:
            distance_vector_x = absolute_pos[0] - body.physics_x
            distance_vector_y = absolute_pos[1] - body.physics_y
            distance_magnitude = sqrt(distance_vector_x**2 + distance_vector_y**2)

            if distance_magnitude == 0:
                continue  # Avoid division by zero if the rocket is exactly at the body's center

            g_magnitude = G * body.mass / distance_magnitude**2
            g_x = -g_magnitude * (distance_vector_x / distance_magnitude)
            g_y = -g_magnitude * (distance_vector_y / distance_magnitude)

            net_g_x += g_x
            net_g_y += g_y

        # Define weight as mass * net gravitational acceleration in each axis
        weight_x = self.wet_mass * net_g_x
        weight_y = self.wet_mass * net_g_y

        return weight_x, weight_y

    def update_temperature(self, state: PhysicsState, altitude: float, dt: float):
        ambient = 300.0

        # Space is cold, radiate down to ambient
        if (
            not self.nearest_body.has_atmosphere
            or altitude > self.nearest_body.atmosphere_thickness
        ):
            air_density = 0.0
        else:
            scale_height = 4000 * (self.nearest_body.atmosphere_thickness / 30000)
            air_density = 1.225 * exp(-altitude / scale_height)

        speed = self.get_state_speed(state)

        # Heating: C * rho * V^3
        # Tune this constant to ensure current simulated orbital velocity generates a reasonable amount of heat.
        c_heat = 0.175
        heating_rate = c_heat * air_density * (speed**3)

        # Cooling: Stefan-Boltzmann (epsilon * sigma * A * T^4)
        c_cool = 2e-6
        cooling_rate = c_cool * ((self.temperature**4) - (ambient**4))

        net_heat = heating_rate - cooling_rate

        self.temperature += (net_heat / self.heat_capacity) * dt

        if self.temperature < ambient:
            self.temperature = ambient

        # Dynamic visual heating glow
        glow_factor = max(
            0.0,
            min(1.0, (self.temperature - 600.0) / (self.max_safe_temperature - 600.0)),
        )

        # Base color of the current hull
        base_color = self._stages[0].color
        if self._parachute_deployed:
            base_color = (
                150,
                150,
                255,
            )

        # Shift towards bright glowing red/orange
        self.color = (
            int(base_color[0] * (1 - glow_factor) + 255 * glow_factor),
            min(255, int(base_color[1] * (1 - glow_factor) + 100 * glow_factor)),
            int(base_color[2] * (1 - glow_factor) + 0 * glow_factor),
        )

    def calculate_fuel(self, dt: float):
        if (
            not self.engaged
            or self._fuel <= 0
            or getattr(self, "cheat_infinite_fuel", False)
        ):
            return

        mass_flow_rate = (
            self._engine_thrust * self._thrust_level / (self._engine_efficiency * 9.81)
        )  # kg/s
        self._fuel = max(0, self._fuel - mass_flow_rate * dt)

    def deploy_parachute(self):
        if self._parachute_deployed is not None:
            self.color = (
                150,
                150,
                255,
            )  # Visual change to indicate parachute deployment
            self._cross_sectional_area = 800
            self._drag_coefficient = 2.2
            self._parachute_deployed = True

    def cut_parachute(self):
        # cut parachute diff colour
        self.color = self._stages[0].color
        self._cross_sectional_area = 20
        self._drag_coefficient = 1.2
        self._parachute_deployed = None

    def jettison_stage(self) -> bool:
        if len(self._stages) <= 1:
            return False  # No more stages to jettison

        # Remove the current stage and update properties to the next stage
        self._stages.pop(0)
        next_stage = self._stages[0]

        self._length = next_stage.length
        self._dry_mass = next_stage.dry_mass
        self._engine_efficiency = next_stage.engine_efficiency
        self._engine_thrust = next_stage.engine_thrust
        self._cross_sectional_area = next_stage.cross_sectional_area
        self._initial_fuel = next_stage.fuel_mass
        self._fuel = next_stage.fuel_mass

        # Don't override parachute deployment colours with staging colours
        if not self._parachute_deployed:
            self.color = next_stage.color

        return True

    def evaluate_derivative(
        self,
        initial_state: PhysicsState,
        dt: float,
        torque: float,
        previous_derivative: PhysicsState | None = None,
    ) -> PhysicsState:
        """
        Primary physics integrator determining forces applied based on position and conditions.
        If editing aerodynamic drag or scaling engine thrust directly within the codebase,
        track these sub-methods carefully; altering 'PhysicsState' logic here will destabilise
        overall simulation behaviour significantly.
        """
        # If this is the initial timestep (k1), simply use the provided state with a 0 dt vector skip.
        if not previous_derivative:
            previous_derivative = PhysicsState()
        state = PhysicsState(
            velocity_x=initial_state.velocity_x + previous_derivative.velocity_x * dt,
            velocity_y=initial_state.velocity_y + previous_derivative.velocity_y * dt,
            angular_velocity=initial_state.angular_velocity
            + previous_derivative.angular_velocity * dt,
            displacement_x=initial_state.displacement_x
            + previous_derivative.displacement_x * dt,
            displacement_y=initial_state.displacement_y
            + previous_derivative.displacement_y * dt,
            rotation=initial_state.rotation + previous_derivative.rotation * dt,
        )

        absolute_pos = (
            self.x + state.displacement_x - self.displacement_x,
            self.y + state.displacement_y - self.displacement_y,
        )
        altitude = (
            sqrt(
                (absolute_pos[0] - self.nearest_body.physics_x) ** 2
                + (absolute_pos[1] - self.nearest_body.physics_y) ** 2
            )
            - self.nearest_body.radius
        )

        thrust_x, thrust_y = self.calculate_thrust(state)
        # Returns [x_Force, y_Force, angular_N_m]
        # Edit calculate_drag() directly to tune atmospheric reentry profiles.
        drag_x, drag_y, rotational_drag = self.calculate_drag(state, altitude)
        weight_x, weight_y = self.calculate_weight(absolute_pos)

        # Summate force vectors (N)
        resultant_force_x = thrust_x + drag_x + weight_x
        resultant_force_y = thrust_y + drag_y + weight_y
        resultant_rotational_force = torque + rotational_drag

        # Resolves to raw acceleration metrics (a = F/m / alpha = T/I)
        acceleration_x = resultant_force_x / self.wet_mass
        acceleration_y = resultant_force_y / self.wet_mass
        angular_acceleration = resultant_rotational_force / self.moment_of_inertia

        return PhysicsState(
            velocity_x=acceleration_x,
            velocity_y=acceleration_y,
            angular_velocity=angular_acceleration,
            displacement_x=state.velocity_x,
            displacement_y=state.velocity_y,
            rotation=state.angular_velocity,
        )

    # ==========================================
    # ON-THE-FLY KEPLERIAN ORBIT PROJECTION
    # ==========================================
    def calculate_trajectory(
        self,
        transfer_body: Body,
        transfer_distance: float,
        num_points: int = 1500,
    ) -> (
        tuple[
            list[tuple[float, float]], tuple[float, float], tuple[float, float], float
        ]
        | None
    ):
        """
        Derives an unpowered Keplerian (classic two-body) orbit around the current dominant celestial object.
        Returns coordinate projection arrays for the HUD.
        Param `num_points` limits projection resolution; lowering this will improve FPS heavily at a cost to line smoothness.
        Param `transfer_distance` triggers TLI (Trans Lunar Injection) calculations if mapping towards the transfer body.
        """
        primary = self.dominant_body
        points = [(self.x, self.y)]

        sim_x, sim_y = self.x, self.y
        sim_vx, sim_vy = self.velocity_x, self.velocity_y

        # Relative state vectors
        r_x = self.x - primary.x
        r_y = self.y - primary.y
        r = sqrt(r_x**2 + r_y**2)

        if primary.is_orbiting:
            assert primary.orbit_radius is not None
            p_v_x = (
                -primary.orbit_radius * primary.angular_velocity * sin(primary.angle)
            )
            p_v_y = primary.orbit_radius * primary.angular_velocity * cos(primary.angle)
        else:
            p_v_x = 0
            p_v_y = 0

        # Determine the total delta relative vector mathematically combining rotation offsets
        rel_v_x = sim_vx - p_v_x
        rel_v_y = sim_vy - p_v_y

        v = sqrt(rel_v_x**2 + rel_v_y**2)
        mu = G * primary.mass
        # Energy identifies orbit shape: E < 0 defines bound orbits (Circle/Ellipse/Crash)
        # E >= 0 implies escape trajectories (Hyperbola/Parabola escaping SOI)
        energy = v**2 / 2 - mu / r

        delta_v = -1  # Default marker fallback, no transfer injection window identified
        tli_x, tli_y = self.x, self.y
        apoapsis = (sim_x, sim_y)

        # 1. KEPLERIAN PROJECTION (Elliptical / Circular Orbits)
        if energy < 0:
            a = -mu / (2 * energy)
            rdotv = r_x * rel_v_x + r_y * rel_v_y

            ex = (1 / mu) * ((v**2 - mu / r) * r_x - rdotv * rel_v_x)
            ey = (1 / mu) * ((v**2 - mu / r) * r_y - rdotv * rel_v_y)
            e = sqrt(ex**2 + ey**2)

            if 0 <= e < 1:
                r_peri = a * (1 - e)
                periapsis_angle = atan2(ey, ex)

                # Find the current true anomaly of the rocket to sweep smoothly from there
                current_angle = atan2(r_y, r_x)
                current_true_anomaly = current_angle - periapsis_angle

                # --- Injection Marker Calculation ---
                if r_peri >= primary.radius:

                    if transfer_body.is_orbiting:
                        # TLI logic: intercepting an orbiting body
                        a_transfer = (r_peri + transfer_distance) / 2
                        tof = pi * sqrt(a_transfer**3 / mu)

                        transfer_travel_angle = transfer_body.angular_velocity * tof
                        transfer_current_angle = atan2(
                            transfer_body.y - primary.y, transfer_body.x - primary.x
                        )
                        future_transfer_angle = (
                            transfer_current_angle + transfer_travel_angle
                        )
                        tli_angle = future_transfer_angle + pi

                        true_anomaly_tli = tli_angle - periapsis_angle
                        r_tli = a * (1 - e**2) / (1 + e * cos(true_anomaly_tli))

                        tli_x = primary.x + r_tli * cos(tli_angle)
                        tli_y = primary.y + r_tli * sin(tli_angle)

                        if 2 / r_tli - 1 / a > 0 and 2 / r_tli - 1 / a_transfer > 0:
                            v_tli_current = sqrt(mu * (2 / r_tli - 1 / a))
                            v_transfer_required = sqrt(
                                mu * (2 / r_tli - 1 / a_transfer)
                            )
                            delta_v = v_transfer_required - v_tli_current

                    else:
                        # TEI logic: returning to the stationary central body
                        # Get the distance between the bodies regardless of which one is orbiting
                        distance_between_bodies = sqrt(
                            (primary.x - transfer_body.x) ** 2
                            + (primary.y - transfer_body.y) ** 2
                        )

                        # 1. Target an atmospheric skim (20km altitude) instead of a vertical drop
                        # This creates an elliptical return trajectory for aerobraking
                        r_target_apogee = distance_between_bodies

                        # Target's radius + 20,000 meters altitude
                        r_target_periapsis = transfer_body.radius + 20000

                        a_target_transfer = (r_target_apogee + r_target_periapsis) / 2
                        mu_target = G * transfer_body.mass

                        # 2. Velocity required at apogee of the Target transfer
                        # Now that we aren't dropping to 0, we retain horizontal speed to orbit!
                        v_target_apogee = sqrt(
                            mu_target * (2 / r_target_apogee - 1 / a_target_transfer)
                        )

                        # 3. The primary body's current orbital velocity
                        v_primary_orbit = (
                            distance_between_bodies * primary.angular_velocity
                            if primary.is_orbiting
                            else 0
                        )

                        # 4. Desired retrograde escape velocity relative to the primary body
                        v_infinity = v_primary_orbit - v_target_apogee

                        # 5. Calculate ideal escape periapsis angle to guarantee the hyperbola
                        # points precisely backwards against the primary body's prograde velocity.
                        e_esc = 1 + (r_peri * v_infinity**2) / mu

                        # The angle of the escape asymptote relative to periapsis
                        cos_val = max(-1.0, min(1.0, -1 / e_esc))
                        theta_inf = acos(cos_val)

                        # Determine direction of current orbit to bend the asymptote appropriately
                        h_z = r_x * sim_vy - r_y * rel_v_x
                        direction = 1 if h_z >= 0 else -1

                        # Primary body moves at primary.angle + pi/2. Retrograde to Primary is primary.angle - pi/2.
                        target_asymptote = primary.angle - pi / 2

                        # Place the marker exactly where periapsis needs to be to yield this asymptote.
                        tli_angle = target_asymptote - direction * theta_inf

                        true_anomaly_tli = tli_angle - periapsis_angle
                        r_tli = a * (1 - e**2) / (1 + e * cos(true_anomaly_tli))

                        tli_x = primary.x + r_tli * cos(tli_angle)
                        tli_y = primary.y + r_tli * sin(tli_angle)

                        # Delta V to achieve this hyperbolic escape velocity
                        if 2 / r_tli - 1 / a > 0:
                            v_tli_current = sqrt(mu * (2 / r_tli - 1 / a))
                            v_transfer_required = sqrt(v_infinity**2 + 2 * mu / r_tli)
                            delta_v = v_transfer_required - v_tli_current

                # --- Keplerian Ellipse Drawing ---
                # Calculate True Apoapsis directly in world space
                apoapsis_angle = periapsis_angle + pi
                r_apo = a * (1 + e)
                apoapsis = (
                    primary.x + r_apo * cos(apoapsis_angle),
                    primary.y + r_apo * sin(apoapsis_angle),
                )

                # Determine direction of orbit (prograde vs retrograde)
                # using the 2D cross product of position and velocity
                h_z = r_x * sim_vy - r_y * rel_v_x
                direction = 1 if h_z >= 0 else -1

                points.clear()

                # Sweep true anomalies to draw the path
                # (+1 ensures the final drawn segment perfectly closes the gap)
                resolution = num_points // 2
                if r_peri >= primary.radius:
                    # Safe orbit: calculate a full unbroken 360-degree circle
                    for i in range(resolution + 1):
                        angle = current_true_anomaly + direction * (
                            i * (2 * pi / resolution)
                        )
                        r_angle = a * (1 - e**2) / (1 + e * cos(angle))

                        # Convert to Absolute world space
                        abs_angle = periapsis_angle + angle
                        px = primary.x + r_angle * cos(abs_angle)
                        py = primary.y + r_angle * sin(abs_angle)

                        points.append((px, py))
                else:
                    # Crashing suborbital orbit: Sweep backwards to ascent point, then forward to descent point
                    backward_points = []

                    # Dynamically calculate the step size based on the exact angular span above the ground
                    if e > 0.0001:
                        cos_theta = (a * (1 - e**2) / primary.radius - 1) / e
                        # Clamp to avoid math domain errors due to floating point inaccuracies
                        cos_theta = max(-1.0, min(1.0, cos_theta))
                        theta_surface = abs(acos(cos_theta))

                        # Total valid angular span where the orbit is above the surface
                        angular_span = 2 * (pi - theta_surface)
                        step_size = angular_span / resolution
                    else:
                        step_size = 2 * pi / resolution

                    # Prevent the step size from becoming too tiny and freezing the game
                    step_size = max(step_size, 1e-6)

                    # 1. Trace backwards towards the launch/ascent ground level
                    prev_angle = current_true_anomaly
                    prev_r_angle = r
                    for i in range(1, resolution + 1):
                        angle = current_true_anomaly - direction * (i * step_size)
                        r_angle = a * (1 - e**2) / (1 + e * cos(angle))

                        if r_angle <= primary.radius:
                            # Interpolate exact surface intersection to stop clipping
                            fraction = (
                                (prev_r_angle - primary.radius)
                                / (prev_r_angle - r_angle)
                                if prev_r_angle != r_angle
                                else 1
                            )
                            exact_angle = prev_angle + fraction * (angle - prev_angle)

                            abs_angle = periapsis_angle + exact_angle
                            px = primary.x + primary.radius * cos(abs_angle)
                            py = primary.y + primary.radius * sin(abs_angle)
                            backward_points.append((px, py))
                            break

                        abs_angle = periapsis_angle + angle
                        backward_points.append(
                            (
                                primary.x + r_angle * cos(abs_angle),
                                primary.y + r_angle * sin(abs_angle),
                            )
                        )
                        prev_angle = angle
                        prev_r_angle = r_angle

                    backward_points.reverse()

                    forward_points = []
                    # 2. Trace forwards towards the crash/descent ground level
                    prev_angle = current_true_anomaly
                    prev_r_angle = r
                    for i in range(1, resolution + 1):
                        angle = current_true_anomaly + direction * (i * step_size)
                        r_angle = a * (1 - e**2) / (1 + e * cos(angle))

                        if r_angle <= primary.radius:
                            # Interpolate exact surface intersection to stop clipping
                            fraction = (
                                (prev_r_angle - primary.radius)
                                / (prev_r_angle - r_angle)
                                if prev_r_angle != r_angle
                                else 1
                            )
                            exact_angle = prev_angle + fraction * (angle - prev_angle)

                            abs_angle = periapsis_angle + exact_angle
                            px = primary.x + primary.radius * cos(abs_angle)
                            py = primary.y + primary.radius * sin(abs_angle)
                            forward_points.append((px, py))
                            break

                        abs_angle = periapsis_angle + angle
                        forward_points.append(
                            (
                                primary.x + r_angle * cos(abs_angle),
                                primary.y + r_angle * sin(abs_angle),
                            )
                        )
                        prev_angle = angle
                        prev_r_angle = r_angle

                    # Assemble the final trajectory as one perfectly contiguous line
                    points.clear()
                    points.extend(backward_points)
                    points.append((sim_x, sim_y))
                    points.extend(forward_points)

        # 2. STEPPING PROJECTION (Hyperbolic / N-Body Fallback)
        else:
            highest_alt = 0

            if not transfer_body.is_orbiting:
                distance_between_bodies = sqrt(
                    (primary.x - transfer_body.x) ** 2
                    + (primary.y - transfer_body.y) ** 2
                )
                r_target_apogee = distance_between_bodies
                r_target_periapsis = transfer_body.radius + 20000
                a_target_transfer = (r_target_apogee + r_target_periapsis) / 2
                mu_target = G * transfer_body.mass

                v_target_apogee = sqrt(
                    mu_target * (2 / r_target_apogee - 1 / a_target_transfer)
                )

                v_primary_orbit = (
                    distance_between_bodies * primary.angular_velocity
                    if primary.is_orbiting
                    else 0
                )
                v_infinity = v_primary_orbit - v_target_apogee

                # Velocity required AT CURRENT R to hit the correct V_infinity
                v_transfer_required = sqrt(v_infinity**2 + 2 * mu / r)

                # Attach marker to the rocket's current position and track the remaining Delta-V
                tli_x, tli_y = self.x, self.y
                # If negative, you've over-burned! We clamp to 0 or leave it to show overburn.
                delta_v = v_transfer_required - v

            # Dynamically track the sweep angle for any body in motion
            sim_angles = {body: body.angle for body in self._bodies if body.is_orbiting}

            for _ in range(num_points):
                # Update positions for all bodies
                sim_positions = {}
                closest_surface_dist = float("inf")

                for body in self._bodies:
                    if body.is_orbiting:
                        assert body.parent_body is not None
                        assert body.orbit_radius is not None

                        # We use a temporary angle state just for projection
                        px = (
                            body.parent_body.x
                            + cos(sim_angles[body]) * body.orbit_radius
                        )
                        py = (
                            body.parent_body.y
                            + sin(sim_angles[body]) * body.orbit_radius
                        )
                        sim_positions[body] = (px, py)
                    else:
                        sim_positions[body] = (body.x, body.y)

                    # Track closest body SURFACE for adaptive dt, not just the center.
                    dist_to_center = sqrt(
                        (sim_x - sim_positions[body][0]) ** 2
                        + (sim_y - sim_positions[body][1]) ** 2
                    )
                    surface_dist = max(1.0, dist_to_center - body.radius)

                    if surface_dist < closest_surface_dist:
                        closest_surface_dist = surface_dist

                # Adaptive Time Step (dt):
                # Drops to very small accurate steps (0.5s) near high-gravity surfaces to stop the helix/precession artifact.
                if closest_surface_dist < 30000:
                    dt = 0.5
                else:
                    dt = min(90.0, max(0.5, closest_surface_dist / 1500.0))

                net_gx, net_gy = 0.0, 0.0
                drag_ax, drag_ay = 0.0, 0.0
                collision = False

                for body in self._bodies:
                    # Update celestial motion by the dt step
                    if body.is_orbiting:
                        sim_angles[body] += body.angular_velocity * dt

                    bx, by = sim_positions[body]

                    dx = sim_x - bx
                    dy = sim_y - by
                    dist = sqrt(dx**2 + dy**2)

                    if dist <= body.radius:
                        collision = True
                        break

                    g_mag = G * body.mass / dist**2
                    net_gx += -g_mag * (dx / dist)
                    net_gy += -g_mag * (dy / dist)

                    if body.has_atmosphere:
                        altitude = dist - body.radius
                        if altitude < body.atmosphere_thickness:
                            scale_height = 4000 * (body.atmosphere_thickness / 30000)
                            sim_air_density = 1.225 * exp(-altitude / scale_height)
                            sim_speed = sqrt(sim_vx**2 + sim_vy**2)
                            if sim_speed > 0:
                                drag_magnitude = (
                                    0.5
                                    * sim_air_density
                                    * sim_speed**2
                                    * self._drag_coefficient
                                    * self._cross_sectional_area
                                )
                                drag_accel = drag_magnitude / self.wet_mass
                                drag_ax += -drag_accel * (sim_vx / sim_speed)
                                drag_ay += -drag_accel * (sim_vy / sim_speed)

                if collision:
                    # Connect to surface smoothly
                    points.append((sim_x, sim_y))
                    break

                sim_vx += (net_gx + drag_ax) * dt
                sim_vy += (net_gy + drag_ay) * dt
                sim_x += sim_vx * dt
                sim_y += sim_vy * dt

                primary_dist = sqrt((sim_x - primary.x) ** 2 + (sim_y - primary.y) ** 2)
                if primary_dist > highest_alt:
                    highest_alt = primary_dist
                    apoapsis = (sim_x, sim_y)

                points.append((sim_x, sim_y))

        return points, apoapsis, (tli_x, tli_y), delta_v
