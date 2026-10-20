## ADDED Requirements

### Requirement: Own profile
The server SHALL keep its browser profile in `GMAIL_MCP_PROFILE`, by default `<GMAIL_MCP_HOME>/profile` with `GMAIL_MCP_HOME` defaulting to `~/.gmail-reader-mcp`. It SHALL NOT read or change the user's everyday browser profile.

#### Scenario: Separate from the everyday browser
- **WHEN** the user has their normal Chrome open and calls `gmail_login`
- **THEN** a second, independent browser instance opens on the server's own profile and the normal Chrome is untouched

### Requirement: Manual sign-in window
`gmail_login` and `server.py login` SHALL open a normal browser window on the profile at Google's sign-in page, with no DevTools port and no automation, because Google refuses to sign in inside an automated browser. `gmail_login` SHALL return at once and tell the model to ask the user to sign in and then quit that browser.

#### Scenario: Login from the assistant
- **WHEN** the model calls `gmail_login`
- **THEN** the sign-in window opens and the tool answers without waiting for the user

#### Scenario: Tools wait for the window to close
- **WHEN** the sign-in window opened by `gmail_login` is still running and the model calls `gmail_accounts`
- **THEN** the call fails with a message asking the user to finish and quit the browser

### Requirement: Headless reuse
Every reading tool SHALL start the same profile headless on first use, with a DevTools port bound to 127.0.0.1, and keep it until the server exits. The sign-in window and the headless browser SHALL store cookies the same way (`--use-mock-keychain` and `--password-store=basic`), so the headless browser can read what the window saved.

#### Scenario: Sign-in survives the switch to headless
- **WHEN** the user signed in and quit the window, and the model calls `gmail_accounts`
- **THEN** the headless browser lists the signed-in accounts without asking for a new sign-in

#### Scenario: Not signed in
- **WHEN** the profile has no Google session and a reading tool runs
- **THEN** Gmail redirects away from `mail.google.com` and the tool answers that the profile is not signed in and that `gmail_login` is needed

### Requirement: One browser per profile
The server SHALL refuse to start a browser while another process holds the profile, and say that the sign-in window or another server is using it. On exit it SHALL ask the browser to quit through CDP `Browser.close` before ending the process, so the profile and its session are saved.

#### Scenario: Profile in use
- **WHEN** another gmail-reader-mcp is running on the same profile and a tool starts the browser
- **THEN** the tool fails with a message naming the profile as in use, and no second browser starts

#### Scenario: Clean exit
- **WHEN** the MCP client closes the server's stdin
- **THEN** the headless browser quits and no browser process remains on the profile
