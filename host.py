import socket
import struct
import time
from collections import defaultdict

PORT = 8080

# Message type constants
MSG_TYPE_1TO1 = 0x01
MSG_TYPE_GROUP = 0x02
MSG_TYPE_ACK = 0x03
MSG_TYPE_SYN = 0x04
MSG_TYPE_CONN_ACCEPT = 0x05
MSG_TYPE_FIN = 0x06
MSG_TYPE_HEARTBEAT = 0x07
MSG_TYPE_ERROR = 0x08

# client id -> (ip, port)
clients = {}
# 1:1 connection id -> (client id, client id)
connections = defaultdict(tuple)
# group id -> set of client ids
group_connections = defaultdict(set)
# client id -> expected sequence number (for duplicate detection)
client_seq_nums = defaultdict(int)
# client id -> last heartbeat time
client_heartbeats = {}

# global socket reference (set in main function for easier access)
sock = None

def parse_packet(data):
    """
    Parse incoming packet according to protocol format.
    Returns: (msg_type, seq_num, source_id, dest_id, payload_len, flags, timestamp, checksum, payload)
    """
    try:
        if len(data) < 18:  # Minimum header size
            return None
        
        # parse fixed header fields
        msg_type = data[0]
        seq_num = struct.unpack('>I', data[1:5])[0]  # 4 bytes, big-endian
        
        # parse variable-length IDs (assuming they're null-terminated strings)
        idx = 5
        # Source ID
        source_end = data.find(b'\x00', idx)
        if source_end == -1:
            return None
        source_id = data[idx:source_end].decode('utf-8')
        idx = source_end + 1
        
        # destination ID
        dest_end = data.find(b'\x00', idx)
        if dest_end == -1:
            return None
        dest_id = data[idx:dest_end].decode('utf-8')
        idx = dest_end + 1
        
        if len(data) < idx + 11:  # payload length + flags + timestamp + checksum
            return None
        
        payload_len = struct.unpack('>H', data[idx:idx+2])[0]  # 2 bytes
        flags = data[idx+2]
        timestamp = struct.unpack('>Q', data[idx+3:idx+11])[0]  # 8 bytes
        checksum = struct.unpack('>H', data[idx+11:idx+13])[0]  # 2 bytes
        
        # payload
        payload_start = idx + 13
        if len(data) < payload_start + payload_len:
            return None
        payload = data[payload_start:payload_start + payload_len]
        
        return (msg_type, seq_num, source_id, dest_id, payload_len, flags, timestamp, checksum, payload)
    except Exception as e:
        print(f"Error parsing packet: {e}")
        return None

def create_ack_packet(seq_num, source_id, dest_id):
    """create an ACK packet."""
    # simple ACK format: type + seq num + source id + dest id
    source_bytes = source_id.encode('utf-8') + b'\x00'
    dest_bytes = dest_id.encode('utf-8') + b'\x00'
    timestamp = int(time.time() * 1000)  # timestamp in milliseconds
    
    packet = struct.pack('>B', MSG_TYPE_ACK)  # message type
    packet += struct.pack('>I', seq_num)  # sequence number
    packet += source_bytes  # source id
    packet += dest_bytes  # destination id
    packet += struct.pack('>H', 0)  # payload length (0 for ACK)
    packet += struct.pack('>B', 0)  # flags
    packet += struct.pack('>Q', timestamp)  # timestamp
    packet += struct.pack('>H', 0)  # checksum (simplified)
    
    return packet

def send_packet(packet, addr):
    """Send packet to address."""
    global sock
    if sock:
        sock.sendto(packet, addr)

def handle_client(data, addr):
    """
    Handle incoming client packet.
    Parses packet, handles different message types, and routes messages.
    """
    global clients, group_connections, client_seq_nums, client_heartbeats
    
    parsed = parse_packet(data)
    if not parsed:
        print(f"Invalid packet from {addr}")
        return
    
    msg_type, seq_num, source_id, dest_id, payload_len, flags, timestamp, checksum, payload = parsed
    
    client_heartbeats[source_id] = time.time()
    
    # handle duplicate detection
    if source_id in client_seq_nums:
        if seq_num <= client_seq_nums[source_id]:
            # duplicate or out-of-order - send ACK anyway but don't process
            print(f"Duplicate/out-of-order packet from {source_id}: seq={seq_num}, expected>{client_seq_nums[source_id]}")
            ack = create_ack_packet(seq_num, "host", source_id)
            send_packet(ack, addr)
            return
    
    # update expected sequence number
    client_seq_nums[source_id] = seq_num
    
    # route based on message type
    if msg_type == MSG_TYPE_SYN:
        handle_connection_request(source_id, addr, seq_num)
        
    elif msg_type == MSG_TYPE_ACK:
        # logging acknowledgement
        print(f"ACK received from {source_id} for seq {seq_num}")
        
    elif msg_type == MSG_TYPE_1TO1:
        # 1:1 message - relay to destination
        handle_1to1_message(source_id, dest_id, payload, seq_num, addr)
        
    elif msg_type == MSG_TYPE_GROUP:
        # broadcasting group message to all group members
        handle_group_message(source_id, dest_id, payload, seq_num, addr)
        
    elif msg_type == MSG_TYPE_FIN:
        # handling connection close
        handle_connection_close(source_id, addr)
        
    elif msg_type == MSG_TYPE_HEARTBEAT:
        # sending ACK for heartbeat
        ack = create_ack_packet(seq_num, "host", source_id)
        send_packet(ack, addr)
        
    else:
        print(f"Unknown message type {msg_type} from {source_id}")

def handle_connection_request(source_id, addr, seq_num):
    """Handle client connection request (SYN)."""
    global clients
    
    # registering or updating client
    clients[source_id] = addr
    print(f"Client {source_id} connected from {addr}")
    
    # send connection accept (SYN-ACK)
    # for simplicity, we'll use a simple accept message
    source_bytes = "host".encode('utf-8') + b'\x00'
    dest_bytes = source_id.encode('utf-8') + b'\x00'
    timestamp = int(time.time() * 1000)
    
    packet = struct.pack('>B', MSG_TYPE_CONN_ACCEPT)
    packet += struct.pack('>I', seq_num + 1)  # next sequence number
    packet += source_bytes
    packet += dest_bytes
    packet += struct.pack('>H', 0)  # payload length
    packet += struct.pack('>B', 0)  # flags
    packet += struct.pack('>Q', timestamp)
    packet += struct.pack('>H', 0)  # checksum
    
    send_packet(packet, addr)
    
    # sending ACK for the SYN
    ack = create_ack_packet(seq_num, "host", source_id)
    send_packet(ack, addr)

def handle_1to1_message(source_id, dest_id, payload, seq_num, source_addr):
    """Handle 1:1 message - relay to destination client."""
    global clients
    
    # sending ACK to sender
    ack = create_ack_packet(seq_num, "host", source_id)
    send_packet(ack, source_addr)
    
    # checking if destination is connected
    if dest_id not in clients:
        print(f"Destination {dest_id} not found. Message from {source_id} dropped.")
        # could queue message here for later delivery
        return
    
    # relaying message to destination
    dest_addr = clients[dest_id]
    
    source_bytes = source_id.encode('utf-8') + b'\x00'
    dest_bytes = dest_id.encode('utf-8') + b'\x00'
    timestamp = int(time.time() * 1000)
    
    packet = struct.pack('>B', MSG_TYPE_1TO1)
    packet += struct.pack('>I', seq_num)
    packet += source_bytes
    packet += dest_bytes
    packet += struct.pack('>H', len(payload))
    packet += struct.pack('>B', 0)
    packet += struct.pack('>Q', timestamp)
    packet += struct.pack('>H', 0)  # Checksum
    packet += payload
    
    send_packet(packet, dest_addr)
    print(f"Relayed 1:1 message from {source_id} to {dest_id}: {payload.decode('utf-8', errors='ignore')}")

def handle_group_message(source_id, group_id, payload, seq_num, source_addr):
    """Handle group message - broadcast to all group members."""
    global group_connections, clients
    
    # sending ACK to sender
    ack = create_ack_packet(seq_num, "host", source_id)
    send_packet(ack, source_addr)
    
    # ensuring sender is in the group
    if source_id not in group_connections[group_id]:
        group_connections[group_id].add(source_id)
        print(f"Added {source_id} to group {group_id}")
    
    # broadcasting to all group members except sender
    message_text = payload.decode('utf-8', errors='ignore')
    print(f"Group message from {source_id} to group {group_id}: {message_text}")
    
    for member_id in group_connections[group_id]:
        if member_id != source_id and member_id in clients:
            dest_addr = clients[member_id]
            
            # creating packet for each recipient
            source_bytes = source_id.encode('utf-8') + b'\x00'
            dest_bytes = group_id.encode('utf-8') + b'\x00'
            timestamp = int(time.time() * 1000)
            
            packet = struct.pack('>B', MSG_TYPE_GROUP)
            packet += struct.pack('>I', seq_num)
            packet += source_bytes
            packet += dest_bytes
            packet += struct.pack('>H', len(payload))
            packet += struct.pack('>B', 0)
            packet += struct.pack('>Q', timestamp)
            packet += struct.pack('>H', 0)
            packet += payload
            
            send_packet(packet, dest_addr)

def handle_connection_close(source_id, addr):
    """Handle client disconnection (FIN)."""
    global clients, group_connections, client_seq_nums, client_heartbeats
    
    # removing from all groups
    for group_id in list(group_connections.keys()):
        group_connections[group_id].discard(source_id)
        if not group_connections[group_id]:  # removing empty groups
            del group_connections[group_id]
    
    # cleaning up client data
    if source_id in clients:
        del clients[source_id]
    if source_id in client_seq_nums:
        del client_seq_nums[source_id]
    if source_id in client_heartbeats:
        del client_heartbeats[source_id]
    
    print(f"Client {source_id} disconnected")
    
    # sending FIN-ACK
    ack = create_ack_packet(0, "host", source_id)
    send_packet(ack, addr)

if __name__ == "__main__":
    global sock
    # creating a UDP socket
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('0.0.0.0', PORT))
    print(f"Server is running on port {PORT}")

    while True:
        data, addr = sock.recvfrom(1024)
        handle_client(data, addr)

    sock.close()
