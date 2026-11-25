# Faberon Chat reference

Faberon Chat is a [Pi](https://github.com/earendil-works/pi-coding-agent) extension for managing Faberon campaigns from a chat session. Install it following [install.md](install.md#6-install-faberon-chat-optional), start Faberon with the CLI (`faberon serve`), then start a chat session with `faberon chat`.

The extension contains two main parts:

- **Slash commands** that can be typed by the human during the chat session.
- **Tools** that can be called by the model during the conversation.

For instance, you can type the slash command `/faberon-list` to list all campaigns directly, or you can ask in natural language ("could you list my campaigns?"), and the model will call the matching tool for you.


## Slash commands

| Command | Purpose |
|---|---|
| `/faberon-list` | List campaigns with live status |
| `/faberon-show <campaign-id>` | Show one campaign's status and plan |
| `/faberon-events <campaign-id> [--verbose]` | Print the campaign's ledger. `--verbose` (or `-v`) adds full event payloads |
| `/faberon-draft` | Draft a research plan conversationally, review it, then submit it |
| `/faberon-create <plan.json> [repo-path]` | Submit a hand-written plan and start a campaign |
| `/faberon-successor <campaign-id> <budget-gpu-hours> <max-experiments>` | Start a successor from a finished campaign's best kept commit |
| `/faberon-cancel <campaign-id> [reason]` | Request cancellation of an active campaign |
| `/faberon-idea <campaign-id> <idea text>` | Inject an advisory idea into an active campaign |
| `/faberon-resume <campaign-id>` | Resume a pending campaign from its last checkpoint |

Some notes:

- Missing arguments are prompted interactively, one at a time. Empty answers are rejected.
- Submission of a new campaign ether through "create" or "successor" requires an explicit confirmation of the human.
- A successor campaign keeps the predecessor's research plan and requires a fresh budget of GPU hours & max experiments. If you want a new campaign with changes to the research plan, use `/faberon-create` or `/faberon-draft` instead.
- `/faberon-idea` is advisory: the idea lands in the ledger as `idea.injected` and the proposer weighs it at its next decision boundary. It does not interrupt an in-flight job and it is not guaranteed that the idea will be executed.

## Tools

Each tool has typed parameters validated against the v0 API contract.

| Tool | Purpose |
|---|---|
| `faberon_list_campaigns` | List campaigns with live status |
| `faberon_show_campaign` | Show one campaign's status and plan |
| `faberon_campaign_events` | Read a bounded slice of a campaign's ledger |
| `faberon_create_campaign` | Submit a research plan and start a campaign |
| `faberon_create_successor` | Create a successor campaign |
| `faberon_cancel_campaign` | Cancel an active campaign |
| `faberon_inject_idea` | Inject an advisory idea into an active campaign |
| `faberon_resume_campaign` | Resume a pending campaign from its checkpoint |
