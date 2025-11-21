class MsgType(IntEnum):
    DATA = 0x01
    ACK = 0x03
    SYN = 0x04
    SYN_ACK = 0x05
    FIN = 0x06
    HEARTBEAT = 0x07
    ERROR = 0x08
    JOIN = 0x09
    LEAVE = 0x0A
    GROUP_MSG = 0x0B
    LIST = 0x0C
    GROUPS = 0x0D
    LIST_RESPONSE = 0x0E
    GROUPS_RESPONSE = 0x0F
    
class PendingMessage:
    sequence_number: int
    packet: bytes
    send_time: float
    attempts: int
    recipient: str
    packet_type: int
    last_retry_time: float = 0.0
