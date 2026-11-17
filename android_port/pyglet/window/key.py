"""Key symbols (same numeric values as pyglet) and KeyStateHandler."""
SPACE = 32
COMMA = 44
PERIOD = 46
BACKSPACE = 0xFF08
ENTER = RETURN = 0xFF0D
ESCAPE = 0xFF1B
LEFT, UP, RIGHT, DOWN = 0xFF51, 0xFF52, 0xFF53, 0xFF54

for _c in "abcdefghijklmnopqrstuvwxyz":
    globals()[_c.upper()] = ord(_c)
for _d in "0123456789":
    globals()["_" + _d] = ord(_d)


class KeyStateHandler(dict):
    """Pushed on a window; keys[SYMBOL] tells whether that key is held right now."""

    def on_key_press(self, symbol, modifiers):
        self[symbol] = True

    def on_key_release(self, symbol, modifiers):
        self[symbol] = False

    def __getitem__(self, key):
        return self.get(key, False)
