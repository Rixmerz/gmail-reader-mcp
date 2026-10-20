# gmail-reader-mcp

A **read-only** Gmail MCP server. It keeps a browser profile of its own: you sign in by hand once, in a normal window, and from then on the server reuses that same profile headless to list, search and read mail.

- No Google API, no OAuth, no app passwords: credentials never leave the browser profile.
- No dependencies: Python ≥ 3.10 (standard library only) and Chrome, Chromium, Edge or Brave. It talks to the browser over the Chrome DevTools Protocol with a WebSocket client of its own.
- macOS, Windows and Linux. CI runs the tests and a real-browser check on all three.
- Isolated: the profile, downloads and state live in `~/.gmail-reader-mcp` (`%USERPROFILE%\.gmail-reader-mcp` on Windows), apart from your everyday browser.

## Install

macOS and Linux:

```bash
git clone https://github.com/Rixmerz/gmail-reader-mcp.git ~/gmail-reader-mcp
claude mcp add --scope user gmail-reader -- python3 ~/gmail-reader-mcp/server.py
```

Windows (PowerShell):

```powershell
git clone https://github.com/Rixmerz/gmail-reader-mcp.git $HOME\gmail-reader-mcp
claude mcp add --scope user gmail-reader -- py "$HOME\gmail-reader-mcp\server.py"
```

Any stdio MCP client works: the command is `python3 /path/to/server.py` (`py` on Windows). The browser is found on its own; if it lives somewhere else, point `GMAIL_MCP_BROWSER` at the executable. Windows always has Edge, which works as well as Chrome.

## First sign-in

From Claude: ask it to use `gmail_login`. Or from a terminal:

```bash
python3 server.py login     # opens a normal window to sign in
python3 server.py status    # the accounts signed in to the profile
```

The sign-in window is **not automated**: Google refuses to sign in inside a browser that tools drive. You can sign in to several Google accounts (Gmail serves them as `/mail/u/0/`, `/u/1/`, …). When you are done, **quit that browser completely**: the profile takes one browser at a time.

| System | How to quit it | `server.py login` |
| --- | --- | --- |
| macOS | Cmd+Q (closing the window is not enough) | Press Enter in the terminal and the server quits it gracefully |
| Windows | Close the window | Waits for you to close it: ending a process from outside is a kill on Windows and could lose the session |
| Linux | Close the window | Press Enter, as on macOS |

Cookies are stored the same way for the window and for headless mode: with Chrome's mock keychain on macOS (`--use-mock-keychain`), with the basic store on Linux (`--password-store=basic`) and with the user account on Windows.

## Tools

| Tool | What it does |
| --- | --- |
| `gmail_login` | Opens the normal sign-in window on the server's profile and returns at once |
| `gmail_accounts` | The signed-in accounts and the unread count of each inbox |
| `gmail_inbox` | A numbered list of conversations: the inbox or a search in Gmail syntax (`from:`, `subject:`, `has:attachment`, `after:`…), optionally unread only |
| `gmail_read` | Reads a whole conversation of the last list by its number: every message, oldest first, with sender, recipients, date and text (without repeating what each reply quotes), and saves the attachments of every message to disk |

There is no tool that sends, replies, archives, deletes or marks mail.

## How it stays read-only

1. **By construction.** The code only navigates to Gmail URLs and evaluates fixed scripts that read the page; it never clicks or types. All that comes from the model is the search text, which goes URL-encoded into the address hash, and parameters, which are declared as JSON literals, never as code.
2. **Reading marks nothing as read.** The list is read from the visible rows without opening conversations. A conversation comes from Gmail's print view (`view=pt`), which holds every message of the thread, and the browser downloads each attachment with the session's cookies. Gmail enforces Trusted Types: the server creates a `gmail-reader-mcp` policy only to hand that HTML to an inert `DOMParser` document, which runs no scripts.
3. **Write guard.** Every request of the headless browser goes through CDP `Fetch`: any POST/PUT/PATCH/DELETE to a host other than `mail.google.com` is failed before it leaves. Gmail needs POSTs to its own host to load and search, so the guard cannot be total; the real guarantee is point 1.

## Configuration

| Variable | Default | What it sets |
| --- | --- | --- |
| `GMAIL_MCP_HOME` | `~/.gmail-reader-mcp` | The server's base folder |
| `GMAIL_MCP_PROFILE` | `$GMAIL_MCP_HOME/profile` | The browser profile with the session |
| `GMAIL_MCP_DOWNLOADS` | `$GMAIL_MCP_HOME/downloads` | Where attachments are saved (`<account>/<date>-<conversation>/<message number>-<file>`) |
| `GMAIL_MCP_ACCOUNTS` | (all) | Comma-separated addresses that may be read |
| `GMAIL_MCP_BROWSER` | the first one found | Chrome, Chromium, Edge or Brave executable |
| `GMAIL_MCP_MAX_MB` | `25` | Largest attachment saved |
| `GMAIL_MCP_BODY_CHARS` | `6000` | Longest text of each message |
| `GMAIL_MCP_THREAD_CHARS` | `30000` | Longest text of a whole conversation; past it, attachments are still listed |

## Risks

- It reads Gmail's web page, not the API: it can break when Google changes the interface. Labels are matched in English and Spanish.
- Automating a Google account may be against the provider's terms or a company's security policy. Check before using it with a work account.
- The profile holds the signed-in session: anyone with access to `~/.gmail-reader-mcp/profile` can read that mail. On macOS and Linux the cookies do not use the system keychain, so headless mode can read them.
- Tested with a real account on macOS only. On Windows and Linux, CI checks everything except signing in with a real account.

## Specs

The behaviour is specified with [OpenSpec](https://github.com/Fission-AI/OpenSpec) in [`openspec/specs`](openspec/specs): `browser-session`, `mailbox-reading`, `read-only-guarantee` and `cross-platform`. Check them with `openspec validate --all`.

## Files

| File | What it does |
| --- | --- |
| `server.py` | MCP server (stdio, JSON-RPC) and the `login` / `status` commands |
| `gmail.py` | Accounts, listing, reading conversations and downloading attachments |
| `browser.py` | Profile, sign-in window, headless browser, write guard and what differs per system |
| `cdp.py` | Minimal WebSocket and Chrome DevTools Protocol client |
| `tests/` | `python3 -m unittest discover -s tests` (no browser) and `python3 tests/smoke_browser.py` (real browser, no account) |
| `openspec/` | Specs and the archived change that introduced them |
| `.github/workflows/ci.yml` | Both checks on macOS, Windows and Linux, with Python 3.10 and 3.13 |

## License

[MIT](LICENSE)
