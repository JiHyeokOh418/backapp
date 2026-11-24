from enum import Enum

class LlmCallPurpose(str, Enum):
    REPLY = "reply"
    SUMMARY = "summary"

class LlmCallParseStatus(str, Enum):
    OK = "ok"
    RETRIED_OK = "retried_ok"
    FAILED = "failed"
