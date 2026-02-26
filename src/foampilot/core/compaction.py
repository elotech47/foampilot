"""Conversation compaction (summarization) to manage context window size.

When triggered, makes a separate LLM call to summarize the conversation while
preserving: original task, key decisions + rationale, current file state, outstanding issues.
The message history is then replaced with the summary.
"""

from anthropic import Anthropic

import structlog

from foampilot import config

log = structlog.get_logger(__name__)

_COMPACTION_SYSTEM_PROMPT = """\
You are a specialized summarization assistant for FoamPilot, an AI agent that manages OpenFOAM CFD simulations.

Your job is to produce a concise, information-dense summary of the conversation so far.
The summary will REPLACE the conversation history, so it must preserve everything needed to continue.

Include ALL of the following:
1. The original user request (verbatim or very close)
2. Key decisions made and their rationale
3. Current state of every file that has been created or modified (list paths and what they contain)
4. Any assumptions the agent made
5. Outstanding issues or next steps
6. Current simulation phase

Format as structured markdown. Be precise and technical. Do NOT omit file paths or numerical values.
"""


def compact_conversation(
    messages: list[dict],
    client: Anthropic | None = None,
) -> list[dict]:
    """Summarize the conversation and return a single-message replacement history.

    Args:
        messages: The full message history to compact.
        client: Optional Anthropic client (creates one if not provided).

    Returns:
        A new message list containing only a single user message with the summary.
    """
    if client is None:
        client = Anthropic(api_key=config.ANTHROPIC_API_KEY)

    log.info("compaction_start", message_count=len(messages))

    # Build a plain-text representation for the summarizer
    transcript_parts = []
    for msg in messages:
        role = msg.get("role", "unknown")
        content = msg.get("content", "")
        if isinstance(content, list):
            # Tool use / tool result blocks
            parts = []
            for block in content:
                if isinstance(block, dict):
                    if block.get("type") == "text":
                        parts.append(block.get("text", ""))
                    elif block.get("type") == "tool_use":
                        parts.append(
                            f"[TOOL_CALL: {block.get('name')} input={block.get('input')}]"
                        )
                    elif block.get("type") == "tool_result":
                        parts.append(f"[TOOL_RESULT: {block.get('content')}]")
            content = "\n".join(parts)
        transcript_parts.append(f"--- {role.upper()} ---\n{content}")

    transcript = "\n\n".join(transcript_parts)

    response = client.messages.create(
        model=config.MODEL_COMPLEX,
        max_tokens=4096,
        system=_COMPACTION_SYSTEM_PROMPT,
        messages=[
            {
                "role": "user",
                "content": f"Summarize this FoamPilot conversation:\n\n{transcript}",
            }
        ],
    )

    summary_text = response.content[0].text  # type: ignore[index]

    log.info(
        "compaction_complete",
        original_messages=len(messages),
        summary_tokens=response.usage.output_tokens,
    )

    # Replace history with a single user message containing the summary
    return [
        {
            "role": "user",
            "content": (
                f"[CONVERSATION SUMMARY — history compacted to save context]\n\n{summary_text}"
            ),
        }
    ]
