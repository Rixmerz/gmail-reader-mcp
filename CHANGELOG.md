# Changelog

All notable changes to this project are documented here.
This project follows [Semantic Versioning](https://semver.org/).

## [0.2.0] — 2026-10-21

### Added

- **Mark conversations as read, if you allow it.** A plugin option, `mark_read`, off by default: Claude Code asks for it when the plugin is enabled, and it can be changed later in `/plugin`. `GMAIL_MCP_MARK_READ=1` does the same for a server registered by hand.
- While the option is on, `gmail_read` takes `mark_read`; with it true the server opens the conversation in Gmail by URL, in a focused page (Gmail does not mark a conversation read in an unfocused one), and the answer says "Marked as read".

### Unchanged

- While the option is off, nothing differs from 0.1.0: `gmail_read` has no `mark_read` parameter, and one sent anyway is ignored. Marking as read is the only change to the mailbox the server can ever make; it still cannot send, reply, archive or delete.

## [0.1.0] — 2026-10-20

First release.

### Added

- A read-only Gmail MCP server over a browser profile of its own: sign in once in a normal, unautomated window, then read headless through the Chrome DevTools Protocol. Python standard library only.
- `gmail_login`, `gmail_accounts`, `gmail_inbox` (inbox or Gmail search) and `gmail_read`, which reads a whole conversation from Gmail's print view and downloads the attachments of every message through the browser.
- A write guard that fails non-idempotent requests to any host other than `mail.google.com`; nothing is marked as read.
- macOS, Windows and Linux, with CI running unit tests and a real-browser check on all three.
- The `gmail-reader` Claude Code plugin, listed in the [Rixmerz marketplace](https://github.com/Rixmerz/claude-plugins).

[0.2.0]: https://github.com/Rixmerz/gmail-reader-mcp/releases/tag/v0.2.0
[0.1.0]: https://github.com/Rixmerz/gmail-reader-mcp/releases/tag/v0.1.0
