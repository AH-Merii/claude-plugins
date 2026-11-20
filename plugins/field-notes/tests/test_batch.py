"""field-notes-batch: the base and its forks, claims, redos, the governor and the contact sheet.

claude is a fake on PATH that logs each call (argv, stdin, working directory) and replies in the JSON
shape of `claude -p --output-format json`, so these tests need neither Claude nor network. The real
cache hit is checked by hand with `batch.sh probe` (see the skill).
"""

import contextlib
import io
import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

SKILL = Path(__file__).resolve().parents[1] / "skills" / "field-notes-batch"
BATCH = SKILL / "scripts" / "batch.sh"
GOVERNOR = SKILL / "scripts" / "governor.sh"
sys.path.insert(0, str(SKILL / "scripts"))

import contact_sheet

FAKE_CLAUDE = r"""#!/usr/bin/env python3
import json, os, signal, sys, time, uuid
args = sys.argv[1:]
prompt_on_stdin = args[-2:] == ["--output-format", "json"]  # the message, when given, comes after these
stdin = sys.stdin.read() if prompt_on_stdin else None
msg = None if prompt_on_stdin else args[-1]
run = os.environ.get("FAKE_RUNNING")
if run:
    open(os.path.join(run, str(os.getpid())), "w").close()
    peak = len(os.listdir(run))
else:
    peak = 0
with open(os.environ["FAKE_LOG"], "a") as f:
    f.write(json.dumps({"argv": args, "stdin": stdin, "cwd": os.getcwd(), "peak": peak}) + "\n")
if msg and "die" in msg:
    os.kill(os.getppid(), signal.SIGKILL)
time.sleep(float(os.environ.get("FAKE_SLEEP", "0")))
if run:
    os.remove(os.path.join(run, str(os.getpid())))
sid = args[args.index("--resume") + 1] if "--resume" in args and "--fork-session" not in args else str(uuid.uuid4())
read = int(os.environ.get("FAKE_READ", "70000"))
print(json.dumps({
    "session_id": sid, "result": f"thinking\n{(msg or 'OK').splitlines()[0]}: OK", "total_cost_usd": 0.5,
    "usage": {"input_tokens": 2, "cache_read_input_tokens": read, "cache_creation_input_tokens": 5000,
              "cache_creation": {"ephemeral_1h_input_tokens": 5000, "ephemeral_5m_input_tokens": 0}},
}))
"""

BATCH_ENV = """GROUP="AWS"
MODEL="test-model"
WORK_DIR="work"
INSPIRATION="$PWD/inspiration"
CLAUDE_FLAGS=(--strict-mcp-config --allowedTools "Bash Read" --add-dir "$INSPIRATION")
ITEM_MESSAGE='Your icon: {{KEY}}'
REDO_MESSAGE='Rejected before. Fix:
{{FEEDBACK}}'
"""


class Run(unittest.TestCase):
    """A run folder with batch.env, prompt templates and the fake claude."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.run_dir = self.tmp / "run"
        (self.run_dir / "work").mkdir(parents=True)
        (self.run_dir / "inspiration").mkdir()
        (self.run_dir / "batch.env").write_text(BATCH_ENV)
        (self.run_dir / "base-load.md").write_text("Load field-notes with {{INSPIRATION}}.\n")
        (self.run_dir / "run-prompt.md").write_text("Shared task for {{GROUP}}. Reply with exactly OK.\n")
        (self.run_dir / "names.tsv").write_text("aws-lambda\tAWS Lambda\n")
        bin_ = self.tmp / "bin"
        bin_.mkdir()
        (bin_ / "claude").write_text(FAKE_CLAUDE)
        (bin_ / "claude").chmod(0o755)
        self.log = self.tmp / "claude.log"
        self.env = dict(os.environ, PATH=f"{bin_}{os.pathsep}{os.environ['PATH']}", FAKE_LOG=str(self.log))
        for name in ("BATCH_DIR", "MAX", "MIN_MB", "STAGGER"):
            self.env.pop(name, None)

    def batch(self, *args, **env):
        return subprocess.run(
            [str(BATCH), *args], check=False, cwd=self.run_dir, env={**self.env, **env}, capture_output=True, text=True
        )

    def calls(self):
        return [json.loads(line) for line in self.log.read_text().splitlines()] if self.log.exists() else []

    def base(self):
        r = self.batch("base")
        self.assertEqual(r.returncode, 0, r.stderr)
        return (self.run_dir / "base.id").read_text().strip()

    @staticmethod
    def shared(argv):
        """The flags that must match between base and forks: drop -p, -n, --resume, --fork-session, the message."""
        if argv[-2:] != ["--output-format", "json"]:
            argv = argv[:-1]
        out, skip = [], False
        for a in argv:
            if skip:
                skip = False
            elif a in ("-n", "--resume"):
                skip = True
            elif a not in ("-p", "--fork-session"):
                out.append(a)
        return out


class BaseAndForks(Run):
    def test_the_base_loads_the_skill_then_takes_the_run_prompt_in_the_same_session(self):
        base_id = self.base()
        load, prompt = self.calls()
        self.assertEqual(load["stdin"], f"Load field-notes with {self.run_dir}/inspiration.\n")
        self.assertEqual(prompt["stdin"], "Shared task for AWS. Reply with exactly OK.\n")
        self.assertEqual(prompt["argv"][prompt["argv"].index("--resume") + 1], base_id)
        self.assertNotIn("--fork-session", load["argv"] + prompt["argv"])

    def test_every_fork_uses_the_base_flags_and_working_directory(self):
        base_id = self.base()
        (self.run_dir / "notes.md").write_text("too angular")
        self.batch("item", "aws-lambda")
        self.batch("redo", "aws-lambda", "1", "notes.md")
        self.batch("probe")
        base, *forks = self.calls()[1:]
        self.assertEqual(len(forks), 3)
        self.assertIn("test-model", base["argv"])
        for fork in forks:
            with self.subTest(fork["argv"][-1]):
                self.assertEqual(self.shared(fork["argv"]), self.shared(base["argv"]))
                self.assertEqual(fork["cwd"], base["cwd"])
                self.assertEqual(fork["cwd"], str(self.run_dir / "work"))
                self.assertIn("--fork-session", fork["argv"])
                self.assertEqual(fork["argv"][fork["argv"].index("--resume") + 1], base_id)

    def test_an_item_is_named_after_its_group_and_name_and_gets_its_message(self):
        self.base()
        r = self.batch("item", "aws-lambda")
        argv = self.calls()[-1]["argv"]
        self.assertEqual(argv[argv.index("-n") + 1], "AWS - AWS Lambda")
        self.assertEqual(argv[-1], "Your icon: aws-lambda")
        self.assertEqual(r.stdout.strip(), "Your icon: aws-lambda: OK")
        self.assertIn("Your icon: aws-lambda: OK", (self.run_dir / "logs" / "results.log").read_text())
        self.assertEqual((self.run_dir / "logs" / "costs.tsv").read_text(), "aws-lambda\t0.5\tAWS - AWS Lambda\n")

    def test_an_item_without_a_name_is_named_after_its_key(self):
        self.base()
        self.batch("item", "aws-s3")
        argv = self.calls()[-1]["argv"]
        self.assertEqual(argv[argv.index("-n") + 1], "AWS - aws-s3")

    def test_approved_and_claimed_items_are_not_drawn_again(self):
        self.base()
        (self.run_dir / "approved.txt").write_text("aws-s3\n")
        self.batch("item", "aws-lambda")
        before = len(self.calls())
        for key, why in (("aws-s3", "skip approved"), ("aws-lambda", "skip claimed")):
            with self.subTest(key):
                r = self.batch("item", key)
                self.assertEqual(r.stdout.strip(), f"{why} {key}")
        self.assertEqual(len(self.calls()), before)

    def test_a_redo_forks_the_base_with_the_notes_even_when_approved(self):
        base_id = self.base()
        (self.run_dir / "approved.txt").write_text("aws-lambda\n")
        (self.run_dir / "notes.md").write_text("the lambda is too angular")
        r = self.batch("redo", "aws-lambda", "2", "notes.md")
        self.assertEqual(r.returncode, 0, r.stderr)
        argv = self.calls()[-1]["argv"]
        self.assertEqual(argv[argv.index("-n") + 1], "AWS - AWS Lambda - redo2")
        self.assertEqual(argv[argv.index("--resume") + 1], base_id)
        self.assertEqual(argv[-1], "Your icon: aws-lambda\n\nRejected before. Fix:\nthe lambda is too angular")
        self.assertTrue((self.run_dir / "logs" / "aws-lambda-redo2.json").exists())

    def test_a_template_with_an_unset_placeholder_sends_nothing(self):
        (self.run_dir / "base-load.md").write_text("Use {{NOT_SET}}.\n")
        r = self.batch("base")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("NOT_SET", r.stderr)
        self.assertEqual(self.calls(), [])

    def test_a_fork_needs_a_base(self):
        r = self.batch("item", "aws-lambda")
        self.assertNotEqual(r.returncode, 0)
        self.assertIn("batch.sh base", r.stderr)
        self.assertEqual(self.calls(), [])

    def test_the_probe_fails_when_the_fork_misses_the_cache(self):
        self.base()
        for read, code, verdict in ((70000, 0, "cache HIT"), (0, 1, "cache MISS")):
            with self.subTest(read=read):
                r = self.batch("probe", FAKE_READ=str(read))
                self.assertEqual(r.returncode, code)
                self.assertIn(verdict, r.stdout + r.stderr)


class Governor(Run):
    def setUp(self):
        super().setUp()
        self.base()
        self.log.unlink()
        self.running = self.tmp / "running"
        self.running.mkdir()
        self.env.update(FAKE_RUNNING=str(self.running), STAGGER="0", POLL="0.1", MIN_MB="0")

    def governor(self, keys, **env):
        (self.run_dir / "queue.txt").write_text("".join(k + "\n" for k in keys))
        return subprocess.Popen(
            [str(GOVERNOR), "queue.txt"], cwd=self.run_dir, env={**self.env, **env}, stdout=subprocess.DEVNULL
        )

    def drawn(self):
        return sorted(c["argv"][-1].removeprefix("Your icon: ") for c in self.calls())

    def test_never_runs_more_than_max_forks_at_once(self):
        keys = [f"aws-{i}" for i in range(6)]
        self.assertEqual(self.governor(keys, MAX="2", FAKE_SLEEP="0.4").wait(timeout=30), 0)
        self.assertEqual(self.drawn(), keys)
        self.assertEqual(max(c["peak"] for c in self.calls()), 2)

    def test_skips_approved_and_already_logged_items(self):
        (self.run_dir / "approved.txt").write_text("aws-a\n")
        (self.run_dir / "logs" / "aws-b.json").write_text("")
        self.governor(["aws-a", "aws-b", "aws-c"], MAX="2").wait(timeout=30)
        self.assertEqual(self.drawn(), ["aws-c"])

    def test_keeps_starting_forks_after_one_is_killed_by_a_signal(self):
        self.governor(["aws-die", "aws-b", "aws-c"], MAX="1").wait(timeout=30)
        self.assertEqual(self.drawn(), ["aws-b", "aws-c", "aws-die"])

    def test_starts_nothing_once_stop_exists(self):
        (self.run_dir / "logs" / "STOP").write_text("")
        self.governor(["aws-a"], MAX="2").wait(timeout=30)
        self.assertEqual(self.calls(), [])

    def test_waits_for_free_ram_before_starting_a_fork(self):
        meminfo = self.tmp / "meminfo"
        meminfo.write_text("MemTotal: 16000000 kB\nMemAvailable: 1024000 kB\n")
        p = self.governor(["aws-a"], MAX="2", MIN_MB="2000", MEMINFO=str(meminfo))
        time.sleep(1)
        self.assertEqual(self.calls(), [])
        meminfo.write_text("MemTotal: 16000000 kB\nMemAvailable: 4096000 kB\n")
        self.assertEqual(p.wait(timeout=30), 0)
        self.assertEqual(self.drawn(), ["aws-a"])


class ContactSheet(unittest.TestCase):
    IMAGE = "out/{prefix}/check/{key}.png"

    def setUp(self):
        self.run_dir = Path(tempfile.mkdtemp())
        (self.run_dir / "logs").mkdir()

    def finish(self, *tags, image=True):
        with open(self.run_dir / "logs" / "costs.tsv", "a") as f:
            for tag in tags:
                f.write(f"{tag}\t0.5\tname\n")
                key = tag.split("-redo")[0]
                if image:
                    path = self.run_dir / "out" / key.split("-")[0] / "check" / f"{key}.png"
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(b"png")

    def test_shows_each_unreviewed_item_once_with_its_latest_redo(self):
        self.finish("aws-a", "aws-b", "gcp-c", "aws-a-redo1")
        self.finish("aws-d", image=False)
        (self.run_dir / "approved.txt").write_text("aws-b\n")
        (self.run_dir / "logs" / "shown.txt").write_text("gcp-c\n")
        items = contact_sheet.new_items(self.run_dir, self.IMAGE)
        self.assertEqual([(tag, key) for tag, key, _ in items], [("aws-a-redo1", "aws-a")])
        self.assertEqual(items[0][2], self.run_dir / "out" / "aws" / "check" / "aws-a.png")

    def test_writes_numbered_sheets_and_remembers_what_it_showed(self):
        self.finish("aws-a", "gcp-b")
        with mock.patch.object(contact_sheet, "render") as render, contextlib.redirect_stdout(io.StringIO()):
            contact_sheet.main(["--image", self.IMAGE, "--dir", str(self.run_dir)])
            self.finish("aws-a-redo1")
            contact_sheet.main(["--image", self.IMAGE, "--dir", str(self.run_dir)])
        first, second = (c.args for c in render.call_args_list)
        self.assertEqual([p.name for p in first], ["batch-01.html", "batch-01.png"])
        self.assertEqual([p.name for p in second], ["batch-02.html", "batch-02.png"])
        sheet = first[0].read_text()
        self.assertIn("aws-a", sheet)
        self.assertIn((self.run_dir / "out" / "gcp" / "check" / "gcp-b.png").as_uri(), sheet)
        self.assertEqual((self.run_dir / "logs" / "shown.txt").read_text().split(), ["aws-a", "gcp-b", "aws-a-redo1"])

    def test_says_so_when_nothing_is_new(self):
        with self.assertRaises(SystemExit) as e:
            contact_sheet.main(["--image", self.IMAGE, "--dir", str(self.run_dir)])
        self.assertEqual(e.exception.code, "nothing new")

    def test_renders_the_sheet_with_the_field_notes_node_packages(self):
        node_dir = Path(tempfile.mkdtemp())
        with (
            mock.patch.object(contact_sheet.inkwash, "node_dir", return_value=node_dir),
            mock.patch.object(contact_sheet.inkwash, "installed", return_value=True),
            mock.patch.object(contact_sheet.inkwash, "need", return_value="node"),
            mock.patch.object(contact_sheet.subprocess, "run") as run,
        ):
            contact_sheet.render(self.run_dir / "s.html", self.run_dir / "s.png")
        (argv,), kwargs = run.call_args
        self.assertEqual(
            argv,
            ["node", str(SKILL / "scripts" / "sheet.js"), str(self.run_dir / "s.png"), str(self.run_dir / "s.html")],
        )
        self.assertEqual(kwargs["env"]["NODE_PATH"], str(node_dir / "node_modules"))


if __name__ == "__main__":
    unittest.main()
