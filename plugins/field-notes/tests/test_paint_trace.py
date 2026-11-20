"""paint_trace.py's pure steps (face options, skeleton walk, line joining) and the traced_photo body file.

The OpenCV steps need opencv and numpy, which the tests don't install; they are checked by running the pipeline on a
photo (see SKILL.md, "Complex images").
"""

import argparse
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SKILL = Path(__file__).resolve().parents[1] / "skills" / "field-notes"
sys.path.insert(0, str(SKILL / "scripts"))

import inkwash
import paint_trace as pt


def row(y, x0, x1):
    return [(y, x) for x in range(x0, x1)]


class FaceOption(unittest.TestCase):
    def test_a_face_is_four_numbers_in_photo_pixels(self):
        self.assertEqual(pt.parse_face("305,515,95,95"), (305, 515, 95, 95))
        self.assertEqual(pt.parse_face("10.4,20,30.6,40"), (10, 20, 31, 40))

    def test_a_face_without_four_numbers_is_refused(self):
        for bad in ("305,515,95", "1,2,3,4,5", "a,b,c,d", ""):
            with self.subTest(bad), self.assertRaises(argparse.ArgumentTypeError):
                pt.parse_face(bad)

    def test_faces_repeat_on_the_command_line(self):
        args = pt.parser().parse_args(["p.png", "--out", "o", "--face", "1,2,3,4", "--face", "5,6,7,8"])
        self.assertEqual(args.face, [(1, 2, 3, 4), (5, 6, 7, 8)])


class SkeletonWalk(unittest.TestCase):
    def test_a_straight_line_is_one_path_end_to_end(self):
        (path,) = pt.skeleton_paths(set(row(3, 0, 6)))
        self.assertIn(path, (row(3, 0, 6), row(3, 0, 6)[::-1]))

    def test_a_staircase_step_does_not_split_the_line(self):
        # (0,2) touches (1,2) and (1,3); the diagonal is covered by the orthogonal step, so no junction
        stair = row(0, 0, 3) + row(1, 2, 5)
        (path,) = pt.skeleton_paths(set(stair))
        self.assertEqual(sorted(path), sorted(stair))

    def test_a_junction_splits_into_one_path_per_branch(self):
        tee = set(row(0, 0, 7)) | {(1, 3), (2, 3), (3, 3)}
        paths = pt.skeleton_paths(tee)
        self.assertEqual(len(paths), 3)
        self.assertTrue(all((0, 3) in (p[0], p[-1]) for p in paths))
        self.assertEqual(set().union(*paths), tee)

    def test_a_closed_ring_is_walked_once(self):
        ring = set(row(0, 0, 4)) | set(row(3, 0, 4)) | {(1, 0), (2, 0), (1, 3), (2, 3)}
        (path,) = pt.skeleton_paths(ring)
        self.assertEqual(set(path), ring)
        self.assertEqual(path[0], path[-1])


class JoinPaths(unittest.TestCase):
    def test_a_line_broken_by_a_short_gap_is_joined(self):
        left, right = row(0, 0, 10), row(0, 15, 25)
        (joined,) = pt.join_paths([left, right[::-1]])
        self.assertEqual(sorted(joined), sorted(left + right))

    def test_ends_too_far_apart_stay_separate(self):
        self.assertEqual(len(pt.join_paths([row(0, 0, 10), row(0, 30, 40)])), 2)

    def test_ends_that_turn_a_corner_stay_separate(self):
        across = row(0, 0, 10)
        down = [(y, 14) for y in range(5, 15)]  # diagonal from the end, then turns down: a corner, not a gap
        self.assertEqual(len(pt.join_paths([across, down])), 2)

    def test_specks_shorter_than_three_pixels_are_dropped(self):
        self.assertEqual(pt.join_paths([[(0, 0), (0, 1)], row(5, 0, 5)]), [row(5, 0, 5)])


class TracedPhotoBody(unittest.TestCase):
    def build(self, trace):
        tmp = Path(tempfile.mkdtemp())
        (tmp / "trace.json").write_text(json.dumps(trace))
        with mock.patch.dict(os.environ, {"TRACE": str(tmp / "trace.json")}):
            inkwash.sketch(SKILL / "examples" / "traced_photo.py", tmp / "s.json", 7, 0.1)
        (item,) = json.loads((tmp / "s.json").read_text())["libraryItems"]
        return item["elements"]

    def test_draws_the_ink_and_washes_but_leaves_the_lightest_regions_as_paper(self):
        square = [[10, 10], [20, 10], [20, 20], [10, 20]]
        trace = {
            "w": 50,
            "h": 40,
            "ink": [{"pts": [[1, 1], [9, 9], [15, 4]], "len": 3.0, "thick": 1.2, "dark": 0.6}],
            "washes": [
                {"pts": square, "rgb": [250, 250, 250], "lum": 0.97, "area": 100},
                {"pts": square, "rgb": [200, 60, 50], "lum": 0.5, "area": 100},
            ],
        }
        elements = self.build(trace)
        # 4 corner dots, 1 ink stroke, and 2 glazes for the red wash; the near-white region adds nothing
        self.assertEqual(len(elements), 7)


if __name__ == "__main__":
    unittest.main()
