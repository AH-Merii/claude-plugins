"""Field Notes example, 3D: a benchtop servo press, converted from a reference photo.

Pairs with press_2d.py: the same machine, same parts, colours and proportions, in front elevation.

Build it with: inkwash.py build examples/press_3d.py --out OUT
"""

import math

from kit import (
    GLASS,
    OVER,
    SHADE,
    STEEL_D,
    P,
    _stroke,
    band,
    bigbox,
    cell,
    cfill,
    ell_full,
    granulate,
    ground,
    ink,
    ink_path,
    knockout,
    parc,
    pdot,
    pell,
    pline,
    prpoly,
    rpoly,
    soft,
    splatter,
    vcyl,
    wash,
)

NAME = "Press (3D)"

# ================= Press (3D): drawn from the reference photo of a benchtop electric servo press =================
# Reference: one-piece C-frame. A tall head box carries a brand strip, a touchscreen and three buttons (black, red, white);
# a black connector box sits on its side. Under the head, the throat curves into the lower column. A short chrome spindle
# comes down from the head. A raised work table with a dark tool plate (centre hole) sits on a foot plate; its front holds
# a small e-stop with a yellow collar and two green palm buttons. Looked up (the maker's product page): integral cast
# frame, servo + ballscrew spindle, the HMI shows force-vs-position curves. The photo shows no part; a small motor on the
# plate (drawn larger than true scale) keeps the icon's meaning: pressing a part.


# ---------------- ground and foot plate ----------------
ground(P(22, 87, -8)[0], P(68, 87, -8)[0], P(68, 87, -8)[1], depth=30, spread=14)
bigbox(22, 68, 84, 87, -8, 28, front="#dee2e6", fo=18, r=1.0, w=0.9, top_breath=False)

# ---------------- the C-frame: column front (seen through the throat), then head front, top and one C-shaped side ----------------
OVER[0] = True
CF = [P(34, 44, 16), P(54, 44, 16), P(54, 84, 16), P(34, 84, 16)]
knockout(CF)
wash(CF, "#e9ecef", 20, layers=1)
wash(
    [P(34.3, 44.5, 16), P(53.7, 44.5, 16), P(53.7, 55, 16), P(34.3, 52.5, 16)], "#343a40", 22, layers=1
)  # the head's shadow and the curve of the throat
wash(
    [P(34.3, 55.5, 16), P(53.7, 55.5, 16), P(53.7, 57.5, 16), P(34.3, 57.2, 16)], "#ffffff", 50, layers=1
)  # light on the fillet's lower lip
pline(P(35, 57.6, 16), P(53.2, 57.6, 16), w=0.22, colour="#868e96", op=60)  # where the fillet meets the flat
ink(P(34, 50, 16), P(34, 84, 16), w=0.8, over=(0, 0.5), restate=0.3, bow=0.3)
cfill([P(38, 62, 16), P(50, 62, 16), P(50, 72, 16), P(38, 72, 16)], "#dee2e6", 50)  # access cover on the column
prpoly([P(38, 62, 16), P(50, 62, 16), P(50, 72, 16), P(38, 72, 16)], r=0.4, w=0.28, colour="#495057", op=70)

arc_ = [
    P(54, 48.5 - 4.5 * math.sin(a_), 11.5 + 4.5 * math.cos(a_)) for a_ in [math.pi / 2 * i / 12 for i in range(13)]
]  # fillet: column front up into the head's underside
SIDE = [P(54, 8, 2), P(54, 8, 26), P(54, 84, 26), P(54, 84, 16)] + arc_ + [P(54, 44, 2)]
FRONT = [P(34, 8, 2), P(54, 8, 2), P(54, 44, 2), P(34, 44, 2)]
TOP = [P(34, 8, 2), P(34, 8, 26), P(54, 8, 26), P(54, 8, 2)]
knockout(FRONT)
knockout(TOP)
knockout(SIDE)
wash(FRONT, "#f8f9fa", 14, layers=1)
wash([P(34, 39, 2), P(54, 39, 2), P(54, 44, 2), P(34, 44, 2)], STEEL_D, 9, layers=1)
wash(TOP, "#e9ecef", 30, layers=1)
wash(SIDE, SHADE, 22, layers=1)
wash(
    [P(54, 50, 18), P(54, 50, 26), P(54, 84, 26), P(54, 84, 18)], SHADE, 22, layers=1
)  # pigment pooling down the column
wash(
    [P(54, 9, 24.8), P(54, 9, 26), P(54, 84, 26), P(54, 84, 24.8)], "#ffffff", 35, layers=1
)  # reflected light at the back edge
rpoly([P(34, 44, 2), P(34, 8, 2), P(34, 8, 26), P(54, 8, 26), P(54, 84, 26)], r=1.6, w=1.0)
ink(
    P(35.2, 44, 2), P(54, 44, 2), w=1.0, over=(0, 0.5), restate=0.3, bow=0.3
)  # underside of the head: shadow side, pressed hard
ink_path(
    [P(54, 44, 2), P(54, 44, 11.5)] + arc_[::-1] + [P(54, 84, 16)], w=0.95, over=(0, 0.6), restate=0.3
)  # the C of the frame
soft(P(54, 9.5, 2), P(54, 43, 2))
soft(P(35.6, 8, 2), P(53, 8, 2))
soft(P(54, 8, 3.6), P(54, 8, 25))
# brand strip: small logo mark, name line, thin blue rule
cfill([P(35.6, 10.0, 2), P(37.2, 10.0, 2), P(36.4, 9.0, 2)], "#1c7ed6", 85)
pline(P(37.8, 9.9, 2), P(42.5, 9.9, 2), w=0.26, colour="#1864ab", op=85)
pline(P(35.4, 11.3, 2), P(52.8, 11.3, 2), w=0.2, colour="#4dabf7", op=80)
# screen: dark bezel, force-vs-position curve through a pass window, readouts
S0, S1 = P(37, 15.5, 2), P(51.6, 26.5, 2)
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
    ((39.0, "#343a40", "#1e1e1e", 55), (44.3, "#f03e3e", "#c92a2a", 80), (49.6, "#f1f3f5", "#adb5bd", 90))
):
    c_ = P(bx_, 33.0, 2)
    r_ = 0.95 + (0.1 if k_ == 1 else 0)
    cell(c_[0] + 0.25, c_[1] + 0.25, r_ + 0.4, r_ + 0.4, "#343a40", 16)
    cell(*c_, r_ + 0.3, r_ + 0.3, "#adb5bd", 80)
    pell(*c_, r_ + 0.3, r_ + 0.3, w=0.3)
    d_ = (c_[0] - 0.12, c_[1] - 0.12)
    cell(*d_, r_ - 0.1, r_ - 0.1, col_, 88)
    cell(d_[0] + 0.2, d_[1] + 0.2, r_ * 0.55, r_ * 0.55, dk_, 40)
    cell(d_[0] - r_ * 0.35, d_[1] - r_ * 0.35, 0.24, 0.18, "#ffffff", hl_)
    pell(*d_, r_ - 0.1, r_ - 0.1, w=0.22, colour="#1e1e1e", op=80)
# panel seams and screws on the side face (the casting is covered by sheet panels)
pline(P(54, 30, 4), P(54, 30, 24.6), w=0.22, colour="#495057", op=55)
for zz in (5, 24):
    pdot(*P(54, 10.4, zz), 0.2, "#343a40", 80)
    pdot(*P(54, 42, zz), 0.2, "#343a40", 80)
# black connector box on the side of the head (in the photo it sits high on the side)
cb0, cb1 = P(54, 13, 15), P(54, 19.5, 20)
cfill([P(54, 13, 15), P(54, 13, 20), P(54, 19.5, 20), P(54, 19.5, 15)], "#212529", 88)
cfill(
    [P(54, 13, 20), P(55.4, 13, 20), P(55.4, 19.5, 20), P(54, 19.5, 20)], "#495057", 85
)  # its thickness, facing us a little
cfill([P(54, 13, 15), P(55.4, 13, 15), P(55.4, 13, 20), P(54, 13, 20)], "#868e96", 80)  # its lit top
for p_, q_ in (
    (P(55.4, 13, 15), P(55.4, 13, 20)),
    (P(55.4, 13, 20), P(55.4, 19.5, 20)),
    (P(55.4, 19.5, 20), P(54, 19.5, 20)),
    (P(54, 13, 15), P(55.4, 13, 15)),
    (P(54, 19.5, 15), P(54, 13, 15)),
    (P(54, 19.5, 15), P(54, 19.5, 20)),
):
    pline(p_, q_, w=0.32)
cfill([P(54, 14.4, 16.2), P(54, 14.4, 18.8), P(54, 18.1, 18.8), P(54, 18.1, 16.2)], "#495057", 85)  # its plug face

# ---------------- spindle under the head: as in the photo, ONE straight chrome cylinder, wide and short ----------------
# (no stepped collar or punch: the photo shows a single uniform tube with a small screw near the bottom)
sp = P(44, 44, 9)
SR_, SRY_ = 3.0, 1.05
yt_ = P(44, 44, 2)[1]
yb_ = yt_ + 6.2  # visible from the head's underside edge down


def sp_x(f):
    return sp[0] + SR_ * f


def sp_yb(f):
    return yb_ + SRY_ * math.sqrt(max(0, 1 - f**2))


knockout([(sp_x(-1), yt_)] + [(sp_x(f), sp_yb(f)) for f in [-1 + i / 8 for i in range(17)]] + [(sp_x(1), yt_)])
cfill(
    [(sp_x(-1), yt_)] + [(sp_x(f), sp_yb(f)) for f in [-1 + i / 8 for i in range(17)]] + [(sp_x(1), yt_)], "#dee2e6", 88
)
for f0, f1, col_, op_ in (
    (-0.9, -0.66, "#868e96", 45),
    (-0.58, -0.38, "#ffffff", 90),
    (-0.22, 0.02, "#495057", 35),
    (0.18, 0.3, "#ffffff", 75),
    (0.45, 0.8, "#343a40", 42),
):  # chrome: a few hard vertical reflections
    cfill([(sp_x(f0), yt_), (sp_x(f1), yt_), (sp_x(f1), sp_yb(f1)), (sp_x(f0), sp_yb(f0))], col_, op_)
wash(
    [(sp_x(-1), yt_), (sp_x(1), yt_), (sp_x(1), yt_ + 1.4), (sp_x(-1), yt_ + 1.0)], "#343a40", 16, layers=1
)  # the head's shadow on its top
pline((sp_x(-1), yt_ + 0.1), (sp_x(-1), yb_), w=0.38)
pline((sp_x(1), yt_ + 0.1), (sp_x(1), yb_), w=0.62)
parc(sp[0], yb_, SR_, SRY_, 0, math.pi, w=0.55)
parc(
    sp[0], yb_ - 0.6, SR_, SRY_, 0.2, math.pi - 0.2, w=0.14, colour="#868e96", op=70, n=16
)  # chamfer line at the bottom
pdot(sp_x(0.55), yb_ - 1.4 + SRY_ * 0.8, 0.22, "#1e1e1e")  # the small screw seen in the photo
# ---------------- work table: raised block with a dark tool plate; e-stop and palm buttons on its front ----------------
knockout([P(26, 84, -6), P(26, 72, -6), P(26, 72, 14), P(64, 72, 14), P(64, 84, 14), P(64, 84, -6)])
bigbox(26, 64, 72, 84, -6, 14, front="#f1f3f5", fo=16, r=1.2, w=1.0, top_breath=True)
wash(
    [P(26.4, 72.4, -6), P(63.6, 72.4, -6), P(63.6, 74.4, -6), P(26.4, 74.4, -6)], "#ffffff", 55, layers=1
)  # chamfered top front edge catching light
pline(P(27.2, 74.5, -6), P(63, 74.5, -6), w=0.22, colour="#868e96", op=60)
tp = [P(30, 72, -3), P(60, 72, -3), P(60, 72, 11), P(30, 72, 11)]
cfill(tp, "#495057", 82)
cfill([P(30, 72, -3), P(60, 72, -3), P(60, 72, -1.6), P(30, 72, -1.6)], "#868e96", 70)  # its lit front edge
for p_, q_ in zip(tp, tp[1:] + tp[:1]):
    pline(p_, q_, w=0.35)
for sx_, sz_ in ((31.5, -1), (58.5, -1), (31.5, 9.5), (58.5, 9.5)):
    pdot(*P(sx_, 72, sz_), 0.22, "#adb5bd", 90)
hc = P(44, 72, 9)
cell(*hc, 1.6, 0.56, "#1e1e1e", 90)
pell(*hc, 1.6, 0.56, w=0.28)  # centre hole for the fixture
# the part: a small outrunner motor, drawn near the size the original icon gave its part (a little smaller), so it reads
# clearly as the thing being pressed: blue anodised bell, spoked top with dark windings between the spokes, steel shaft
MR_, MRY_, MH_ = 4.4, 1.55, 5.4
t_ = hc[1] - MH_
cfill(
    [(hc[0] + 3.6, hc[1] + 0.4), (hc[0] + 12.5, hc[1] - 4.6), (hc[0] + 13.4, hc[1] - 2.6), (hc[0] + 4.4, hc[1] + 1.6)],
    "#1e1e1e",
    25,
)
knockout(band(hc[0], t_, hc[1], MR_, MRY_))
knockout(ell_full(hc[0], t_, MR_, MRY_))
vcyl(hc[0], t_, hc[1], MR_, MRY_, col="#4dabf7", dark="#1864ab", top="#0b3b66", w=0.55)
pell(hc[0], t_, MR_ - 0.45, MRY_ - 0.16, w=0.2, colour="#1864ab", op=80)  # rim of the cage
for k_ in range(5):  # spokes, each a little different in weight
    a_ = 0.5 + k_ * 2 * math.pi / 5
    cfill(
        [
            (hc[0] + 0.8 * math.cos(a_ - 0.25), t_ + 0.28 * math.sin(a_ - 0.25)),
            (hc[0] + (MR_ - 0.5) * math.cos(a_ - 0.12), t_ + (MRY_ - 0.17) * math.sin(a_ - 0.12)),
            (hc[0] + (MR_ - 0.5) * math.cos(a_ + 0.12), t_ + (MRY_ - 0.17) * math.sin(a_ + 0.12)),
            (hc[0] + 0.8 * math.cos(a_ + 0.25), t_ + 0.28 * math.sin(a_ + 0.25)),
        ],
        "#74c0fc",
        92,
    )
for k_ in range(5):  # copper windings glinting in the gaps
    a_ = 0.5 + (k_ + 0.5) * 2 * math.pi / 5
    pdot(hc[0] + 2.4 * math.cos(a_), t_ + 0.84 * math.sin(a_), 0.2, "#e8590c", 70)
cell(hc[0], t_, 0.95, 0.34, "#4dabf7", 95)
pell(hc[0], t_, 0.95, 0.34, w=0.2, colour="#1864ab")
parc(hc[0], t_ + 2.3, MR_, MRY_, 0.15, math.pi * 0.62, w=0.22, colour="#1864ab", op=55, n=16)  # etched name band
parc(hc[0], t_ + 3.3, MR_, MRY_, 0.2, math.pi * 0.5, w=0.18, colour="#1864ab", op=45, n=16)
vcyl(hc[0], t_ - 2.2, t_, 0.5, 0.18, col="#e9ecef", dark="#868e96", top="#f8f9fa", w=0.3)  # shaft
# front of the table: two green palm buttons at the ends, a small e-stop with a yellow collar in the middle
for bx_ in (30.0, 60.0):
    c_ = P(bx_, 79, -6)
    d_ = (c_[0] - 0.3, c_[1] - 0.25)
    cell(c_[0] + 0.35, c_[1] + 0.35, 2.1, 2.1, "#343a40", 18)
    cell(*c_, 2.0, 2.0, "#adb5bd", 85)
    pell(*c_, 2.0, 2.0, w=0.36)
    knockout(ell_full(*d_, 1.4, 1.4))
    cell(*d_, 1.4, 1.4, "#40c057", 88)
    cell(d_[0] + 0.3, d_[1] + 0.3, 0.9, 0.9, "#2f9e44", 50)
    cell(d_[0] - 0.5, d_[1] - 0.5, 0.36, 0.26, "#ffffff", 80)
    pell(*d_, 1.4, 1.4, w=0.28, colour="#1b5e20")
ec = P(45, 79.2, -6)
cell(ec[0] + 0.25, ec[1] + 0.25, 1.7, 1.7, "#343a40", 14)
cell(*ec, 1.6, 1.6, "#fcc419", 80)
pell(*ec, 1.6, 1.6, w=0.3, colour="#e67700")
cell(ec[0] - 0.15, ec[1] - 0.15, 1.0, 1.0, "#f03e3e", 88)
cell(ec[0] + 0.1, ec[1] + 0.1, 0.6, 0.6, "#c92a2a", 45)
cell(ec[0] - 0.5, ec[1] - 0.5, 0.25, 0.18, "#ffffff", 75)
pell(ec[0] - 0.15, ec[1] - 0.15, 1.0, 1.0, w=0.24, colour="#a61e1e")
OVER[0] = False

# ---------------- character ----------------
granulate([P(54, 8, 2), P(54, 8, 26), P(54, 44, 26), P(54, 44, 2)], "#495057", n=24, op=30)
granulate([P(64, 72, -6), P(64, 72, 14), P(64, 84, 14), P(64, 84, -6)], "#495057", n=18, op=32)
granulate([P(22, 85, -8), P(68, 85, -8), P(68, 87, -8), P(22, 87, -8)], "#868e96", n=12, op=25)
wash([P(56, 6, 2), P(62, 2, 10), P(63, 14, 10), P(57, 17, 2)], "#4dabf7", 9, layers=1)  # wet-in-wet bloom
wash([P(18, 70, -6), P(30, 70, -6), P(28, 77, -6), P(18, 78, -6)], GLASS, 11, layers=1)
for p, q in [
    (P(35.5, 8.6, 2), P(48, 8.6, 2)),
    (P(26.6, 75, -6), P(26.6, 81, -6)),
    (P(34.6, 56, 16), P(34.6, 64, 16)),
    (P(28, 72.5, -6), P(40, 72.5, -6)),
]:
    ink(p, q, w=0.7, colour="#ffffff", over=(0, 0.2), restate=0, bow=0.1)
splatter(50, 45, 44, 54, n=10, bbox=(8, -14, 96, 96))
for p, q in [((12, 24), (16, 21)), ((90, 40), (94, 37)), ((88, 84), (91, 80)), ((14, 60), (17, 57))]:
    ink(p, q, w=0.5, over=(0, 0.6), restate=0, bow=0.6)
