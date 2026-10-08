import json
import urllib.request
import urllib.error
from pydantic import ValidationError
from approval.core.models import Extraction
from approval.infrastructure.retry import retry, TransientFailure, PermanentFailure, InvalidModelOutput
from .prompt import SYSTEM, VERSION

class ClaudeExtractor:
    def __init__(self, api_key, model, transport=None):
        if not api_key or not model: raise ValueError("Set ANTHROPIC_API_KEY and ANTHROPIC_MODEL")
        self.api_key, self.model = api_key, model
        self.identity = f"claude:{model}:{VERSION}"
        self.transport = transport or self._post
        self.last_usage = {}

    def _post(self, body):
        req = urllib.request.Request("https://api.anthropic.com/v1/messages",
            data=json.dumps(body).encode(), headers={"x-api-key": self.api_key,
            "anthropic-version": "2023-06-01", "content-type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=45) as response:
                return json.load(response)
        except urllib.error.HTTPError as exc:
            if exc.code in (408, 429, 500, 502, 503, 504, 529):
                raise TransientFailure(f"provider_http_{exc.code}") from None
            raise PermanentFailure(f"provider_http_{exc.code}") from None
        except (urllib.error.URLError, TimeoutError):
            raise TransientFailure("provider_connection_failure") from None

    def extract(self, document):
        content = json.dumps({"document_id": document.id, "role": document.role,
            "pages": [{"page": p.number, "text": p.text} for p in document.pages if p.usable]}, ensure_ascii=False)
        if len(content) > 100_000: raise PermanentFailure("document_context_limit")
        body = {"model": self.model, "max_tokens": 6500, "system": SYSTEM,
            "messages": [{"role": "user", "content": content}],
            "tools": [{"name": "submit_extraction", "description": "Return evidence-grounded facts",
                "input_schema": Extraction.model_json_schema()}],
            "tool_choice": {"type": "tool", "name": "submit_extraction"}}
        # One schema repair; content contradictions never trigger retries.
        for repair in range(2):
            response = retry(lambda: self.transport(body))
            self.last_usage = response.get("usage", {})
            try:
                if response.get("stop_reason") == "max_tokens": raise ValueError("truncated")
                outputs = [b for b in response.get("content", []) if b.get("type") == "tool_use" and b.get("name") == "submit_extraction"]
                if len(outputs) != 1: raise ValueError("expected_one_tool_output")
                return Extraction.model_validate(outputs[0]["input"])
            except (ValidationError, ValueError, KeyError):
                if repair: raise InvalidModelOutput("invalid_structured_output") from None
                body["messages"][0]["content"] = content + "\nPrevious output violated the schema or was truncated. Return compact, correctly typed observations with all required evidence keys."
