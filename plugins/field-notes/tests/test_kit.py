"""The drawing kit: deterministic hands, layers the renderer reads, and line weight that follows light."""

import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "skills" / "field-notes" / "scripts"))

import kit


def draw_sample():
    """A little of everything a body file does."""
    kit.bigbox(10, 40, 10, 40, 0, 12)
    kit.OVER[0] = True
    kit.knockout(kit.ell_full(20, 20, 3, 2))
    kit.vcyl(20, 15, 25, 3, 1, knock=True)
    kit.OVER[0] = False
    kit.pline((0, 0), (10, 0), normal=(0, -1))
    kit.ground(10, 40, 40)


class Determinism(unittest.TestCase):
    def test_the_same_seed_draws_the_same_sketch(self):
        kit.reset(seed=3)
        draw_sample()
        first = json.dumps(kit.els)
        kit.reset(seed=3)
        draw_sample()
        self.assertEqual(json.dumps(kit.els), first)

    def test_another_seed_draws_another_hand(self):
        kit.reset(seed=3)
        draw_sample()
        first = json.dumps(kit.els)
        kit.reset(seed=4)
        draw_sample()
        self.assertNotEqual(json.dumps(kit.els), first)

    def test_reset_empties_the_sketch_and_leaves_the_front_layer(self):
        kit.reset()
        kit.OVER[0] = True
        draw_sample()
        kit.reset(stroke=0.3, group="icon-x")
        self.assertEqual(kit.els, [])
        self.assertFalse(kit.OVER[0])
        kit.pline((0, 0), (5, 0))
        self.assertEqual(kit.els[0]["strokeWidth"], 0.3)
        self.assertEqual(kit.els[0]["groupIds"], ["icon-x"])


class Layers(unittest.TestCase):
    """render.js sorts elements into layers by type and customData; the kit has to mark them."""

    def setUp(self):
        kit.reset()

    def test_marks_made_in_front_go_to_the_front_layer(self):
        kit.pline((0, 0), (5, 0))
        kit.OVER[0] = True
        kit.pline((0, 1), (5, 1))
        kit.OVER[0] = False
        behind, front = kit.els
        self.assertNotIn("over", behind.get("customData", {}))
        self.assertTrue(front["customData"]["over"])
        self.assertTrue(front["customData"]["precise"])

    def test_a_knockout_is_paper_white_and_marked(self):
        kit.knockout([(0, 0), (4, 0), (4, 4)])
        (e,) = kit.els
        self.assertEqual(e["backgroundColor"], "#ffffff")
        self.assertTrue(e["customData"]["knockout"])

    def test_precise_fills_are_crisp_and_washes_are_not(self):
        kit.cfill([(0, 0), (4, 0), (4, 4)], kit.STEEL, 50)
        kit.wash([(0, 0), (4, 0), (4, 4)], kit.STEEL, 30, layers=1)
        crisp, wash = kit.els
        self.assertTrue(crisp["customData"]["crisp"])
        self.assertNotIn("customData", wash)
        self.assertEqual(wash["type"], "line")

    def test_untapered_strokes_are_flat(self):
        kit._stroke([(0, 0), (1, 0), (2, 0)], taper=False)
        self.assertTrue(kit.els[0]["customData"]["flat"])

    def test_a_pool_adds_a_darker_wash(self):
        kit.wash([(0, 0), (4, 0), (4, 4)], kit.SHADE, 30, layers=2, pool=[(0, 0), (1, 0), (1, 1)])
        self.assertEqual([e["opacity"] for e in kit.els], [30, 30, 50])


class LineWeight(unittest.TestCase):
    """Light comes from the upper left: shadow-side edges press harder, recesses flip that."""

    def setUp(self):
        kit.reset()

    def weight(self, normal):
        kit.rnd.seed(1)  # the same hand each time; reset() would also put the light back
        kit.pline((0, 0), (20, 0), normal=normal)
        return sum(kit.els[-1]["pressures"])

    def test_the_shadow_side_is_heavier_than_the_lit_side(self):
        self.assertGreater(self.weight((0, 1)), self.weight((0, -1)))

    def test_a_recess_flips_the_weight_and_then_restores_it(self):
        lit_bottom = self.weight((0, 1))
        with kit.recess():
            inside = self.weight((0, 1))
        self.assertLess(inside, lit_bottom)
        self.assertEqual(self.weight((0, 1)), lit_bottom)

    def test_a_recess_restores_the_light_after_an_error(self):
        light = kit.LIGHT_AWAY
        with self.assertRaises(RuntimeError), kit.recess():
            raise RuntimeError
        self.assertEqual(kit.LIGHT_AWAY, light)


class Forms(unittest.TestCase):
    def setUp(self):
        kit.reset()

    def test_oblique_projection_runs_depth_back_up_right(self):
        self.assertEqual(kit.P(10, 20), (10, 20))
        self.assertEqual(kit.P(10, 20, 10), (20, 13))
        self.assertEqual(kit.bk((10, 20), 10), kit.P(10, 20, 10))

    def test_a_floating_bigbox_has_no_floor_band_but_draws_its_underside(self):
        def counts(**kw):
            kit.reset()
            kit.bigbox(0, 30, 0, 20, 0, 10, soft_edges=False, **kw)
            washes = sum(e["type"] == "line" for e in kit.els)
            bottom = [e for e in kit.els if e["type"] == "freedraw" and e["y"] > 19 and e["width"] > 15]
            return washes, len(bottom)

        standing, floating = counts(), counts(closed=True)
        self.assertEqual(floating[0], standing[0] - 1)
        self.assertGreater(floating[1], standing[1])

    def test_splatter_stays_outside_the_drawing(self):
        kit.splatter(50, 50, 0, 40, n=60, bbox=(30, 30, 70, 70))
        self.assertTrue(kit.els)
        for e in kit.els:
            cx, cy = e["x"] + e["width"] / 2, e["y"] + e["height"] / 2
            self.assertFalse(30 < cx < 70 and 30 < cy < 70, (cx, cy))

    def test_every_form_draws(self):
        forms = [
            lambda: kit.box(0, 0, 10, 8, 3),
            lambda: kit.obox(0, 10, 0, 8, 2, 3),
            lambda: kit.big2d(0, 0, 30, 20, floor=True),
            lambda: kit.tube((0, 0), (10, 5)),
            lambda: kit.vcyl(5, 0, 10, 3, 1, cap=False),
            lambda: kit.ecyl(0, 10, 0, 4, ends=False),
            lambda: kit.eblock(0, 0, 10, 4, bevel=False),
            lambda: kit.ground(0, 30, 20, oblique=False),
            lambda: kit.loop(5, 5, 3, 2),
            lambda: kit.poly([(0, 0), (5, 0), (5, 5)]),
            lambda: kit.rpoly([(0, 0), (5, 0), (5, 5), (0, 5)], closed=True),
            lambda: kit.soft((0, 0), (10, 0)),
            lambda: kit.arc(5, 5, 3, 2, 0, 3),
            lambda: kit.parc(5, 5, 3, 2, 0, 3),
            lambda: kit.pell(5, 5, 3, 2),
            lambda: kit.cell(5, 5, 3, 2, kit.GLASS, 50),
            lambda: kit.pdot(5, 5, 0.3),
            lambda: kit.dot(5, 5, 0.3),
            lambda: kit.blob(kit.ell_pts(5, 5, 3, 2), kit.COPPER, 30),
            lambda: kit.granulate([(0, 0), (10, 10)], kit.SHADE, n=5),
            lambda: kit.cfill(kit.band(5, 0, 10, 3, 1), kit.ALU, 80),
        ]
        for form in forms:
            before = len(kit.els)
            form()
            self.assertGreater(len(kit.els), before)


class Save(unittest.TestCase):
    def test_save_writes_one_library_item(self):
        kit.reset()
        kit.pline((0, 0), (5, 0))
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "s.json"
            self.assertEqual(kit.save("lib-x", "X", str(out)), 1)
            (item,) = json.loads(out.read_text())["libraryItems"]
        self.assertEqual((item["id"], item["name"], len(item["elements"])), ("lib-x", "X", 1))


if __name__ == "__main__":
    unittest.main()
