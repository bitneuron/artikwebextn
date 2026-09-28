"""Offline checks for the API contracts required by the model migration."""
from types import SimpleNamespace as NS
from unittest.mock import Mock

import pytest
from models import openai_create, anthropic_create, _compat

ToolNotCalled = _compat.ToolNotCalled


def test_astra_tool_round_trip_preserves_reasoning_and_call_ids():
    reasoning = {"type": "reasoning", "id": "rs_1", "encrypted_content": "opaque"}
    call = {"type": "function_call", "id": "fc_1", "call_id": "call_1",
            "name": "lookup", "arguments": '{"ticker":"ABC"}'}
    outputs = [NS(**v, model_dump=Mock(return_value=v)) for v in (reasoning, call)]
    client = Mock()
    client.responses.create.return_value = NS(status="completed", output=outputs, output_text="")
    messages = [{"role": "user", "content": "Look up ABC"}]
    args = dict(model="gpt-6-astra", messages=messages, max_completion_tokens=2000,
                reasoning_effort="minimal", tools=[{"type": "function", "function": {
                    "name": "lookup", "parameters": {"type": "object", "properties": {}}}}],
                tool_choice={"type": "function", "function": {"name": "lookup"}})
    result = openai_create(client, **args)
    request = client.responses.create.call_args.kwargs
    assert request["reasoning"] == {"effort": "low"}
    assert request["tools"][0]["strict"] is False
    assert request["tool_choice"] == {"type": "function", "name": "lookup"}
    assert request["store"] is False
    message = result.choices[0].message
    assert message.tool_calls[0].id == "call_1"
    messages.extend([message, {"role": "tool", "tool_call_id": "call_1", "content": "42"}])
    openai_create(client, **args)
    replay = client.responses.create.call_args.kwargs["input"]
    assert replay[1:3] == [reasoning, call]
    assert replay[3] == {"type": "function_call_output", "call_id": "call_1", "output": "42"}
    client.chat.completions.create.assert_not_called()


def test_legacy_model_still_uses_chat_without_internal_history_fields():
    client = Mock()
    openai_create(client, model="gpt-5", messages=[{"role": "assistant", "content": "ok",
                                                  "_responses_output": None}],
                  reasoning_effort="minimal")
    assert client.chat.completions.create.call_args.kwargs["messages"] == [
        {"role": "assistant", "content": "ok"}]
    client.responses.create.assert_not_called()


def test_astra_text_uses_supported_reasoning():
    client = Mock()
    openai_create(client, model="gpt-6-astra", messages=[], reasoning_effort="minimal", temperature=1)
    args = client.chat.completions.create.call_args.kwargs
    assert args["reasoning_effort"] == "low"
    assert "temperature" not in args


def test_opus_5_forced_tool_keeps_non_thinking_contract():
    client = Mock()
    anthropic_create(client, model="claude-opus-5", tool_choice={"type": "tool", "name": "emit"})
    assert client.messages.create.call_args.kwargs["thinking"] == {"type": "disabled"}
    anthropic_create(client, model="claude-opus-5", thinking={"type": "adaptive"})
    assert client.messages.create.call_args.kwargs["thinking"] == {"type": "adaptive"}


def _replying(*blocks):
    client = Mock()
    client.messages.create.return_value = NS(content=list(blocks), stop_reason="end_turn")
    return client


def test_opus_5_5_is_never_sent_disabled_thinking():
    # Opus 5.5 returns 400 for thinking {"type": "disabled"} at every effort level.
    # A mock can't see that, so pin the contract here: the shim must leave it alone.
    client = _replying(NS(type="tool_use", name="emit", input={}))
    anthropic_create(client, model="claude-opus-5-5", tool_choice={"type": "tool", "name": "emit"})
    assert "thinking" not in client.messages.create.call_args.kwargs


def test_forced_tool_on_opus_5_5_becomes_auto_plus_an_instruction():
    # Opus 5.5 400s on a forced tool_choice; the shim asks for the tool in the prompt instead.
    client = _replying(NS(type="tool_use", name="emit", input={"ok": True}))
    msg = anthropic_create(client, model="claude-opus-5-5", max_tokens=1200, system="SYS",
                           tools=[{"name": "emit"}], tool_choice={"type": "tool", "name": "emit"})
    sent = client.messages.create.call_args.kwargs
    assert sent["tool_choice"] == {"type": "auto"}
    assert sent["system"].startswith("SYS") and "`emit`" in sent["system"]
    assert sent["max_tokens"] >= 8000          # thinking would otherwise eat a 1,200 budget
    assert msg.content[0].input == {"ok": True}


def test_a_list_system_prompt_gets_a_block_and_the_callers_list_is_untouched():
    system = [{"type": "text", "text": "SYS", "cache_control": {"type": "ephemeral"}}]
    client = _replying(NS(type="tool_use", name="emit", input={}))
    anthropic_create(client, model="claude-opus-5-5", system=system, tool_choice={"type": "tool", "name": "emit"})
    sent = client.messages.create.call_args.kwargs["system"]
    assert sent[0] == system[0] and "`emit`" in sent[-1]["text"] and len(system) == 1


def test_opus_5_5_skipping_the_tool_raises_so_the_chain_falls_back():
    # A text reply where a tool was required would break every caller; raising hands
    # the request to Opus 5, which still honours a forced tool_choice.
    client = _replying(NS(type="text", text="Here you go"))
    with pytest.raises(ToolNotCalled, match="emit"):
        anthropic_create(client, model="claude-opus-5-5", tool_choice={"type": "tool", "name": "emit"})


def test_opus_5_still_gets_a_real_forced_tool_choice():
    client = _replying(NS(type="tool_use", name="emit", input={}))
    anthropic_create(client, model="claude-opus-5", tool_choice={"type": "tool", "name": "emit"})
    assert client.messages.create.call_args.kwargs["tool_choice"] == {"type": "tool", "name": "emit"}


def test_incomplete_astra_response_is_not_treated_as_success():
    client = Mock()
    client.responses.create.return_value = NS(status="incomplete")
    with pytest.raises(RuntimeError, match="incomplete"):
        openai_create(client, model="gpt-6-astra", messages=[], tools=[{
            "type": "function", "function": {"name": "lookup"}}], max_completion_tokens=100)
