"""Reading Gmail through its own web page, in the signed-in headless profile.

Every Google account signed in to the profile is served as /mail/u/0/, /u/1/, ...
Listing reads the visible rows of Gmail's list (the inbox, or a search with
Gmail's syntax). Reading takes the whole conversation from Gmail's print view,
which holds every message of the thread with its attachments, and the browser
downloads each attachment; nothing is opened in the interface and nothing is
marked as read. There is no code here that clicks, types or sends.
"""
from __future__ import annotations

import base64
import html
import json
import os
import re
import time
import urllib.parse
from datetime import datetime
from pathlib import Path

from browser import HOME, Headless, BrowserError
from cdp import CDP, CDPError

BASE = "https://mail.google.com"
MAIL_HOST = "mail.google.com"
DOWNLOADS = Path(os.environ.get("GMAIL_MCP_DOWNLOADS", HOME / "downloads"))
MAX_BYTES = int(os.environ.get("GMAIL_MCP_MAX_MB", "25")) * 1024 * 1024
BODY_CAP = int(os.environ.get("GMAIL_MCP_BODY_CHARS", "6000"))  # per message
THREAD_CAP = int(os.environ.get("GMAIL_MCP_THREAD_CHARS", "30000"))  # the whole conversation
ONLY = {a.strip().lower() for a in os.environ.get("GMAIL_MCP_ACCOUNTS", "").split(",") if a.strip()}
MAX_ACCOUNTS = 10
TINY_INLINE = 15 * 1024  # pictures in the body below this are signatures and logos, not content
HEX_ID = re.compile(r"[0-9a-f]{6,24}")
LIST_FIRST = "Call gmail_inbox first."


class GmailError(Exception):
    """A failure the model should relay: the message says what to do next."""


def page(body: str, **params) -> str:
    """An async page script with its parameters declared as JSON literals (never spliced into the code)."""
    decl = "".join(f"  const {k} = {json.dumps(v, ensure_ascii=False)};\n" for k, v in params.items())
    return "(async () => {\n" + decl + body + "\n})()"


def evaluate(cdp: CDP, expr: str, timeout: float = 60):
    res = cdp.call("Runtime.evaluate", {"expression": expr, "awaitPromise": True, "returnByValue": True}, timeout=timeout)
    if "exceptionDetails" in res:
        detail = res["exceptionDetails"].get("exception", {}).get("description") or res["exceptionDetails"].get("text")
        raise GmailError(f"Gmail's page failed: {str(detail)[:300]}. Tell the user.")
    value = res.get("result", {}).get("value")
    return json.loads(value) if isinstance(value, str) else value


STATE = "JSON.stringify({host: location.host, ready: document.readyState, gmail: !!(window.GLOBALS && GLOBALS[9])})"


def goto(cdp: CDP, url: str, timeout: float = 90) -> None:
    """Load `url` and wait until Gmail is up; a redirect away from Gmail means the profile is not signed in."""
    cdp.call("Page.navigate", {"url": url}, timeout=60)
    deadline = time.time() + timeout
    while time.time() < deadline:
        time.sleep(0.5)
        try:
            s = evaluate(cdp, STATE, timeout=10)
        except (CDPError, GmailError):
            continue  # the page is between documents
        if s["host"] == MAIL_HOST and s["gmail"]:
            return
        if s["host"] not in (MAIL_HOST, "") and s["ready"] == "complete":
            raise GmailError("The browser profile is not signed in to Google. Tell the user to call gmail_login "
                             "(or run `python3 server.py login`) and sign in; do not retry.")
    raise GmailError(f"Gmail did not load within {timeout:.0f} s. Tell the user; do not retry.")


def download(cdp: CDP, url: str, limit: int) -> bytes | None:
    """`url` loaded by the browser itself with the page's cookies (no CORS); None when it is over `limit` bytes."""
    frame = cdp.call("Page.getFrameTree")["frameTree"]["frame"]["id"]
    res = cdp.call("Network.loadNetworkResource", {"frameId": frame, "url": url,
                                                   "options": {"disableCache": True, "includeCredentials": True}}, timeout=120)
    resource = res.get("resource") or {}
    if not resource.get("success"):
        raise GmailError(f"Gmail answered {resource.get('httpStatusCode') or resource.get('netErrorName')} for a download.")
    handle, data = resource["stream"], bytearray()
    try:
        while True:
            chunk = cdp.call("IO.read", {"handle": handle, "size": 1 << 20}, timeout=60)
            data += base64.b64decode(chunk["data"]) if chunk.get("base64Encoded") else chunk["data"].encode("utf-8")
            if len(data) > limit:
                return None
            if chunk.get("eof"):
                return bytes(data)
    finally:
        cdp.send("IO.close", {"handle": handle})


ACCOUNTS = r"""
  // Each signed-in account answers at /mail/u/<n>/; past the last one Gmail serves account 0 again.
  const seen = [];
  for (let i = 0; i < max; i++) {
    const r = await fetch(`/mail/u/${i}/feed/atom`, {credentials: "include"});
    if (!r.ok) { if (i === 0) return JSON.stringify({error: r.status}); break; }
    const t = await r.text();
    const m = t.match(/<title>[^<]*?([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+)<\/title>/);
    if (!m || seen.some(s => s.address === m[1].toLowerCase())) break;
    seen.push({index: i, address: m[1].toLowerCase(), unread: Number((t.match(/<fullcount>(\d+)</) || [])[1] || 0)});
  }
  return JSON.stringify({accounts: seen});
"""

LIST = r"""
  const sleep = ms => new Promise(r => setTimeout(r, ms));
  // The list renders after the page loads; only the visible rows belong to this view.
  let rows = [];
  for (let i = 0; i < 40; i++) {
    await sleep(500);
    rows = [...document.querySelectorAll("tr.zA")].filter(r => r.offsetParent !== null);
    const main = document.querySelector('div[role="main"]');
    const empty = main && /No hay|No messages|No se encontraron|didn't match|no coinciden/i.test(main.innerText.slice(0, 400));
    if ((rows.length || empty) && i >= 2) break;
  }
  const pick = (r, s) => r.querySelector(s);
  return JSON.stringify({rows: rows.slice(0, limit).map(r => {
    const who = pick(r, "span[email]");
    const date = pick(r, "td.xW span[title], td.xW span");
    const th = pick(r, "[data-legacy-thread-id]");
    const count = pick(r, ".bx0");
    return {thread: th ? th.getAttribute("data-legacy-thread-id") : null,
      from: who ? (who.getAttribute("name") || who.textContent.trim()) : "", email: who ? who.getAttribute("email") : "",
      subject: (pick(r, ".bog") || {}).textContent || "", messages: count ? count.textContent.trim() : "",
      snippet: ((pick(r, ".y2") || {}).textContent || "").replace(/\s+/g, " ").replace(/^\s*-\s*/, ""),
      date: date ? (date.getAttribute("title") || date.textContent) : "", unread: r.classList.contains("zE"),
      attachments: !!pick(r, ".brd, .aKS, [aria-label*='ttach'], [aria-label*='djunto']")};
  })});
"""

THREAD = r"""
  // The print view holds every message of the conversation; fetching it marks nothing as read.
  const id = BigInt("0x" + hex).toString();
  const r = await fetch(`/mail/u/${index}/?ik=${GLOBALS[9]}&view=pt&search=all&permthid=thread-f:${id}`, {credentials: "include"});
  if (!r.ok) return JSON.stringify({error: r.status});
  // Gmail enforces Trusted Types; this policy only feeds an inert DOMParser document, which never runs scripts.
  window.__gmailReaderPolicy = window.__gmailReaderPolicy || trustedTypes.createPolicy("gmail-reader-mcp", {createHTML: s => s});
  const doc = new DOMParser().parseFromString(window.__gmailReaderPolicy.createHTML(await r.text()), "text/html");
  const abs = href => new URL(href, `${location.origin}/mail/u/${index}/`).href;
  const subject = ((doc.querySelector("font[size='+1'] b") || {}).textContent || "").trim();
  const messages = [...doc.querySelectorAll("table.message")].map(t => {
    const [head, meta, content] = t.rows;
    const cells = head ? head.cells : [];
    const lines = meta ? [...meta.querySelectorAll("div")].map(d => d.textContent.replace(/\s+/g, " ").trim()) : [];
    const files = [...t.querySelectorAll("a[href*='view=att'][href*='disp=attd']")].map(a => {
      const row = a.closest("tr");
      return {name: ((row && row.querySelector("b")) || a).textContent.trim(), url: abs(a.getAttribute("href"))};
    });
    const pictures = [...t.querySelectorAll("img[src*='view=att']")].map((img, i) =>
      ({name: img.getAttribute("alt") || `picture-${i + 1}`, url: abs(img.getAttribute("src")), inline: true}));
    let body = "";
    if (content) {
      const box = content.querySelector("div[style*='overflow']") || content;
      // Earlier messages are in the thread already: drop what each reply quotes of them.
      box.querySelectorAll(".gmail_quote, .gmail_quote_container, blockquote[type='cite']").forEach(q => q.remove());
      body = box.innerHTML;
    }
    return {from: cells[0] ? cells[0].textContent.replace(/\s+/g, " ").trim() : "",
            date: cells[1] ? cells[1].textContent.trim() : "",
            to: lines.find(l => /^(Para|To):/i.test(l)) || "", cc: lines.find(l => /^Cc:/i.test(l)) || "",
            body, files: [...new Map(files.map(f => [f.url, f])).values()], pictures};
  });
  return JSON.stringify({subject, messages});
"""


# ---------------------------------------------------------------- formatting (no browser)

def html_to_text(body: str) -> str:
    body = re.sub(r"(?is)<(script|style|head)[^>]*>.*?</\1>", "", body)
    body = re.sub(r"(?i)<img[^>]*>", "", body)
    body = re.sub(r"(?i)<br\s*/?>|</p>|</div>|</tr>|</li>|</h\d>", "\n", body)
    body = re.sub(r"(?i)</td>", " | ", body)
    body = html.unescape(re.sub(r"<[^>]+>", "", body))
    body = re.sub(r"[ \t\xa0]+", " ", body)
    body = re.sub(r" ?\| ?(\n|$)", r"\1", body)
    return re.sub(r"\n\s*\n+", "\n\n", body).strip()


def safe(name: str) -> str:
    """A file name with no directory part, so an attachment cannot be written outside its folder."""
    cleaned = re.sub(r"[^\w.\-]+", "-", (name or "attachment").strip()).strip("-.")[:100]
    return cleaned or "attachment"


def render(address: str, number: int, thread: dict, cap: int = THREAD_CAP) -> str:
    """The conversation as text, oldest message first; `files` entries already carry `path` or `note`."""
    msgs = thread["messages"]
    out = [f"Conversation {number} of {address}: \"{thread['subject'] or '(no subject)'}\", {len(msgs)} message(s), "
           "oldest first. Nothing was marked as read."]
    used = 0
    for i, m in enumerate(msgs, 1):
        text = html_to_text(m["body"])
        text = text[:BODY_CAP] + ("\n… (message cut)" if len(text) > BODY_CAP else "")
        if used + len(text) > cap:
            text = "… (left out: the conversation is over the length limit; the attachments below are still listed)"
        used += len(text)
        out += ["", f"=== Message {i}/{len(msgs)}", f"From: {m['from']}", f"Date: {m['date']}"]
        out += [line for line in (m["to"], m["cc"]) if line]
        out += ["---", text]
        for f in m["files"]:
            out.append(f"Attachment: {f['name']}: {f.get('path') or f.get('note', '')}")
    if any(f.get("path") for m in msgs for f in m["files"]):
        out += ["", "To look at an image or a PDF, open it with Read at that exact path."]
    return "\n".join(out)


def choose(accounts: list[dict], account: str | None) -> dict:
    """The one signed-in account this call reads, or a GmailError that names the ones there are."""
    usable = [a for a in accounts if not ONLY or a["address"] in ONLY]
    if not usable:
        raise GmailError("No readable account is signed in to the profile. Tell the user to call gmail_login.")
    names = ", ".join(a["address"] for a in usable)
    if not account:
        if len(usable) == 1:
            return usable[0]
        raise GmailError(f"{len(usable)} mailboxes are signed in: {names}. Ask the user which one, and pass it as account.")
    want = account.strip().lower()
    hits = [a for a in usable if want in (a["address"], a["address"].split("@")[0])]
    if len(hits) != 1:
        raise GmailError(f"\"{account}\" is not a readable mailbox here. Readable: {names}.")
    return hits[0]


def search_hash(search: str, unread: bool) -> tuple[str, str]:
    query = " ".join(x for x in (search.strip(), "is:unread" if unread else "") if x)
    return query, ("search/" + urllib.parse.quote(query, safe="").replace("%20", "+")) if query else "inbox"


# ---------------------------------------------------------------- the reader

class Gmail:
    def __init__(self, browser: Headless):
        self.browser = browser
        self.listing: dict | None = None  # the last list, so the model refers to conversations by number

    def _gmail_page(self) -> CDP:
        cdp = self.browser.page()
        s = evaluate(cdp, STATE, timeout=10)
        if not (s["host"] == MAIL_HOST and s["gmail"]):
            goto(cdp, f"{BASE}/mail/u/0/")
        return cdp

    def _accounts(self, cdp: CDP) -> list[dict]:
        res = evaluate(cdp, page(ACCOUNTS, max=MAX_ACCOUNTS), timeout=60)
        if res.get("error") or not res.get("accounts"):
            raise GmailError("The browser profile is not signed in to Google. Tell the user to call gmail_login.")
        return res["accounts"]

    def accounts(self) -> str:
        accounts = self._accounts(self._gmail_page())
        lines = [f"{len(accounts)} account(s) signed in to the profile:"]
        for a in accounts:
            note = "" if not ONLY or a["address"] in ONLY else "  (not readable: left out of GMAIL_MCP_ACCOUNTS)"
            lines.append(f"/u/{a['index']}  {a['address']}  {a['unread']} unread in the inbox{note}")
        return "\n".join(lines)

    def inbox(self, search: str = "", unread: bool = False, limit: int = 15, account: str | None = None) -> str:
        cdp = self._gmail_page()
        acct = choose(self._accounts(cdp), account)
        query, hash_ = search_hash(search or "", unread)
        # A full load: changing only the hash of a running Gmail page does not always run the search.
        cdp.call("Page.navigate", {"url": "about:blank"})
        goto(cdp, f"{BASE}/mail/u/{acct['index']}/#{hash_}")
        rows = [r for r in evaluate(cdp, page(LIST, limit=limit), timeout=90)["rows"] if r["thread"]]
        self.listing = {"address": acct["address"], "index": acct["index"],
                        "threads": {str(i): r["thread"] for i, r in enumerate(rows, 1)}}
        what = f"matching \"{query}\"" if query else "in the inbox"
        out = [f"Today is {datetime.now().astimezone():%Y-%m-%d}. {len(rows)} conversation(s) {what} for {acct['address']}, "
               "newest first (number | date | from | subject | marks | start):"]
        for i, r in enumerate(rows, 1):
            marks = [x for x in ("UNREAD" if r["unread"] else "", "ATTACHMENTS" if r["attachments"] else "") if x]
            if r["messages"]:
                marks.append(f"{r['messages']} MESSAGES")
            sender = f"{r['from']} <{r['email']}>" if r["email"] else r["from"]
            out.append(f"{i} | {r['date']} | {sender} | {r['subject'] or '(no subject)'} | {' '.join(marks) or '-'} | "
                       f"{r['snippet'][:90]}")
        if rows:
            out.append("To read a whole conversation, with its attachments: gmail_read with its number. "
                       "Nothing was marked as read.")
        return "\n".join(out)

    def read(self, number: int, attachments: bool = True) -> str:
        listing = self.listing
        if not listing:
            raise GmailError(f"There is no list yet. {LIST_FIRST}")
        thread_id = listing["threads"].get(str(number))
        if not thread_id:
            raise GmailError(f"There is no conversation number {number} in the last list. {LIST_FIRST}")
        if not HEX_ID.fullmatch(thread_id):
            raise GmailError(f"Conversation {number} has an id Gmail did not give in the expected form. {LIST_FIRST}")
        cdp = self.browser.page()
        goto(cdp, f"{BASE}/mail/u/{listing['index']}/")
        thread = evaluate(cdp, page(THREAD, index=listing["index"], hex=thread_id), timeout=120)
        if thread.get("error"):
            raise GmailError(f"Gmail answered {thread['error']} for that conversation. Tell the user; do not retry.")
        if not thread["messages"]:
            raise GmailError("Gmail's print view of that conversation had no messages. Tell the user; do not retry.")
        folder = DOWNLOADS / safe(listing["address"]) / f"{datetime.now().astimezone():%Y%m%d}-{thread_id}"
        for i, m in enumerate(thread["messages"], 1):
            self._save(cdp, m, folder, f"{i}-", attachments)
        return render(listing["address"], number, thread)

    def _save(self, cdp: CDP, message: dict, folder: Path, prefix: str, attachments: bool) -> None:
        """Download a message's attachments (and the larger pictures in its body) into `folder`, noting each outcome."""
        kept = []
        for f in message["files"] + message["pictures"]:
            if not attachments:
                if not f.get("inline"):
                    f["note"] = "not saved (attachments=false)"
                    kept.append(f)
                continue
            try:
                data = download(cdp, f["url"], MAX_BYTES)
            except (GmailError, CDPError) as e:
                f["note"] = f"could not be downloaded ({e})"
                kept.append(f)
                continue
            if data is None:
                f["note"] = f"not saved: over the {MAX_BYTES // (1024 * 1024)} MB limit"
            elif f.get("inline") and len(data) < TINY_INLINE:
                continue  # a logo or a signature
            else:
                folder.mkdir(parents=True, exist_ok=True)
                path = folder / (prefix + safe(f["name"]))
                path.write_bytes(data)
                f["path"] = f"{path} ({len(data) // 1024} KB{', picture in the body' if f.get('inline') else ''})"
            kept.append(f)
        message["files"] = kept


__all__ = ["Gmail", "GmailError", "BrowserError", "html_to_text", "render", "choose", "search_hash", "safe"]
