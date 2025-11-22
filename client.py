''''
Joyce and Sophie's UDP Messaging Client

Citing LLM on 
 - Retry and Retransmission logic on how to track unacknowledged messages and retransmit them using exponential backoffs 
- Helped w. packet parsing 
'''

import socket
import struct
import time
import threading
from collections import deque
from enum import IntEnum
from dataclasses import dataclass
from typing import Dict, Optional, Tuple
from data import MsgType, PendingMessage, MessageStatus
import sys

HOST = "127.0.0.1"
PORT = 5001
HEARTBEAT_INTERVAL = 30  # seconds
CONNECTION_TIMEOUT = 5  # seconds for handshake timeout
MAX_RETRIES = 3
INITIAL_RETRANSMIT_DELAY = 0.5  # 500ms
MAX_RETRANSMIT_DELAY = 8.0  # 8 seconds
RECEIVED_SEQ_WINDOW_SIZE = 100

def calculate_checksum(data: bytes) -> int:
    """Calculate 16-bit checksum for packet"""
    checksum = 0
    for i in range(0, len(data), 2):
        if i + 1 < len(data):
            word = (data[i] << 8) | data[i + 1]
        else:
            word = data[i] << 8
        checksum = (checksum + word) & 0xFFFF
    return (~checksum) & 0xFFFF

def create_packet(packet_type: int, sequence_number: int, sender: str, 
                  recipient: str, payload: bytes = b"") -> bytes:
    """Create a packet with the specified fields"""
    timestamp = time.time()
    
    # Encode strings
    sender_bytes = sender.encode('utf-8')
    recipient_bytes = recipient.encode('utf-8')
    header = struct.pack('!B I d H', packet_type, sequence_number, timestamp, len(sender_bytes))
    header += sender_bytes
    header += struct.pack('!H', len(recipient_bytes))
    header += recipient_bytes
    header += struct.pack('!I', len(payload))
    header += payload
    
    # Calculate checksum on everything except checksum field
    checksum = calculate_checksum(header)
    header += struct.pack('!H', checksum)
    
    return header

def parse_packet(data: bytes) -> Optional[Dict]:
    """Parse a packet and return dictionary with fields, or None if invalid"""
    try:
        if len(data) < 19:  # Minimum size for header
            return None
        
        # Parse fixed header
        packet_type, seq_num, timestamp, sender_len = struct.unpack('!B I d H', data[:15])
        
        offset = 15
        if offset + sender_len > len(data):
            return None
        
        sender = data[offset:offset + sender_len].decode('utf-8')
        offset += sender_len
        
        if offset + 2 > len(data):
            return None
        
        recipient_len, = struct.unpack('!H', data[offset:offset + 2])
        offset += 2
        
        if offset + recipient_len > len(data):
            return None
        
        recipient = data[offset:offset + recipient_len].decode('utf-8')
        offset += recipient_len
        
        if offset + 4 > len(data):
            return None
        
        payload_len, = struct.unpack('!I', data[offset:offset + 4])
        offset += 4
        
        if offset + payload_len + 2 > len(data):
            return None
        
        payload = data[offset:offset + payload_len]
        offset += payload_len
        
        if offset + 2 > len(data):
            return None
        
        received_checksum, = struct.unpack('!H', data[offset:offset + 2])
        
        # Verify checksum
        packet_without_checksum = data[:offset]
        calculated_checksum = calculate_checksum(packet_without_checksum)
        
        if received_checksum != calculated_checksum:
            return None
        
        return {
            'packet_type': packet_type,
            'sequence_number': seq_num,
            'timestamp': timestamp,
            'sender': sender,
            'recipient': recipient,
            'payload': payload,
            'checksum': received_checksum
        }
    except (struct.error, UnicodeDecodeError, IndexError):
        return None

class UDPClient:
    def __init__(self, username: str, host: str = HOST, port: int = PORT):
        self.username = username
        self.host = host
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(1.0)  # 1 second timeout for recv
        
        self.connected = False
        self.sequence_number = 0
        self.pending_messages: Dict[int, PendingMessage] = {}
        self.received_seq_window = deque(maxlen=RECEIVED_SEQ_WINDOW_SIZE)
        self.lock = threading.Lock()
        self.running = True
        self.last_received_time = time.time()  # track last received packet
        self.handshake_complete = False
        self.handshake_lock = threading.Lock()
        
    def get_next_sequence(self) -> int:
        """Get next sequence number for outgoing packets"""
        with self.lock:
            self.sequence_number += 1
            return self.sequence_number
    
    def log(self, message: str):
        """Log a message with timestamp"""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        print(f"[{timestamp}] {message}")
    
    def send_packet(self, packet: bytes, address: Optional[Tuple[str, int]] = None):
        """Send a packet to the server"""
        if address is None:
            address = (self.host, self.port)
        try:
            self.sock.sendto(packet, address)
        except Exception as e:
            self.log(f"Error sending packet: {e}")
    
    def connect(self) -> bool:
        """Establish connection via three-way handshake"""
        print(f"Connecting to server at {self.host}:{self.port}...")
        
        for attempt in range(MAX_RETRIES):
            try:
                syn_packet = create_packet(MsgType.SYN, 0, self.username, "SERVER")
                self.send_packet(syn_packet)
                
                # wait for SYN_ACK or ERROR
                start_time = time.time()
                while time.time() - start_time < CONNECTION_TIMEOUT:
                    try:
                        data, addr = self.sock.recvfrom(4096)
                        packet = parse_packet(data)
                        
                        if packet and packet['packet_type'] == MsgType.SYN_ACK:
                            # received SYN_ACK, send ACK to complete handshake
                            ack_packet = create_packet(MsgType.ACK, 0, self.username, "SERVER")
                            self.send_packet(ack_packet)
                            
                            with self.lock:
                                self.connected = True
                                self.handshake_complete = True
                            
                            print(f"Connected to server at {addr[0]}:{addr[1]}")
                            self.log("Connection established")
                            return True
                        elif packet and packet['packet_type'] == MsgType.ERROR:
                            # server rejected connection
                            error_msg = packet['payload'].decode('utf-8') if packet['payload'] else "Connection rejected"
                            print(f"Connection failed: {error_msg}")
                            return False
                    except socket.timeout:
                        continue
                    except Exception as e:
                        self.log(f"Error during handshake: {e}")
                        break
                
                if attempt < MAX_RETRIES - 1:
                    self.log(f"Connection attempt {attempt + 1} failed, retrying...")
                    time.sleep(1)
                    
            except Exception as e:
                self.log(f"Connection error: {e}")
                if attempt < MAX_RETRIES - 1:
                    time.sleep(1)
        
        print("Failed to connect after maximum retries")
        return False
    
    def check_connection_health(self):
        """Check if connection is still alive based on last received time"""
        current_time = time.time()
        with self.lock:
            # if no packets received for 2 * HEARTBEAT_INTERVAL -> connection might be lost
            if self.connected and (current_time - self.last_received_time) > (HEARTBEAT_INTERVAL * 2):
                self.log("Connection appears lost, attempting reconnection...")
                self.connected = False
                return self.attempt_reconnection()
        return True
    
    def attempt_reconnection(self):
        """Attempt to reconnect if connection is lost"""
        if not self.running:
            return False
        
        reconnect_attempts = 0
        max_reconnect_attempts = 3
        
        while reconnect_attempts < max_reconnect_attempts and self.running:
            if self.connect():
                self.log("Reconnection successful")
                return True
            reconnect_attempts += 1
            if reconnect_attempts < max_reconnect_attempts:
                time.sleep(2)  # wait before retry
        
        if reconnect_attempts >= max_reconnect_attempts:
            self.log("Failed to reconnect after maximum attempts")
            self.running = False
            return False
        return False
    
    def disconnect(self):
        """Gracefully disconnect from server"""
        if not self.connected:
            return
        
        try:
            # Send FIN
            fin_packet = create_packet(MsgType.FIN, 0, self.username, "SERVER")
            self.send_packet(fin_packet)
            
            # Wait for FIN_ACK
            start_time = time.time()
            while time.time() - start_time < CONNECTION_TIMEOUT:
                try:
                    data, addr = self.sock.recvfrom(4096)
                    packet = parse_packet(data)
                    
                    if packet and packet['packet_type'] == MsgType.FIN_ACK:
                        # Received FIN_ACK, send final ACK
                        ack_packet = create_packet(MsgType.ACK, 0, self.username, "SERVER")
                        self.send_packet(ack_packet)
                        break
                except socket.timeout:
                    break
                except Exception:
                    break
        except Exception as e:
            self.log(f"Error during disconnect: {e}")
        
        with self.lock:
            self.connected = False
            self.handshake_complete = False
    
    def send_message(self, recipient: str, message: str) -> bool:
        """Send a direct message to a user"""
        if not self.connected:
            print("Not connected to server")
            return False
        
        seq_num = self.get_next_sequence()
        payload = message.encode('utf-8')
        packet = create_packet(MsgType.DATA, seq_num, self.username, recipient, payload)
        
        with self.lock:
            self.pending_messages[seq_num] = PendingMessage(
                sequence_number=seq_num,
                packet=packet,
                send_time=time.time(),
                attempts=0,
                recipient=recipient,
                packet_type=MsgType.DATA,
                last_retry_time=0.0
            )
        
        self.send_packet(packet)
        return True
    
    def send_group_message(self, group_name: str, message: str) -> bool:
        """Send a message to a group"""
        if not self.connected:
            print("Not connected to server")
            return False
        
        seq_num = self.get_next_sequence()
        payload = message.encode('utf-8')
        packet = create_packet(MsgType.GROUP_MSG, seq_num, self.username, group_name, payload)
        
        with self.lock:
            self.pending_messages[seq_num] = PendingMessage(
                sequence_number=seq_num,
                packet=packet,
                send_time=time.time(),
                attempts=0,
                recipient=group_name,
                packet_type=MsgType.GROUP_MSG,
                last_retry_time=0.0
            )
        
        self.send_packet(packet)
        return True
    
    def create_group(self, group_name: str) -> bool:
        """Create a new group (same as join, but with explicit intent)"""
        return self.join_group(group_name)
    
    def join_group(self, group_name: str) -> bool:
        """Join or create a group"""
        if not self.connected:
            print("Not connected to server")
            return False
        
        seq_num = self.get_next_sequence()
        packet = create_packet(MsgType.JOIN, seq_num, self.username, group_name)
        
        with self.lock:
            self.pending_messages[seq_num] = PendingMessage(
                sequence_number=seq_num,
                packet=packet,
                send_time=time.time(),
                attempts=0,
                recipient=group_name,
                packet_type=MsgType.JOIN,
                last_retry_time=0.0
            )
        
        self.send_packet(packet)
        return True
    
    def leave_group(self, group_name: str) -> bool:
        """Leave a group"""
        if not self.connected:
            print("Not connected to server")
            return False
        
        seq_num = self.get_next_sequence()
        packet = create_packet(MsgType.LEAVE, seq_num, self.username, group_name)
        
        with self.lock:
            self.pending_messages[seq_num] = PendingMessage(
                sequence_number=seq_num,
                packet=packet,
                send_time=time.time(),
                attempts=0,
                recipient=group_name,
                packet_type=MsgType.LEAVE,
                last_retry_time=0.0
            )
        
        self.send_packet(packet)
        return True
    
    def request_user_list(self) -> bool:
        """Request list of online users"""
        if not self.connected:
            print("Not connected to server")
            return False
        
        seq_num = self.get_next_sequence()
        packet = create_packet(MsgType.LIST, seq_num, self.username, "SERVER")
        
        with self.lock:
            self.pending_messages[seq_num] = PendingMessage(
                sequence_number=seq_num,
                packet=packet,
                send_time=time.time(),
                attempts=0,
                recipient="SERVER",
                packet_type=MsgType.LIST,
                last_retry_time=0.0
            )
        
        self.send_packet(packet)
        return True
    
    def request_groups_list(self) -> bool:
        """Request list of available groups"""
        if not self.connected:
            print("Not connected to server")
            return False
        
        seq_num = self.get_next_sequence()
        packet = create_packet(MsgType.GROUPS, seq_num, self.username, "SERVER")
        
        with self.lock:
            self.pending_messages[seq_num] = PendingMessage(
                sequence_number=seq_num,
                packet=packet,
                send_time=time.time(),
                attempts=0,
                recipient="SERVER",
                packet_type=MsgType.GROUPS,
                last_retry_time=0.0
            )
        
        self.send_packet(packet)
        return True
    
    def send_heartbeat(self):
        """Send heartbeat to server"""
        if not self.connected:
            return
        
        try:
            heartbeat_packet = create_packet(MsgType.HEARTBEAT, 0, self.username, "SERVER")
            self.send_packet(heartbeat_packet)
        except Exception as e:
            self.log(f"Error sending heartbeat: {e}")
    
    def handle_ack(self, packet: Dict):
        """Handle ACK packet and mark message as delivered"""
        seq_num = packet['sequence_number']
        
        with self.lock:
            if seq_num in self.pending_messages:
                self.pending_messages[seq_num].status = MessageStatus.DELIVERED
                del self.pending_messages[seq_num]
    
    def handle_data(self, packet: Dict):
        """Handle DATA packet - display message"""
        sender = packet['sender']
        payload = packet['payload']
        seq_num = packet['sequence_number']
        
        # Check for duplicates
        with self.lock:
            if seq_num in self.received_seq_window:
                # Duplicate - resend ACK but ignore payload
                ack_packet = create_packet(MsgType.ACK, seq_num, self.username, sender)
                self.send_packet(ack_packet)
                return
            
            # Add to received window
            self.received_seq_window.append(seq_num)
        
        # Display message
        try:
            message = payload.decode('utf-8')
            print(f"\n[{sender}]: {message}")
            print(f"{self.username}> ", end='', flush=True)
        except UnicodeDecodeError:
            self.log(f"Error decoding message from {sender}")
        
        # Send ACK
        ack_packet = create_packet(MsgType.ACK, seq_num, self.username, sender)
        self.send_packet(ack_packet)
    
    def handle_error(self, packet: Dict):
        """Handle ERROR packet"""
        payload = packet['payload']
        try:
            error_msg = payload.decode('utf-8')
            print(f"\n[ERROR]: {error_msg}")
            print(f"{self.username}> ", end='', flush=True)
        except UnicodeDecodeError:
            self.log("Error decoding error message")
    
    def handle_list_response(self, packet: Dict):
        """Handle LIST_RESPONSE packet"""
        payload = packet['payload']
        try:
            user_list = payload.decode('utf-8')
            print(f"\n[Online Users]:")
            users = user_list.split(',') if user_list else []
            for user in users:
                if user.strip():
                    print(f"  - {user.strip()}")
            print(f"{self.username}> ", end='', flush=True)
        except UnicodeDecodeError:
            self.log("Error decoding user list")
    
    def handle_groups_response(self, packet: Dict):
        """Handle GROUPS_RESPONSE packet"""
        payload = packet['payload']
        try:
            groups_list = payload.decode('utf-8')
            print(f"\n[Available Groups]:")
            groups = groups_list.split(',') if groups_list else []
            for group in groups:
                if group.strip():
                    print(f"  - {group.strip()}")
            print(f"{self.username}> ", end='', flush=True)
        except UnicodeDecodeError:
            self.log("Error decoding groups list")
    
    def recv_thread(self):
        """Thread for receiving and processing packets"""
        while self.running:
            try:
                data, addr = self.sock.recvfrom(4096)
                packet = parse_packet(data)
                
                if packet is None:
                    continue
                
                # update last received time
                with self.lock:
                    self.last_received_time = time.time()
                
                packet_type = packet['packet_type']
                
                # Handle handshake completion during connection
                if packet_type == MsgType.SYN_ACK and not self.handshake_complete:
                    with self.handshake_lock:
                        if not self.handshake_complete:
                            ack_packet = create_packet(MsgType.ACK, 0, self.username, "SERVER")
                            self.send_packet(ack_packet)
                            with self.lock:
                                self.connected = True
                                self.handshake_complete = True
                            continue
                
                if not self.connected:
                    continue
                
                # Route packet to appropriate handler
                if packet_type == MsgType.DATA:
                    self.handle_data(packet)
                elif packet_type == MsgType.ACK:
                    self.handle_ack(packet)
                elif packet_type == MsgType.ERROR:
                    self.handle_error(packet)
                elif packet_type == MsgType.LIST_RESPONSE:
                    self.handle_list_response(packet)
                elif packet_type == MsgType.GROUPS_RESPONSE:
                    self.handle_groups_response(packet)
                elif packet_type == MsgType.FIN:
                    # Server is disconnecting us
                    self.log("Server disconnected")
                    with self.lock:
                        self.connected = False
                    break
                elif packet_type == MsgType.FIN_ACK:
                    # Server sent FIN_ACK (during disconnect)
                    # Send final ACK
                    ack_packet = create_packet(MsgType.ACK, 0, self.username, "SERVER")
                    self.send_packet(ack_packet)
                    with self.lock:
                        self.connected = False
                    break
                    
            except socket.timeout:
                # check for connection loss - no packets received for a while
                if self.connected:
                    # try to detect if connection is lost
                    # if no heartbeat response or no packets for extended period
                    continue
                continue
            except Exception as e:
                if self.running:
                    self.log(f"Error in recv_thread: {e}")
    
    def retransmit_thread(self):
        """Thread for retransmitting unacknowledged messages"""
        while self.running:
            if not self.connected:
                time.sleep(0.1)
                continue
            
            current_time = time.time()
            messages_to_retransmit = []
            
            with self.lock:
                for seq_num, pending_msg in list(self.pending_messages.items()):
                    # Calculate exponential backoff delay
                    delay = min(INITIAL_RETRANSMIT_DELAY * (2 ** pending_msg.attempts), MAX_RETRANSMIT_DELAY)
                    
                    # Check if enough time has passed since last retry
                    time_since_last_retry = current_time - pending_msg.last_retry_time
                    time_since_send = current_time - pending_msg.send_time
                    
                    if pending_msg.last_retry_time == 0.0:
                        # First retry check
                        if time_since_send >= INITIAL_RETRANSMIT_DELAY:
                            messages_to_retransmit.append((seq_num, pending_msg))
                    else:
                        # Subsequent retries
                        if time_since_last_retry >= delay:
                            messages_to_retransmit.append((seq_num, pending_msg))
            
            # Retransmit messages
            for seq_num, pending_msg in messages_to_retransmit:
                pending_msg.attempts += 1
                pending_msg.last_retry_time = current_time
                
                if pending_msg.attempts > 10:  # Give up after 10 attempts
                    with self.lock:
                        if seq_num in self.pending_messages:
                            self.pending_messages[seq_num].status = MessageStatus.FAILED
                            del self.pending_messages[seq_num]
                    self.log(f"Message to {pending_msg.recipient} failed after maximum retries")
                else:
                    self.send_packet(pending_msg.packet)
            
            time.sleep(0.1)  # Check every 100ms
    
    def heartbeat_thread(self):
        """Thread for sending periodic heartbeats"""
        while self.running:
            if self.connected:
                self.send_heartbeat()
                # check connection health periodically
                self.check_connection_health()
            time.sleep(HEARTBEAT_INTERVAL)
    
    def input_thread(self):
        """Thread for handling user input"""
        print(f"\n{'='*60}")
        print(f"UDP Messaging Client")
        print(f"Username: {self.username}")
        print(f"Status: Connected to server at {self.host}:{self.port}")
        print(f"{'='*60}\n")
        print("Commands:")
        print("  @username message  - Send a direct message")
        print("  #groupname message - Send a message to a group")
        print("  /create groupname  - Create a new group")
        print("  /join groupname    - Join or create a group")
        print("  /leave groupname   - Leave a group")
        print("  /list              - List online users")
        print("  /groups            - List available groups")
        print("  /quit              - Exit the application")
        print(f"\n{self.username}> ", end='', flush=True)
        
        while self.running:
            try:
                user_input = input().strip()
                
                if not user_input:
                    print(f"{self.username}> ", end='', flush=True)
                    continue
                
                if user_input == "/quit":
                    print("Disconnecting...")
                    self.running = False
                    self.disconnect()
                    break
                
                elif user_input.startswith("@"):
                    # Direct message: @username message
                    parts = user_input[1:].split(" ", 1)
                    if len(parts) == 2:
                        recipient, message = parts
                        self.send_message(recipient, message)
                    else:
                        print("Usage: @username message")
                
                elif user_input.startswith("#"):
                    # Group message: #groupname message
                    parts = user_input[1:].split(" ", 1)
                    if len(parts) == 2:
                        group_name, message = parts
                        self.send_group_message(group_name, message)
                    else:
                        print("Usage: #groupname message")
                
                elif user_input.startswith("/create "):
                    # Create group
                    group_name = user_input[8:].strip()
                    if group_name:
                        self.create_group(group_name)
                        print(f"Creating group '{group_name}'...")
                    else:
                        print("Usage: /create groupname")
                
                elif user_input.startswith("/join "):
                    # Join group
                    group_name = user_input[6:].strip()
                    if group_name:
                        self.join_group(group_name)
                        print(f"Joining group '{group_name}'...")
                    else:
                        print("Usage: /join groupname")
                
                elif user_input.startswith("/leave "):
                    # Leave group
                    group_name = user_input[7:].strip()
                    if group_name:
                        self.leave_group(group_name)
                        print(f"Leaving group '{group_name}'...")
                    else:
                        print("Usage: /leave groupname")
                
                elif user_input == "/list":
                    # List online users
                    self.request_user_list()
                
                elif user_input == "/groups":
                    # List available groups
                    self.request_groups_list()
                
                else:
                    print("Unknown command. Type /quit to exit.")
                
                if self.running:
                    print(f"{self.username}> ", end='', flush=True)
                    
            except EOFError:
                break
            except Exception as e:
                self.log(f"Error in input_thread: {e}")
                if self.running:
                    print(f"{self.username}> ", end='', flush=True)
    
    def run(self):
        """Main client loop"""
        # Connect to server
        if not self.connect():
            return
        
        # Start threads
        recv_thread = threading.Thread(target=self.recv_thread, daemon=True)
       # retransmit_thread = threading.Thread(target=self.retransmit_thread, daemon=True)
        heartbeat_thread = threading.Thread(target=self.heartbeat_thread, daemon=True)
        
        recv_thread.start()
        #retransmit_thread.start()
        heartbeat_thread.start()
        
        # Run input thread in main thread (blocks)
        try:
            self.input_thread()
        except KeyboardInterrupt:
            print("\nInterrupted by user")
        finally:
            self.running = False
            self.disconnect()
            self.sock.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python client.py <username> [host] [port]")
        sys.exit(1)
    
    username = sys.argv[1]
    host = sys.argv[2] if len(sys.argv) > 2 else HOST
    port = int(sys.argv[3]) if len(sys.argv) > 3 else PORT
    
    client = UDPClient(username, host, port)
    client.run()

