#!/usr/bin/env python3
"""
Test script for reliable UDP messaging system.
Tests connection, message delivery, retransmission, packet loss, group chat, etc.
"""

import socket
import struct
import time
import threading
import random
import sys
from collections import deque
from enum import IntEnum
from typing import Dict, Optional, List, Tuple

# protocol constants
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

# packet loss simulation
PACKET_LOSS_RATE = 0.0  # 0.0 = no loss, 0.1 = 10% loss, etc.
SIMULATE_PACKET_LOSS = False

def calculate_checksum(data: bytes) -> int:
    """Calculate checksum for packet"""
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
    """Create a packet"""
    timestamp = time.time()
    sender_bytes = sender.encode('utf-8')
    recipient_bytes = recipient.encode('utf-8')
    
    header = struct.pack('!B I d H', packet_type, sequence_number, timestamp, len(sender_bytes))
    header += sender_bytes
    header += struct.pack('!H', len(recipient_bytes))
    header += recipient_bytes
    header += struct.pack('!I', len(payload))
    header += payload
    
    checksum = calculate_checksum(header)
    header += struct.pack('!H', checksum)
    return header

def parse_packet(data: bytes) -> Optional[Dict]:
    """Parse a packet, return dict or None if invalid"""
    try:
        if len(data) < 19:
            return None
        
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

class TestClient:
    """Test client for testing"""
    def __init__(self, username: str, host: str, port: int):
        self.username = username
        self.host = host
        self.port = port
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.settimeout(2.0)
        self.connected = False
        self.sequence_number = 0
        self.received_messages = []
        self.received_seq_window = deque(maxlen=100)
        self.pending_messages: Dict[int, Dict] = {}
        self.lock = threading.Lock()
        self.running = True
        
    def get_next_sequence(self) -> int:
        with self.lock:
            self.sequence_number += 1
            return self.sequence_number
    
    def send_packet(self, packet: bytes, simulate_loss: bool = False):
        """Send packet, optionally simulate loss"""
        if simulate_loss and SIMULATE_PACKET_LOSS and random.random() < PACKET_LOSS_RATE:
            return  # simulate loss
        try:
            self.sock.sendto(packet, (self.host, self.port))
        except Exception as e:
            print(f"[{self.username}] Error sending: {e}")
    
    def connect(self) -> bool:
        """Connect to server"""
        try:
            syn_packet = create_packet(MsgType.SYN, 0, self.username, "SERVER")
            self.send_packet(syn_packet)
            
            start_time = time.time()
            while time.time() - start_time < 5:
                try:
                    data, addr = self.sock.recvfrom(4096)
                    packet = parse_packet(data)
                    if packet and packet['packet_type'] == MsgType.SYN_ACK:
                        ack_packet = create_packet(MsgType.ACK, 0, self.username, "SERVER")
                        self.send_packet(ack_packet)
                        self.connected = True
                        return True
                except socket.timeout:
                    continue
            return False
        except Exception as e:
            print(f"[{self.username}] Connection error: {e}")
            return False
    
    def send_message(self, recipient: str, message: str) -> bool:
        """Send message"""
        if not self.connected:
            return False
        
        seq_num = self.get_next_sequence()
        payload = message.encode('utf-8')
        packet = create_packet(MsgType.DATA, seq_num, self.username, recipient, payload)
        
        with self.lock:
            self.pending_messages[seq_num] = {
                'packet': packet,
                'send_time': time.time(),
                'recipient': recipient,
                'message': message
            }
        
        self.send_packet(packet, simulate_loss=True)
        return True
    
    def send_group_message(self, group_name: str, message: str) -> bool:
        """Send group message"""
        if not self.connected:
            return False
        
        seq_num = self.get_next_sequence()
        payload = message.encode('utf-8')
        packet = create_packet(MsgType.GROUP_MSG, seq_num, self.username, group_name, payload)
        
        with self.lock:
            self.pending_messages[seq_num] = {
                'packet': packet,
                'send_time': time.time(),
                'recipient': group_name,
                'message': message
            }
        
        self.send_packet(packet, simulate_loss=True)
        return True
    
    def join_group(self, group_name: str) -> bool:
        """Join group"""
        if not self.connected:
            return False
        
        seq_num = self.get_next_sequence()
        packet = create_packet(MsgType.JOIN, seq_num, self.username, group_name)
        self.send_packet(packet)
        return True
    
    def receive_messages(self, timeout: float = 1.0):
        """Receive messages"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                data, addr = self.sock.recvfrom(4096)
                packet = parse_packet(data)
                
                if packet is None:
                    continue
                
                if packet['packet_type'] == MsgType.DATA:
                    seq_num = packet['sequence_number']
                    with self.lock:
                        if seq_num not in self.received_seq_window:
                            self.received_seq_window.append(seq_num)
                            message = packet['payload'].decode('utf-8')
                            self.received_messages.append({
                                'sender': packet['sender'],
                                'message': message,
                                'seq': seq_num
                            })
                    
                    # send ACK
                    ack_packet = create_packet(MsgType.ACK, seq_num, self.username, packet['sender'])
                    self.send_packet(ack_packet, simulate_loss=True)
                
                elif packet['packet_type'] == MsgType.ACK:
                    seq_num = packet['sequence_number']
                    with self.lock:
                        if seq_num in self.pending_messages:
                            del self.pending_messages[seq_num]
                            
            except socket.timeout:
                continue
            except Exception as e:
                if self.running:
                    print(f"[{self.username}] Receive error: {e}")
    
    def disconnect(self):
        """Disconnect"""
        if self.connected:
            fin_packet = create_packet(MsgType.FIN, 0, self.username, "SERVER")
            self.send_packet(fin_packet)
        self.connected = False
        self.running = False
        self.sock.close()

def test_basic_connection(host: str, port: int):
    """Test basic connection"""
    print("\n" + "="*60)
    print("TEST 1: Basic Connection")
    print("="*60)
    
    client1 = TestClient("alice", host, port)
    client2 = TestClient("bob", host, port)
    
    print("Connecting clients...")
    if client1.connect() and client2.connect():
        print("✓ Both clients connected successfully")
        client1.disconnect()
        client2.disconnect()
        return True
    else:
        print("✗ Connection failed")
        return False

def test_message_delivery(host: str, port: int):
    """Test message delivery"""
    print("\n" + "="*60)
    print("TEST 2: Message Delivery")
    print("="*60)
    
    client1 = TestClient("alice", host, port)
    client2 = TestClient("bob", host, port)
    
    if not (client1.connect() and client2.connect()):
        print("✗ Connection failed")
        return False
    
    print("Sending message from alice to bob...")
    client1.send_message("bob", "Hello, Bob!")
    
    # give time for delivery
    time.sleep(0.5)
    client2.receive_messages(timeout=2.0)
    
    if len(client2.received_messages) > 0:
        print(f"✓ Message received: {client2.received_messages[0]['message']}")
        client1.disconnect()
        client2.disconnect()
        return True
    else:
        print("✗ Message not received")
        client1.disconnect()
        client2.disconnect()
        return False

def test_retransmission(host: str, port: int):
    """Test retransmission with packet loss"""
    print("\n" + "="*60)
    print("TEST 3: Retransmission (with 25% packet loss)")
    print("="*60)
    
    global PACKET_LOSS_RATE, SIMULATE_PACKET_LOSS
    SIMULATE_PACKET_LOSS = True
    PACKET_LOSS_RATE = 0.25
    
    client1 = TestClient("alice", host, port)
    client2 = TestClient("bob", host, port)
    
    if not (client1.connect() and client2.connect()):
        print("✗ Connection failed")
        SIMULATE_PACKET_LOSS = False
        PACKET_LOSS_RATE = 0.0
        return False
    
    print("Sending message with packet loss simulation...")
    client1.send_message("bob", "Test message with retransmission")
    
    time.sleep(3.0)  # wait for retransmission
    client2.receive_messages(timeout=2.0)
    
    # retransmit unacked
    current_time = time.time()
    with client1.lock:
        for seq_num, pending in list(client1.pending_messages.items()):
            if current_time - pending['send_time'] > 0.5:
                client1.send_packet(pending['packet'], simulate_loss=True)
    
    time.sleep(1.0)
    client2.receive_messages(timeout=2.0)
    
    success = len(client2.received_messages) > 0
    if success:
        print(f"✓ Message received despite packet loss: {client2.received_messages[0]['message']}")
    else:
        print("✗ Message not received")
    
    SIMULATE_PACKET_LOSS = False
    PACKET_LOSS_RATE = 0.0
    client1.disconnect()
    client2.disconnect()
    return success

def test_group_chat(host: str, port: int):
    """Test group chat"""
    print("\n" + "="*60)
    print("TEST 4: Group Chat")
    print("="*60)
    
    client1 = TestClient("alice", host, port)
    client2 = TestClient("bob", host, port)
    client3 = TestClient("charlie", host, port)
    
    if not (client1.connect() and client2.connect() and client3.connect()):
        print("✗ Connection failed")
        return False
    
    print("Creating group 'test-group'...")
    client1.join_group("test-group")
    time.sleep(0.2)
    
    print("Joining group...")
    client2.join_group("test-group")
    client3.join_group("test-group")
    time.sleep(0.2)
    
    print("Sending group message...")
    client1.send_group_message("test-group", "Hello everyone!")
    
    time.sleep(1.0)
    client2.receive_messages(timeout=2.0)
    client3.receive_messages(timeout=2.0)
    
    bob_received = len([m for m in client2.received_messages if 'test-group' in str(m) or 'alice' in m.get('sender', '')]) > 0
    charlie_received = len([m for m in client3.received_messages if 'test-group' in str(m) or 'alice' in m.get('sender', '')]) > 0
    
    if bob_received and charlie_received:
        print("✓ Group message received by both members")
        client1.disconnect()
        client2.disconnect()
        client3.disconnect()
        return True
    else:
        print(f"✗ Group message not received (bob: {bob_received}, charlie: {charlie_received})")
        client1.disconnect()
        client2.disconnect()
        client3.disconnect()
        return False

def test_multiple_clients(host: str, port: int, num_clients: int = 10):
    """Test multiple concurrent clients"""
    print("\n" + "="*60)
    print(f"TEST 5: Multiple Concurrent Clients ({num_clients} clients)")
    print("="*60)
    
    clients = []
    for i in range(num_clients):
        client = TestClient(f"client{i}", host, port)
        clients.append(client)
    
    print("Connecting all clients...")
    connected = 0
    for client in clients:
        if client.connect():
            connected += 1
        time.sleep(0.1)
    
    print(f"✓ {connected}/{num_clients} clients connected")
    
    if connected < num_clients * 0.8:  # allow 20% failures
        print("✗ Too many connection failures")
        for client in clients:
            client.disconnect()
        return False
    
    print("Sending messages between clients...")
    for i in range(min(5, num_clients - 1)):
        clients[i].send_message(f"client{i+1}", f"Message {i}")
        time.sleep(0.1)
    
    time.sleep(1.0)
    for client in clients[1:6]:
        client.receive_messages(timeout=1.0)
    
    received_count = sum(len(c.received_messages) for c in clients[1:6])
    print(f"✓ {received_count} messages received")
    
    for client in clients:
        client.disconnect()
    
    return received_count >= 3  # at least 3 messages should be received

def test_duplicate_detection(host: str, port: int):
    """Test duplicate packet detection"""
    print("\n" + "="*60)
    print("TEST 6: Duplicate Packet Detection")
    print("="*60)
    
    client1 = TestClient("alice", host, port)
    client2 = TestClient("bob", host, port)
    
    if not (client1.connect() and client2.connect()):
        print("✗ Connection failed")
        return False
    
    print("Sending message...")
    seq_num = client1.get_next_sequence()
    payload = "Test message".encode('utf-8')
    packet = create_packet(MsgType.DATA, seq_num, "alice", "bob", payload)
    client1.send_packet(packet)
    
    time.sleep(0.3)
    client2.receive_messages(timeout=1.0)
    initial_count = len(client2.received_messages)
    
    print("Sending duplicate packet...")
    client1.send_packet(packet)  # Send same packet again
    time.sleep(0.3)
    client2.receive_messages(timeout=1.0)
    
    final_count = len(client2.received_messages)
    
    if final_count == initial_count:
        print("✓ Duplicate packet correctly ignored")
        client1.disconnect()
        client2.disconnect()
        return True
    else:
        print(f"✗ Duplicate not detected (count: {initial_count} -> {final_count})")
        client1.disconnect()
        client2.disconnect()
        return False

def main():
    """Run all tests"""
    if len(sys.argv) < 2:
        print("Usage: python test_reliable_udp.py <host> [port]")
        print("Example: python test_reliable_udp.py 127.0.0.1 5001")
        sys.exit(1)
    
    host = sys.argv[1]
    port = int(sys.argv[2]) if len(sys.argv) > 2 else 5001
    
    print("\n" + "="*60)
    print("Reliable UDP Test Suite")
    print(f"Testing server at {host}:{port}")
    print("="*60)
    
    results = []
    
    # run tests
    results.append(("Basic Connection", test_basic_connection(host, port)))
    time.sleep(1)
    
    results.append(("Message Delivery", test_message_delivery(host, port)))
    time.sleep(1)
    
    results.append(("Retransmission", test_retransmission(host, port)))
    time.sleep(1)
    
    results.append(("Group Chat", test_group_chat(host, port)))
    time.sleep(1)
    
    results.append(("Multiple Clients", test_multiple_clients(host, port, 10)))
    time.sleep(1)
    
    results.append(("Duplicate Detection", test_duplicate_detection(host, port)))
    
    # print summary
    print("\n" + "="*60)
    print("TEST SUMMARY")
    print("="*60)
    
    passed = 0
    for test_name, result in results:
        status = "✓ PASS" if result else "✗ FAIL"
        print(f"{status}: {test_name}")
        if result:
            passed += 1
    
    print(f"\nTotal: {passed}/{len(results)} tests passed")
    print("="*60)

if __name__ == "__main__":
    main()

