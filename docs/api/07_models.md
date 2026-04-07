# Models

LLM adapters. Protocol-based — no inheritance required.

## BaseModelProtocol

```python
class BaseModelProtocol(Protocol):
    async def call(
        self,
        messages:    list[Message],
        tools:       list[ToolSchema],
        system:      str,
        max_tokens:  int,
    ) -> ModelResponse
```

Any object implementing this works as a model.

---

## ClaudeModel

```python
from codeminions.models import ClaudeModel

ClaudeModel(
    model:       str = "claude-sonnet-4-6",
    api_key:     str | None = None,     # defaults to ANTHROPIC_API_KEY env var
    max_tokens:  int = 8096,
    temperature: float = 1.0,
)
```

### String shorthand

```python
Minion(model="claude-sonnet-4-6")
Minion(model="claude-opus-4-6")
Minion(model="claude-haiku-4-5")
```

---

## OpenAIModel

```python
from codeminions.models import OpenAIModel

OpenAIModel(
    model:       str = "gpt-4o",
    api_key:     str | None = None,     # defaults to OPENAI_API_KEY env var
    max_tokens:  int = 4096,
    temperature: float = 1.0,
)
```

---

## Auto-detection

When `model` is not specified, SDK detects from environment:

```
ANTHROPIC_API_KEY set → ClaudeModel("claude-sonnet-4-6")
OPENAI_API_KEY set    → OpenAIModel("gpt-4o")
neither set           → raises ConfigurationError at run time
```

---

## ModelResponse (internal)

```python
@dataclass
class ModelResponse:
    tool_calls:  list[ToolCall]     # model wants to call tools
    text:        str                # model text response (if no tool calls)
    stop_reason: Literal["tool_use", "end_turn", "max_tokens"]
    input_tokens:  int
    output_tokens: int
```

---

## Custom model

```python
class MyModel:
    async def call(self, messages, tools, system, max_tokens) -> ModelResponse:
        ...

result = await Minion(model=MyModel()).run(task)
```
