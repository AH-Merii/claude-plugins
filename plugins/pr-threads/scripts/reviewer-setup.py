"""One-time: create the reviewer bot's GitHub App from a manifest and save its credentials.

Opens GitHub's "create app" page with the manifest filled in. After you confirm, GitHub
redirects back here, and the app's id, slug and private key are saved where
bin/reviewer-token reads them. Then install the app on the repos it should review.

    python3 reviewer-setup.py [--owner LOGIN] [--org] [--name APP_NAME]

The owner defaults to your gh login. Runs on any OS with Python and gh.
"""
import argparse
import html
import json
import os
import subprocess
import sys
import threading
import urllib.parse
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, HTTPServer


def options():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--owner", default=os.environ.get("REVIEWER_APP_OWNER"),
                   help="GitHub user or org the app belongs to (env REVIEWER_APP_OWNER, "
                        "default: your gh login)")
    p.add_argument("--org", action="store_true", help="create the app under the --owner org")
    p.add_argument("--name", default=os.environ.get("REVIEWER_APP_NAME"),
                   help="app name, so the bot shows as <name>[bot] (default: <owner>-claude-reviewer)")
    p.add_argument("--dir", default=os.environ.get("CLAUDE_REVIEWER_DIR",
                                                   os.path.expanduser("~/.config/claude-reviewer")),
                   help="where to save app.json and private-key.pem (env CLAUDE_REVIEWER_DIR)")
    p.add_argument("--port", type=int, default=8765)
    args = p.parse_args()
    args.owner = args.owner or gh_login()
    args.name = args.name or f"{args.owner.lower()}-claude-reviewer"
    return args


def gh_login():
    out = subprocess.run(["gh", "api", "user", "--jq", ".login"], capture_output=True, text=True)
    if out.returncode or not out.stdout.strip():
        sys.exit(f"can't read your gh login ({out.stderr.strip()}): log in with gh, or pass --owner")
    return out.stdout.strip()


def manifest(args):
    return {
        "name": args.name,
        "url": f"https://github.com/{args.owner}",
        "description": f"Posts Claude's code reviews on {args.owner}'s pull requests.",
        "hook_attributes": {"url": f"https://github.com/{args.owner}", "active": False},
        "redirect_url": f"http://localhost:{args.port}/callback",
        "public": False,
        "default_permissions": {"pull_requests": "write"},
        "default_events": [],
    }


def form(args):
    action = (f"https://github.com/organizations/{args.owner}/settings/apps/new" if args.org
              else "https://github.com/settings/apps/new")
    return f"""<!doctype html><html><body>
<form id="f" method="post" action="{action}">
<input type="hidden" name="manifest" value="{html.escape(json.dumps(manifest(args)))}">
<p>Creating GitHub App <b>{html.escape(args.name)}</b>…</p><button>Continue to GitHub</button></form>
<script>document.getElementById('f').submit()</script></body></html>"""


def save(app, out):
    os.makedirs(out, mode=0o700, exist_ok=True)
    fd = os.open(os.path.join(out, "private-key.pem"), os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
    with os.fdopen(fd, "w") as f:
        f.write(app["pem"])
    with open(os.path.join(out, "app.json"), "w") as f:
        json.dump({k: app[k] for k in ("id", "slug", "client_id", "html_url")}, f, indent=2)


def handler(args):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def reply(self, body):
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(body.encode())

        def do_GET(self):
            url = urllib.parse.urlparse(self.path)
            if url.path != "/callback":
                return self.reply(form(args))
            code = urllib.parse.parse_qs(url.query).get("code", [""])[0]
            req = urllib.request.Request(
                f"https://api.github.com/app-manifests/{code}/conversions",
                method="POST", headers={"Accept": "application/vnd.github+json"})
            app = json.load(urllib.request.urlopen(req))
            save(app, args.dir)
            install = f"https://github.com/apps/{app['slug']}/installations/new"
            self.reply(f"<p>Created <b>{app['slug']}</b>. Now install it: "
                       f"<a href='{install}'>{install}</a></p>")
            print(json.dumps({"slug": app["slug"], "id": app["id"], "install_url": install}))
            raise SystemExit

    return Handler


if __name__ == "__main__":
    args = options()
    start = f"http://localhost:{args.port}/"
    server = HTTPServer(("127.0.0.1", args.port), handler(args))
    print(f"open {start}", flush=True)
    # $BROWSER or the OS default; a text-mode browser mustn't hold up the server
    threading.Thread(target=webbrowser.open, args=(start,), daemon=True).start()
    try:
        server.serve_forever()
    except SystemExit:
        pass
