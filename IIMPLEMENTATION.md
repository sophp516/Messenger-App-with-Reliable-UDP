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

### Client Registry - Who is in the system?
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

### Group chat structure (Stretch Feature)

```
Group:
    - group_name: string
    - admin: string
    - members: Set<string>
    - created_at: timestamp
    - message_history: List<Message> (optional, limited size)
```

### Pending Message Queue
```
PendingMessage:
    - sequence_number: integer
    - packet: Packet
    - send_time: timestamp
    - attempts: integer
    - recipient: string
    - callback: function (on success/failure)
```
## Key Modules 

### Client.py


### Server.py

### Protocol.py 