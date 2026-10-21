## Why

Users who let Claude go through their mail want what it read to stop showing as unread. The server is read-only on purpose, so this has to be a change only the user can allow, not something the model can switch on.

## What Changes

- A plugin option `mark_read` (boolean, off by default) that Claude Code asks for when the plugin is enabled; `GMAIL_MCP_MARK_READ` does the same for a server registered by hand.
- While it is on, `gmail_read` offers `mark_read`; with it true the conversation is opened in Gmail's interface in a focused page, which marks it read.
- While it is off, nothing changes: no `mark_read` parameter, and one sent anyway is ignored.

## Capabilities

### New Capabilities

(none)

### Modified Capabilities

- `read-only-guarantee`: marking as read becomes the one change to the mailbox, behind a user option.

## Impact

- `gmail.py`, `server.py`, `.claude-plugin/plugin.json` (version 0.2.0), README.
