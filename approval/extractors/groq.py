"""Groq JSON-schema extraction; no streaming or agent tools."""
import json
import time
from pydantic import ValidationError
from approval.core.models import Extraction
from approval.infrastructure.retry import retry, TransientFailure, PermanentFailure, InvalidModelOutput
from .prompt import SYSTEM, VERSION

class GroqExtractor:
    retry_pause = 20  # seconds added to each retry wait; the free tier limit resets per minute
    def __init__(self, api_key, model="openai/gpt-oss-120b", transport=None):
        if not api_key: raise ValueError("Set GROQ_API_KEY")
        self.api_key, self.model = api_key, model
        self.identity = f"groq:{model}:{VERSION}:v1"
        self.transport = transport or self._post
        self.last_usage = {}

    def _post(self, body):
        from groq import Groq, APIStatusError, APIConnectionError, APITimeoutError
        try:
            with Groq(api_key=self.api_key, max_retries=0, timeout=60.0) as client:
                return client.chat.completions.create(**body).model_dump()
        except APIStatusError as exc:
            if exc.status_code in (408, 429, 500, 502, 503, 504):
                raise TransientFailure(f"provider_http_{exc.status_code}") from None
            raise PermanentFailure(f"provider_http_{exc.status_code}") from None
        except (APIConnectionError, APITimeoutError):
            raise TransientFailure("provider_connection_failure") from None

    def extract(self, document):
        content=json.dumps({"document_id":document.id,"role":document.role,
            "pages":[{"page":p.number,"text":p.text} for p in document.pages if p.usable]},ensure_ascii=False)
        if len(content)>100_000: raise PermanentFailure("document_context_limit")
        system=SYSTEM.replace("Use the submit_extraction tool exactly once. No other tools or actions are available.",
            "Return only a JSON object conforming to the provided schema. No tools or actions are available.")
        body={"model":self.model,"messages":[{"role":"system","content":system},{"role":"user","content":content}],
            "temperature":0,"max_completion_tokens":4000,"reasoning_effort":"low","stream":False,
            "response_format":{"type":"json_schema","json_schema":{"name":"medical_extraction","strict":True,
                "schema":Extraction.model_json_schema()}}}
        self.last_usage={"prompt_tokens":0,"completion_tokens":0,"total_tokens":0,"http_attempts":0,"responses":0}
        def invoke():
            self.last_usage["http_attempts"]+=1
            response=self.transport(body)
            self.last_usage["responses"]+=1
            for k in ("prompt_tokens","completion_tokens","total_tokens"):
                self.last_usage[k]+=response.get("usage",{}).get(k,0)
            return response
        for repair in range(2):
            response=retry(invoke,attempts=4,sleep=lambda s:time.sleep(s+self.retry_pause))
            try:
                choice=response["choices"][0]
                if choice.get("finish_reason")!="stop" or choice["message"].get("refusal"):
                    raise ValueError("incomplete_or_refused")
                return Extraction.model_validate_json(choice["message"]["content"])
            except (ValidationError, ValueError, KeyError, IndexError, TypeError):
                if repair: raise InvalidModelOutput("invalid_structured_output") from None
                body["messages"][1]["content"]=content+"\nReturn compact, complete, schema-valid JSON. Do not omit evidence keys or change field types."
