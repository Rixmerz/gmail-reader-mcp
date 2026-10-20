## Why

Assistants need to read the user's Gmail to keep context (requests, invoices, documents sent in a thread), but Google's API needs an OAuth app, consent screens and tokens, and broad automation tools can also send or delete mail. A small server that reuses a browser profile the user signed in to by hand, and that can only read, gives the assistant the mailbox without credentials leaving the browser and without any way to change it.

## What Changes

- New stdio MCP server `server.py`, Python standard library only, with `login` and `status` commands.
- A profile of its own in `~/.gmail-reader-mcp`: a normal, unautomated window to sign in, then the same profile headless for reading.
- A minimal Chrome DevTools Protocol client over a WebSocket of its own (`cdp.py`).
- Tools `gmail_login`, `gmail_accounts`, `gmail_inbox` (inbox or Gmail search) and `gmail_read` (the whole conversation with every attachment).
- Read-only by construction, a CDP write guard, and nothing marked as read.
- macOS, Windows and Linux, with CI running unit tests and a real-browser check on all three.

## Capabilities

### New Capabilities

- `browser-session`: own profile, manual sign-in window, headless reuse, one browser per profile.
- `mailbox-reading`: accounts, listing and search, whole conversations, attachments.
- `read-only-guarantee`: no writing tools, model input as data, nothing marked as read, write guard, Trusted Types.
- `cross-platform`: no dependencies, browser discovery, user agent, profile lock, sign-in window and text streams per system.

### Modified Capabilities

(none)

## Impact

- New repository; no existing code changes.
- Depends only on Python >= 3.10 and an installed Chromium-based browser.
