## 1. Browser and protocol

- [x] 1.1 `cdp.py` WebSocket client and CDP command/event matching, unit tests against a fake server
- [x] 1.2 `browser.py` profile, sign-in window, headless start, DevTools port, write guard
- [x] 1.3 Graceful quit with `Browser.close`, one browser per profile

## 2. Reading

- [x] 2.1 Accounts from each account's Atom feed
- [x] 2.2 Inbox and search from Gmail's visible rows
- [x] 2.3 Whole conversation from the print view through a Trusted Types policy
- [x] 2.4 Attachment downloads with `Network.loadNetworkResource`
- [x] 2.5 Checked with a real account: whole thread, PDFs, still unread

## 3. Server

- [x] 3.1 `server.py` stdio JSON-RPC: initialize, tools/list, tools/call, ping
- [x] 3.2 `login` and `status` commands
- [x] 3.3 MCP handshake test

## 4. Platforms

- [x] 4.1 Browser discovery for macOS, Windows and Linux
- [x] 4.2 User agent through CDP, profile lock per system, UTF-8 streams
- [x] 4.3 CI on macOS, Windows and Linux with Python 3.10 and 3.13, including a real-browser check
