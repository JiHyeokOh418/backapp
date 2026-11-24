from enum import Enum

class MessageRole(str, Enum):
    USER = "user"
    ASSISTANT = "assistant"

class MessageSystemRecordStatus(str, Enum):
    OK = "ok"
    PARTIAL = "partial"
    FAILED = "failed"

class MessageInputType(str, Enum):
    TEXT = "text"
    VOICE = "voice"
