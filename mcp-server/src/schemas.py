from enum import Enum
from pydantic import BaseModel

class BlooTools(str, Enum):
    PING = 'ping'
    QUERY_EXECUTE = 'query-execute'
