"""Field Notes example, 3D: a stator winding machine, very detailed. The approved reference for the style.

Oblique view from the front right and above. Big forms (the cabinets, the window, the ground shadow) are loose
washes and loose ink; the work area, spools, tensioner, HMI and tower light are drawn precisely. Repeats are never
copies: each coil, spool and lamp is wound, filled and lit differently.

Build it with: inkwash.py build examples/winding_machine.py --out OUT
"""

import itertools
import math
from typing import Any

from kit import (
    ALU,
    ALU_L,
    COOL,
    COPPER,
    COPPER_D,
    DARK,
    GLASS,
    INK,
    OVER,
    SHADE,
    STEEL,
    STEEL_D,
    _stroke,
    arc,
    band,
    bk,
    blob,
    box,
    cell,
    cfill,
    dot,
    ell_full,
    ell_pts,
    granulate,
    ink,
    knockout,
    loop,
    parc,
    pdot,
    pell,
    pline,
    prpoly,
    recess,
    rnd,
    rpoly,
    soft,
    tube,
    wash,
)

NAME = "Winding machine"

# ================= Winding machine: detailed, built as real 3D forms =================
# Oblique view from the front-right and above; depth runs up-right: one unit back = (+1, -0.7).
# Light from the upper left: tops near paper white, fronts mid, right-hand faces in shade,
# cast shadows fall to the right and back.


# ---------------- washes (colour first, under the ink) ----------------
# ground shadow: falls right and back, darker where the cabinet meets the floor
wash([(12, 91), (75, 91.5), (86, 84.5), (104, 82), (98, 90), (78, 96.5), (16, 97)], "#868e96", 16, layers=2)
wash([(14, 90.6), (75, 91), (85, 84), (88, 86), (76, 93.4), (15, 93.6)], "#495057", 22, layers=1)

# --- lower cabinet ---
wash([(15, 63.5), (73, 63), (73.5, 89), (14.5, 89)], STEEL, 15, layers=1)  # front, light grey
wash([(15, 84), (73, 83.5), (73.5, 89.4), (14.5, 89.6)], STEEL_D, 18, layers=1)  # darker toward the floor
for dx0, dx1 in [(16, 43), (45, 72)]:  # door insets: shade on top/left inner edge
    wash([(dx0, 65), (dx1, 65), (dx1 - 1, 66.4), (dx0 + 1.4, 66.6), (dx0 + 1.4, 86.5), (dx0, 87)], SHADE, 24, layers=1)
wash(
    [(78, 61.5), (85.4, 56), (85.4, 82.3), (78, 87.6)],
    SHADE,
    26,
    layers=2,
    pool=[(78.2, 62), (80.6, 60.6), (80.6, 86), (78.2, 87.6)],
)  # side, white strip left at the turn
wash([(83.6, 56), (85.4, 55), (85.4, 82), (83.6, 83.2)], "#ffffff", 35, layers=1)  # reflected light at the back edge

# --- upper enclosure ---
wash([(14.5, 25.5), (73.5, 25.5), (73.5, 60), (14.5, 60)], COOL, 20, layers=1)  # bezel around the window
wash(
    [(78, 24.8), (85.4, 19.4), (85.4, 52.6), (78, 58)],
    SHADE,
    26,
    layers=2,
    pool=[(78.2, 26), (80.6, 24.6), (80.6, 57), (78.2, 58)],
)
wash([(83.6, 19.6), (85.4, 18.6), (85.4, 52), (83.6, 53.3)], "#ffffff", 35, layers=1)
wash(
    [(30, 18.2), (80, 18.0), (76, 21.6), (34, 22.2)], "#e9ecef", 30, layers=1
)  # top: a breath of grey at the back only
# HMI arm casts a shadow on the side face

# --- window: recessed work area seen through glass ---
wash([(21, 27.4), (72.6, 27.4), (72.6, 53.6), (21, 53.6)], "#c5d6e2", 24, layers=1)  # back panel, cool blue-grey
wash([(18.3, 29.2), (21, 27.4), (21, 53.8), (18.3, 55.8)], "#343a40", 34, layers=1)  # left inner wall in shade
wash([(18.5, 29.2), (70, 29.2), (72.5, 27.6), (21, 27.6)], "#343a40", 26, layers=1)  # cast shadow under the top frame
wash([(18.5, 55.8), (21, 53.8), (72.6, 53.8), (70, 55.8)], "#e9ecef", 30, layers=1)  # floor, lit
wash([(19, 30), (69, 30), (69.5, 55), (19, 55)], GLASS, 10, layers=1)  # glass tint, loose
wash([(22, 53), (31, 30), (35, 30), (26, 54)], "#ffffff", 45, layers=1)  # glass reflection band (lifted paint)
wash([(60, 54.5), (67, 31), (68.5, 31), (62, 54.5)], "#ffffff", 40, layers=1)

# --- stator in its fixture ---
SC = (33, 43)
SR = 8.6
SD = 2.6
wash(ell_pts(*bk(SC, SD), SR, SR, 12), STEEL_D, 30, layers=1)  # back face (body depth)
wash(ell_pts(*SC, SR, SR, 12), STEEL, 40, layers=2, pool=[(36, 46), (41, 41), (41.5, 46), (37, 51)])
COILS = []  # each coil wound separately: slightly different
for k in range(9):  # size, fullness and light, never a copy
    a = -math.pi / 2 + k * 2 * math.pi / 9
    rr = 5.3 + rnd.uniform(-0.12, 0.12)
    cx, cy = SC[0] + rr * math.cos(a), SC[1] + rr * math.sin(a)
    cr = 1.5 + rnd.uniform(-0.12, 0.1)
    lit = max(0.0, -(math.cos(a) * 0.7 + math.sin(a) * 0.7))  # 1 = facing the light (upper left)
    COILS.append((a, cx, cy, cr, lit))
cell(*SC, 2.2, 2.2, "#343a40", 70)  # bore

# --- top: spools, tensioner, tower light ---

# --- HMI on its swing arm ---
wash([(91, 22), (105, 22), (105, 34.5), (91, 34.5)], "#e9ecef", 40, layers=1)
wash([(105, 22), (107, 20.6), (107, 33.1), (105, 34.5)], SHADE, 40, layers=1)
cfill([(92.7, 23.7), (103.3, 23.7), (103.3, 30.5), (92.7, 30.5)], "#1c7ed6", 62)
blob([(99.5, 24.4), (102.8, 24.2), (102.8, 30.0), (100.2, 30.0)], "#1864ab", 30, wob=0.2)  # screen: the colour pop
wash([(94, 30), (97.5, 24), (99, 24), (95.5, 30.4)], "#ffffff", 45, layers=1)
for bx, col in [(95.0, "#40c057"), (98.0, "#fab005"), (101.0, "#fa5252")]:  # buttons: equal, on one line, centred
    cell(bx, 32.6, 0.65, 0.65, col, 80)
    cell(bx - 0.2, 32.4, 0.22, 0.2, "#ffffff", 70)
    pell(bx, 32.6, 0.65, 0.65, w=0.3, colour=INK, op=85)
wash([(91, 34.6), (107, 33.2), (105, 36.5), (93, 37)], "#495057", 18, layers=1)

# --- e-stop on the lower cabinet ---
EX, EY = 67.5, 68.6  # e-stop: small and quiet, flat on the door; just enough depth to read as a button


def fwd(p: tuple[float, float], d: float) -> tuple[float, float]:
    return (p[0] - d, p[1] + 0.7 * d)


R, DEP = 1.2, 0.45  # shallow: a lip, not a cylinder
c0, c1 = (EX, EY), fwd((EX, EY), DEP)
cell(*c0, R + 0.4, R + 0.4, "#adb5bd", 30)  # faint bezel, same family as the door
cell(c0[0] + 0.3, c0[1] + 0.25, R, R, "#343a40", 22)  # small soft shadow, down-right
OVER[0] = True
cell(*c0, R, R, "#a61e1e", 85)  # depth: only a crescent of the side shows
knockout(ell_full(*c1, R, R))
cell(*c1, R, R, "#f03e3e", 80)  # face
cell(c1[0] - 0.4, c1[1] - 0.4, 0.38, 0.28, "#ffffff", 60)  # light, upper left
pell(*c1, R, R, w=0.38, colour="#a61e1e", op=90)
OVER[0] = False

# granulation where pigment settles
granulate([(78.5, 24), (85.5, 19), (85.5, 82), (78.5, 88)], "#495057", n=40, op=35)
granulate([(15, 64), (73, 64), (73, 89), (15, 89)], "#868e96", n=30, op=25)
granulate([(12, 91), (100, 84), (95, 96), (16, 97)], "#495057", n=24, op=30)
granulate([(21, 28), (72, 28), (72, 53), (21, 53)], "#5c6b78", n=20, op=25)
# wet-in-wet blooms: colour drifting across forms
wash([(79, 30), (87, 22), (88, 40), (79.5, 46)], "#4dabf7", 16, layers=1)
wash([(74, 63), (88, 58), (89, 70), (76, 76)], "#a9785a", 12, layers=1)
wash([(12, 57), (38, 57), (32, 65), (12, 66)], GLASS, 12, layers=1)

# ---------------- ink ----------------
# cabinet silhouettes: corners are curves inside the stroke; inner edges are soft and broken
rpoly([(13, 61), (13, 24), (23, 17), (85, 17), (85, 53), (75, 60)], r=4.0, w=1.0)
soft((16, 24.2), (72.5, 24.2))
soft((75.2, 27), (75.2, 58))
soft((77.2, 22.6), (83, 18.6))
ink((77.4, 27), (77.6, 44), w=0.3, over=(0, 0.5), restate=0, op=55, bow=0.3)
rpoly([(13, 61.5), (13, 90), (75, 90), (85, 83), (85, 53)], r=4.0, w=1.0)
soft((14, 61.4), (74, 61.4), w=0.6, op=90)
soft((75.2, 63), (75.2, 88))
ink((77.4, 64), (77.6, 80), w=0.3, over=(0, 0.5), restate=0, op=55, bow=0.3)
ink((14, 60.8), (74.5, 60.8), w=1.2, over=(0, 0.6), restate=0, op=85)  # dark crevice between the two cabinets

# window opening and the depth of its recess
rpoly([(18, 29), (70, 29), (70, 56), (18, 56)], r=2.5, closed=True, w=0.75, over=(0.2, 0.9))
ink((18.6, 29.4), (21, 27.6), w=0.4, over=(0, 0.3), restate=0, op=80)
ink((21, 27.6), (72.6, 27.6), w=0.35, over=(0, 0.6), restate=0, op=60)
ink((21, 27.6), (21, 53.8), w=0.35, over=(0, 0.6), restate=0, op=60)
ink((21, 53.8), (69, 53.8), w=0.3, over=(0, 0.6), restate=0, op=45)
ink((18.6, 55.6), (21, 53.8), w=0.35, over=(0, 0.3), restate=0, op=70)
for hy in (33, 50):  # door hinges and handle
    ink((15.8, hy), (15.8, hy + 2.4), w=0.9, over=(0, 0.2), restate=0)
ink((72.2, 37), (72.2, 47), w=1.0, over=(0, 0.3), restate=0)
ink((72.9, 37.4), (72.9, 46.6), w=0.5, over=(0, 0.2), restate=0, op=60)

# stator: front ring, body depth, teeth, bore
loop(*SC, SR, SR, w=0.95)
n_ = (0.573, 0.819)
for sgn in (1, -1):
    p = (SC[0] + sgn * SR * n_[0], SC[1] + sgn * SR * n_[1])
    ink(p, bk(p, SD), w=0.6, over=(0, 0.3), restate=0)
bc = bk(SC, SD)
arc(bc[0], bc[1], SR, SR, -2.2, 0.9, w=0.6, over=(0, 0.3), restate=0)
for k in range(9):
    a = -math.pi / 2 + k * 2 * math.pi / 9
    for da in (-0.2, 0.2):  # tooth tip (shoe) between bore and coil
        pline(
            (SC[0] + 2.4 * math.cos(a + da), SC[1] + 2.4 * math.sin(a + da)),
            (SC[0] + 3.8 * math.cos(a + da * 0.5), SC[1] + 3.8 * math.sin(a + da * 0.5)),
            w=0.3,
        )
    pline(
        (SC[0] + 6.8 * math.cos(a), SC[1] + 6.8 * math.sin(a)),
        (SC[0] + 7.6 * math.cos(a), SC[1] + 7.6 * math.sin(a)),
        w=0.3,
        op=70,
    )
pell(*SC, 2.2, 2.2, w=0.5)


# coils: end-turns of wire wrapped round each tooth: lumpy bundles, longer than wide, each one wound differently,
# lit from the upper left. They stand proud of the stator face, so they go in the front layer.
def coil_pts(cx, cy, a, rad, tan, bulge, ph, n=28):
    ux, uy = math.cos(a), math.sin(a)
    vx, vy = -uy, ux
    P = []
    for i in range(n):
        t = 2 * math.pi * i / n
        k = 1 + bulge * math.sin(2 * t + ph) + 0.04 * math.sin(3 * t + ph * 2)
        r_, s_ = rad * math.cos(t) * k, tan * math.sin(t) * k
        P.append((cx + ux * r_ + vx * s_, cy + uy * r_ + vy * s_))
    return P


OVER[0] = True
for a, cx, cy, cr, lit in COILS:
    rad, tan = cr * rnd.uniform(1.05, 1.2), cr * rnd.uniform(0.78, 0.9)
    P = coil_pts(cx, cy, a, rad, tan, rnd.uniform(0.03, 0.09), rnd.uniform(0, 6.3))
    knockout(P)
    cfill(P, "#ffa94d" if lit > 0.5 else COPPER, int(70 + 15 * lit))
    sh = coil_pts(
        cx + 0.35, cy + 0.3, a, rad * 0.75, tan * 0.7, 0.05, rnd.uniform(0, 6.3)
    )  # body shade, always down-right
    cfill(sh, COPPER_D, int(30 + 35 * (1 - lit)))
    if lit > 0.2:
        cfill(
            coil_pts(cx - 0.45 * tan, cy - 0.45 * tan, a + 0.6, rad * 0.35, tan * 0.18, 0.0, 0),
            "#ffffff",
            int(45 + 45 * lit),
        )

    def mm(pp, cx=cx, cy=cy):  # weight by outward normal: lit side thin, shadow side full
        out = []
        for x_, y_ in pp:
            dx, dy = x_ - cx, y_ - cy
            l = math.hypot(dx, dy) or 1
            out.append(max(0.35, 1 + 0.75 * (dx / l * 0.6 + dy / l * 0.8)))
        return out

    A_ = P[:16]
    B_ = P[13:] + P[:3]
    _stroke(A_, 0.3, COPPER_D, 100, mult=mm(A_))
    _stroke(B_, 0.3, COPPER_D, 100, mult=mm(B_))
    ux, uy = math.cos(a), math.sin(a)
    vx, vy = -uy, ux
    nt = rnd.choice([1, 2, 2])
    ts = sorted(rnd.uniform(-0.1, 0.6) for _ in range(nt))
    for t in ts:  # a turn or two of wire, toward the shadow side
        hl = tan * math.sqrt(max(0.05, 1 - t * t)) * 0.85
        bow = rnd.uniform(0.15, 0.35) * (1 if t > 0 else -1)
        c0_ = (cx + ux * t * rad, cy + uy * t * rad)
        _stroke(
            [
                (c0_[0] + vx * hl * u + ux * bow * (1 - u * u), c0_[1] + vy * hl * u + uy * bow * (1 - u * u))
                for u in [i / 6 - 1 for i in range(13)]
            ],
            rnd.uniform(0.14, 0.22),
            COPPER_D,
            rnd.choice([45, 60]),
        )
OVER[0] = False


# HMI: slab with a screen, on an arm from the side face
box(91, 22, 105, 34.5, 2.0, fo=0, so=0, to=0, w=0.6)  # HMI housing: rounded silhouette, soft inner edges

# screen: what an operator actually sees while winding: header bar, progress ring, readouts, a trend, a RUN status
OVER[0] = True
knockout([(92.7, 23.7), (103.3, 23.7), (103.3, 30.5), (92.7, 30.5)])
cfill([(92.7, 23.7), (103.3, 23.7), (103.3, 30.5), (92.7, 30.5)], "#1864ab", 80)
cfill([(92.7, 23.7), (103.3, 23.7), (103.3, 24.7), (92.7, 24.7)], "#0b3b66", 85)  # header bar
_stroke([(93.2, 24.2), (95.4, 24.2)], 0.22, "#e7f5ff", 95, taper=False)  # title
for k_, cx_ in enumerate((101.2, 101.9, 102.6)):
    pdot(cx_, 24.2, 0.17, ["#e7f5ff", "#e7f5ff", "#69db7c"][k_], 95)
GC = (95.3, 27.5)  # progress ring: turns done
_stroke(
    [
        (GC[0] + 1.6 * math.cos(t), GC[1] + 1.6 * math.sin(t))
        for t in [math.radians(-90 + 360 * i / 40) for i in range(41)]
    ],
    0.28,
    "#4a7fb0",
    90,
    taper=False,
)
_stroke(
    [
        (GC[0] + 1.6 * math.cos(t), GC[1] + 1.6 * math.sin(t))
        for t in [math.radians(-90 + 270 * i / 30) for i in range(31)]
    ],
    0.42,
    "#8ce99a",
    100,
    taper=False,
)
_stroke([(94.7, 27.4), (95.9, 27.4)], 0.3, "#ffffff", 100, taper=False)
_stroke([(94.9, 28.0), (95.7, 28.0)], 0.18, "#a5d8ff", 95, taper=False)
for k_, (ln, yy) in enumerate([(3.0, 25.6), (2.2, 26.4), (2.6, 27.2)]):  # readouts: label + value
    _stroke([(97.8, yy), (97.8 + ln * 0.45, yy)], 0.18, "#a5d8ff", 90, taper=False)
    _stroke([(99.6, yy), (99.6 + ln * 0.5, yy)], 0.26, "#ffffff", 100, taper=False)
for k_, hgt in enumerate([0.8, 1.3, 1.0, 1.6, 1.2, 1.9, 1.5]):  # tension trend
    _stroke([(97.9 + k_ * 0.55, 29.9), (97.9 + k_ * 0.55, 29.9 - hgt)], 0.3, "#74c0fc", 100, taper=False)
knockout([(93.6, 29.3), (96.9, 29.3), (96.9, 30.1), (93.6, 30.1)])
cfill([(93.6, 29.3), (96.9, 29.3), (96.9, 30.1), (93.6, 30.1)], "#2f9e44", 90)  # RUN status
_stroke([(94.2, 29.7), (96.3, 29.7)], 0.2, "#ffffff", 100, taper=False)
_stroke([(93.4, 30.2), (96.6, 23.9)], 0.5, "#ffffff", 22, taper=False)  # glare on the glass
OVER[0] = False
OVER[0] = True
prpoly([(92.6, 23.6), (103.4, 23.6), (103.4, 30.6), (92.6, 30.6)], r=0.5, w=0.4)
OVER[0] = False


# swing arm: bracket bolted to the side face, a tube out to a pivot, a second link up to the tilt hub behind the HMI
def side(d: float, h: float) -> tuple[float, float]:
    return (78 + d, h - 0.7 * d)  # a point on the cabinet's right face


br = [side(4.0, 36.0), side(6.2, 36.0), side(6.2, 40.6), side(4.0, 40.6)]
cfill(br, "#adb5bd", 85)
cfill([br[1], (br[1][0] + 0.6, br[1][1]), (br[2][0] + 0.6, br[2][1]), br[2]], DARK, 60)
for p1, p2 in zip(br, br[1:] + br[:1]):
    pline(p1, p2, w=0.35)
for d_, h_ in [(4.5, 36.7), (5.7, 36.7), (4.5, 39.9), (5.7, 39.9)]:
    pdot(*side(d_, h_), 0.17, DARK)
OVER[0] = True
P0, P1, P2 = (83.3, 34.4), (88.2, 35.0), (91.1, 32.0)
knockout([(83.1, 33.7), (88.6, 34.2), (90.9, 31.4), (90.9, 32.8), (88.6, 36.2), (83.1, 35.2)])
tube(P0, P1, 1.0)
tube(P1, P2, 0.9)
cell(P1[0], P1[1] - 0.9, 0.85, 0.32, ALU, 90)
cfill(band(P1[0], P1[1] - 0.9, P1[1] + 0.9, 0.85, 0.32), "#ced4da", 90)  # pivot
cfill(band(P1[0] + 0.25, P1[1] - 0.9, P1[1] + 0.9, 0.45, 0.32), SHADE, 30)
pell(P1[0], P1[1] - 0.9, 0.85, 0.32, w=0.35)
parc(P1[0], P1[1] + 0.9, 0.85, 0.32, 0, math.pi, w=0.4)
pline((P1[0] - 0.85, P1[1] - 0.9), (P1[0] - 0.85, P1[1] + 0.9), w=0.35)
pline((P1[0] + 0.85, P1[1] - 0.9), (P1[0] + 0.85, P1[1] + 0.9), w=0.4)
pdot(P1[0], P1[1] - 0.9, 0.15, DARK)
OVER[0] = False
# cable: from the bottom of the HMI, sagging under its own weight, into a gland on the side face
gl = side(5.0, 42.6)
cab = [
    (96.5 + (gl[0] - 96.5) * t, 34.4 + (gl[1] - 34.4) * t + 4.2 * math.sin(math.pi * t) ** 1.3)
    for t in [i / 24 for i in range(25)]
]
_stroke(cab, 0.42, DARK, 90)
cell(gl[0], gl[1], 0.45, 0.6, "#495057", 90)
pell(gl[0], gl[1], 0.45, 0.6, w=0.3)
wash(
    [side(3.2, 37.2), side(7.4, 37.0), side(7.4, 41.0), side(3.2, 42.0)], "#343a40", 14, layers=1
)  # arm and bracket shadow on the side

# lower cabinet: doors, handles, louvres, e-stop, feet
# doors sit in recesses: the frame shades their top and left inner edges (heavy), the bottom and right catch light (thin)
for dx0, dx1 in ((16, 43), (45, 72)):
    with recess():  # the frame shades the door's top and left edges: weight flips to the top left, strongly
        prpoly([(dx0, 65), (dx1, 65), (dx1, 87), (dx0, 87)], r=1.6, w=0.62)
    pline((dx0 + 0.8, 65.7), (dx1 - 1.6, 65.7), w=0.22, op=55)  # second, thinner line: the recess wall seen at the top
    pline((dx0 + 0.7, 66.2), (dx0 + 0.7, 85.8), w=0.2, op=45)
for hx, side_ in ((40.6, 1), (47.4, -1)):  # pull handles: heavy on the shadow side, a thin lit edge
    ink((hx, 72.5), (hx, 79.5), w=1.1, over=(0, 0.2), restate=0)
    ink((hx + 0.7, 72.9), (hx + 0.7, 79.1), w=0.35, over=(0, 0.1), restate=0, op=55)
    ink((hx - 0.5, 72.8), (hx - 0.5, 79.2), w=0.25, colour="#ffffff", over=(0, 0.1), restate=0)
for i, ly in enumerate((76, 78.4, 80.8, 83.2)):  # louvres: slit plus its shadow
    pline((19, ly), (31, ly), w=0.65)
    pline((19.3, ly + 0.7), (30.7, ly + 0.7), w=0.3, op=45)
for i in range(5):  # side louvres in perspective
    y = 67 + i * 3
    pline((78.4, y), (83.2, y - 3.36), w=0.45)
for fx, fy in [(17, 90.6), (71, 90.6), (83, 84)]:  # levelling feet
    cfill(band(fx, fy + 1.0, fy + 2.0, 1.8, 0.6), "#495057", 80)
    pline((fx - 0.5, fy), (fx - 0.5, fy + 1.0), w=0.5)
    pline((fx + 0.5, fy), (fx + 0.5, fy + 1.0), w=0.5)
    parc(fx, fy + 1.0, 1.8, 0.6, math.pi, 2 * math.pi, w=0.4)
    parc(fx, fy + 2.0, 1.8, 0.6, 0, math.pi, w=0.6)
    pline((fx - 1.8, fy + 1.0), (fx - 1.8, fy + 2.0), w=0.5)
    pline((fx + 1.8, fy + 1.0), (fx + 1.8, fy + 2.0), w=0.5)

# white gel: a few broken highlights on lit edges and the glass
for p, q in [
    ((23, 50), (29, 33)),
    ((25.5, 51), (30.5, 38)),
    ((76.5, 27), (76.5, 36)),
    ((92.2, 26), (92.2, 29.5)),
    ((30, 23.2), (48, 23.2)),
    ((79, 20.2), (83, 17.6)),
    ((15.2, 66), (15.2, 72)),
    ((44, 23.4), (66, 23.4)),
]:
    ink(p, q, w=0.75, colour="#ffffff", over=(0, 0.2), restate=0, bow=0.1)


# ================= work area: indexing fixture, linear axis, needle arm (drawn precisely) =================
# A needle winder: the stator is clamped in a 3-jaw indexing fixture on a pedestal; a vertical linear axis
# (two guide rails + ball screw, servo motor at the top, cable chain looping beside it) carries a carriage
# whose arm holds the needle; wire runs down from the roof, through a guide roller and out of the needle tip.


# back-wall mounting plate behind the axis, with its bolts
cfill([(53.5, 28.2), (66.5, 28.2), (66.5, 53.4), (53.5, 53.4)], "#adb5bd", 28)
pline((53.5, 28.6), (53.5, 53.4), w=0.3, op=55)
pline((53.5, 53.4), (66.5, 53.4), w=0.3, op=45)
for bx, by in [(54.6, 30.0), (65.4, 30.0), (54.6, 52.2), (65.4, 52.2)]:
    pdot(bx, by, 0.28, "#495057", 90)

# linear axis: base, two guide rails, ball screw with an even thread, end block
RX0, RX1, RY0, RY1 = 56.4, 60.6, 29.0, 52.6
cfill([(RX0, RY0), (RX1, RY0), (RX1, RY1), (RX0, RY1)], "#ced4da", 55)
cfill([(RX1, RY0), bk((RX1, RY0), 0.9), bk((RX1, RY1), 0.9), (RX1, RY1)], SHADE, 50)
pline((RX0, RY0), (RX0, RY1), w=0.35)
pline((RX1, RY0), (RX1, RY1), w=0.6)
pline(bk((RX1, RY0), 0.9), bk((RX1, RY1), 0.9), w=0.3, op=70)
for gx in (57.1, 59.9):  # guide rails
    cfill([(gx - 0.3, RY0), (gx + 0.3, RY0), (gx + 0.3, RY1), (gx - 0.3, RY1)], "#868e96", 60)
    pline((gx + 0.3, RY0), (gx + 0.3, RY1), w=0.24, op=70)
pline((59.0, RY0), (59.0, RY1), w=0.22, op=55)  # ball screw: one shadow-side edge
y = RY0 + 0.5
while y < RY1 - 0.3:
    pline((58.0, y + 0.3), (59.0, y), w=0.18, colour="#495057", op=60)
    y += 1.05
box(RX0 - 0.4, RY1 - 1.2, RX1 + 0.4, RY1 + 0.6, 0.9, front="#adb5bd", fo=70)  # end block on the floor
# servo motor at the top: body runs up behind the bezel, so only its lower part shows
box(56.2, 29.0, 60.8, 32.2, 1.6, front=DARK, side="#212529", top=DARK, fo=80, so=80, to=0)
for k in range(4):  # cooling fins
    pline((56.8 + k * 1.15, 29.4), (56.8 + k * 1.15, 31.7), w=0.2, colour="#868e96", op=80)
pline((56.2, 32.6), (60.8, 32.6), w=0.3, op=70)  # coupling flange line


# cable chain: fixed at the top of the axis, loops round and follows the carriage
def chain(path, wid=1.1, links=14):
    L = [0.0]
    for a, b in itertools.pairwise(path):
        L.append(L[-1] + math.dist(a, b))

    def at(s):
        for i in range(len(path) - 1):
            if L[i + 1] >= s:
                t = (s - L[i]) / ((L[i + 1] - L[i]) or 1)
                a, b = path[i], path[i + 1]
                tx_, ty_ = b[0] - a[0], b[1] - a[1]
                n = math.hypot(tx_, ty_) or 1
                return (a[0] + tx_ * t, a[1] + ty_ * t), (-ty_ / n, tx_ / n)
        a, b = path[-2], path[-1]
        n = math.dist(a, b) or 1
        return b, (-(b[1] - a[1]) / n, (b[0] - a[0]) / n)

    N = 60
    inner, outer = [], []
    for i in range(N + 1):
        p, nrm = at(L[-1] * i / N)
        inner.append((p[0] - nrm[0] * wid / 2, p[1] - nrm[1] * wid / 2))
        outer.append((p[0] + nrm[0] * wid / 2, p[1] + nrm[1] * wid / 2))
    cfill(inner + outer[::-1], "#495057", 70)
    _stroke(inner, 0.35, INK, 90)
    _stroke(outer, 0.35, INK, 90)
    for i in range(1, links):
        p, nrm = at(L[-1] * i / links)
        pline(
            (p[0] - nrm[0] * wid / 2, p[1] - nrm[1] * wid / 2),
            (p[0] + nrm[0] * wid / 2, p[1] + nrm[1] * wid / 2),
            w=0.25,
            colour="#adb5bd",
            op=90,
        )


loop_pts = (
    [(56.0, 33.6)]
    + [
        (52.6 + 2.0 * math.cos(a), 35.6 - 2.0 * math.sin(a))
        for a in [math.pi / 2 + math.pi * i / 12 for i in range(13)]
    ]
    + [(56.0, 37.6)]
)
chain(loop_pts)

# carriage on the rails, with its arm reaching left to the needle holder (stands in front of the stator ring)
OVER[0] = True
knockout(
    [(55.4, 36.4), bk((55.4, 36.4), 1.6), bk((62.0, 36.4), 1.6), bk((62.0, 44.6), 1.6), (62.0, 44.6), (55.4, 44.6)]
)
knockout([(42.4, 37.8), bk((42.4, 37.8), 1.0), bk((55.4, 38.6), 1.0), (55.4, 41.6), (42.4, 41.6)])
box(44.6, 38.6, 56.4, 40.6, 1.0, front=ALU_L, fo=85, so=50)  # arm
cfill([(44.6, 40.6), (55.4, 40.6), (55.4, 41.3), (44.6, 41.3)], DARK, 18)  # arm's shadow under it
knockout(
    [(55.4, 36.4), bk((55.4, 36.4), 1.6), bk((62.0, 36.4), 1.6), bk((62.0, 44.6), 1.6), (62.0, 44.6), (55.4, 44.6)]
)  # carriage stands in front of the arm's root
box(55.4, 36.4, 62.0, 44.6, 1.6, front=ALU, fo=85)  # carriage
for bx, by in [(56.4, 37.4), (61.0, 37.4), (56.4, 43.6), (61.0, 43.6)]:
    pdot(bx, by, 0.26, DARK)
cfill([(57.2, 39.4), (60.2, 39.4), (60.2, 41.4), (57.2, 41.4)], "#ffffff", 90)  # small label plate
pline((57.6, 40.1), (59.6, 40.1), w=0.18, colour="#868e96")
pline((57.6, 40.8), (59.0, 40.8), w=0.18, colour="#868e96")
box(42.4, 37.8, 44.6, 41.6, 1.0, front="#adb5bd", fo=85)  # needle holder
pdot(43.5, 38.9, 0.22, DARK)
# needle: a fine tapered tube pointing into a slot; wire leaves the tip and runs into the coil
NT = (39.4, 42.3)
cfill([(42.4, 40.0), (42.4, 41.2), (NT[0] + 0.15, NT[1] + 0.2), (NT[0], NT[1] - 0.1)], "#495057", 95)
pline((42.4, 40.0), NT, w=0.35)
pline((42.4, 41.2), (NT[0] + 0.15, NT[1] + 0.2), w=0.35)
pline((42.1, 40.3), (40.2, 41.8), w=0.2, colour="#ffffff", op=90)  # glint along the needle
_stroke(
    [(NT[0], NT[1] + 0.05), (38.9, 42.4), (38.3, 42.1), (37.9, 41.7)], 0.4, COPPER, 100
)  # wire from the tip into the coil
OVER[0] = False
# wire: down from the roof, round a guide roller on the motor bracket, into the carriage
pline((61.6, 29.0), (61.6, 33.4), w=0.26, colour=COPPER_D, op=90)
cell(61.6, 34.0, 0.6, 0.6, ALU, 90)
pell(61.6, 34.0, 0.6, 0.6, w=0.3)
pdot(61.6, 34.0, 0.15, DARK)
pline((61.1, 34.4), (60.4, 36.0), w=0.26, colour=COPPER_D, op=90)

# indexing fixture: pedestal on the floor with a saddle, three clamp jaws on the stator (in front of the ring)
PX0, PX1, PY0, PY1 = 29.0, 37.0, 51.8, 55.2
box(PX0, PY0, PX1, PY1, 2.2, front="#adb5bd", fo=75, so=60, to=0)
cfill([(PX0, PY0), bk((PX0, PY0), 2.2), bk((PX1, PY0), 2.2), (PX1, PY0)], "#e9ecef", 60)
pdot(30.0, 53.6, 0.25, DARK)
pdot(36.0, 53.6, 0.25, DARK)
OVER[0] = True
for ang_deg in (270, 30, 150):  # three jaws, 120 degrees apart, one at the top
    a = math.radians(ang_deg)
    ux, uy = math.cos(a), math.sin(a)
    vx, vy = -uy, ux
    r0, r1, hw = SR - 0.5, SR + 1.3, 0.8
    q = [
        (SC[0] + ux * r0 + vx * hw, SC[1] + uy * r0 + vy * hw),
        (SC[0] + ux * r1 + vx * hw, SC[1] + uy * r1 + vy * hw),
        (SC[0] + ux * r1 - vx * hw, SC[1] + uy * r1 - vy * hw),
        (SC[0] + ux * r0 - vx * hw, SC[1] + uy * r0 - vy * hw),
    ]
    knockout(q)
    cfill(q, "#495057", 85)
    cfill([q[1], bk(q[1], 0.9), bk(q[2], 0.9), q[2]], DARK, 70)
    for p1, p2 in zip(q, q[1:] + q[:1]):
        pline(p1, p2, w=0.35)
    pdot((q[1][0] + q[2][0]) / 2 - ux * 0.5, (q[1][1] + q[2][1]) / 2 - uy * 0.5, 0.2, "#adb5bd")
OVER[0] = False

# T-slot table on the floor of the work area, lines running back in depth
for tx_ in (23.0, 41.0, 47.0, 66.0):
    pline((tx_, 55.6), bk((tx_, 55.6), 2.4), w=0.25, colour="#868e96", op=80)

# ================= top of the machine: wire spools, tensioner, tower light (drawn precisely) =================
# Magnet-wire bobbins on a payoff plate: dark plastic flanges with thickness, a hub with a spindle,
# copper wound body (lit band on the left, core shade, reflected light on the right, fine winding lines,
# a paper label), wire pulled off the top through a pigtail guide, over to a felt-pad tensioner and dancer.
FL, FL_D = "#495057", "#343a40"

OVER[0] = True
SPOOLS: list[
    dict[str, Any]
] = [  # two real spools, not copies: one fresh and full, one part-used; labels stuck on by hand at different turns
    {"sx": 27, "rx": 4.6, "lab": (-2.6, 1.2, 12.6, 16.2), "turns": 12, "off": (-3.6, 1.0), "shade_left": 0.0},
    {"sx": 42, "rx": 3.2, "lab": (-0.2, 2.2, 11.8, 14.6), "turns": 8, "off": (2.4, -0.6), "shade_left": 1.0},
]
for SPL in SPOOLS:
    sx = SPL["sx"]
    yt, yb, rx, ry = 9.6, 19.6, SPL["rx"], 1.6 * SPL["rx"] / 4.6  # copper body: top and bottom ellipse centres
    fr, fry, th = 5.8, 2.0, 0.9  # flange radius, flange ellipse height, flange thickness
    knockout(ell_full(sx + 0.4, yb + th + 1.1, fr + 1.5, fry + 0.6))
    # payoff plate on the roof, and the spool's cast shadow falling right and back
    cell(sx + 0.4, yb + th + 1.1, fr + 1.4, fry + 0.5, "#adb5bd", 45)
    pell(sx + 0.4, yb + th + 1.1, fr + 1.4, fry + 0.5, w=0.4, colour=FL_D, op=70)
    wash([(sx + 4.5, yb + 1.4), (sx + 11, yb - 3.0), (sx + 11.8, yb - 1.2), (sx + 6, yb + 3.2)], FL, 24, layers=1)
    knockout(band(sx, yt - th, yb + th, fr + 0.1, fry + 0.1))
    knockout(ell_full(sx, yt - th, fr + 0.1, fry + 0.1))
    # bottom flange: rim band + top face (more of it shows round a part-used spool)
    cfill(band(sx, yb, yb + th, fr, fry), FL, 70)
    cell(sx, yb, fr, fry, "#868e96", 55)
    # copper body
    cfill(band(sx, yt, yb, rx, ry), COPPER, 50)
    cfill([(sx + 1.2, yt), (sx + 3.6, yt), (sx + 3.6, yb + 1.4), (sx + 1.2, yb + 1.5)], COPPER_D, 30)  # core shade
    cfill(
        [(sx + 3.9, yt), (sx + rx - 0.2, yt), (sx + rx - 0.2, yb + 0.6), (sx + 3.9, yb + 1.0)], "#ffd8a8", 35
    )  # reflected light
    cfill(
        [(sx - 3.2, yt), (sx - 2.0, yt), (sx - 2.0, yb + 1.3), (sx - 3.2, yb + 1.1)], "#ffffff", 55
    )  # specular band on the wire
    blob(
        [(sx + 0.4, yt + 1.0), (sx + 4.4, yt + 1.0), (sx + 4.2, yb), (sx + 1.0, yb + 1.2)], COPPER_D, 18, wob=0.3
    )  # watercolour depth inside the body
    if SPL["shade_left"]:  # the first spool's shadow falls across this one
        cfill(
            [(sx - rx, yt + 2.5), (sx - rx + 1.6, yt + 2.2), (sx - rx + 2.4, yb + ry * 0.9), (sx - rx, yb + ry * 0.4)],
            "#343a40",
            22,
        )
    nt = SPL["turns"]
    hy = yt + rnd.uniform(0.4, 0.8)  # winds: many strokes, each its own pressure:
    while hy < yb + ry * 0.2:  # pressed hard on the shadow side, lifting
        a_end = math.pi * rnd.uniform(0.55, 0.92)  # off toward the light; some run nearly across,
        a_st = rnd.uniform(0.04, 0.22)  # some stop short; spacing loosens and tightens
        n_ = 18
        angs = [a_st + (a_end - a_st) * i / n_ for i in range(n_ + 1)]
        pts_ = [(sx + rx * math.cos(a_), hy + ry * math.sin(a_)) for a_ in angs]
        pk = rnd.uniform(0.75, 1.35)
        mult_ = [pk * (0.35 + 0.95 * (1 - i / n_) ** 0.8) for i in range(n_ + 1)]  # weight falls off along the stroke
        _stroke(pts_, rnd.uniform(0.2, 0.3), COPPER_D, rnd.choice([55, 70, 85]), mult=mult_)
        if rnd.random() < 0.35:  # a hair-thin companion turn right beside it
            _stroke([(x_, y_ + 0.28) for x_, y_ in pts_[: n_ // 2 + 2]], 0.14, COPPER_D, 50)
        hy += rnd.uniform(0.55, 1.05) * (yb - yt) / 10
    # label wrapped on the body
    lx0, lx1, ly0, ly1 = SPL["lab"]
    lab = [
        (sx + lx0, ly0 + ry * 0.55),
        (sx + lx1, ly0 + ry * 0.95),
        (sx + lx1, ly1 + ry * 0.95),
        (sx + lx0, ly1 + ry * 0.55),
    ]
    cfill(lab, "#f8f9fa", 85)
    for k, yy in enumerate([ly0 + 1.2 + i * 1.0 for i in range(2 if ly1 - ly0 > 3.2 else 1)]):
        pline(
            (sx + lx0 + 0.6, yy + ry * 0.6),
            (sx + lx1 - (0.6 if k else 1.4), yy + ry * 0.9),
            w=0.22,
            colour="#868e96",
            op=80,
        )
    # top flange: thickness band + top face + hub
    cfill(band(sx, yt - th, yt, fr, fry), FL, 75)
    cell(sx, yt - th, fr, fry, "#868e96", 70)
    cfill(
        [
            (sx - fr + 0.8, yt - th - 0.4),
            (sx - 1.5, yt - th - fry + 0.25),
            (sx - 0.6, yt - th - fry + 0.3),
            (sx - fr + 1.8, yt - th + 0.1),
        ],
        "#ffffff",
        45,
    )  # sheen
    cell(sx, yt - th, 1.6, 0.6, FL_D, 85)
    cell(sx, yt - th, 0.7, 0.26, "#212529", 90)
    # ink: precise ellipses and verticals
    pell(sx, yt - th, fr, fry, w=0.42, colour=INK)
    parc(sx, yt, fr, fry, 0, math.pi, w=0.55, colour=INK)
    pline((sx - fr, yt - th), (sx - fr, yt), w=0.4)
    pline((sx + fr, yt - th), (sx + fr, yt), w=0.7)
    pell(sx, yt - th, 1.6, 0.6, w=0.28, colour=INK, op=75)
    pline((sx - rx, yt + 0.4), (sx - rx, yb), w=0.32, colour=COPPER_D)
    pline((sx + rx, yt + 0.4), (sx + rx, yb), w=0.7, colour=COPPER_D)
    parc(
        sx, yb, fr, fry, math.pi + 0.5, 2 * math.pi - 0.15, w=0.3, colour=INK, op=50
    )  # bottom flange back edge, seen past the body
    parc(sx, yb + th, fr, fry, 0, math.pi, w=0.65, colour=INK)
    pline((sx - fr, yb), (sx - fr, yb + th), w=0.4)
    pline((sx + fr, yb), (sx + fr, yb + th), w=0.7)
    # spindle up through the hub to a pigtail guide; wire comes off the top edge of the winding
    pline((sx, yt - th), (sx, 2.4), w=0.45, colour=FL_D)
    pell(sx, 1.8, 0.7, 0.55, w=0.35, colour=FL_D)
    ox, oy = SPL["off"]
    _stroke(
        [
            (sx + ox - ox * t, yt - 0.4 + oy * (1 - t) - 1.0 * math.sin(math.pi * t * 0.5) - (yt - 2.4 - 1.0) * t**1.6)
            for t in [i / 12 for i in range(13)]
        ],
        w=0.28,
        colour=COPPER_D,
        op=90,
    )  # balloon of wire up to the guide
    _stroke(
        [
            (sx + (57.6 - sx) * t, 1.8 - (1.8 - 1.4) * t + 0.9 * math.sin(math.pi * t) * 0.4)
            for t in [i / 20 for i in range(21)]
        ],
        w=0.26,
        colour=COPPER_D,
        op=85,
    )  # across to the tensioner

knockout([(57.7, 23.0), (59.3, 23.0), (59.3, 0.6), (57.7, 0.6)])
# tensioner: post on a base, felt-pad block, top pulley, sprung dancer arm and pulley, feed down to the needle
cell(58.5, 23.0, 2.4, 0.8, "#adb5bd", 55)
pell(58.5, 23.0, 2.4, 0.8, w=0.4, colour=FL_D, op=80)
cfill([(57.9, 22.8), (59.1, 22.8), (59.1, 2.0), (57.9, 2.0)], "#ced4da", 70)
cfill([(58.7, 22.8), (59.1, 22.8), (59.1, 2.0), (58.7, 2.0)], SHADE, 45)
pline((57.9, 22.8), (57.9, 2.2), w=0.32)
pline((59.1, 22.8), (59.1, 2.2), w=0.65)
cfill([(56.4, 5.6), (60.6, 5.6), (60.6, 8.0), (56.4, 8.0)], "#dee2e6", 85)  # felt-pad block
cfill([(60.6, 5.6), (61.6, 4.9), (61.6, 7.3), (60.6, 8.0)], SHADE, 60)
cfill([(56.4, 5.6), (57.4, 4.9), (61.6, 4.9), (60.6, 5.6)], "#ffffff", 80)
cfill([(56.6, 6.6), (60.4, 6.6), (60.4, 7.0), (56.6, 7.0)], "#e03131", 45)  # felt
for p, q in [
    ((56.4, 5.6), (60.6, 5.6)),
    ((60.6, 5.6), (60.6, 8.0)),
    ((60.6, 8.0), (56.4, 8.0)),
    ((56.4, 8.0), (56.4, 5.6)),
    ((56.4, 5.6), (57.4, 4.9)),
    ((57.4, 4.9), (61.6, 4.9)),
    ((61.6, 4.9), (61.6, 7.3)),
    ((61.6, 7.3), (60.6, 8.0)),
    ((60.6, 5.6), (61.6, 4.9)),
]:
    pline(p, q, w=0.4)
pdot(57.4, 6.8, 0.25, FL_D)
pdot(59.7, 6.8, 0.25, FL_D)
for cx, cy, r in [(57.6, 1.4, 1.5), (56.4, 13.0, 1.3)]:  # pulleys: grooved wheels with an axle
    cell(cx, cy, r, r * 0.8, "#dee2e6", 85)
    cell(cx + 0.25, cy + 0.2, r * 0.55, r * 0.45, "#adb5bd", 70)
    pell(cx, cy, r, r * 0.8, w=0.45, colour=INK)
    pell(cx, cy, r * 0.55, r * 0.45, w=0.3, colour=FL_D, op=80)
    pdot(cx, cy, 0.28, INK)
pline((58.5, 10.4), (56.4, 13.0), w=0.5)  # dancer arm
_stroke(
    [(58.5 + 0.35 * math.sin(i * 1.3), 10.4 + i * 0.35) for i in range(9)], w=0.25, colour=FL_D, op=80
)  # its spring
pline((56.1, 1.6), (56.8, 6.3), w=0.26, colour=COPPER_D, op=85)
pline((56.8, 7.6), (55.2, 12.6), w=0.26, colour=COPPER_D, op=85)
pline((55.2, 13.4), (57.6, 24.0), w=0.26, colour=COPPER_D, op=85)

# tower light: stacked lenses on one axis, each a true cylinder; a cap on top, a pole into a round base
TX, TR, TRY = 80.0, 2.2, 0.75
tiers = [(3.2, "#fa5252"), (6.2, "#fab005"), (9.2, "#40c057")]
knockout([(TX - 0.5, 12.4), (TX + 0.5, 12.4), (TX + 0.5, 20.2), (TX - 0.5, 20.2)])
knockout(ell_full(TX, 19.9, 1.7, 0.65))
cell(TX, 2.4, TR, TRY, "#495057", 85)  # cap
cfill(band(TX, 2.4, 3.2, TR, TRY), "#495057", 85)
LAMP = {
    3.2: ("#e03131", 34, False),
    6.2: ("#f59f00", 36, False),
    9.2: ("#2f9e44", 80, True),
}  # running: green on, others off
for ty, col in tiers:
    c, o, on = LAMP[ty]
    cfill(band(TX, ty, ty + 3, TR, TRY), c, o)
    if on:  # lit lens: bright core, glow spills round it
        cfill(band(TX - 0.3, ty + 0.5, ty + 2.6, 0.9, 0.35), "#d3f9d8", 85)
        blob(ell_full(TX, ty + 1.6, 3.8, 2.6, 12), "#8ce99a", 22, wob=0.3)
    else:
        cfill(
            [(TX + 0.9, ty + 0.6), (TX + 2.0, ty + 0.4), (TX + 2.0, ty + 3.2), (TX + 0.9, ty + 3.6)],
            "#000000",
            14 + int(rnd.uniform(0, 8)),
        )  # shade side
        cfill(
            [
                (TX - 1.5, ty + 0.5),
                (TX - 1.0, ty + 0.55),
                (TX - 1.0, ty + 2.4 + rnd.uniform(0, 0.5)),
                (TX - 1.5, ty + 2.5),
            ],
            "#ffffff",
            55 + int(rnd.uniform(0, 20)),
        )  # reflection on an unlit lens
cell(TX, 12.2, TR, TRY, "#868e96", 80)
cfill([(TX - 0.35, 12.4), (TX + 0.35, 12.4), (TX + 0.35, 19.8), (TX - 0.35, 19.8)], "#495057", 80)
cell(TX, 19.9, 1.6, 0.55, "#495057", 80)
pell(TX, 2.4, TR, TRY, w=0.45)
pline((TX - TR, 2.4), (TX - TR, 12.2), w=0.4)
pline((TX + TR, 2.4), (TX + TR, 12.2), w=0.75)
for ty in (3.2, 6.2, 9.2, 12.2):
    parc(TX, ty, TR, TRY, 0, math.pi, w=0.45 if ty < 12 else 0.55)
pline((TX - 0.35, 12.95), (TX - 0.35, 19.6), w=0.35)
pline((TX + 0.35, 12.95), (TX + 0.35, 19.6), w=0.45)
pell(TX, 19.9, 1.6, 0.55, w=0.4)

OVER[0] = False

# character: splatter and flicks
for _ in range(10):
    a = rnd.uniform(0, 2 * math.pi)
    rr = rnd.uniform(50, 60)
    x, y = 56 + rr * math.cos(a), 48 + rr * math.sin(a) * 0.85
    if -4 < x < 116 and -6 < y < 102 and not (-1 < x < 111 and -1 < y < 98):
        dot(
            x,
            y,
            rnd.uniform(0.3, 0.7),
            rnd.choice([INK, INK, "#495057", "#1c7ed6", COPPER_D]),
            op=rnd.choice([100, 80]),
        )
for p, q in [((4, 30), (8, 27)), ((108, 44), (112, 41)), ((104, 70), (107, 66)), ((6, 74), (9, 71))]:
    ink(p, q, w=0.5, over=(0, 0.6), restate=0, bow=0.6)
