# mailbox-reading Specification

## Purpose
Lets an assistant find and read whole Gmail conversations, with every attachment, from the accounts signed in to the profile.

## Requirements

### Requirement: Accounts
`gmail_accounts` SHALL list every Google account signed in to the profile, with its `/mail/u/<n>/` index and the unread count of its inbox. When `GMAIL_MCP_ACCOUNTS` is set, only the addresses it lists SHALL be readable, and the others SHALL be shown as not readable.

#### Scenario: Several accounts
- **WHEN** two accounts are signed in and `gmail_inbox` is called without `account`
- **THEN** the call fails and names both addresses so the model can ask which one

### Requirement: Listing and search
`gmail_inbox` SHALL list up to `limit` (1 to 50) conversations newest first, numbered, with date, sender, subject, unread and attachment marks, message count and the start of the text. Without `search` it SHALL list the inbox; with `search` it SHALL run that Gmail search; `unread` SHALL add `is:unread`. The numbers SHALL stay valid for `gmail_read` until the next list.

#### Scenario: Search with Gmail syntax
- **WHEN** the model calls `gmail_inbox` with `search` `has:attachment filename:pdf`
- **THEN** the list holds only conversations Gmail matches for that query

### Requirement: Whole conversation
`gmail_read` SHALL read every message of the numbered conversation, oldest first, from Gmail's print view, each with sender, date, recipients, Cc and text. Text that a reply quotes of earlier messages SHALL be left out. Each message's text SHALL be cut at `GMAIL_MCP_BODY_CHARS` and the conversation's at `GMAIL_MCP_THREAD_CHARS`; past the limit the remaining messages' attachments SHALL still be listed.

#### Scenario: Attachment in an earlier message
- **WHEN** a conversation has four messages and the PDF was sent in the first one
- **THEN** `gmail_read` shows all four messages and the PDF under the first one

### Requirement: Attachments
Unless `attachments` is false, `gmail_read` SHALL download each attachment, and each picture in a body larger than 15 KB, through the browser with the page's cookies, into `<GMAIL_MCP_DOWNLOADS>/<account>/<date>-<conversation>/<message number>-<file name>`, and return each path. File names SHALL be reduced to letters, digits, `.`, `-` and `_`, so no attachment can be written outside its folder. A file over `GMAIL_MCP_MAX_MB` SHALL be listed as not saved.

#### Scenario: List without saving
- **WHEN** the model calls `gmail_read` with `attachments` false
- **THEN** every attachment is named with "not saved" and nothing is written to disk

#### Scenario: Hostile file name
- **WHEN** an attachment is named `../../evil name.pdf`
- **THEN** it is saved as `<n>-evil-name.pdf` inside the conversation's folder
