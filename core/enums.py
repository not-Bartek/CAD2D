from enum import Enum, auto

class EdgeType(Enum):
    STRAIGHT = auto()
    BEZIER = auto()
    ARC = auto()