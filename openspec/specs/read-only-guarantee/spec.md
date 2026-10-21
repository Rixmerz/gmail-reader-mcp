# read-only-guarantee Specification

## Purpose
Makes sure the server can only read mail: it never sends, replies, archives, deletes or labels anything, whatever the model asks or a message says, and it marks a conversation as read only when the user turned that option on.

## Requirements

### Requirement: No writing tools
The server SHALL expose only `gmail_login`, `gmail_accounts`, `gmail_inbox` and `gmail_read`. Its code SHALL only navigate to Gmail URLs and evaluate fixed page scripts; it SHALL NOT click, type or submit anything in Gmail's interface. A call to any other tool name SHALL fail.

#### Scenario: Asked to send
- **WHEN** the client calls a tool named `gmail_send`
- **THEN** the call fails and nothing reaches Gmail

### Requirement: Model input is data
Values from the model SHALL reach the page only as JSON literals declared ahead of the fixed script, and a search SHALL reach Gmail only URL-encoded in the address hash. Conversation ids SHALL be checked as hexadecimal before use.

#### Scenario: Search that looks like code
- **WHEN** `search` is `"); alert(1); ("`
- **THEN** it is sent as an encoded Gmail search and no script runs

### Requirement: Nothing marked as read
Listing SHALL read the visible rows without opening a conversation, and reading SHALL use the print view and attachment downloads, so an unread conversation SHALL stay unread unless the model passed `mark_read` true while the user's option is on.

#### Scenario: Read an unread conversation
- **WHEN** `gmail_read` reads a conversation marked unread without `mark_read`
- **THEN** the conversation is still unread

### Requirement: Optional mark as read
Marking as read SHALL be off by default and turned on only by the user, through the plugin option `mark_read` (`CLAUDE_PLUGIN_OPTION_MARK_READ`) or `GMAIL_MCP_MARK_READ`. While it is off, `gmail_read` SHALL NOT offer a `mark_read` parameter and SHALL ignore one if sent. While it is on, `gmail_read` SHALL offer `mark_read`, defaulting to false, and with it true SHALL open the conversation in Gmail's interface in a focused page, which marks it read, and say so. Marking as read SHALL be the only change to the mailbox the server can make.

#### Scenario: Option off
- **WHEN** the option is off and the client calls `gmail_read` with `mark_read` true
- **THEN** the conversation is read and stays unread, and the answer says nothing was marked as read

#### Scenario: Option on
- **WHEN** the option is on and the model calls `gmail_read` with `mark_read` true
- **THEN** the answer says "Marked as read" and the conversation no longer shows as unread

### Requirement: Write guard
Every request of the headless browser SHALL pass through CDP `Fetch`: GET, HEAD and OPTIONS SHALL proceed, and any other method to a host other than `mail.google.com` SHALL be failed before it leaves the browser. Gmail's own POSTs to `mail.google.com` SHALL proceed because Gmail loads and searches through them.

#### Scenario: Post to another Google service
- **WHEN** Gmail's page posts to `play.google.com` or `calendar-pa.clients6.google.com`
- **THEN** the request is failed and Gmail keeps working

### Requirement: Trusted Types
Gmail enforces Trusted Types, so the server SHALL create a policy named `gmail-reader-mcp` used only to hand the print view's HTML to an inert `DOMParser` document, which runs no scripts.

#### Scenario: Parsing the print view
- **WHEN** `gmail_read` parses a conversation
- **THEN** the HTML is parsed through that policy and no script in it runs
