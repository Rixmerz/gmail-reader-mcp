## ADDED Requirements

### Requirement: No dependencies
The server SHALL run on Python 3.10 or newer using only the standard library.

#### Scenario: Fresh machine
- **WHEN** a machine has Python and a Chromium-based browser and nothing else
- **THEN** `python3 server.py status` (`py` on Windows) runs without installing packages

### Requirement: Finding the browser
The server SHALL use `GMAIL_MCP_BROWSER` when set, and otherwise the first of Chrome, Chromium, Edge and Brave found where each system installs it: `/Applications` on macOS; `%PROGRAMFILES%`, `%PROGRAMFILES(X86)%` and `%LOCALAPPDATA%` on Windows; `/usr/bin` and `/snap/bin` on Linux.

#### Scenario: Windows with only Edge
- **WHEN** a Windows machine has no Chrome
- **THEN** the server uses `msedge.exe` from Program Files

### Requirement: A normal user agent
The headless browser SHALL present the user agent the browser reports, with `HeadlessChrome` replaced by `Chrome`, set through CDP so it works the same on every system.

#### Scenario: User agent on Windows
- **WHEN** the headless browser runs on Windows
- **THEN** `navigator.userAgent` contains `Windows NT` and `Chrome/`, and not `HeadlessChrome`

### Requirement: Profile lock per system
The server SHALL detect a profile in use from Chrome's `SingletonLock` symlink to a live process of this host on macOS and Linux, and from a `lockfile` it cannot delete on Windows.

#### Scenario: Lock while running
- **WHEN** the headless browser is running and the lock is checked
- **THEN** the profile is reported busy on every system, and free once the browser has quit

### Requirement: Closing the sign-in window
On Windows, `server.py login` SHALL wait for the user to close the browser, because ending a process there is a kill that may lose the session. On macOS and Linux it SHALL wait for Enter and then send SIGTERM. Messages SHALL say how to quit on each system.

#### Scenario: Login on Windows
- **WHEN** the user runs `py server.py login` and closes the window after signing in
- **THEN** the command lists the signed-in accounts

### Requirement: Text streams
The server SHALL read and write JSON-RPC as UTF-8 lines ending in `\n` on every system, whatever the console's code page.

#### Scenario: Accented subject on Windows
- **WHEN** a subject contains `ó` and the server runs on a cp1252 console
- **THEN** the client receives valid UTF-8 JSON
