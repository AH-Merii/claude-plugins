"""Field Notes example, 2D: the benchtop servo press of press_3d.py in front elevation.

Build it with: inkwash.py build examples/press_2d.py --out OUT
"""

from kit import (
    GLASS,
    OVER,
    SHADE,
    _stroke,
    big2d,
    cell,
    cfill,
    eblock,
    ecyl,
    ell_full,
    granulate,
    ground,
    ink,
    knockout,
    pdot,
    pell,
    pline,
    prpoly,
    splatter,
    wash,
)

# ================= Press (2D): the same servo press-fit workstation, front elevation =================
# 2D means one plane: no receding faces. Depth has to come from other places:
#   overlap (head in front of the column, posts in front of the plate), cast shadows that fall right and down,
#   value bands that turn flat rectangles into round forms, heavier ink on the shadow side (bottom, right),
#   lighter or broken ink on lit edges (top, left), and a flat ground shadow. Light from the upper left.


NAME = "Press (2D)"

# ================= Press (2D): front elevation of the reference photo (a benchtop electric servo press) =================
# Same parts as the 3D: tall head box (brand strip, touchscreen, black/red/white buttons, side connector box sticking out),
# the throat with the column face set back behind it, chrome spindle, raised work table with a dark tool plate,
# green palm buttons and a small yellow-collared e-stop on its front, a wider foot plate. A small blue part on the plate.
# Depth in elevation: the column face sits in the head's shadow, the fillet catches a lip of light, the part and spindle
# cast shadows onto the column, heavier ink on bottoms and right sides.

ground(19, 71, 87.5, spread=12, oblique=False)
big2d(18, 84, 72, 87.5, front="#dee2e6", fo=18, r=0.8, w=0.9, turn=0.04)  # foot plate

# ---------------- column face, set back in the throat ----------------
OVER[0] = True
knockout([(30.6, 46), (57.4, 46), (57.4, 70), (30.6, 70)])
wash([(30.6, 46), (57.4, 46), (57.4, 70), (30.6, 70)], "#dee2e6", 26, layers=1)
wash(
    [(30.8, 46.2), (57.2, 46.2), (57.2, 55.5), (30.8, 53)], "#343a40", 26, layers=1
)  # the head's shadow, deepest right under it
wash(
    [(30.8, 55.6), (57.2, 55.6), (57.2, 57.6), (30.8, 57.3)], "#ffffff", 55, layers=1
)  # the fillet's lower lip catching light
pline((31.4, 57.7), (56.6, 57.7), w=0.22, colour="#868e96", op=60)
wash([(51.5, 47), (57.2, 47), (57.2, 70), (52.5, 70)], SHADE, 18, layers=1)  # the column's far edge turning away
cfill([(37, 61), (51, 61), (51, 68.6), (37, 68.6)], "#e9ecef", 55)  # access cover
prpoly([(37, 61), (51, 61), (51, 68.6), (37, 68.6)], r=0.4, w=0.28, colour="#495057", op=70)
ink((30.6, 47), (30.6, 70), w=0.75, over=(0, 0.4), restate=0.2, bow=0.3)
ink((57.4, 47), (57.4, 70), w=1.0, over=(0, 0.4), restate=0.3, bow=0.3)
wash(
    [(48.6, 47), (51.6, 47.6), (51.6, 56.6), (48.6, 56)], "#343a40", 14, layers=1
)  # the spindle's shadow on the column
wash([(49.2, 62.6), (53.2, 63.4), (53.2, 69), (49.2, 69)], "#343a40", 16, layers=1)  # the part's shadow on the column

# ---------------- head ----------------
knockout([(30, 6), (58, 6), (58, 46), (30, 46)])
big2d(30, 6, 58, 46, front="#f8f9fa", fo=14, r=1.6, w=1.0, turn=0.08)
# brand strip
cfill([(32.4, 10.6), (34.0, 10.6), (33.2, 9.4)], "#1c7ed6", 85)
pline((34.8, 10.3), (40.5, 10.3), w=0.26, colour="#1864ab", op=85)
pline((32.0, 12.0), (55.8, 12.0), w=0.2, colour="#4dabf7", op=80)
# screen in a dark bezel
S0, S1 = (34.2, 16.2), (53.6, 29.6)
cfill(
    [(S0[0] - 0.9, S0[1] - 0.9), (S1[0] + 0.9, S0[1] - 0.9), (S1[0] + 0.9, S1[1] + 0.9), (S0[0] - 0.9, S1[1] + 0.9)],
    "#343a40",
    88,
)
prpoly(
    [(S0[0] - 0.9, S0[1] - 0.9), (S1[0] + 0.9, S0[1] - 0.9), (S1[0] + 0.9, S1[1] + 0.9), (S0[0] - 0.9, S1[1] + 0.9)],
    r=0.4,
    w=0.45,
)
knockout([S0, (S1[0], S0[1]), S1, (S0[0], S1[1])])
cfill(
    [(S0[0] - 0.8, S0[1] - 0.8), (S1[0] + 0.8, S0[1] - 0.8), (S1[0] + 0.8, S1[1] + 0.8), (S0[0] - 0.8, S1[1] + 0.8)],
    "#343a40",
    88,
)
prpoly(
    [(S0[0] - 0.8, S0[1] - 0.8), (S1[0] + 0.8, S0[1] - 0.8), (S1[0] + 0.8, S1[1] + 0.8), (S0[0] - 0.8, S1[1] + 0.8)],
    r=0.4,
    w=0.42,
)
knockout([S0, (S1[0], S0[1]), S1, (S0[0], S1[1])])
cfill([S0, (S1[0], S0[1]), S1, (S0[0], S1[1])], "#1864ab", 85)
cfill([S0, (S1[0], S0[1]), (S1[0], S0[1] + 0.9), (S0[0], S0[1] + 0.9)], "#0b3b66", 85)
for k_, cx_ in enumerate((S1[0] - 1.7, S1[0] - 1.1, S1[0] - 0.5)):
    pdot(cx_, S0[1] + 0.45, 0.14, ["#e7f5ff", "#e7f5ff", "#69db7c"][k_], 95)
gx0, gy0, gx1, gy1 = S0[0] + 1.0, S0[1] + 1.7, S1[0] - 4.2, S1[1] - 0.8
_stroke([(gx0, gy0), (gx0, gy1), (gx1, gy1)], 0.16, "#a5d8ff", 90, taper=False)
wx0, wx1, wy0, wy1 = gx0 + (gx1 - gx0) * 0.64, gx0 + (gx1 - gx0) * 0.9, gy0 + 0.3, gy0 + 2.4
for p_, q_ in (((wx0, wy0), (wx1, wy0)), ((wx1, wy0), (wx1, wy1)), ((wx1, wy1), (wx0, wy1)), ((wx0, wy1), (wx0, wy0))):
    _stroke([p_, ((p_[0] + q_[0]) / 2, (p_[1] + q_[1]) / 2), q_], 0.13, "#8ce99a", 95, taper=False)
curve = [
    (gx0 + (gx1 - gx0) * t, gy1 - (gy1 - gy0) * (0.08 + 0.2 * t + 0.62 * max(0, t - 0.55) ** 1.5 * 3.4))
    for t in [i / 24 for i in range(25)]
]
_stroke([(x_, max(gy0 + 0.3, y_)) for x_, y_ in curve], 0.26, "#ffffff", 100, taper=False)
for ln, yy in ((2.0, S0[1] + 2.1), (1.6, S0[1] + 3.0), (1.9, S0[1] + 3.9)):
    _stroke([(S1[0] - 3.6, yy), (S1[0] - 3.6 + ln * 0.5, yy)], 0.15, "#a5d8ff", 90, taper=False)
    _stroke([(S1[0] - 2.2, yy), (S1[0] - 2.2 + ln * 0.7, yy)], 0.22, "#ffffff", 100, taper=False)
cfill(
    [(S1[0] - 3.6, S1[1] - 1.6), (S1[0] - 0.6, S1[1] - 1.6), (S1[0] - 0.6, S1[1] - 0.8), (S1[0] - 3.6, S1[1] - 0.8)],
    "#2f9e44",
    90,
)
_stroke([(S0[0] + 0.8, S1[1] - 0.3), (S0[0] + 4.6, S0[1] + 1.3)], 0.5, "#ffffff", 22, taper=False)
# three buttons in a row under the screen: black, red, white; small, each in its own bezel
for k_, (bx_, col_, dk_, hl_) in enumerate(
    ((37.6, "#343a40", "#1e1e1e", 55), (44.0, "#f03e3e", "#c92a2a", 80), (50.4, "#f1f3f5", "#adb5bd", 90))
):
    c_ = (bx_, 37.0)
    r_ = 1.2 + (0.1 if k_ == 1 else 0)
    cell(c_[0] + 0.25, c_[1] + 0.25, r_ + 0.4, r_ + 0.4, "#343a40", 16)
    cell(*c_, r_ + 0.3, r_ + 0.3, "#adb5bd", 80)
    pell(*c_, r_ + 0.3, r_ + 0.3, w=0.3)
    d_ = (c_[0] - 0.12, c_[1] - 0.12)
    cell(*d_, r_ - 0.1, r_ - 0.1, col_, 88)
    cell(d_[0] + 0.2, d_[1] + 0.2, r_ * 0.55, r_ * 0.55, dk_, 40)
    cell(d_[0] - r_ * 0.35, d_[1] - r_ * 0.35, 0.24, 0.18, "#ffffff", hl_)
    pell(*d_, r_ - 0.1, r_ - 0.1, w=0.22, colour="#1e1e1e", op=80)
for sx_ in (31.6, 56.2):
    pdot(sx_, 8.2, 0.22, "#343a40", 80)
    pdot(sx_, 44.2, 0.22, "#343a40", 80)
# connector box on the side of the head, sticking out past its right edge
eblock(58, 13.4, 60.4, 20.4, col="#343a40", fo=88, w=0.4, r=0.2, bevel=False)
cfill([(58, 13.4), (60.4, 13.4), (60.4, 14.2), (58, 14.2)], "#868e96", 80)
cfill([(60.4, 14.4), (61.1, 14.8), (61.1, 19.4), (60.4, 19.8)], "#212529", 85)
pline((61.1, 14.8), (61.1, 19.4), w=0.3)

# ---------------- spindle: one straight chrome cylinder, wide and short, as in the photo ----------------
X0_, X1_, Y0_, Y1_ = 39.6, 48.4, 46.0, 54.2
knockout([(X0_, Y0_), (X1_, Y0_), (X1_, Y1_), (X0_, Y1_)])
cfill([(X0_, Y0_), (X1_, Y0_), (X1_, Y1_), (X0_, Y1_)], "#dee2e6", 88)
W_ = X1_ - X0_
for f0, f1, col_, op_ in (
    (0.05, 0.17, "#868e96", 45),
    (0.21, 0.31, "#ffffff", 90),
    (0.39, 0.51, "#495057", 35),
    (0.59, 0.65, "#ffffff", 75),
    (0.72, 0.9, "#343a40", 42),
):
    cfill([(X0_ + W_ * f0, Y0_), (X0_ + W_ * f1, Y0_), (X0_ + W_ * f1, Y1_), (X0_ + W_ * f0, Y1_)], col_, op_)
pline((X0_, Y0_ + 0.2), (X0_, Y1_), w=0.38)
pline((X1_, Y0_ + 0.2), (X1_, Y1_), w=0.62)
pline((X0_ + 0.2, Y1_), (X1_ - 0.2, Y1_), w=0.55)
pline((X0_ + 0.3, Y1_ - 0.6), (X1_ - 0.3, Y1_ - 0.6), w=0.14, colour="#868e96", op=70)  # bottom chamfer
pdot(X0_ + W_ * 0.78, Y1_ - 1.3, 0.24, "#1e1e1e")  # the small screw seen in the photo
wash(
    [(X0_, Y0_), (X1_, Y0_), (X1_, Y0_ + 1.4), (X0_, Y0_ + 1.0)], "#343a40", 16, layers=1
)  # the head's shadow on its top
# ---------------- work table ----------------
knockout([(22, 68.6), (66, 68.6), (66, 84), (22, 84)])
big2d(22, 70, 66, 84, front="#f1f3f5", fo=16, r=1.2, w=1.0, turn=0.06)
wash(
    [(22.6, 70.4), (65.4, 70.4), (65.4, 72.2), (22.6, 72.2)], "#ffffff", 55, layers=1
)  # chamfered top edge catching light
pline((23.2, 72.4), (65, 72.4), w=0.22, colour="#868e96", op=60)
eblock(26, 68.6, 62, 70.1, col="#495057", fo=85, w=0.42, r=0.2)  # dark tool plate, seen edge-on
pline((26.6, 68.95), (61.4, 68.95), w=0.18, colour="#adb5bd", op=85)
# the part: a small outrunner motor, near the size the original icon gave its part (a little smaller): blue bell,
# spoked cage top seen edge-on, etched name band, shaft standing up under the spindle
MX0, MX1, MY0, MY1 = 38.8, 49.2, 62.2, 68.6
knockout([(MX0, MY0 - 1.0), (MX1, MY0 - 1.0), (MX1, MY1), (MX0, MY1)])
ecyl(MX0, MX1, MY0, MY1, col="#4dabf7", dark="#1864ab", fo=85, w=0.55)
cfill([(MX0 + 0.6, MY0 - 0.9), (MX1 - 0.6, MY0 - 0.9), (MX1, MY0), (MX0, MY0)], "#1864ab", 85)  # the cage top, edge-on
for k_, x_ in enumerate((40.4, 42.3, 44.2, 46.1, 47.8)):  # spokes with windings glinting between
    cfill([(x_ - 0.3, MY0 - 0.85), (x_ + 0.3, MY0 - 0.85), (x_ + 0.3, MY0), (x_ - 0.3, MY0)], "#74c0fc", 92)
    if k_ < 4:
        pdot(x_ + 0.95, MY0 - 0.42, 0.18, "#e8590c", 70)
pline((MX0 + 0.6, MY0 - 0.9), (MX1 - 0.6, MY0 - 0.9), w=0.4)
pline((MX0, MY0), (MX0 + 0.6, MY0 - 0.9), w=0.3)
pline((MX1, MY0), (MX1 - 0.6, MY0 - 0.9), w=0.45)
pline((MX0 + 1.2, 64.3), (MX1, 64.3), w=0.22, colour="#1864ab", op=55)
pline((MX0 + 2.2, 65.4), (MX1, 65.4), w=0.18, colour="#1864ab", op=45)  # etched name band
ecyl(43.4, 44.6, 59.0, 61.3, col="#e9ecef", dark="#868e96", w=0.3)  # shaft
# palm buttons and e-stop on the table front
for bx_ in (27.6, 60.4):
    c_ = (bx_, 77.6)
    d_ = (c_[0] - 0.3, c_[1] - 0.25)
    cell(c_[0] + 0.35, c_[1] + 0.35, 2.2, 2.2, "#343a40", 18)
    cell(*c_, 2.1, 2.1, "#adb5bd", 85)
    pell(*c_, 2.1, 2.1, w=0.36)
    knockout(ell_full(*d_, 1.5, 1.5))
    cell(*d_, 1.5, 1.5, "#40c057", 88)
    cell(d_[0] + 0.3, d_[1] + 0.3, 1.0, 1.0, "#2f9e44", 50)
    cell(d_[0] - 0.55, d_[1] - 0.55, 0.38, 0.28, "#ffffff", 80)
    pell(*d_, 1.5, 1.5, w=0.28, colour="#1b5e20")
ec = (44.0, 77.8)
cell(ec[0] + 0.25, ec[1] + 0.25, 1.75, 1.75, "#343a40", 14)
cell(*ec, 1.65, 1.65, "#fcc419", 80)
pell(*ec, 1.65, 1.65, w=0.3, colour="#e67700")
cell(ec[0] - 0.15, ec[1] - 0.15, 1.05, 1.05, "#f03e3e", 88)
cell(ec[0] + 0.1, ec[1] + 0.1, 0.62, 0.62, "#c92a2a", 45)
cell(ec[0] - 0.5, ec[1] - 0.5, 0.26, 0.19, "#ffffff", 75)
pell(ec[0] - 0.15, ec[1] - 0.15, 1.05, 1.05, w=0.24, colour="#a61e1e")
OVER[0] = False

# ---------------- character ----------------
granulate([(55.5, 7), (58, 7), (58, 46), (55.5, 46)], "#495057", n=14, op=30)
granulate([(63, 71), (66, 71), (66, 84), (63, 84)], "#495057", n=12, op=30)
granulate([(18, 85), (72, 85), (72, 87.5), (18, 87.5)], "#868e96", n=12, op=25)
wash([(59, 4), (65, 1), (66, 13), (60, 16)], "#4dabf7", 9, layers=1)
wash([(16, 66), (26, 66), (24, 73), (16, 74)], GLASS, 11, layers=1)
for p, q in [((32, 6.6), (46, 6.6)), ((22.6, 74), (22.6, 80)), ((30.9, 58.5), (30.9, 66)), ((19, 84.6), (30, 84.6))]:
    ink(p, q, w=0.7, colour="#ffffff", over=(0, 0.2), restate=0, bow=0.1)
splatter(45, 46, 40, 50, n=10, bbox=(12, -2, 80, 94))
for p, q in [((10, 22), (14, 19)), ((76, 36), (80, 33)), ((76, 80), (79, 76)), ((11, 58), (14, 55))]:
    ink(p, q, w=0.5, over=(0, 0.6), restate=0, bow=0.6)
