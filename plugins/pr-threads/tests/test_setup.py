"""scripts/reviewer-setup.py: the one-time bot setup works for any user on any OS.

The script runs for real with a stand-in gh, a recording $BROWSER (what webbrowser.open
uses when it is set) and a decoy xdg-open, so no browser opens and nothing leaves the
machine: the test only fetches the manifest form from the script's local server.
"""
import html
import json
import os
import re
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request

from helpers import FAKE_GH, PLUGIN, clean_env

SCRIPT = os.path.join(PLUGIN, "scripts", "reviewer-setup.py")
LOGIN = "octocat-dev"


def free_port():
    with socket.socket() as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


class ReviewerSetupTest(unittest.TestCase):
    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.dir = tmp.name
        self.opened = os.path.join(self.dir, "opened.log")
        self.table = os.path.join(self.dir, "table.json")
        with open(self.table, "w") as f:
            json.dump({"GET user$": {"stdout": json.dumps({"login": LOGIN})}}, f)
        self.exe("gh", f"#!/bin/sh\nexec '{sys.executable}' '{FAKE_GH}' \"$@\"\n")
        self.exe("browser", f"#!/bin/sh\necho \"browser $1\" >> '{self.opened}'\n")
        self.exe("xdg-open", f"#!/bin/sh\necho \"xdg-open $1\" >> '{self.opened}'\n")

    def exe(self, name, text):
        path = os.path.join(self.dir, name)
        with open(path, "w") as f:
            f.write(text)
        os.chmod(path, 0o755)

    def start(self, *args):
        """Run the setup script with `args`; return its local server's URL."""
        port = free_port()
        env = clean_env(PATH=self.dir + os.pathsep + os.environ["PATH"],
                        BROWSER=os.path.join(self.dir, "browser"),
                        FAKE_GH_LOG=os.path.join(self.dir, "calls.jsonl"), FAKE_GH_TABLE=self.table)
        for name in ("REVIEWER_APP_OWNER", "REVIEWER_APP_NAME", "GH_TOKEN", "GITHUB_TOKEN"):
            env.pop(name, None)
        proc = subprocess.Popen([sys.executable, SCRIPT, "--port", str(port),
                                 "--dir", os.path.join(self.dir, "conf"), *args],
                                env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.addCleanup(proc.wait)
        self.addCleanup(proc.kill)
        self.proc = proc
        return f"http://localhost:{port}/"

    def wait_for(self, check, what, seconds=10):
        deadline = time.monotonic() + seconds
        while time.monotonic() < deadline:
            if (got := check()) is not None:
                return got
            if self.proc.poll() is not None:
                self.fail(f"the script exited before {what}: {self.proc.stderr.read()}")
            time.sleep(0.05)
        self.fail(f"timed out waiting for {what}")

    def opened_lines(self):
        if os.path.exists(self.opened):
            with open(self.opened) as f:
                return f.read().splitlines() or None
        return None

    def manifest(self, url):
        """The app manifest in the form the script serves at `url`."""
        def fetch():
            try:
                with urllib.request.urlopen(url, timeout=2) as r:
                    return r.read().decode()
            except OSError:
                return None
        page = self.wait_for(fetch, "the setup page")
        m = re.search(r'name="manifest" value="([^"]*)"', page)
        self.assertIsNotNone(m, "the page carries the app manifest")
        return json.loads(html.unescape(m.group(1)))

    def test_opens_the_setup_page_the_cross_platform_way(self):
        # xdg-open exists only on Linux desktops; webbrowser works everywhere
        url = self.start()
        lines = self.wait_for(self.opened_lines, "the browser to open")
        self.assertFalse([l for l in lines if l.startswith("xdg-open")],
                         "the script ran xdg-open, which macOS and Windows don't have")
        self.assertEqual(lines, [f"browser {url}"])

    def test_the_app_belongs_to_the_logged_in_gh_user_unless_told_otherwise(self):
        for args, owner, name in [
            ((), LOGIN, f"{LOGIN}-claude-reviewer"),
            (("--name", "my-reviewer"), LOGIN, "my-reviewer"),
            (("--owner", "some-org"), "some-org", "some-org-claude-reviewer"),
            (("--owner", "some-org", "--name", "org-reviewer"), "some-org", "org-reviewer"),
        ]:
            with self.subTest(args=args):
                got = self.manifest(self.start(*args))
                self.assertEqual(got["name"], name)
                self.assertEqual(got["url"], f"https://github.com/{owner}")
                self.assertIn(owner, got["description"])
                self.assertNotIn("ah-merii", json.dumps(got).lower(), "no hard-coded owner")
                self.proc.kill()
                self.proc.wait()


if __name__ == "__main__":
    unittest.main()
