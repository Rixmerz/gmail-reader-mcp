## ADDED Requirements

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
Listing SHALL read the visible rows without opening a conversation, and reading SHALL use the print view and attachment downloads, so an unread conversation SHALL stay unread.

#### Scenario: Read an unread conversation
- **WHEN** `gmail_read` reads a conversation marked unread and `gmail_inbox` lists unread mail again
- **THEN** the conversation is still unread

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
