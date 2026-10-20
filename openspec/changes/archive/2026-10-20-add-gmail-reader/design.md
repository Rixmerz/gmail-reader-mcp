## Context

The logic comes from the Gmail module of Tanka, which drives Gmail's web app through Rastro. This server stands alone: no Tanka, no Rastro, no Playwright, so it installs with a `git clone` and runs anywhere Python and a Chromium-based browser run.

## Goals / Non-Goals

**Goals:**
- Read and search mail, and read whole conversations with their attachments.
- Sign in once by hand; reuse the sign-in headless.
- Make writing to the mailbox impossible from the server.

**Non-Goals:**
- Sending, replying, archiving, deleting, labelling or marking mail.
- Google's API or OAuth.
- Signing in automatically.

## Decisions

- **CDP over a WebSocket of our own instead of Playwright or Rastro.** Keeps the server dependency-free. The WebSocket client covers only what CDP needs: text frames, fragmentation, ping/pong, close.
- **Sign-in in a plain window.** Google blocks sign-in in automated browsers, so the window has no DevTools port; both it and the headless browser store cookies the same way (`--use-mock-keychain`, `--password-store=basic`).
- **Print view for conversations.** `view=pt` holds every message of a thread and opening it marks nothing as read. The earlier approach, the latest message's original MIME, lost attachments sent earlier in the thread.
- **Downloads through the browser.** Attachment links redirect to `mail-attachment.googleusercontent.com`, which a page `fetch` cannot read (CORS); `Network.loadNetworkResource` downloads them with the frame's cookies.
- **Trusted Types policy.** Gmail enforces Trusted Types; a named policy feeds the print view's HTML to an inert `DOMParser` document only.
- **User agent through CDP.** `Browser.getVersion` with `HeadlessChrome` replaced, set with `Emulation.setUserAgentOverride`, works on every system (`chrome.exe --version` prints nothing on Windows).
- **Graceful quit.** `Browser.close` before ending the process, because on Windows ending it is a kill that may lose the session.

## Risks / Trade-offs

- [Gmail changes its page] → selectors and the print view layout are isolated in `gmail.py`; CI's real-browser check catches a broken start.
- [Gmail needs POSTs to its own host to load and search, so the write guard cannot block them] → the guarantee rests on the code never clicking or typing; the guard blocks writes to every other host.
- [Automating a Google account may break a provider's terms or a company's policy] → stated in the README.
- [The profile holds a live session] → it lives in the user's home folder; anyone with access to it can read that mail.
