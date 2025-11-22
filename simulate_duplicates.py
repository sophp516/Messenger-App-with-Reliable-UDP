#!/usr/bin/env python3
"""
Script to simulate duplicate UDP messages for testing duplicate detection.

This demonstrates how to manually create duplicate packets to test
the duplicate detection logic in the client.
"""

import socket
import time
import struct
from data import MsgType

HOST = "127.0.0.1"
PORT = 5001

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

def simulate_duplicates():
    """Send the same packet multiple times to simulate duplicates"""
    print("Simulating duplicate UDP messages...")
    print("=" * 60)
    
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    
    # Create a test packet
    seq_num = 12345
    sender = "test_sender"
    recipient = "test_recipient"
    message = "This is a test message that will be duplicated"
    payload = message.encode('utf-8')
    
    packet = create_packet(MsgType.DATA, seq_num, sender, recipient, payload)
    
    print(f"Created packet with sequence number: {seq_num}")
    print(f"Message: {message}")
    print(f"\nSending packet 5 times to simulate duplicates...")
    
    # Send the same packet multiple times
    for i in range(5):
        sock.sendto(packet, (HOST, PORT))
        print(f"  Sent duplicate #{i+1}")
        time.sleep(0.1)  # Small delay between sends
    
    print("\n" + "=" * 60)
    print("All duplicates sent!")
    print("If a client is listening, it should:")
    print("  1. Process the first packet")
    print("  2. Detect duplicates for packets 2-5")
    print("  3. Still send ACKs for duplicates (to prevent retransmission)")
    
    sock.close()

if __name__ == "__main__":
    simulate_duplicates()

