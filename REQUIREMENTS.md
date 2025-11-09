# Messenger App with Reliable UDP

**CS60 Computer Networks (F25)**  
**Authors:** Sophie Park, Joyce Zou


## Overview

This project implements a reliable messaging application using UDP as the underlying transport protocol. The system consists of a central host server and multiple clients that communicate through the host. The application supports both one-to-one (1:1) messaging and group messaging, with reliability guarantees implemented at the application layer.

### Key Features
- **1:1 Messaging**: Direct message exchange between two clients
- **Group Messaging**: Broadcast messages to multiple participants in a group chat
- **Reliable Delivery**: Application-layer reliability mechanisms ensure message delivery despite UDP's unreliable nature
- **Connection Management**: Robust connection establishment, maintenance, and teardown



## System Architecture

The system follows a client-server architecture:
- **Host (Server)**: Central message relay server that manages client connections and routes messages
- **Client**: End-user application that connects to the host to send and receive messages

All communication between clients is routed through the host server, which acts as a message broker.



## Client Requirements

The client application shall:

### Connection Management
- Establish a connection to the host server using UDP
- Implement a three-way handshake for connection establishment
- Maintain connection state and handle connection teardown gracefully
- Support automatic reconnection in case of connection loss
- Display connection status (connected, disconnected, connecting) to the user

### Messaging Capabilities
- **1:1 Messaging**:
  - Send messages to specific clients identified by unique client IDs
  - Receive and display incoming 1:1 messages with sender identification
  - Support message history for active conversations
  
- **Group Messaging**:
  - Join existing group chats by group ID
  - Create new group chats
  - Send messages to groups, which are broadcast to all group members
  - Receive and display group messages with sender and group identification
  - Distinguish between 1:1 and group messages in the user interface

### Reliable UDP Implementation
- **Sequence Numbers**:
  - Assign unique, monotonically increasing sequence numbers to each outgoing message
  - Maintain separate sequence number spaces for each connection/peer
  - Track expected sequence numbers for incoming messages
  
- **Acknowledgments (ACKs)**:
  - Send ACK packets immediately upon successful receipt of messages
  - Include the sequence number of the acknowledged message in ACK packets
  - Handle cumulative ACKs if implementing sliding window protocol
  
- **Retransmission**:
  - Maintain a retransmission queue for unacknowledged messages
  - Implement timeout mechanism (e.g., 500ms initial timeout)
  - Retransmit messages that have not been acknowledged within timeout period
  - Implement exponential backoff for retransmission timeouts (max retries: 5)
  
- **Duplicate Detection**:
  - Track received sequence numbers to detect duplicates
  - Ignore duplicate messages (same sequence number from same sender)
  - Send ACK for duplicates to prevent unnecessary retransmissions

### User Interface
- Display incoming messages in real-time
- Show message delivery status (sent, delivered, failed)
- Display error messages for connection failures or delivery failures
- Provide clear visual distinction between 1:1 and group messages
- Support command-line or graphical interface for user interaction

### Error Handling
- Handle network packet loss gracefully without crashing
- Detect and report connection failures to the user
- Implement timeout handling for unresponsive connections
- Validate incoming packet format and handle malformed packets
- Provide meaningful error messages to the user



## Host Requirements

The host server shall:

### Server Management
- Listen for incoming client connections on a configurable UDP port (default: 8080)
- Support multiple concurrent client connections
- Maintain a registry of all connected clients including:
  - Client ID (unique identifier)
  - Client IP address and port
  - Connection state and timestamp
  - Sequence number state for each client connection
  
- Implement connection timeout mechanism to detect and remove stale connections
- Log all connection events (connect, disconnect, timeout) for debugging

### Message Routing
- **1:1 Message Relay**:
  - Receive messages from sender clients
  - Validate message format and sender authentication
  - Route messages to the intended recipient based on client ID
  - Handle cases where recipient is not connected (queue or reject)
  
- **Group Message Management**:
  - Maintain group membership information
  - Support group creation and deletion
  - Allow clients to join and leave groups
  - Broadcast group messages to all members of the group
  - Handle group membership changes dynamically

### Reliable UDP Implementation
- **Sequence Number Tracking**:
  - Maintain separate sequence number state for each client connection
  - Track expected sequence numbers for messages from each client
  - Detect out-of-order messages and handle appropriately
  
- **Acknowledgment Handling**:
  - Send ACK packets to clients upon successful receipt of messages
  - Relay ACKs between clients for end-to-end reliability (if applicable)
  - Handle ACK loss and retransmission
  
- **Retransmission Support**:
  - Support client retransmissions by accepting duplicate sequence numbers
  - Detect and filter duplicate messages before forwarding
  - Maintain message queues for temporarily unreachable clients
  
- **Duplicate Detection**:
  - Track received sequence numbers per client connection
  - Filter duplicate messages before routing
  - Prevent duplicate messages from being delivered to recipients

### Message Queuing
- Maintain message queues for clients that are temporarily unreachable
- Implement queue size limits to prevent memory exhaustion
- Deliver queued messages when client reconnects
- Expire old queued messages after a timeout period

### Resource Management
- Handle client disconnections gracefully
- Clean up resources (connection state, queues) when clients disconnect
- Implement connection limits to prevent resource exhaustion
- Monitor and log server resource usage

### Logging and Debugging
- Log all connection events (connect, disconnect, errors)
- Log message routing events (source, destination, message type)
- Provide detailed error logs for troubleshooting
- Support different log levels (INFO, WARNING, ERROR)



## Protocol Specifications

### Transport Protocol
- **Base Protocol**: UDP (User Datagram Protocol)
- **Reliability Layer**: Application-layer reliability mechanisms
- **Port Configuration**: Configurable, default 8080 for host

### Packet Format

All packets shall follow a structured format with the following fields:

```
+------------------+------------------+------------------+
|  Message Type    |  Sequence Number |  Source ID       |
+------------------+------------------+------------------+
|  Destination ID  |  Payload Length  |  Flags           |
+------------------+------------------+------------------+
|  Timestamp       |  Checksum        |                  |
+------------------+------------------+------------------+
|                  Payload (Variable Length)              |
+---------------------------------------------------------+
```

**Field Descriptions:**
- **Message Type** (1 byte): 
  - `0x01`: 1:1 Message
  - `0x02`: Group Message
  - `0x03`: ACK
  - `0x04`: Connection Request (SYN)
  - `0x05`: Connection Accept
  - `0x06`: Connection Close (FIN)
  - `0x07`: Heartbeat/Keepalive
  - `0x08`: Error Message
  
- **Sequence Number** (4 bytes): Unique sequence number for message ordering
- **Source ID** (variable): Identifier of the message sender
- **Destination ID** (variable): Identifier of the message recipient (group ID for group messages)
- **Payload Length** (2 bytes): Length of the message payload in bytes
- **Flags** (1 byte): Control flags (e.g., retransmission flag, end-of-message flag)
- **Timestamp** (8 bytes): Message timestamp for ordering and timeout calculations
- **Checksum** (2 bytes): Packet integrity check
- **Payload**: Actual message content (text, binary data, etc.)

### Reliability Mechanisms

#### Sequence Numbers
- Each message is assigned a unique sequence number
- Sequence numbers are monotonically increasing within each connection
- Sequence number space is per-connection (client-host or client-client through host)
- Sequence numbers wrap around after reaching maximum value (modular arithmetic)

#### Acknowledgments
- Receivers send ACK packets immediately upon successful message receipt
- ACK packets contain the sequence number of the acknowledged message
- Senders maintain a list of unacknowledged messages
- Cumulative ACKs may be used to acknowledge multiple messages efficiently

#### Timeout and Retransmission
- Initial retransmission timeout: 500ms
- Exponential backoff: timeout doubles after each retry (500ms, 1s, 2s, 4s, 8s)
- Maximum retransmission attempts: 5
- After max retries, message is considered failed and user is notified

#### Duplicate Detection
- Receivers maintain a sliding window of received sequence numbers
- Messages with sequence numbers already in the window are considered duplicates
- Duplicates are discarded but ACKed to prevent sender retransmission
- Window size should accommodate expected network reordering

### Connection Management

#### Connection Establishment
- **Three-way handshake**:
  1. Client sends SYN packet to host
  2. Host responds with SYN-ACK packet
  3. Client sends ACK packet
- Connection is established after successful handshake
- Client receives unique client ID from host upon connection

#### Connection Maintenance
- **Heartbeat/Keepalive**:
  - Clients send periodic heartbeat packets (every 30 seconds)
  - Host responds to heartbeat packets
  - Missing heartbeats indicate connection failure
  - Connection timeout: 90 seconds (3 missed heartbeats)

#### Connection Teardown
- **Graceful shutdown**:
  1. Initiator sends FIN packet
  2. Receiver responds with FIN-ACK
  3. Initiator sends final ACK
- Resources are cleaned up after teardown
- Abrupt disconnections are detected via timeout mechanism


## Error Handling

### Network Errors
- **Packet Loss**: Handled through retransmission mechanism
- **Out-of-Order Delivery**: Sequence numbers ensure correct ordering
- **Duplicate Packets**: Detected and filtered using sequence number tracking
- **Network Congestion**: Exponential backoff prevents network flooding

### Connection Errors
- **Connection Timeout**: Detected via heartbeat mechanism, user notified
- **Connection Refused**: Client displays error message, allows retry
- **Unexpected Disconnection**: Automatic cleanup and reconnection attempt

### Protocol Errors
- **Malformed Packets**: Discarded with error logged, no ACK sent
- **Invalid Sequence Numbers**: Handled according to protocol (accept, reject, or request retransmission)
- **Protocol Violations**: Logged and connection may be terminated

### User Feedback
- All errors are reported to the user in a clear, non-technical manner
- Delivery failures are indicated in the user interface
- Connection status is always visible to the user


## Performance Requirements

### Scalability
- Host must support at least 50 concurrent client connections
- System should handle at least 100 messages per second aggregate throughput
- Message delivery latency should be under 200ms under normal network conditions

### Resource Usage
- Client memory usage should remain under 50MB for typical usage
- Host memory usage should scale linearly with number of connected clients
- CPU usage should remain reasonable under normal load


## Testing Requirements

### Functional Testing
1. **1:1 Messaging**:
   - Test message exchange between two clients
   - Verify message delivery and ordering
   - Test with multiple concurrent 1:1 conversations

2. **Group Messaging**:
   - Test group creation and joining
   - Test message broadcasting to all group members
   - Test with groups of varying sizes (3, 5, 10+ members)
   - Test dynamic group membership changes

3. **Connection Management**:
   - Test connection establishment (three-way handshake)
   - Test graceful connection teardown
   - Test connection timeout and cleanup
   - Test reconnection after disconnection

### Reliability Testing
4. **Packet Loss Scenarios**:
   - Test system behavior with simulated packet loss (10%, 25%, 50%)
   - Verify retransmission mechanism works correctly
   - Verify no message loss under packet loss conditions
   - Test duplicate detection under packet loss

5. **Network Conditions**:
   - Test with high latency (simulated 200ms+ RTT)
   - Test with out-of-order packet delivery
   - Test with duplicate packets
   - Test with network congestion scenarios

6. **Edge Cases**:
   - Test handling of duplicate messages
   - Test sequence number wraparound
   - Test behavior with maximum retransmission attempts
   - Test with malformed packets
   - Test with rapid connect/disconnect cycles

### Stress Testing
7. **Load Testing**:
   - Test with maximum concurrent connections (50+)
   - Test with high message rate (100+ messages/second)
   - Test with large message payloads
   - Test system stability under sustained load

8. **Concurrent Operations**:
   - Test multiple clients connecting simultaneously
   - Test multiple groups with overlapping membership
   - Test concurrent 1:1 and group messaging

### Integration Testing
9. **End-to-End Scenarios**:
   - Test complete user workflows (connect, send messages, disconnect)
   - Test multi-client group chat scenarios
   - Test system recovery after host restart
   - Test client behavior during host unavailability


## Implementation Notes

### Development Considerations
- Use a programming language that supports UDP sockets (Python, Java, C/C++, Go, etc.)
- Implement proper error handling and logging throughout
- Use thread-safe data structures for concurrent operations
- Consider using a packet serialization library (e.g., Protocol Buffers, MessagePack)
- Implement comprehensive unit tests for reliability mechanisms

### Security Considerations
- Validate all incoming packets before processing
- Implement basic authentication for client connections
- Sanitize user input to prevent injection attacks
- Consider rate limiting to prevent abuse
- Log security-relevant events

### Future Enhancements (Optional)
- Message encryption for privacy
- User authentication and authorization
- Message persistence and history
- File transfer capabilities
- Typing indicators
- Message read receipts


## Deliverables

1. **Source Code**:
   - Client implementation
   - Host/server implementation

2. **Documentation**:
   - This requirements document
   - Implementation document

3. **Testing**:
   - Test suite with test cases covering all requirements
   - Test results and analysis
   - Demonstration of reliability under packet loss

4. **Demonstration**:
   - Working demo showing 1:1 and group messaging
   - Demo of reliability features (packet loss simulation)
   - Performance metrics and analysis
