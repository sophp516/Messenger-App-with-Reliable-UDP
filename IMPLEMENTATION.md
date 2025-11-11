# Design and Implementation Spec

## User Interface

### Client Side

#### UDP Messaging Client

**Username:** `[user input]`  
**Status:** Connected to server at `127.0.0.1:5000`

---

### **Commands**

| Command             | Description            |
| ------------------- | ---------------------- |
| `@username message` | Send a direct message  |
| `/join groupname`   | Join or create a group |
| `/leave groupname`  | Leave a group          |
| `/list`             | List online users      |
| `/groups`           | List available groups  |
| `/quit`             | Exit the application   |

---

### Server Side

#### UDP Messaging Server

```
Server started on port 5000
Listening for connections...

[TIMESTAMP] Client 'alice' connected from 192.168.1.10:12345
[TIMESTAMP] Group 'project-team' created by 'alice'
[TIMESTAMP] Client 'bob' joined group 'project-team'
[TIMESTAMP] Message relayed: alice -> bob
```

## Major Data Structures

### Packet Structure

```
Packet:
    - packet_type: enum (DATA, ACK, JOIN, LEAVE, GROUP_MSG)
    - sequence_number: integer (32-bit)
    - timestamp: float
    - sender: string
    - recipient: string (or group_name for group messages)
    - payload: bytes
    - checksum: integer (16-bit)
```

### Client Registry - Who is in the system? (Server Side)

```
ClientRegistry:
    Map<username, ClientInfo>

ClientInfo:
    - username: string
    - address: (IP, port) tuple
    - last_seen: timestamp
    - sequence_number: integer
    - status: enum (ONLINE, OFFLINE)
```

### Group chat structure (Stretch Feature) (Server side)

```
GroupRegistry:
    Map<group_name, Group>

Group:
    - group_name: string
    - admin: string                      # username of creator
    - members: Set<string>              # usernames
    - created_at: timestamp
    - message_history: List<GroupMessage> (optional, fixed-size ring buffer)

GroupMessage (optional):
    - sender: string
    - timestamp: float
    - payload: string
    - sequence_number: uint32 (server-assigned)
```

### Pending Message Queue

```
Tracks delivery state of each sent message.

MessageStatus:
    Map<sequence_number, MessageInfo>

MessageInfo:
    - status: enum (SENT, DELIVERED, FAILED)
    - timestamp: float (when sent)
    - retries: int

PendingMessage:
    - sequence_number: integer
    - packet: Packet
    - send_time: timestamp
    - attempts: integer
    - recipient: string
    - callback: function (on success/failure)
```

### Duplicate Detection (Client-side)

received_seq_window: - Type: deque (maxlen=100) - Purpose: Tracks recently received sequence numbers - Used by: recv_thread - Behavior: - If seq in window → resend ACK, ignore duplicate - Else → process message, append seq

## Key Modules for basic specs

### Client.py

```
send SYN → wait SYN_ACK → send ACK
start input_thread, recv_thread, retransmit_thread

input_thread:
  read user input
  if has message: send DATA(seq=n)
  if "/quit": send FIN, exit

recv_thread:
  if DATA: print msg, send ACK
  if ACK: mark delivered
  if FIN_ACK: disconnect, mark failed
  if seq in received_seq_window: send ACK (duplicate), ignore payload
    else: process message, add seq to window
  if connection lost: attempt reconnect up to 3 times before exit.

retransmit_thread:
  retry unacked msgs
```

### Server.py

```

bind UDP socket on port 5000
init ClientRegistry, PendingQueue
loop:
  packet = recv()

  if invalid checksum or missing fields: drop packet and log error.

  if SYN:
    register client, send SYN_ACK

  elif ACK (from handshake):
    mark client connected

  elif DATA:
    validate seq
    forward to dest client
    send ACK to sender

  elif ACK:
    mark message delivered

  elif FIN:
    send FIN_ACK, remove client

periodically:
  clean inactive clients (timeout > 90s)
  handle heartbeat packets to maintain active connections

heartbeat handling:
  - Each connected client is expected to send a HEARTBEAT packet every 30 seconds.
  - Upon receiving a HEARTBEAT, the server updates the client’s `last_seen` timestamp.
  - If a client fails to send a HEARTBEAT within 90 seconds, it is considered disconnected and removed from the registry.
  - HEARTBEAT messages use the packet_type = HEARTBEAT (0x07) as defined in Protocol.py.
  - The client’s retransmission or input thread may periodically send this packet on a background timer.
```

### Protocol.py

- Handles packet creation, parsing, and checksum verification

```
class MsgType(Enum):
    DATA = 0x01
    ACK = 0x03
    SYN = 0x04
    SYN_ACK = 0x05
    FIN = 0x06
    HEARTBEAT = 0x07
    ERROR = 0x08
```

## Error Handlings

- In cases of packet loss, we can try retransmit the message
- Handle connection timeout by marking client as disconnected and try reconnect 3x
- Drop packet that doesn't meet standards

## Resource Management (building off requirement)

- Handle client disconnections gracefully -> Server removes inactive clients after 90s.
- Both client and server need to free connection state, message queues, and pending messages when a session end to clean up resources
- Implement connection limits to prevent resource exhaustion by defining a max client threshold

## Testing Plan

- Functional: message send/receive, retransmission, connection teardown.
- Reliability: simulate 10%, 25%, 50% packet loss.
- Stress: running 50+ clients concurrently using thread simulation
- Edge: duplicate packets, out-of-order delivery.
