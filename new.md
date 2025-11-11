Messenger App with Reliable UDP

CS60 Computer Networks (F25)
Authors: Sophie Park, Joyce Zou

⸻

1. Project Overview

The Messenger App with Reliable UDP is a lightweight chat system designed to provide dependable message delivery over UDP. Unlike TCP-based messengers, it recreates reliability at the application layer, allowing us to study retransmission, sequencing, and connection control directly.

The system supports:
• 1:1 Messaging: private chats between two users.
• Group Messaging: broadcasting to multi-member chatrooms. [Extension Feature if time allows]
• Reliability: acknowledgments, retransmissions, and duplicate detection over UDP.
• Connection Management: connection setup (three-way handshake), periodic heartbeats, and graceful teardown.

The app demonstrates how real-world messaging systems handle reliability and connection management over stateless transport.

⸻

2. Purpose and Users

The system serves students, developers, and instructors exploring networking fundamentals. Its goal is to:
• Illustrate how reliable communication can be achieved without TCP.
• Provide an educational platform for experimenting with message delivery, packet loss, and network latency.
• Offer a functional chat environment for testing concurrent UDP clients.

⸻

3. Major Entities

Entity Description
Client End-user application that sends and receives messages. Each user is identified by a unique username.
Host Server Central relay responsible for message routing, reliability control, and group management.
Packet Core data unit containing message type, sequence number, sender, recipient, timestamp, and checksum.
Client Registry Server data structure mapping connected usernames to IP/port pairs.
Group Registry Tracks group membership for broadcast delivery.
Message Queue Stores pending or undelivered messages until acknowledgment.

⸻

4. Functionality

Client Functions
• Establish UDP connection to host through a three-way handshake (SYN → SYN-ACK → ACK).
• Send private or group messages via structured packets.
• Maintain connection status and attempt reconnection up to 3× on timeout.
• Display real-time incoming messages and delivery confirmations.

Server Functions
• Accept and manage multiple concurrent clients.
• Route 1:1 messages to intended recipients and broadcast group messages.
• Track sequence numbers for each client to detect duplicates.
• Log connection, message, and error events for debugging.
• Remove inactive clients after 90 s of missed heartbeats.

Reliability and Error Recovery
• Each message carries a unique sequence number.
• Receivers send ACKs for successful receipt.
• Unacknowledged packets are retransmitted with exponential backoff (500 ms → 1 s → 2 s…).
• Duplicates are ignored but ACKed to suppress further retries.
• Malformed packets (bad checksum or missing fields) are dropped and logged.

⸻

5. Business Rules and Communication Plan

Connection Lifecycle

1. Establishment: Client sends SYN; server replies SYN-ACK; client completes with ACK.
2. Maintenance: Heartbeats every 30 s keep the session alive.
3. Teardown: FIN → FIN-ACK → ACK sequence cleans up both sides.

Message Flow
• All packets flow through the host (no direct client-to-client transmission).
• Host forwards packets using each client’s registered address.
• ACKs flow back from recipients to confirm delivery.
• Retransmission queues on clients ensure eventual delivery.

Network Structure

A single host machine (default port 8080) handles multiple client sockets concurrently.
Messages are serialized using a lightweight binary header containing:

Field Purpose
Message Type (1 B) DATA, ACK, SYN, FIN, etc.
Seq Num (4 B) Ensures ordering & reliability.
Source / Dest IDs Identify sender and recipient.
Payload Len + Flags + Timestamp + Checksum Integrity and timing data.

⸻

6. Performance and Resource Goals

The main goal is to achieve reliable data transfer over UDP under basic network conditions.
	•	The system should correctly deliver all messages despite simulated packet loss.
	•	The connection should remain stable for multiple users exchanging messages at once.
	•	The server should handle up to 50 concurrent simulated clients without crashing or data loss.
Periodic cleanup will remove inactive clients to free resources, ensuring stable performance during longer runs.

⸻

7. Security and Reliability
   • Checksum validation protects against packet corruption.
   • No arbitrary code execution or external dependencies.
   • Heartbeats prevent ghost clients and detect dropped connections.
   • Messages are plaintext for demonstration; encryption could be added as a stretch goal.

⸻

8. Hardware, Software, and Personnel
   • Hardware: Any machine supporting Python 3 and UDP sockets.
   • Software: Python standard library (socket, struct, threading, collections).
   • Team:
   • Joyce Zou – Client implementation
   • Sophie Park – Server implementation

9. Timeline 
- Complete server and host by end of week 9, start testing earlier if we finish earlier
- Start testing Nov 16 - Nov 18 to ensure everything is working 
- Get inital video with bare minimum scope recorded on Nov 18
- Work on group chat feature and new video by end of Nov 22. Depending on how much bug we have on MVP 1, we will submit second video if everything goes well. 