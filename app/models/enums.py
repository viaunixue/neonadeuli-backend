from enum import Enum

class RoleType(Enum):
    USER = "user"
    ASSISTANT = "assistant"

class RouteType(Enum):
    RECOMMENDED = "recommended"
    CUSTOM = "custom"