"""A real browser, no Google account: start the profile headless, reach Gmail, see that it is not signed in, quit.

    GMAIL_MCP_HOME=<empty folder> python3 tests/smoke_browser.py

Run by CI on macOS, Windows and Linux. Exits 0 when every step behaves.
"""
import os
import sys
import tempfile
import time
from pathlib import Path

os.environ.setdefault("GMAIL_MCP_HOME", tempfile.mkdtemp())
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import browser  # noqa: E402
from server import Server  # noqa: E402


def main() -> int:
    print(f"browser: {browser.find_browser()}\nprofile: {browser.PROFILE}")
    server = Server()
    reply = server.handle({"method": "tools/call", "params": {"name": "gmail_accounts", "arguments": {}}})
    text = reply["content"][0]["text"]
    print(f"gmail_accounts -> isError={reply['isError']}: {text}")
    agent = server.headless.cdp.call("Runtime.evaluate", {"expression": "navigator.userAgent", "returnByValue": True})
    agent = agent["result"]["value"]
    print(f"user agent: {agent}")
    busy_while_running = browser.profile_busy()
    server.headless.close()
    time.sleep(2)
    checks = {"not signed in is reported": reply["isError"] and "not signed in" in text,
              "user agent is not HeadlessChrome": "HeadlessChrome" not in agent,
              "profile is busy while the browser runs": busy_while_running,
              "profile is free after close": not browser.profile_busy()}
    for name, ok in checks.items():
        print(f"{'ok  ' if ok else 'FAIL'} {name}")
    return 0 if all(checks.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
