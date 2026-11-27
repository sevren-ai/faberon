# Faberon Chat reference

Faberon Chat is a [Pi](https://github.com/earendil-works/pi) extension for managing Faberon campaigns from a chat session. Install it following [install.md](install.md#6-install-faberon-chat-optional), start Faberon with the CLI (`faberon serve`), then start a chat session with `faberon chat`.

The extension contains two main parts:

- **Slash commands** that can be typed by the human during the chat session.
- **Tools** that can be called by the model during the conversation.

For instance, you can type the slash command `/faberon-list` to list all campaigns directly, or you can ask in natural language ("could you list my campaigns?"), and the model will call the matching tool for you.


## Slash commands and tools

Each slash command has a matching tool, and each tool has typed parameters validated against the v0 API contract. The drafter is the exception: it is just a conversational mode without specific tools.

| Slash command | Tool | Purpose |
|---|---|---|
| `/faberon-list` | `faberon_list_campaigns` | List campaigns with live status |
| `/faberon-show <campaign-id>` | `faberon_show_campaign` | Show one campaign's status and plan |
| `/faberon-events <campaign-id> [--verbose]` | `faberon_campaign_events` | Print the campaign's ledger. `--verbose` (or `-v`) adds full event payloads |
| `/faberon-draft` | - | Draft a research plan conversationally, review it, then submit it |
| `/faberon-create <plan.json> [repo-path]` | `faberon_create_campaign` | Submit a hand-written plan and start a campaign |
| `/faberon-successor <campaign-id> <budget-gpu-hours> <max-experiments>` | `faberon_create_successor` | Start a successor from a finished campaign's best kept commit |
| `/faberon-cancel <campaign-id> [reason]` | `faberon_cancel_campaign` | Request cancellation of an active campaign |
| `/faberon-idea <campaign-id> <idea text>` | `faberon_inject_idea` | Inject an advisory idea into an active campaign |
| `/faberon-resume <campaign-id>` | `faberon_resume_campaign` | Resume a pending campaign from its last checkpoint |

Some notes:

- Missing arguments are prompted interactively, one at a time. Empty answers are rejected.
- If a tool that writes campaign state is called by the AI in conversation, e.g. `faberon_create_campaign`, `faberon_create_successor`, `faberon_cancel_campaign` or `faberon_resume_campaign`, explicit confirmation by the human is required.
- Using the corresponding slash tools to create/cancel a campaign do not require additional human confirmation as the human already gave permission by typing the slash command.
- A successor campaign keeps the predecessor's research plan and requires a fresh budget of GPU hours & max experiments. If you want a new campaign with changes to the research plan, use `/faberon-create` or `/faberon-draft` instead.
- `/faberon-idea` is advisory: the idea lands in the ledger as `idea.injected` and the proposer weighs it at its next decision boundary. It does not interrupt an in-flight job and it is not guaranteed that the idea will be executed.
