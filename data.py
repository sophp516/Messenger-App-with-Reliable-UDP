from enum import IntEnum
from dataclasses import dataclass, field
from typing import Tuple, Optional
from collections import deque

class MsgType(IntEnum):
    DATA = 0x01
    ACK = 0x03
    SYN = 0x04
    SYN_ACK = 0x05
    FIN = 0x06
    FIN_ACK = 0x10
    HEARTBEAT = 0x07
    ERROR = 0x08
    JOIN = 0x09
    LEAVE = 0x0A
    GROUP_MSG = 0x0B
    LIST = 0x0C
    GROUPS = 0x0D
    LIST_RESPONSE = 0x0E
    GROUPS_RESPONSE = 0x0F

class MessageStatus(IntEnum):
    SENT = 1
    DELIVERED = 2
    FAILED = 3

@dataclass
class PendingMessage:
    sequence_number: int
    packet: bytes
    send_time: float
    attempts: int
    recipient: str
    packet_type: int
    last_retry_time: float = 0.0
    status: int = MessageStatus.SENT
    retry_timestamps: list[float] = field(default_factory=list)

@dataclass
class ClientInfo:
    username: str
    address: Tuple[str, int]
    last_seen: float
    sequence_number: int
    status: str
    pending_ack: Optional[int] = None 
    received_seq_window: Optional[deque] = field(default=None)