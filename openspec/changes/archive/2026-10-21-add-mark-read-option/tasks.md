## 1. Option

- [x] 1.1 `mark_read_enabled` reads `CLAUDE_PLUGIN_OPTION_MARK_READ` or `GMAIL_MCP_MARK_READ`, off by default
- [x] 1.2 `userConfig.mark_read` in `plugin.json`

## 2. Marking

- [x] 2.1 `gmail_read` offers `mark_read` only while the option is on
- [x] 2.2 Open the conversation with focus emulation, wait for it to show, report "Marked as read"
- [x] 2.3 Checked with a real account: ignored while off, marked read while on

## 3. Tests

- [x] 3.1 Option parsing, tool schema per option, MCP tools/list and instructions with the plugin option
