"""inkwash.py: body files become sketches, and the Node steps run with the cached packages.

Node and npm are fakes on PATH that log their calls, so these tests need neither. The real renderer is
checked by hand: `inkwash.py build examples/winding_machine.py --out OUT` (see the README).
"""

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

SKILL = Path(__file__).resolve().parents[1] / "skills" / "field-notes"
sys.path.insert(0, str(SKILL / "scripts"))

import inkwash

FAKE_NODE = """#!/bin/sh
echo "node $* NODE_PATH=$NODE_PATH" >> "$FAKE_LOG"
"""
FAKE_NPM = """#!/bin/sh
echo "npm $* in $(pwd)" >> "$FAKE_LOG"
mkdir -p node_modules
"""


class Sketch(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_every_example_builds_and_is_named(self):
        for stem, name in (
            ("winding_machine", "Winding machine"),
            ("press_3d", "Press (3D)"),
            ("press_2d", "Press (2D)"),
        ):
            with self.subTest(stem):
                out = self.tmp / f"{stem}.json"
                count = inkwash.sketch(SKILL / "examples" / f"{stem}.py", out, 7, 0.1)
                (item,) = json.loads(out.read_text())["libraryItems"]
                self.assertGreater(count, 100)
                self.assertEqual((item["id"], item["name"]), (f"lib-{stem}", name))
                self.assertEqual(len(item["elements"]), count)

    def test_a_body_draws_the_same_sketch_every_time_for_a_seed(self):
        body = SKILL / "examples" / "press_2d.py"
        a, b, c = self.tmp / "a.json", self.tmp / "b.json", self.tmp / "c.json"
        inkwash.sketch(body, a, 7, 0.1)
        inkwash.sketch(body, b, 7, 0.1)
        inkwash.sketch(body, c, 8, 0.1)
        self.assertEqual(a.read_text(), b.read_text())
        self.assertNotEqual(a.read_text(), c.read_text())

    def test_a_body_without_a_name_is_named_after_its_file(self):
        body = self.tmp / "tiny-gear_box.py"
        body.write_text("from kit import pline\n\npline((0, 0), (5, 0))\n")
        inkwash.sketch(body, self.tmp / "s.json", 7, 0.1)
        (item,) = json.loads((self.tmp / "s.json").read_text())["libraryItems"]
        self.assertEqual(item["name"], "Tiny gear box")
        self.assertEqual(item["elements"][0]["groupIds"], ["icon-tiny-gear_box"])


class NodeSteps(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        bin_ = self.tmp / "bin"
        bin_.mkdir()
        for name, text in (("node", FAKE_NODE), ("npm", FAKE_NPM)):
            (bin_ / name).write_text(text)
            (bin_ / name).chmod(0o755)
        self.log = self.tmp / "log"
        self.cache = self.tmp / "cache"
        env = {
            "PATH": f"{bin_}{os.pathsep}{os.environ['PATH']}",
            "FAKE_LOG": str(self.log),
            "XDG_CACHE_HOME": str(self.cache),
        }
        patch = mock.patch.dict(os.environ, env)
        patch.start()
        self.addCleanup(patch.stop)
        os.environ.pop("FIELD_NOTES_NODE_DIR", None)
        os.environ.pop("NODE_PATH", None)

    def calls(self):
        return self.log.read_text().splitlines() if self.log.exists() else []

    def run_cli(self, *argv):
        with contextlib.redirect_stdout(io.StringIO()) as out, contextlib.redirect_stderr(io.StringIO()):
            inkwash.main(list(argv))
        return out.getvalue()

    def test_packages_install_into_the_cache_once(self):
        target = self.cache / "field-notes" / "node"
        self.assertEqual(self.run_cli("setup", "--no-browser").strip(), str(target))
        self.run_cli("setup", "--no-browser")
        npm = [c for c in self.calls() if c.startswith("npm")]
        self.assertEqual(npm, [f"npm ci --no-audit --no-fund in {target}"])
        self.assertEqual((target / "package.json").read_bytes(), (SKILL / "scripts" / "package.json").read_bytes())

    def test_changed_package_files_install_again(self):
        self.run_cli("setup", "--no-browser")
        target = self.cache / "field-notes" / "node"
        (target / "package-lock.json").write_text("{}")
        self.run_cli("setup", "--no-browser")
        self.assertEqual(sum(c.startswith("npm") for c in self.calls()), 2)

    def test_setup_installs_chromium_unless_told_not_to(self):
        self.run_cli("setup")
        (call,) = [c for c in self.calls() if c.startswith("node")]
        self.assertIn("playwright/cli.js install chromium", call)

    def test_a_folder_named_by_the_environment_wins(self):
        os.environ["FIELD_NOTES_NODE_DIR"] = str(self.tmp / "mine")
        self.run_cli("preview", "o.png", "a.svg")
        self.assertTrue((self.tmp / "mine" / "node_modules").is_dir())

    def test_build_sketches_renders_and_previews_with_the_cached_packages(self):
        out = self.tmp / "out"
        printed = self.run_cli(
            "build",
            str(SKILL / "examples" / "press_2d.py"),
            "--out",
            str(out),
            "--px",
            "900",
            "--paper",
            "--compare",
            "orig.svg",
        )
        modules = self.cache / "field-notes" / "node" / "node_modules"
        render, preview = [c for c in self.calls() if c.startswith("node")]
        self.assertTrue((out / "press_2d.sketch.json").is_file())
        self.assertIn(f"render.js {out}/press_2d.sketch.json {out}/press_2d.svg --px 900 --paper", render)
        self.assertIn(f"prev.js {out}/press_2d.png orig.svg {out}/press_2d.svg", preview)
        self.assertTrue(render.endswith(f"NODE_PATH={modules}"))
        self.assertIn("press_2d.png", printed)

    def test_build_without_preview_only_renders(self):
        self.run_cli("build", str(SKILL / "examples" / "press_2d.py"), "--out", str(self.tmp), "--no-preview")
        (render,) = [c for c in self.calls() if c.startswith("node")]
        self.assertIn("render.js", render)

    def test_an_existing_node_path_is_kept_behind_the_cache(self):
        os.environ["NODE_PATH"] = "/elsewhere"
        self.run_cli("crop", "d.svg", "c.png", "1", "2", "30", "20")
        (call,) = [c for c in self.calls() if c.startswith("node")]
        self.assertIn("crop.js d.svg c.png 1 2 30 20", call)
        self.assertTrue(call.endswith(f"node_modules{os.pathsep}/elsewhere"))

    def test_the_script_runs_from_any_folder(self):
        script = SKILL / "scripts" / "inkwash.py"
        subprocess.run([sys.executable, str(script), "preview", "o.png", "a.svg"], cwd=self.tmp, check=True)
        (call,) = [c for c in self.calls() if c.startswith("node")]
        self.assertIn(f"{script.parent}/prev.js o.png a.svg", call)

    def test_a_missing_node_says_what_to_install(self):
        os.environ["PATH"] = str(self.tmp / "empty")
        with self.assertRaises(SystemExit) as stop:
            self.run_cli("crop", "d.svg", "c.png", "1", "2", "3", "4")
        self.assertIn("npm is not on PATH", str(stop.exception.code))


if __name__ == "__main__":
    unittest.main()
