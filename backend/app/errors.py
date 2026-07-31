from __future__ import annotations


class PipelineError(Exception):
    code = "pipeline_error"
    retryable = False

    def __init__(self, message: str, *, status_code: int | None = None, request_id: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.request_id = request_id

    def as_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "message": str(self),
            "retryable": self.retryable,
            "status_code": self.status_code,
            "request_id": self.request_id,
        }


class AnalysisError(PipelineError):
    code = "analysis_failed"
    retryable = True


class OpenAIError(PipelineError):
    code = "openai_error"


class OpenAIAuthenticationError(OpenAIError):
    code = "openai_authentication_error"
    retryable = False


class OpenAIRateLimitError(OpenAIError):
    code = "openai_rate_limit"
    retryable = True


class OpenAIServiceError(OpenAIError):
    code = "openai_service_unavailable"
    retryable = True


class OpenAIRequestError(OpenAIError):
    code = "openai_request_error"
    retryable = False


class GeminiError(PipelineError):
    code = "gemini_error"


class GeminiAuthenticationError(GeminiError):
    code = "gemini_authentication_error"
    retryable = False


class GeminiRateLimitError(GeminiError):
    code = "gemini_rate_limit"
    retryable = True


class GeminiServiceError(GeminiError):
    code = "gemini_service_unavailable"
    retryable = True


class GeminiRequestError(GeminiError):
    code = "gemini_request_error"
    retryable = False
