"""gmail-reader-mcp without a browser: WebSocket framing, the write guard, thread text, account choice and MCP."""
from __future__ import annotations

import base64
import hashlib
import json
import os
import shutil
import socket
import struct
import subprocess
import sys
import tempfile
import threading
import unittest
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
import browser  # noqa: E402
import cdp  # noqa: E402
import gmail  # noqa: E402


def fake_cdp_server(handler):
    """A one-connection WebSocket server on the loopback; `handler(send, recv)` speaks CDP on it."""
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)

    def run():
        conn, _ = srv.accept()
        head = b""
        while b"\r\n\r\n" not in head:
            head += conn.recv(4096)
        key = next(ln.split(":", 1)[1].strip() for ln in head.decode().split("\r\n") if ln.lower().startswith("sec-websocket-key"))
        accept = base64.b64encode(hashlib.sha1((key + cdp.GUID).encode(), usedforsecurity=False).digest()).decode()  # NOSONAR
        conn.sendall(f"HTTP/1.1 101 Switching Protocols\r\nUpgrade: websocket\r\nConnection: Upgrade\r\n"
                     f"Sec-WebSocket-Accept: {accept}\r\n\r\n".encode())
        buf = bytearray()

        def exact(n):
            while len(buf) < n:
                buf.extend(conn.recv(65536))
            out = bytes(buf[:n])
            del buf[:n]
            return out

        def recv():
            b1, b2 = exact(2)
            n = b2 & 0x7F
            if n == 126:
                n = struct.unpack("!H", exact(2))[0]
            elif n == 127:
                n = struct.unpack("!Q", exact(8))[0]
            key = exact(4)
            return json.loads(cdp.mask(exact(n), key))

        def send(obj, fragments=1):
            data = json.dumps(obj).encode()
            step = max(1, len(data) // fragments)
            chunks = [data[i:i + step] for i in range(0, len(data), step)]
            for i, c in enumerate(chunks):
                op = 0x1 if i == 0 else 0x0
                fin = 0x80 if i == len(chunks) - 1 else 0
                n = len(c)
                head = struct.pack("!BB", fin | op, n) if n < 126 else (
                    struct.pack("!BBH", fin | op, 126, n) if n < 65536 else struct.pack("!BBQ", fin | op, 127, n))
                conn.sendall(head + c)

        handler(send, recv)
        conn.close()
        srv.close()

    threading.Thread(target=run, daemon=True).start()
    return f"ws://127.0.0.1:{srv.getsockname()[1]}/devtools/page/x"


class TestWebSocket(unittest.TestCase):
    def test_mask_is_its_own_inverse(self):
        key = b"\x01\x02\x03\x04"
        self.assertEqual(cdp.mask(cdp.mask(b"hello world", key), key), b"hello world")

    def test_call_matches_answers_and_events_reach_the_callback(self):
        events = []
        big = "x" * 200_000  # a 64-bit length, like a raw message

        def handler(send, recv):
            req = recv()
            send({"method": "Fetch.requestPaused", "params": {"requestId": "r1"}})
            send({"id": req["id"], "result": {"value": big}}, fragments=3)

        client = cdp.CDP(fake_cdp_server(handler), on_event=lambda c, m, p: events.append(m))
        self.assertEqual(client.call("Runtime.evaluate", {}, timeout=10)["value"], big)
        self.assertEqual(events, ["Fetch.requestPaused"])
        client.close()

    def test_error_answer_raises(self):
        def handler(send, recv):
            req = recv()
            send({"id": req["id"], "error": {"message": "nope"}})

        client = cdp.CDP(fake_cdp_server(handler))
        with self.assertRaisesRegex(cdp.CDPError, "nope"):
            client.call("Page.navigate", {}, timeout=10)
        client.close()


class TestWriteGuard(unittest.TestCase):
    def test_reads_pass_everywhere(self):
        self.assertTrue(browser.request_allowed("GET", "https://example.com/x"))

    def test_writes_only_to_gmail(self):
        self.assertTrue(browser.request_allowed("POST", "https://mail.google.com/sync/u/0/i/bv"))
        for url in ("https://accounts.google.com/x", "https://evil.example/x", "https://mail.google.com.evil.example/"):
            self.assertFalse(browser.request_allowed("POST", url), url)
        self.assertFalse(browser.request_allowed("DELETE", "https://www.googleapis.com/gmail/v1/x"))


class TestThreadText(unittest.TestCase):
    THREAD = {"subject": "Invoice", "messages": [
        {"from": "Ana <ana@example.com>", "date": "lun, 19 oct 2026, 10:00", "to": "To: me@example.com", "cc": "",
         "body": "<div>Hi<br>here is the <b>invoice</b></div><style>x{}</style><table><tr><td>a</td><td>b</td></tr></table>",
         "files": [{"name": "f.pdf", "path": "/x/1-f.pdf (1 KB)"}]},
        {"from": "Yo <me@example.com>", "date": "lun, 19 oct 2026, 11:00", "to": "To: ana@example.com", "cc": "Cc: b@example.com",
         "body": "<p>Thanks</p>", "files": [{"name": "g.xlsx", "note": "not saved (attachments=false)"}]}]}

    def test_html_to_text(self):
        self.assertEqual(gmail.html_to_text("<p>Hello <b>world</b></p><style>x{}</style><img src=x>"), "Hello world")
        self.assertEqual(gmail.html_to_text("<table><tr><td>a</td><td>b</td></tr></table>"), "a | b")

    def test_every_message_in_order_with_its_attachments(self):
        out = gmail.render("me@example.com", 3, self.THREAD)
        self.assertIn("Conversation 3 of me@example.com: \"Invoice\", 2 message(s)", out)
        self.assertLess(out.index("=== Message 1/2"), out.index("=== Message 2/2"))
        self.assertIn("Hi\nhere is the invoice", out)
        self.assertIn("Attachment: f.pdf: /x/1-f.pdf (1 KB)", out)
        self.assertIn("Attachment: g.xlsx: not saved (attachments=false)", out)
        self.assertIn("Cc: b@example.com", out)
        self.assertIn("open it with Read", out)

    def test_long_conversations_keep_listing_attachments(self):
        out = gmail.render("me@example.com", 1, self.THREAD, cap=10)
        self.assertIn("left out", out)
        self.assertIn("Attachment: g.xlsx", out)

    def test_safe_names_have_no_directory(self):
        self.assertEqual(gmail.safe("../../evil name.pdf"), "evil-name.pdf")
        self.assertEqual(gmail.safe(""), "attachment")


class TestPlatforms(unittest.TestCase):
    def test_windows_looks_in_program_files_and_local_app_data(self):
        env = {"PROGRAMFILES": r"C:\Program Files", "PROGRAMFILES(X86)": r"C:\Program Files (x86)",
               "LOCALAPPDATA": r"C:\Users\u\AppData\Local"}
        found = browser.candidates("win32", env)
        self.assertEqual(found[0], str(Path(r"C:\Program Files") / r"Google\Chrome\Application\chrome.exe"))
        self.assertTrue(any(f.endswith("msedge.exe") for f in found))
        self.assertTrue(any("Local" in f for f in found))

    def test_macos_and_linux(self):
        self.assertTrue(browser.candidates("darwin", {})[0].startswith("/Applications/Google Chrome.app"))
        self.assertIn("/usr/bin/google-chrome", browser.candidates("linux", {}))

    @unittest.skipIf(os.name == "nt", "Chrome's SingletonLock symlink is POSIX only")
    def test_posix_lock_belongs_to_a_live_process_on_this_host(self):
        profile = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, profile)
        lock = profile / "SingletonLock"
        for target, busy in ((f"{socket.gethostname()}-{os.getpid()}", True), (f"{socket.gethostname()}-99999999", False),
                             (f"another-host-{os.getpid()}", False)):
            lock.unlink(missing_ok=True)
            os.symlink(target, lock)
            self.assertEqual(browser.profile_busy(profile), busy, target)

    @unittest.skipUnless(os.name == "nt", "Chrome's lockfile is held open only on Windows")
    def test_windows_lockfile_held_open_means_busy(self):
        profile = Path(tempfile.mkdtemp())
        self.addCleanup(shutil.rmtree, profile, True)
        with open(profile / "lockfile", "w"):
            self.assertTrue(browser.profile_busy(profile))
        self.assertFalse(browser.profile_busy(profile))  # a stale one is removed


class TestMarkRead(unittest.TestCase):
    def test_off_unless_the_user_turns_it_on(self):
        self.assertFalse(gmail.mark_read_enabled({}))
        self.assertFalse(gmail.mark_read_enabled({"CLAUDE_PLUGIN_OPTION_MARK_READ": "false"}))
        self.assertTrue(gmail.mark_read_enabled({"CLAUDE_PLUGIN_OPTION_MARK_READ": "true"}))
        self.assertTrue(gmail.mark_read_enabled({"GMAIL_MCP_MARK_READ": "1"}))

    def test_the_flag_exists_only_when_on(self):
        import server
        read_off = next(t for t in server.tools(False) if t["name"] == "gmail_read")
        read_on = next(t for t in server.tools(True) if t["name"] == "gmail_read")
        self.assertNotIn("mark_read", read_off["inputSchema"]["properties"])
        self.assertTrue(read_off["annotations"]["readOnlyHint"])
        self.assertIn("mark_read", read_on["inputSchema"]["properties"])
        self.assertFalse(read_on["annotations"]["readOnlyHint"])
        self.assertNotIn("mark_read", read_off["inputSchema"]["properties"])  # building the "on" list changed nothing


class TestAccounts(unittest.TestCase):
    ACCOUNTS = [{"index": 0, "address": "me@example.com"}, {"index": 1, "address": "work@example.org"}]

    def test_one_account_is_the_default(self):
        self.assertEqual(gmail.choose(self.ACCOUNTS[:1], None)["index"], 0)

    def test_several_need_a_choice(self):
        with self.assertRaisesRegex(gmail.GmailError, "Ask the user which one"):
            gmail.choose(self.ACCOUNTS, None)
        self.assertEqual(gmail.choose(self.ACCOUNTS, "work")["index"], 1)

    def test_unknown_account_is_refused(self):
        with self.assertRaisesRegex(gmail.GmailError, "not a readable mailbox"):
            gmail.choose(self.ACCOUNTS, "other@example.com")

    def test_search_goes_only_into_the_url_hash(self):
        self.assertEqual(gmail.search_hash("", False), ("", "inbox"))
        self.assertEqual(gmail.search_hash("from:a b/c#", True), ("from:a b/c# is:unread", "search/from%3Aa+b%2Fc%23+is%3Aunread"))

    def test_page_params_are_json_literals(self):
        self.assertIn('const q = "\\"); alert(1); (\\"";', gmail.page("", q='"); alert(1); ("'))


class TestMcp(unittest.TestCase):
    def run_server(self, reqs, **env_extra):
        env = {k: v for k, v in os.environ.items() if k not in ("GMAIL_MCP_MARK_READ", "CLAUDE_PLUGIN_OPTION_MARK_READ")}
        env.update(GMAIL_MCP_HOME=tempfile.mkdtemp(), **env_extra)
        self.addCleanup(shutil.rmtree, env["GMAIL_MCP_HOME"])
        p = subprocess.run([sys.executable, str(REPO / "server.py")], input="\n".join(json.dumps(r) for r in reqs) + "\n",
                           capture_output=True, text=True, encoding="utf-8", timeout=30, env=env)
        return [json.loads(line) for line in p.stdout.splitlines()]

    def test_handshake_and_tools(self):
        out = self.run_server([{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": "2025-06-18"}},
                               {"jsonrpc": "2.0", "method": "notifications/initialized"},
                               {"jsonrpc": "2.0", "id": 2, "method": "tools/list"},
                               {"jsonrpc": "2.0", "id": 3, "method": "tools/call", "params": {"name": "gmail_send", "arguments": {}}},
                               {"jsonrpc": "2.0", "id": 4, "method": "nope"}])
        self.assertEqual([m["id"] for m in out], [1, 2, 3, 4])
        self.assertEqual(out[0]["result"]["serverInfo"]["name"], "gmail-reader")
        tools = {t["name"]: t for t in out[1]["result"]["tools"]}
        self.assertEqual(set(tools), {"gmail_login", "gmail_accounts", "gmail_inbox", "gmail_read"})
        self.assertNotIn("mark_read", tools["gmail_read"]["inputSchema"]["properties"])
        self.assertTrue(out[2]["result"]["isError"])  # there is no way to send
        self.assertEqual(out[3]["error"]["code"], -32601)

    def test_plugin_option_adds_mark_read(self):
        out = self.run_server([{"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {}},
                               {"jsonrpc": "2.0", "id": 2, "method": "tools/list"}], CLAUDE_PLUGIN_OPTION_MARK_READ="true")
        self.assertIn("marking as read", out[0]["result"]["instructions"])
        read = next(t for t in out[1]["result"]["tools"] if t["name"] == "gmail_read")
        self.assertIn("mark_read", read["inputSchema"]["properties"])


if __name__ == "__main__":
    unittest.main()
