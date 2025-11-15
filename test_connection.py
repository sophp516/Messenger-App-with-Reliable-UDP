#!/usr/bin/env python3
"""
Quick test script to verify host and client can communicate
"""
import socket
import struct
import time
import sys

PORT = 5000
HOST = "127.0.0.1"

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

# Test connection
print("Testing connection to server...")
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.settimeout(3.0)

# Send SYN
syn_packet = create_packet(0x04, 0, "testuser", "SERVER")  # 0x04 = SYN
sock.sendto(syn_packet, (HOST, PORT))
print(f"Sent SYN to {HOST}:{PORT}")

# Wait for SYN-ACK
try:
    data, addr = sock.recvfrom(4096)
    print(f"Received response from {addr}")
    print("✓ Server is responding!")
    print("\nYou can now run clients in separate terminals:")
    print("  Terminal 1: python host.py")
    print("  Terminal 2: python client.py alice")
    print("  Terminal 3: python client.py bob")
except socket.timeout:
    print("✗ No response from server. Is host.py running?")
    sys.exit(1)
finally:
    sock.close()

