from enum import Enum, auto


class EdgeType(Enum):
    STRAIGHT = auto()
    BEZIER = auto()
    ARC = auto()


class Continuity(Enum):
    G0 = auto()
    G1 = auto()
    C1 = auto()
