"""Small scheduler with the pyglet.clock API the game uses.

The backend calls tick(dt) once per frame.  An interval callback fires at most
once per tick and receives the real elapsed time (the game's physics is
dt-based with sub-stepping, so this is fine at any frame rate).
"""

_MAX_DT = 0.1
_items = []  # [func, interval, elapsed, once]


def schedule_interval(func, interval):
    _items.append([func, float(interval), 0.0, False])


def schedule_once(func, delay):
    _items.append([func, float(delay), 0.0, True])


def unschedule(func):
    _items[:] = [it for it in _items if it[0] is not func]


def tick(dt):
    dt = min(dt, _MAX_DT)
    for it in list(_items):
        if it not in _items:
            continue
        it[2] += dt
        if it[2] >= it[1]:
            elapsed = it[2]
            if it[3]:
                _items.remove(it)
            else:
                it[2] = 0.0
            it[0](elapsed)
