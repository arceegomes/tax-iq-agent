import json
import os
import re
import time
from typing import Generator

from openai import AzureOpenAI

from agent.prompts.system_prompt import SYSTEM_PROMPT
from agent.tools.tax_calculator import TOOL_DEFINITIONS, TOOL_FUNCTIONS


def _dispatch_tool(name: str, arguments_json: str, fallback_expenses: dict = None, tax_year: int = 2025) -> str:
    fn = TOOL_FUNCTIONS.get(name)
    if not fn:
        return json.dumps({"error": f"Unknown tool: {name}"})
    args = json.loads(arguments_json)
    # Always inject tax_year — not exposed in tool schema, injected server-side
    args["tax_year"] = tax_year
    # Model sometimes omits expenses — inject from user prompt as fallback
    if name in ("identify_deductions", "flag_audit_risks") and fallback_expenses:
        if not args.get("expenses"):
            args["expenses"] = fallback_expenses
    return fn(**args)


def run_tax_agent(user_message: str, tax_year: int = 2025) -> Generator[dict, None, None]:
    endpoint = os.environ.get("AZURE_OPENAI_ENDPOINT")
    api_key = os.environ.get("AZURE_OPENAI_API_KEY")
    model = os.environ.get("FOUNDRY_MODEL_NAME", "gpt-4o")

    if not endpoint or not api_key:
        yield {"type": "error", "content": "AZURE_OPENAI_ENDPOINT or AZURE_OPENAI_API_KEY not set in .env"}
        return

    try:
        client = AzureOpenAI(
            api_version="2025-01-01-preview",
            azure_endpoint=endpoint,
            api_key=api_key,
        )
    except Exception as e:
        yield {"type": "error", "content": f"Failed to connect: {e}"}
        return

    yield {"type": "status", "content": "Connected to Azure OpenAI (Foundry)"}

    try:
        assistant = client.beta.assistants.create(
            model=model,
            name="TaxIQ",
            instructions=SYSTEM_PROMPT,
            tools=TOOL_DEFINITIONS,
        )
    except Exception as e:
        yield {"type": "error", "content": f"Failed to create agent: {e}"}
        return

    yield {"type": "status", "content": "TaxIQ Agent initialized — starting analysis..."}

    thread = client.beta.threads.create()
    client.beta.threads.messages.create(thread_id=thread.id, role="user", content=user_message)
    run = client.beta.threads.runs.create(thread_id=thread.id, assistant_id=assistant.id)

    yield {"type": "status", "content": "Reasoning through your tax situation..."}

    # Parse expenses from user message as fallback in case model omits them in tool calls
    fallback_expenses = {}
    exp_match = re.search(r'Expenses:\s*(\{[^}]+\})', user_message)
    if exp_match:
        try:
            fallback_expenses = json.loads(exp_match.group(1))
        except Exception:
            fallback_expenses = {}

    reasoning_log = []

    for _ in range(30):
        time.sleep(2)
        run = client.beta.threads.runs.retrieve(thread_id=thread.id, run_id=run.id)

        if run.status == "completed":
            break

        if run.status in ("failed", "cancelled", "expired"):
            yield {"type": "error", "content": f"Agent run {run.status}: {getattr(run.last_error, 'message', '')}"}
            break

        if run.status == "requires_action":
            tool_calls = run.required_action.submit_tool_outputs.tool_calls
            outputs = []
            for tc in tool_calls:
                args_preview = tc.function.arguments[:100]
                yield {"type": "tool_call", "content": f"Calling: {tc.function.name}({args_preview}...)"}
                result = _dispatch_tool(tc.function.name, tc.function.arguments, fallback_expenses, tax_year)
                reasoning_log.append(
                    f"Tool: {tc.function.name}\nArgs: {tc.function.arguments}\nResult: {result}"
                )
                yield {"type": "tool_result", "content": result}
                outputs.append({"tool_call_id": tc.id, "output": result})
            run = client.beta.threads.runs.submit_tool_outputs(
                thread_id=thread.id, run_id=run.id, tool_outputs=outputs
            )

    # Collect ALL assistant messages in chronological order
    messages = client.beta.threads.messages.list(thread_id=thread.id)
    all_assistant_texts = []
    for msg in reversed(messages.data):
        if msg.role == "assistant":
            for block in msg.content:
                if hasattr(block, "text"):
                    all_assistant_texts.append(block.text.value)

    final_text = all_assistant_texts[-1] if all_assistant_texts else ""
    full_reasoning = "\n\n".join(all_assistant_texts)

    client.beta.assistants.delete(assistant.id)

    yield {
        "type": "done",
        "content": final_text,
        "reasoning_log": full_reasoning,
    }
