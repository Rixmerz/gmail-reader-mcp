"""The browser behind the server: one Chrome profile, signed in by hand, then driven headless.

Google refuses to sign in inside a browser that automation drives, so the sign-in
window is a plain browser window on the profile, with no debugging port. Once it is
closed, the tools start the same profile headless with a DevTools port bound to
127.0.0.1 and read through it.

Both must store cookies the same way. On macOS that means the fake keychain
(--use-mock-keychain): a normal window would otherwise encrypt them with the real
keychain and the headless browser could not read them. On Linux it means the
basic password store. Windows encrypts them for the user account, the same for both.

Works on macOS, Windows and Linux with Chrome, Chromium, Edge or Brave.
"""
from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

from cdp import CDP, CDPError

HOME = Path(os.environ.get("GMAIL_MCP_HOME", Path.home() / ".gmail-reader-mcp"))
PROFILE = Path(os.environ.get("GMAIL_MCP_PROFILE", HOME / "profile"))
SIGN_IN = "https://accounts.google.com/AddSession?continue=https://mail.google.com/mail/"
COMMON = ["--use-mock-keychain", "--password-store=basic", "--no-first-run", "--no-default-browser-check"]
DEVTOOLS_HOST = "127.0.0.1"  # Chrome binds its DevTools port to the loopback address only
READ_METHODS = {"GET", "HEAD", "OPTIONS"}
# Gmail loads and searches through POSTs to its own host; every other write is refused before it leaves the browser.
WRITE_HOSTS = {"mail.google.com"}
WINDOWS = os.name == "nt"
QUIT_HINT = "Cmd+Q on macOS; close its window on Windows and Linux"

MAC_BROWSERS = ("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome",
                "/Applications/Chromium.app/Contents/MacOS/Chromium",
                "/Applications/Microsoft Edge.app/Contents/MacOS/Microsoft Edge",
                "/Applications/Brave Browser.app/Contents/MacOS/Brave Browser")
LINUX_BROWSERS = ("/usr/bin/google-chrome-stable", "/usr/bin/google-chrome", "/usr/bin/chromium", "/usr/bin/chromium-browser",
                  "/snap/bin/chromium", "/usr/bin/microsoft-edge", "/usr/bin/microsoft-edge-stable", "/usr/bin/brave-browser")
WINDOWS_BROWSERS = (r"Google\Chrome\Application\chrome.exe", r"Chromium\Application\chrome.exe",
                    r"Microsoft\Edge\Application\msedge.exe", r"BraveSoftware\Brave-Browser\Application\brave.exe")


class BrowserError(Exception):
    """A failure the model should relay to the user as it is."""


def request_allowed(method: str, url: str) -> bool:
    if method.upper() in READ_METHODS:
        return True
    return (urllib.parse.urlparse(url).hostname or "") in WRITE_HOSTS


def candidates(platform: str = sys.platform, env: dict | None = None) -> list[str]:
    """Where a Chromium-based browser is usually installed on `platform`, in order of preference."""
    env = os.environ if env is None else env
    if platform == "darwin":
        return list(MAC_BROWSERS)
    if platform.startswith("win"):
        roots = [env.get(k) for k in ("PROGRAMFILES", "PROGRAMFILES(X86)", "LOCALAPPDATA")]
        return [str(Path(root) / rel) for rel in WINDOWS_BROWSERS for root in roots if root]
    return list(LINUX_BROWSERS)


def find_browser() -> str:
    for b in (os.environ.get("GMAIL_MCP_BROWSER"), *candidates()):
        if b and Path(b).is_file() and os.access(b, os.X_OK):
            return b
    raise BrowserError("No Chrome, Chromium, Edge or Brave found. Install one, or set GMAIL_MCP_BROWSER to its executable.")


def _posix_busy(profile: Path) -> bool:
    """Chrome's SingletonLock is a symlink to <host>-<pid> while a browser holds the profile."""
    try:
        target = os.readlink(profile / "SingletonLock")
    except OSError:
        return False
    host, _, pid = target.rpartition("-")
    if not pid.isdigit() or host != socket.gethostname():
        return False
    try:
        os.kill(int(pid), 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        pass
    return True


def _windows_busy(profile: Path) -> bool:
    """Chrome keeps <profile>/lockfile open while it runs, so Windows refuses to delete it; a stale one just goes."""
    lock = profile / "lockfile"
    try:
        lock.unlink(missing_ok=True)
    except PermissionError:
        return True
    return False


def profile_busy(profile: Path = PROFILE) -> bool:
    return _windows_busy(profile) if WINDOWS else _posix_busy(profile)


def check_free() -> None:
    if profile_busy():
        raise BrowserError(f"The browser profile is in use: the sign-in window is still open (quit it: {QUIT_HINT}) "
                           "or another gmail-reader-mcp is running. Tell the user; do not retry.")


def detached() -> dict:
    """Popen options that keep the sign-in window out of the server's process group (and its Ctrl+C)."""
    if WINDOWS:
        return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP}
    return {"start_new_session": True}


def open_login_window() -> subprocess.Popen:
    """A normal, unautomated window on the profile, at Google's sign-in page. Does not wait for it."""
    check_free()
    PROFILE.mkdir(parents=True, exist_ok=True)
    return subprocess.Popen([find_browser(), f"--user-data-dir={PROFILE}", *COMMON, SIGN_IN],
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, **detached())


class Headless:
    """The headless browser, started on first use and kept until `close`."""

    def __init__(self):
        self.proc: subprocess.Popen | None = None
        self.cdp: CDP | None = None
        self.blocked: list[str] = []

    def page(self) -> CDP:
        if self.cdp and self.cdp.alive and self.proc and self.proc.poll() is None:
            return self.cdp
        self.close()
        self._start()
        return self.cdp

    def _start(self) -> None:
        check_free()
        PROFILE.mkdir(parents=True, exist_ok=True)
        port_file = PROFILE / "DevToolsActivePort"
        port_file.unlink(missing_ok=True)
        self.proc = subprocess.Popen([find_browser(), "--headless=new", "--remote-debugging-port=0",
                                      f"--user-data-dir={PROFILE}", *COMMON, "about:blank"],
                                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        port = self._port(port_file)
        with urllib.request.urlopen(f"http://{DEVTOOLS_HOST}:{port}/json/list", timeout=10) as r:  # NOSONAR loopback only
            targets = json.load(r)
        page = next((t for t in targets if t.get("type") == "page"), None)
        if not page:
            self.close()
            raise BrowserError("The headless browser opened no page. Tell the user.")
        self.cdp = CDP(page["webSocketDebuggerUrl"], on_event=self._event)
        # Headless Chrome calls itself HeadlessChrome, which Google treats differently: send what a normal window sends.
        agent = self.cdp.call("Browser.getVersion")["userAgent"].replace("HeadlessChrome", "Chrome")
        self.cdp.call("Emulation.setUserAgentOverride", {"userAgent": agent})
        self.cdp.call("Fetch.enable", {"patterns": [{"urlPattern": "*", "requestStage": "Request"}]})

    def _port(self, port_file: Path) -> int:
        deadline = time.time() + 30
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise BrowserError("The headless browser exited at start. Is the profile in use? Tell the user.")
            lines = port_file.read_text().splitlines() if port_file.is_file() else []
            if len(lines) >= 2 and lines[0].isdigit():
                return int(lines[0])
            time.sleep(0.2)
        self.close()
        raise BrowserError("The headless browser did not open its DevTools port within 30 s. Tell the user.")

    def _event(self, cdp: CDP, method: str, params: dict) -> None:
        if method != "Fetch.requestPaused":
            return
        req = params.get("request") or {}
        if request_allowed(req.get("method", "GET"), req.get("url", "")):
            cdp.send("Fetch.continueRequest", {"requestId": params["requestId"]})
        else:
            self.blocked.append(f"{req.get('method')} {urllib.parse.urlparse(req.get('url', '')).hostname}")
            cdp.send("Fetch.failRequest", {"requestId": params["requestId"], "errorReason": "BlockedByClient"})

    def close(self) -> None:
        # Ask the browser to quit first: it saves the profile, which a kill (all Windows has) would not let it do.
        asked = False
        if self.cdp and self.cdp.alive:
            try:
                self.cdp.send("Browser.close")
                asked = True
            except (CDPError, OSError):
                pass
        if self.proc and self.proc.poll() is None:
            self._stop(asked)
        if self.cdp:
            try:
                self.cdp.close()
            except OSError:
                pass
        self.cdp = None
        self.proc = None

    def _stop(self, asked: bool) -> None:
        """Wait for a quit the browser was asked for; otherwise, or if it hangs, end the process."""
        if asked:
            try:
                self.proc.wait(timeout=10)
                return
            except subprocess.TimeoutExpired:
                pass
        self.proc.terminate()
        try:
            self.proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            self.proc.kill()
