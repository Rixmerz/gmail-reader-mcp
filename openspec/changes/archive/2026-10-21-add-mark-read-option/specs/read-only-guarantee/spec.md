## MODIFIED Requirements

### Requirement: Nothing marked as read
Listing SHALL read the visible rows without opening a conversation, and reading SHALL use the print view and attachment downloads, so an unread conversation SHALL stay unread unless the model passed `mark_read` true while the user's option is on.

#### Scenario: Read an unread conversation
- **WHEN** `gmail_read` reads a conversation marked unread without `mark_read`
- **THEN** the conversation is still unread

## ADDED Requirements

### Requirement: Optional mark as read
Marking as read SHALL be off by default and turned on only by the user, through the plugin option `mark_read` (`CLAUDE_PLUGIN_OPTION_MARK_READ`) or `GMAIL_MCP_MARK_READ`. While it is off, `gmail_read` SHALL NOT offer a `mark_read` parameter and SHALL ignore one if sent. While it is on, `gmail_read` SHALL offer `mark_read`, defaulting to false, and with it true SHALL open the conversation in Gmail's interface in a focused page, which marks it read, and say so. Marking as read SHALL be the only change to the mailbox the server can make.

#### Scenario: Option off
- **WHEN** the option is off and the client calls `gmail_read` with `mark_read` true
- **THEN** the conversation is read and stays unread, and the answer says nothing was marked as read

#### Scenario: Option on
- **WHEN** the option is on and the model calls `gmail_read` with `mark_read` true
- **THEN** the answer says "Marked as read" and the conversation no longer shows as unread

