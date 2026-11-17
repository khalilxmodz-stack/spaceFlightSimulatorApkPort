"""Backend-neutral frame recorder.

Drawing calls (shape.draw(), batch.draw(), label.draw()) append *ops* here
while the game's on_draw runs.  The Kivy backend then turns the finished list
into GPU work.  Nothing in this file imports Kivy, so it can be unit-tested
on any machine.

op = ["mesh",  affine, array('f')]   interleaved x, y, r, g, b, a per vertex (triangles)
op = ["label", affine, spec_tuple]   see add_label()
affine = (a, b, c, d, tx, ty): the window.view matrix at the time of the call
"""
from array import array

window = None            # the Window instance (set by Window.__init__)
clear_color = (0.0, 0.0, 0.0, 1.0)
font_files = []
run_hook = None          # set by the backend
exit_hook = None
ops = []

_IDENTITY = (1.0, 0.0, 0.0, 1.0, 0.0, 0.0)


def _affine():
    if window is None:
        return _IDENTITY
    return window.view.affine2d()


def begin_frame():
    del ops[:]


def add_mesh(verts):
    if len(verts) == 0:
        return
    aff = _affine()
    if ops and ops[-1][0] == "mesh" and ops[-1][1] == aff:
        ops[-1][2].extend(verts)
    else:
        ops.append(["mesh", aff, array("f", verts)])


def add_label(label):
    ops.append([
        "label",
        _affine(),
        (
            label.text, label.font_name, label.font_size,
            tuple(c / 255.0 for c in label.color),
            label.x, label.y, label.anchor_x, label.anchor_y,
            label.width, label.multiline,
        ),
    ])
