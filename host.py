import socket
import struct
import time
import threading
from collections import defaultdict
from enum import IntEnum
from dataclasses import dataclass
from typing import Dict, Set, Optional, Tuple
import sys

# Protocol Constants
PORT = 5001
HEARTBEAT_INTERVAL = 30  # seconds
CLIENT_TIMEOUT = 90  # seconds
MAX_CLIENTS = 100

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

@dataclass
class ClientInfo:
    username: str
    address: Tuple[str, int]
    last_seen: float
    sequence_number: int
    status: str  # "ONLINE" or "OFFLINE"
    pending_ack: Optional[int] = None  # sequence number waiting for ACK

class Group:
    def __init__(self, group_name: str, admin: str):
        self.group_name = group_name
        self.admin = admin
        self.members: Set[str] = set([admin])
        self.created_at = time.time()
        self.message_history = []  # Optional: fixed-size ring buffer

    def add_member(self, member: str):
        self.members.add(member)

    def remove_member(self, member: str):
        self.members.discard(member)

    def get_members(self) -> Set[str]:
        return self.members.copy()

    def has_member(self, username: str) -> bool:
        return username in self.members

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
    
    # Packet structure:
    # packet_type (1 byte)
    # sequence_number (4 bytes, unsigned int)
    # timestamp (8 bytes, double)
    # sender_len (2 bytes, unsigned short)
    # sender (variable)
    # recipient_len (2 bytes, unsigned short)
    # recipient (variable)
    # payload_len (4 bytes, unsigned int)
    # payload (variable)
    # checksum (2 bytes, unsigned short)
    
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

class UDPServer:
    def __init__(self, port: int = PORT):
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('0.0.0.0', port))
        self.client_registry: Dict[str, ClientInfo] = {}
        self.group_registry: Dict[str, Group] = {}
        self.pending_messages: Dict[int, Dict] = {}  # seq_num -> message info
        self.sequence_counter = 0
        self.lock = threading.Lock()
        self.running = True
        
    def get_next_sequence(self) -> int:
        """Get next sequence number for server-originated packets"""
        with self.lock:
            self.sequence_counter += 1
            return self.sequence_counter
    
    def log(self, message: str):
        """Log a message with timestamp"""
        timestamp = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime())
        print(f"[{timestamp}] {message}")
    
    def send_packet(self, packet: bytes, address: Tuple[str, int]):
        """Send a packet to the specified address"""
        try:
            self.sock.sendto(packet, address)
        except Exception as e:
            self.log(f"Error sending packet to {address}: {e}")
    
    def handle_syn(self, packet: Dict, address: Tuple[str, int]):
        """Handle SYN packet - register new client"""
        username = packet['sender']
        
        with self.lock:
            # Check if username already exists
            if username in self.client_registry:
                # Client reconnecting - update address
                self.client_registry[username].address = address
                self.client_registry[username].last_seen = time.time()
                self.client_registry[username].status = "ONLINE"
                self.log(f"Client '{username}' reconnected from {address[0]}:{address[1]}")
            else:
                # New client
                if len(self.client_registry) >= MAX_CLIENTS:
                    # Send error packet
                    error_payload = "Server is full. Maximum clients reached.".encode('utf-8')
                    error_packet = create_packet(MsgType.ERROR, 0, "SERVER", username, error_payload)
                    self.send_packet(error_packet, address)
                    return
                
                self.client_registry[username] = ClientInfo(
                    username=username,
                    address=address,
                    last_seen=time.time(),
                    sequence_number=0,
                    status="ONLINE"
                )
                self.log(f"Client '{username}' connected from {address[0]}:{address[1]}")
        
        # Send SYN_ACK
        syn_ack_packet = create_packet(MsgType.SYN_ACK, 0, "SERVER", username)
        self.send_packet(syn_ack_packet, address)
    
    def handle_ack_handshake(self, packet: Dict, address: Tuple[str, int]):
        """Handle ACK packet from handshake - mark client as connected"""
        username = packet['sender']
        
        with self.lock:
            if username in self.client_registry:
                self.client_registry[username].last_seen = time.time()
                self.client_registry[username].status = "ONLINE"
    
    def handle_data(self, packet: Dict, address: Tuple[str, int]):
        """Handle DATA packet - forward to recipient"""
        sender = packet['sender']
        recipient = packet['recipient']
        seq_num = packet['sequence_number']
        payload = packet['payload']
        
        with self.lock:
            # Verify sender is registered
            if sender not in self.client_registry:
                return
            
            # Update sender's last_seen
            self.client_registry[sender].last_seen = time.time()
            
            # Send ACK to sender
            ack_packet = create_packet(MsgType.ACK, seq_num, "SERVER", sender)
            self.send_packet(ack_packet, address)
            
            # Forward to recipient
            if recipient in self.client_registry:
                recipient_info = self.client_registry[recipient]
                data_packet = create_packet(MsgType.DATA, seq_num, sender, recipient, payload)
                self.send_packet(data_packet, recipient_info.address)
                self.log(f"Message relayed: {sender} -> {recipient}")
            else:
                # Recipient not found - send error to sender
                error_payload = f"User '{recipient}' is not online.".encode('utf-8')
                error_packet = create_packet(MsgType.ERROR, seq_num, "SERVER", sender, error_payload)
                self.send_packet(error_packet, address)
    
    def handle_group_msg(self, packet: Dict, address: Tuple[str, int]):
        """Handle GROUP_MSG packet - broadcast to group members"""
        sender = packet['sender']
        group_name = packet['recipient']  # recipient field contains group name
        seq_num = packet['sequence_number']
        payload = packet['payload']
        
        with self.lock:
            if sender not in self.client_registry:
                return
            
            self.client_registry[sender].last_seen = time.time()
            
            # Send ACK to sender
            ack_packet = create_packet(MsgType.ACK, seq_num, "SERVER", sender)
            self.send_packet(ack_packet, address)
            
            # Check if group exists
            if group_name not in self.group_registry:
                error_payload = f"Group '{group_name}' does not exist.".encode('utf-8')
                error_packet = create_packet(MsgType.ERROR, seq_num, "SERVER", sender, error_payload)
                self.send_packet(error_packet, address)
                return
            
            group = self.group_registry[group_name]
            
            # Check if sender is a member
            if not group.has_member(sender):
                error_payload = f"You are not a member of group '{group_name}'.".encode('utf-8')
                error_packet = create_packet(MsgType.ERROR, seq_num, "SERVER", sender, error_payload)
                self.send_packet(error_packet, address)
                return
            
            # Broadcast to all members except sender
            for member in group.get_members():
                if member != sender and member in self.client_registry:
                    member_info = self.client_registry[member]
                    data_packet = create_packet(MsgType.DATA, seq_num, sender, member, payload)
                    self.send_packet(data_packet, member_info.address)
            
            self.log(f"Group message relayed: {sender} -> group '{group_name}'")
    
    def handle_join(self, packet: Dict, address: Tuple[str, int]):
        """Handle JOIN packet - add client to group"""
        sender = packet['sender']
        group_name = packet['recipient']  # recipient field contains group name
        
        with self.lock:
            if sender not in self.client_registry:
                return
            
            self.client_registry[sender].last_seen = time.time()
            
            # Create group if it doesn't exist
            if group_name not in self.group_registry:
                self.group_registry[group_name] = Group(group_name, sender)
                self.log(f"Group '{group_name}' created by '{sender}'")
            else:
                # Add member to existing group
                self.group_registry[group_name].add_member(sender)
                self.log(f"Client '{sender}' joined group '{group_name}'")
            
            # Send ACK
            ack_packet = create_packet(MsgType.ACK, packet['sequence_number'], "SERVER", sender)
            self.send_packet(ack_packet, address)
    
    def handle_leave(self, packet: Dict, address: Tuple[str, int]):
        """Handle LEAVE packet - remove client from group"""
        sender = packet['sender']
        group_name = packet['recipient']  # recipient field contains group name
        
        with self.lock:
            if sender not in self.client_registry:
                return
            
            self.client_registry[sender].last_seen = time.time()
            
            if group_name in self.group_registry:
                group = self.group_registry[group_name]
                if group.has_member(sender):
                    group.remove_member(sender)
                    self.log(f"Client '{sender}' left group '{group_name}'")
                    
                    # Remove group if empty
                    if len(group.get_members()) == 0:
                        del self.group_registry[group_name]
            
            # Send ACK
            ack_packet = create_packet(MsgType.ACK, packet['sequence_number'], "SERVER", sender)
            self.send_packet(ack_packet, address)
    
    def handle_heartbeat(self, packet: Dict, address: Tuple[str, int]):
        """Handle HEARTBEAT packet - update last_seen"""
        username = packet['sender']
        
        with self.lock:
            if username in self.client_registry:
                self.client_registry[username].last_seen = time.time()
                self.client_registry[username].status = "ONLINE"
    
    def handle_fin(self, packet: Dict, address: Tuple[str, int]):
        """Handle FIN packet - disconnect client"""
        username = packet['sender']
        
        with self.lock:
            if username in self.client_registry:
                # Remove from all groups
                groups_to_remove = []
                for group_name, group in self.group_registry.items():
                    if group.has_member(username):
                        group.remove_member(username)
                        if len(group.get_members()) == 0:
                            groups_to_remove.append(group_name)
                
                for group_name in groups_to_remove:
                    del self.group_registry[group_name]
                
                # Remove client
                del self.client_registry[username]
                self.log(f"Client '{username}' disconnected")
        
        # Send FIN_ACK
        fin_ack_packet = create_packet(MsgType.FIN, 0, "SERVER", username)
        self.send_packet(fin_ack_packet, address)
    
    def handle_ack(self, packet: Dict, address: Tuple[str, int]):
        """Handle ACK packet - mark message as delivered"""
        # ACKs are handled by clients, but we can update last_seen
        username = packet['sender']
        
        with self.lock:
            if username in self.client_registry:
                self.client_registry[username].last_seen = time.time()
    
    def handle_list(self, packet: Dict, address: Tuple[str, int]):
        """Handle LIST packet - send list of online users"""
        sender = packet['sender']
        
        with self.lock:
            if sender not in self.client_registry:
                return
            
            self.client_registry[sender].last_seen = time.time()
            
            # Get list of online users
            online_users = [username for username, info in self.client_registry.items() 
                          if info.status == "ONLINE"]
            user_list = ','.join(online_users)
            
            # Send ACK first
            ack_packet = create_packet(MsgType.ACK, packet['sequence_number'], "SERVER", sender)
            self.send_packet(ack_packet, address)
            
            # Send list response
            response_packet = create_packet(MsgType.LIST_RESPONSE, 0, "SERVER", sender, 
                                          user_list.encode('utf-8'))
            self.send_packet(response_packet, address)
    
    def handle_groups(self, packet: Dict, address: Tuple[str, int]):
        """Handle GROUPS packet - send list of available groups"""
        sender = packet['sender']
        
        with self.lock:
            if sender not in self.client_registry:
                return
            
            self.client_registry[sender].last_seen = time.time()
            
            # Get list of groups
            group_names = list(self.group_registry.keys())
            groups_list = ','.join(group_names)
            
            # Send ACK first
            ack_packet = create_packet(MsgType.ACK, packet['sequence_number'], "SERVER", sender)
            self.send_packet(ack_packet, address)
            
            # Send groups response
            response_packet = create_packet(MsgType.GROUPS_RESPONSE, 0, "SERVER", sender,
                                          groups_list.encode('utf-8'))
            self.send_packet(response_packet, address)
    
    def cleanup_inactive_clients(self):
        """Periodically clean up inactive clients"""
        while self.running:
            time.sleep(10)  # Check every 10 seconds
            
            current_time = time.time()
            clients_to_remove = []
            
            with self.lock:
                for username, client_info in self.client_registry.items():
                    if current_time - client_info.last_seen > CLIENT_TIMEOUT:
                        clients_to_remove.append(username)
                
                for username in clients_to_remove:
                    # Remove from groups
                    groups_to_remove = []
                    for group_name, group in self.group_registry.items():
                        if group.has_member(username):
                            group.remove_member(username)
                            if len(group.get_members()) == 0:
                                groups_to_remove.append(group_name)
                    
                    for group_name in groups_to_remove:
                        del self.group_registry[group_name]
                    
                    # Remove client
                    del self.client_registry[username]
                    self.log(f"Client '{username}' timed out and removed")
    
    def run(self):
        """Main server loop"""
        self.log(f"Server started on port {self.port}")
        self.log("Listening for connections...")
        
        # Start cleanup thread
        cleanup_thread = threading.Thread(target=self.cleanup_inactive_clients, daemon=True)
        cleanup_thread.start()
        
        while self.running:
            try:
                data, addr = self.sock.recvfrom(4096)
                packet = parse_packet(data)
                
                if packet is None:
                    self.log(f"Invalid packet received from {addr[0]}:{addr[1]} - dropped")
                    continue
                
                packet_type = packet['packet_type']
                
                # Route packet to appropriate handler
                if packet_type == MsgType.SYN:
                    self.handle_syn(packet, addr)
                elif packet_type == MsgType.ACK:
                    # Check if this is a handshake ACK (sequence 0) or regular ACK
                    if packet['sequence_number'] == 0 and packet['sender'] in self.client_registry:
                        self.handle_ack_handshake(packet, addr)
                    else:
                        self.handle_ack(packet, addr)
                elif packet_type == MsgType.DATA:
                    self.handle_data(packet, addr)
                elif packet_type == MsgType.GROUP_MSG:
                    self.handle_group_msg(packet, addr)
                elif packet_type == MsgType.JOIN:
                    self.handle_join(packet, addr)
                elif packet_type == MsgType.LEAVE:
                    self.handle_leave(packet, addr)
                elif packet_type == MsgType.HEARTBEAT:
                    self.handle_heartbeat(packet, addr)
                elif packet_type == MsgType.FIN:
                    self.handle_fin(packet, addr)
                elif packet_type == MsgType.LIST:
                    self.handle_list(packet, addr)
                elif packet_type == MsgType.GROUPS:
                    self.handle_groups(packet, addr)
                else:
                    self.log(f"Unknown packet type {packet_type} from {addr[0]}:{addr[1]}")
                    
            except Exception as e:
                self.log(f"Error handling packet: {e}")
        
        self.sock.close()

if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else PORT
    server = UDPServer(port)
    try:
        server.run()
    except KeyboardInterrupt:
        server.log("Server shutting down...")
        server.running = False
