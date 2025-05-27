#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebP Video Receiver
WebP video reception program optimized for UART serial communication
Supports both wired UART and wireless transmission modes
"""

import cv2
import numpy as np
import serial
import time
import struct
import threading
import queue
from collections import deque
import hashlib
import io
from PIL import Image
import socket

# ==================== Transmission Mode Selection ====================
def select_transmission_mode():
    """Select transmission mode"""
    print("🔧 Please select transmission mode:")
    print("1. Wired UART (300,000 bps)")
    print("2. Wireless transmission (UART rate)")
    
    while True:
        choice = input("Please enter choice (1 or 2): ").strip()
        if choice == '1':
            return 'uart', 400000
        elif choice == '2':
            return select_wireless_speed()
        else:
            print("❌ Invalid choice, please enter 1 or 2")

def select_wireless_speed():
    """Select wireless speed"""
    print("\n🌐 Please select wireless speed:")
    print("1. 1MHz (Standard) - Balanced performance")
    print("2. 2MHz (High speed) - Enhanced FPS and quality")
    print("3. 5MHz (Ultra speed) - Maximum performance")
    print("4. Custom speed")
    
    speed_options = {
        '1': 1000000,   # 1MHz
        '2': 2000000,   # 2MHz
        '3': 5000000,   # 5MHz
    }
    
    while True:
        choice = input("Please enter choice (1-4): ").strip()
        if choice in speed_options:
            speed = speed_options[choice]
            print(f"✅ Selected speed: {speed/1000:.0f}K bps")
            return 'wireless', speed
        elif choice == '4':
            try:
                custom_speed = int(input("Please enter custom speed (bps, e.g. 3000000): "))
                if custom_speed < 100000:
                    print("❌ Speed too low, minimum is 100,000 bps")
                    continue
                elif custom_speed > 10000000:
                    print("❌ Speed too high, maximum is 10,000,000 bps")
                    continue
                print(f"✅ Custom speed: {custom_speed/1000:.0f}K bps")
                return 'wireless', custom_speed
            except ValueError:
                print("❌ Please enter a valid number")
        else:
            print("❌ Invalid choice, please enter 1-4")

# Default configuration (will be selected in main function)
TRANSMISSION_MODE = 'uart'
BAUD_RATE = 300000

# ==================== Configuration Parameters ====================
# Serial port configuration (UART mode)
RECEIVER_PORT = 'COM8'      # Receiver port (modify according to actual situation)

# Wireless configuration (wireless mode)
WIRELESS_HOST = '127.0.0.1'  # Server IP (localhost for same computer testing)
WIRELESS_PORT = 8888         # Wireless port

# Display configuration
WINDOW_NAME = 'WebP Video Receiver'  # Display window name
SHOW_STATS = True           # Whether to show statistics
AUTO_RESIZE = True          # Whether to auto-resize window

# Buffer configuration
FRAME_BUFFER_SIZE = 3       # Frame buffer size
STATS_BUFFER_SIZE = 50      # Statistics buffer size

# Advanced configuration (generally no need to modify)
PROTOCOL_MAGIC = b'WEBP'    # Protocol magic number (must match sender)
PACKET_TYPE = "WEBP"        # Packet type
RECEIVE_TIMEOUT = 0.05      # Receive timeout
# ================================================

class WebPReceiver:
    def __init__(self, transmission_mode=None, baud_rate=None):
        self.running = False
        
        # Transmission related
        self.transmission_mode = transmission_mode or TRANSMISSION_MODE
        self.baud_rate = baud_rate or BAUD_RATE
        
        # Serial port (UART mode)
        self.ser_receiver = None
        
        # Wireless (wireless mode)
        self.wireless_socket = None
        
        # Smart buffering
        self.received_frames = queue.Queue(maxsize=FRAME_BUFFER_SIZE)
        
        # Error recovery
        self.last_successful_time = time.time()
        self.error_count = 0
        
        # Statistics
        self.stats = {
            'frames_received': 0,
            'frames_displayed': 0,
            'bytes_received': 0,
            'errors': 0,
            'compression_ratios': deque(maxlen=STATS_BUFFER_SIZE),
            'packet_sizes': deque(maxlen=STATS_BUFFER_SIZE),
            'fps_history': deque(maxlen=30)
        }
        
    def init_devices(self):
        """Initialize devices"""
        print("🚀 Initializing WebP video receiver...")
        print("📊 Receiver features:")
        print("- WebP decoding and display")
        print("- Smart buffering to prevent frame loss")
        print("- Real-time statistics monitoring")
        print("- Automatic error recovery")
        print(f"- Supports {self.transmission_mode.upper()} transmission mode")
        
        # Initialize communication according to transmission mode
        if self.transmission_mode == 'uart':
            return self.init_uart()
        else:
            return self.init_wireless()
    
    def init_uart(self):
        """Initialize UART serial port"""
        try:
            self.ser_receiver = serial.Serial(RECEIVER_PORT, self.baud_rate, timeout=RECEIVE_TIMEOUT)
            
            # Clear buffers
            self.ser_receiver.reset_input_buffer()
            self.ser_receiver.reset_output_buffer()
            
            print(f"✅ Receiver serial port initialization successful ({RECEIVER_PORT} @ {self.baud_rate}bps)")
            return True
        except Exception as e:
            print(f"❌ Receiver serial port initialization failed: {e}")
            print(f"Please check if serial port {RECEIVER_PORT} is available")
            return False
    
    def init_wireless(self):
        """Initialize wireless connection"""
        try:
            # Create TCP client socket
            self.wireless_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            
            print(f"🌐 Connecting to wireless sender...")
            print(f"   Address: {WIRELESS_HOST}:{WIRELESS_PORT}")
            print(f"   Speed: {self.baud_rate/1000}K bps")
            
            # Connect to server
            self.wireless_socket.connect((WIRELESS_HOST, WIRELESS_PORT))
            print(f"✅ Connected to sender: {WIRELESS_HOST}:{WIRELESS_PORT}")
            
            # Set receive timeout
            self.wireless_socket.settimeout(RECEIVE_TIMEOUT)
            
            return True
        except Exception as e:
            print(f"❌ Wireless connection failed: {e}")
            return False
    
    def decode_frame_webp(self, webp_data):
        """WebP frame decoding"""
        try:
            # Use PIL to decode WebP
            pil_image = Image.open(io.BytesIO(webp_data))
            frame = np.array(pil_image)
            
            # Ensure grayscale image
            if len(frame.shape) == 3:
                frame = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
            
            return frame
            
        except Exception as e:
            print(f"❌ WebP decoding failed: {e}")
            return None
    
    def calculate_frame_hash(self, frame_data):
        """Calculate frame data hash for verification"""
        return hashlib.md5(frame_data).digest()[:4]
    
    def receive_packet(self):
        """Receive data packet"""
        try:
            # Select receiving method according to transmission mode
            if self.transmission_mode == 'uart':
                return self.receive_packet_uart()
            else:
                return self.receive_packet_wireless()
        except Exception as e:
            print(f"❌ Receive failed: {e}")
            self.stats['errors'] += 1
            self.error_count += 1
            return None, None
    
    def receive_packet_uart(self):
        """UART method to receive data packet"""
        # Find magic number
        buffer = bytearray()
        magic_found = False
        
        start_time = time.time()
        while not magic_found and (time.time() - start_time) < 0.1:
            byte = self.ser_receiver.read(1)
            if not byte:
                break
                
            buffer.extend(byte)
            
            if len(buffer) >= 4:
                magic_pos = buffer.find(PROTOCOL_MAGIC)
                if magic_pos != -1:
                    buffer = buffer[magic_pos:]
                    magic_found = True
        
        if not magic_found:
            return None, None
        
        # Ensure complete header (4+4+4+8+4=24)
        while len(buffer) < 24:
            byte = self.ser_receiver.read(1)
            if not byte:
                return None, None
            buffer.extend(byte)
        
        # Parse header
        frame_id = struct.unpack('<I', buffer[4:8])[0]
        packet_length = struct.unpack('<I', buffer[8:12])[0]
        packet_type = buffer[12:20].decode('ascii').strip()
        expected_hash = buffer[20:24]
        
        # Verify packet length
        if packet_length > 10000 or packet_length < 50:
            print(f"⚠️  Abnormal packet length: {packet_length}")
            return None, None
        
        # Read remaining data
        remaining = packet_length - (len(buffer) - 24)
        while remaining > 0:
            chunk = self.ser_receiver.read(min(remaining, 1024))
            if not chunk:
                print(f"⚠️  Incomplete data: need {remaining} more bytes")
                return None, None
            buffer.extend(chunk)
            remaining -= len(chunk)
        
        # Extract packet data
        packet_data = bytes(buffer[24:24+packet_length])
        
        # Verify hash
        actual_hash = self.calculate_frame_hash(packet_data)
        if actual_hash != expected_hash:
            print(f"⚠️  Packet {frame_id} hash verification failed")
            self.stats['errors'] += 1
            return None, None
        
        self.stats['frames_received'] += 1
        self.stats['bytes_received'] += len(packet_data)
        self.stats['packet_sizes'].append(len(packet_data))
        self.last_successful_time = time.time()
        self.error_count = 0
        
        return packet_data, packet_type
    
    def receive_packet_wireless(self):
        """Wireless method to receive data packet"""
        # Find magic number
        buffer = bytearray()
        magic_found = False
        
        start_time = time.time()
        while not magic_found and (time.time() - start_time) < 0.1:
            try:
                byte = self.wireless_socket.recv(1)
                if not byte:
                    break
                    
                buffer.extend(byte)
                
                if len(buffer) >= 4:
                    magic_pos = buffer.find(PROTOCOL_MAGIC)
                    if magic_pos != -1:
                        buffer = buffer[magic_pos:]
                        magic_found = True
            except socket.timeout:
                break
            except Exception:
                break
        
        if not magic_found:
            return None, None
        
        # Ensure complete header (4+4+4+8+4=24)
        while len(buffer) < 24:
            try:
                byte = self.wireless_socket.recv(1)
                if not byte:
                    return None, None
                buffer.extend(byte)
            except Exception:
                return None, None
        
        # Parse header
        frame_id = struct.unpack('<I', buffer[4:8])[0]
        packet_length = struct.unpack('<I', buffer[8:12])[0]
        packet_type = buffer[12:20].decode('ascii').strip()
        expected_hash = buffer[20:24]
        
        # Verify packet length
        if packet_length > 10000 or packet_length < 50:
            print(f"⚠️  Abnormal packet length: {packet_length}")
            return None, None
        
        # Read remaining data
        remaining = packet_length - (len(buffer) - 24)
        while remaining > 0:
            try:
                chunk = self.wireless_socket.recv(min(remaining, 1024))
                if not chunk:
                    print(f"⚠️  Incomplete data: need {remaining} more bytes")
                    return None, None
                buffer.extend(chunk)
                remaining -= len(chunk)
            except Exception:
                print(f"⚠️  Wireless receive interrupted: need {remaining} more bytes")
                return None, None
        
        # Extract packet data
        packet_data = bytes(buffer[24:24+packet_length])
        
        # Verify hash
        actual_hash = self.calculate_frame_hash(packet_data)
        if actual_hash != expected_hash:
            print(f"⚠️  Packet {frame_id} hash verification failed")
            self.stats['errors'] += 1
            return None, None
        
        self.stats['frames_received'] += 1
        self.stats['bytes_received'] += len(packet_data)
        self.stats['packet_sizes'].append(len(packet_data))
        self.last_successful_time = time.time()
        self.error_count = 0
        
        return packet_data, packet_type
    
    def receiver_thread(self):
        """Receiver thread"""
        print("🚀 WebP receiver thread started")
        
        while self.running:
            try:
                packet_data, packet_type = self.receive_packet()
                if packet_data and packet_type == PACKET_TYPE:
                    # WebP decoding
                    frame = self.decode_frame_webp(packet_data)
                    if frame is not None:
                        # Calculate compression ratio
                        original_size = frame.nbytes
                        compressed_size = len(packet_data)
                        compression_ratio = original_size / compressed_size
                        self.stats['compression_ratios'].append(compression_ratio)
                        
                        # Non-blocking put into queue
                        try:
                            self.received_frames.put_nowait(frame)
                        except queue.Full:
                            try:
                                self.received_frames.get_nowait()
                                self.received_frames.put_nowait(frame)
                            except queue.Empty:
                                pass
                else:
                    time.sleep(0.001)
                    
            except Exception as e:
                print(f"❌ Receiver thread error: {e}")
                time.sleep(0.01)
    
    def display_thread(self):
        """Display thread"""
        print("🚀 WebP display thread started")
        
        try:
            if AUTO_RESIZE:
                cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_AUTOSIZE)
            else:
                cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
            
            print(f"✅ OpenCV window created successfully: {WINDOW_NAME}")
        except Exception as e:
            print(f"❌ OpenCV window creation failed: {e}")
            return
        
        last_fps_time = time.time()
        frame_count_for_fps = 0
        
        while self.running:
            try:
                frame = self.received_frames.get(timeout=0.5)
                
                if frame is not None:
                    # Convert to color for displaying information
                    frame_bgr = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
                    
                    # Add status information
                    if SHOW_STATS:
                        self.add_status_overlay(frame_bgr)
                    
                    # Display
                    cv2.imshow(WINDOW_NAME, frame_bgr)
                    self.stats['frames_displayed'] += 1
                    frame_count_for_fps += 1
                    
                    # Calculate display frame rate
                    current_time = time.time()
                    if current_time - last_fps_time >= 1.0:
                        fps = frame_count_for_fps / (current_time - last_fps_time)
                        self.stats['fps_history'].append(fps)
                        last_fps_time = current_time
                        frame_count_for_fps = 0
                    
                    if cv2.waitKey(1) & 0xFF == ord('q'):
                        self.running = False
                        break
                
            except queue.Empty:
                self.show_no_signal()
                continue
            except Exception as e:
                print(f"❌ Display thread error: {e}")
                time.sleep(0.1)
        
        cv2.destroyAllWindows()
    
    def add_status_overlay(self, frame):
        """Add status information overlay"""
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.4
        thickness = 1
        
        avg_compression = np.mean(list(self.stats['compression_ratios'])) if self.stats['compression_ratios'] else 1.0
        avg_packet_size = np.mean(list(self.stats['packet_sizes'])) if self.stats['packet_sizes'] else 0
        current_fps = np.mean(list(self.stats['fps_history'])[-3:]) if len(self.stats['fps_history']) >= 3 else 0
        
        info_lines = [
            f"Receiver: WebP",
            f"Compression: {avg_compression:.1f}x",
            f"FPS: {current_fps:.1f}",
            f"Packet: {avg_packet_size:.0f}B",
            f"Received: {self.stats['frames_received']}",
            f"Displayed: {self.stats['frames_displayed']}",
            f"Errors: {self.stats['errors']}"
        ]
        
        color = (0, 255, 0)  # Green
        
        for i, line in enumerate(info_lines):
            y = 15 + i * 15
            cv2.putText(frame, line, (5, y), font, font_scale, color, thickness)
    
    def show_no_signal(self):
        """Show no signal status"""
        no_signal = np.zeros((240, 320, 3), dtype=np.uint8)
        cv2.putText(no_signal, "NO SIGNAL", (80, 120), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
        
        if self.transmission_mode == 'uart':
            wait_text = "Waiting for UART"
        else:
            wait_text = "Waiting for Wireless"
            
        cv2.putText(no_signal, wait_text, (70, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        cv2.imshow(WINDOW_NAME, no_signal)
        cv2.waitKey(100)
    
    def start(self):
        """Start receiver"""
        print("=== WebP Video Receiver ===")
        print("🎯 Receiver features:")
        print("- WebP decoding and display")
        print("- Smart buffering to prevent frame loss")
        print("- Real-time statistics monitoring")
        print("- Automatic error recovery")
        print()
        if self.transmission_mode == 'uart':
            print(f"📡 Serial port configuration: {RECEIVER_PORT} @ {self.baud_rate}bps")
        else:
            print(f"🌐 Wireless configuration: {WIRELESS_HOST}:{WIRELESS_PORT} @ {self.baud_rate/1000}K bps")
        print(f"📺 Display configuration: {WINDOW_NAME}")
        print()
        
        if not self.init_devices():
            return
        
        self.running = True
        self.last_successful_time = time.time()
        
        # Start threads
        receiver = threading.Thread(target=self.receiver_thread, daemon=True)
        display = threading.Thread(target=self.display_thread, daemon=True)
        
        receiver.start()
        display.start()
        
        print("✅ All threads started")
        print("📺 WebP video window should be open")
        print("Press 'q' key or Ctrl+C to exit")
        print()
        
        try:
            while self.running:
                time.sleep(5)
                self.print_stats()
        except KeyboardInterrupt:
            print("\nReceived stop signal...")
        
        self.stop()
    
    def print_stats(self):
        """Print statistics"""
        avg_compression = np.mean(list(self.stats['compression_ratios'])) if self.stats['compression_ratios'] else 1.0
        avg_packet_size = np.mean(list(self.stats['packet_sizes'])) if self.stats['packet_sizes'] else 0
        current_fps = np.mean(list(self.stats['fps_history'])[-5:]) if len(self.stats['fps_history']) >= 5 else 0
        
        print(f"📊 Receive statistics - Compression:{avg_compression:.1f}x FPS:{current_fps:.1f}fps "
              f"Packet size:{avg_packet_size:.0f}B Received:{self.stats['frames_received']} "
              f"Displayed:{self.stats['frames_displayed']} Errors:{self.stats['errors']}")
    
    def stop(self):
        """Stop receiver"""
        print("🛑 Stopping WebP video receiver...")
        self.running = False
        
        # Clean up connection according to transmission mode
        if self.transmission_mode == 'uart':
            if self.ser_receiver:
                self.ser_receiver.close()
        else:
            if self.wireless_socket:
                try:
                    self.wireless_socket.close()
                except:
                    pass
        
        cv2.destroyAllWindows()
        print("✅ Receiver stopped")

def main():
    """Main function"""
    # Get transmission mode
    transmission_mode, baud_rate = select_transmission_mode()
    
    print("Starting WebP video receiver")
    print("Usage: python webp_receiver.py")
    print()
    
    receiver = WebPReceiver(transmission_mode=transmission_mode, baud_rate=baud_rate)
    receiver.start()

if __name__ == "__main__":
    main() 