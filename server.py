#!/usr/bin/env python3
"""gmail-reader-mcp: a read-only Gmail MCP server (stdio, JSON-RPC), standard library only.

    python3 server.py           the MCP server (what Claude Code starts)
    python3 server.py login     a normal browser window to sign in; press Enter when done
    python3 server.py status    the accounts signed in to the profile
"""
from __future__ import annotations

import atexit
import json
import signal
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import browser  # noqa: E402
from cdp import CDPError  # noqa: E402
from gmail import Gmail, GmailError  # noqa: E402

VERSION = "0.1.0"
INSTRUCTIONS = (
    "Read-only access to the user's Gmail through a browser profile they signed in to by hand. "
    "These tools list, search and read mail; none of them sends, replies, archives, deletes or marks anything. "
    "If the profile is not signed in, call gmail_login and let the user sign in."
)

TOOLS = [
    {"name": "gmail_login",
     "description": "Opens a normal (not automated) browser window on this server's own profile, at Google's sign-in page, "
                    "and returns at once. Use it the first time, or when another tool says the profile is not signed in. "
                    "Tell the user to sign in to every Google account to read and then QUIT that browser "
                    f"({browser.QUIT_HINT}), and only then call gmail_accounts.",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
     "annotations": {"readOnlyHint": False, "destructiveHint": False, "openWorldHint": False}},
    {"name": "gmail_accounts",
     "description": "Lists the Google accounts signed in to the profile, with how many unread conversations each inbox has. "
                    "Use it to check the sign-in worked or to learn which mailboxes exist.",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False},
     "annotations": {"readOnlyHint": True, "openWorldHint": False}},
    {"name": "gmail_inbox",
     "description": "Lists conversations, newest first and numbered: date, sender, subject, whether unread or with "
                    "attachments, and how it starts. Without search it is the inbox; search takes Gmail syntax "
                    "(from:, subject:, has:attachment, after:2026/01/01, in:anywhere...). Opens nothing and marks nothing "
                    "as read. The numbers are valid for gmail_read until the next list.",
     "inputSchema": {"type": "object", "additionalProperties": False, "properties": {
         "search": {"type": "string", "description": "Gmail search, e.g. \"from:clara invoice\". Leave out for the inbox."},
         "unread": {"type": "boolean", "default": False, "description": "true to show only unread conversations."},
         "limit": {"type": "integer", "default": 15, "minimum": 1, "maximum": 50, "description": "How many at most."},
         "account": {"type": "string", "description": "Address (or the part before @) of the mailbox, when several are signed in."}}},
     "annotations": {"readOnlyHint": True, "openWorldHint": False}},
    {"name": "gmail_read",
     "description": "Reads a whole conversation of the last gmail_inbox list by its number: every message, oldest first, "
                    "with sender, recipients, date and text (what each reply quotes of earlier messages is left out, since "
                    "those messages are shown), and saves the attachments of every message to disk (their paths are "
                    "returned; open images and PDFs with Read). Nothing is marked as read. Call gmail_inbox first if you "
                    "have no number.",
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["number"], "properties": {
         "number": {"type": "integer", "minimum": 1, "maximum": 50, "description": "Number of the conversation in the last gmail_inbox list."},
         "attachments": {"type": "boolean", "default": True, "description": "false to list attachments without saving them."}}},
     "annotations": {"readOnlyHint": True, "openWorldHint": False}},
]


class Server:
    def __init__(self):
        self.headless = browser.Headless()
        self.gmail = Gmail(self.headless)
        self.login_window: subprocess.Popen | None = None

    def _login_open(self) -> bool:
        return bool(self.login_window and self.login_window.poll() is None)

    def call(self, name: str, args: dict) -> str:
        if name == "gmail_login":
            if self._login_open():
                return f"The sign-in window is already open. Ask the user to finish and quit it ({browser.QUIT_HINT})."
            self.headless.close()
            self.login_window = browser.open_login_window()
            return ("A normal browser window is open at Google's sign-in page, on this server's own profile. Ask the user "
                    f"to sign in to each account to read, then quit that browser ({browser.QUIT_HINT}), and tell you. "
                    "Then call gmail_accounts.")
        if self._login_open():
            raise GmailError("The sign-in window is still open. Ask the user to finish signing in and quit it "
                             f"({browser.QUIT_HINT}), then try again.")
        if name == "gmail_accounts":
            return self.gmail.accounts()
        if name == "gmail_inbox":
            limit = max(1, min(50, int(args.get("limit") or 15)))
            return self.gmail.inbox(str(args.get("search") or ""), bool(args.get("unread")), limit, args.get("account"))
        if name == "gmail_read":
            return self.gmail.read(int(args["number"]), args.get("attachments", True) is not False)
        raise GmailError(f"There is no tool named {name}.")

    def handle(self, req: dict):
        method = req.get("method")
        params = req.get("params") or {}
        if method == "initialize":
            return {"protocolVersion": params.get("protocolVersion", "2024-11-05"),
                    "capabilities": {"tools": {}},
                    "serverInfo": {"name": "gmail-reader", "version": VERSION},
                    "instructions": INSTRUCTIONS}
        if method == "tools/list":
            return {"tools": TOOLS}
        if method == "tools/call":
            try:
                text, err = self.call(params.get("name", ""), params.get("arguments") or {}), False
            except (GmailError, browser.BrowserError) as e:
                text, err = str(e), True
            except (CDPError, OSError, KeyError, ValueError) as e:
                self.headless.close()  # start clean on the next call
                text, err = f"The browser failed: {e}. Tell the user; the next call starts a fresh browser.", True
            return {"content": [{"type": "text", "text": text}], "isError": err}
        if method == "ping":
            return {}
        raise LookupError(method)

    def serve(self) -> None:
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
            except json.JSONDecodeError:
                continue
            rid = req.get("id")
            if rid is None:
                continue  # a notification
            try:
                msg = {"jsonrpc": "2.0", "id": rid, "result": self.handle(req)}
            except LookupError:
                msg = {"jsonrpc": "2.0", "id": rid, "error": {"code": -32601, "message": f"method not found: {req.get('method')}"}}
            except Exception as exc:  # never kill the session over one bad request
                msg = {"jsonrpc": "2.0", "id": rid, "error": {"code": -32603, "message": str(exc)}}
            sys.stdout.write(json.dumps(msg, ensure_ascii=False) + "\n")
            sys.stdout.flush()


def login() -> int:
    window = browser.open_login_window()
    print("A normal browser window is open (not automated: Google refuses to sign in inside an automated one).")
    if browser.WINDOWS:
        # Ending a process on Windows is a kill, which may lose the session: the user closes the browser instead.
        print("Sign in to each Google account to read, then close the browser window. This waits for it.")
        window.wait()
        return status()
    print("Sign in to each Google account to read, then come back here and press Enter.")
    try:
        input()
    except EOFError:
        pass
    window.terminate()  # SIGTERM: a graceful quit, so the browser saves the session
    try:
        window.wait(timeout=20)
    except subprocess.TimeoutExpired:
        window.kill()
    return status()


def status() -> int:
    server = Server()
    try:
        print(server.gmail.accounts())
        return 0
    except (GmailError, browser.BrowserError, CDPError) as e:
        print(f"x {e}", file=sys.stderr)
        return 1
    finally:
        server.headless.close()


def main(argv: list[str]) -> int:
    # Windows defaults to a legacy code page and \r\n: JSON-RPC lines must be UTF-8 and end in \n everywhere.
    sys.stdin.reconfigure(encoding="utf-8")
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    if argv[:1] == ["login"]:
        return login()
    if argv[:1] == ["status"]:
        return status()
    if argv:
        print(__doc__, file=sys.stderr)
        return 1
    server = Server()
    atexit.register(server.headless.close)
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    server.serve()
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
