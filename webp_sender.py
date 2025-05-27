#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebP Video Sender
WebP video transmission program optimized for UART serial communication
Supports both wired UART and wireless transmission modes
"""

import cv2
import numpy as np
import serial
import time
import struct
import threading
from collections import deque
import hashlib
import io
from PIL import Image
import socket
import select

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
SENDER_PORT = 'COM7'        # Sender port (modify according to actual situation)

# Wireless configuration (wireless mode)
WIRELESS_HOST = '127.0.0.1'  # Server IP (localhost for same computer testing)
WIRELESS_PORT = 8888         # Wireless port

# Camera configuration
CAMERA_INDEX = 0            # Camera index (usually 0)
FRAME_WIDTH = 320           # Frame width
FRAME_HEIGHT = 240          # Frame height

# Performance mode configuration (options: high_fps, balanced, high_quality, ultra_fast)
PERFORMANCE_MODE = "balanced"

# Advanced configuration (generally no need to modify)
PROTOCOL_MAGIC = b'WEBP'    # Protocol magic number
PACKET_TYPE = "WEBP"        # Packet type
# ================================================

class WirelessUARTController:
    """Wireless UART Controller - Intelligent UART transmission rate control"""
    
    def __init__(self, baud_rate):
        self.baud_rate = baud_rate
        self.bytes_per_second = baud_rate / 8  # Bytes per second
        self.last_send_time = time.time()
        self.bytes_sent_this_second = 0
        
        # Use more relaxed limits for high speeds
        if baud_rate > 500000:
            self.burst_allowance = 1.5  # Allow 150% burst transmission
            self.adaptive_window = 0.5   # 500ms window
        else:
            self.burst_allowance = 1.0   # Strict limit
            self.adaptive_window = 1.0   # 1 second window
        
    def calculate_delay(self, data_size):
        """Calculate transmission delay to control UART rate"""
        current_time = time.time()
        
        # Ultra-high speed mode: Significantly reduce restrictions
        if self.baud_rate >= 1000000:
            # 1MHz and above: Very relaxed limits, focus on maintaining average rate rather than strict limiting
            time_window = 0.1  # 100ms window
            burst_multiplier = 3.0  # Allow 3x burst
        elif self.baud_rate > 500000:
            time_window = self.adaptive_window
            burst_multiplier = self.burst_allowance
        else:
            time_window = 1.0
            burst_multiplier = 1.0
        
        # Reset counter if time window exceeded
        if current_time - self.last_send_time >= time_window:
            self.last_send_time = current_time
            self.bytes_sent_this_second = 0
        
        # Calculate allowed bytes in window
        allowed_bytes = (self.bytes_per_second * time_window * burst_multiplier)
        remaining_bytes = allowed_bytes - self.bytes_sent_this_second
        
        if data_size <= remaining_bytes:
            # Can send immediately
            self.bytes_sent_this_second += data_size
            return 0
        else:
            # Ultra-high speed mode: Minimal wait time
            if self.baud_rate >= 1000000:
                # Calculate minimal delay to ensure high-speed transmission is not blocked
                excess_bytes = data_size - remaining_bytes
                min_wait = excess_bytes / (self.bytes_per_second * 2)  # Half wait time
                return min(min_wait, 0.01)  # Wait at most 10ms
            elif self.baud_rate > 500000:
                excess_bytes = data_size - remaining_bytes
                min_wait = excess_bytes / self.bytes_per_second
                return min(min_wait, time_window - (current_time - self.last_send_time))
            else:
                # Standard wait time
                wait_time = time_window - (current_time - self.last_send_time)
                return max(0, wait_time)

class WebPSender:
    def __init__(self, performance_mode=PERFORMANCE_MODE, transmission_mode=None, baud_rate=None):
        self.running = False
        self.frame_counter = 0
        self.successful_frames = 0
        self.failed_frames = 0
        
        # Transmission related
        self.transmission_mode = transmission_mode or TRANSMISSION_MODE
        self.baud_rate = baud_rate or BAUD_RATE
        
        # Serial port (UART mode)
        self.ser_sender = None
        
        # Wireless (wireless mode)
        self.wireless_socket = None
        self.wireless_controller = None
        if self.transmission_mode == 'wireless':
            self.wireless_controller = WirelessUARTController(self.baud_rate)
        
        # Camera
        self.cap = None
        
        # Smart buffering
        self.frame_buffer = deque(maxlen=100)
        
        # Performance mode configuration
        self.performance_mode = performance_mode
        self.setup_performance_mode()
        
        # Error recovery
        self.last_successful_time = time.time()
        self.error_count = 0
        self.recovery_mode = False
        
        # Statistics
        self.stats = {
            'frames_sent': 0,
            'bytes_sent': 0,
            'errors': 0,
            'recoveries': 0,
            'compression_ratios': deque(maxlen=50),
            'packet_sizes': deque(maxlen=50),
            'fps_history': deque(maxlen=30)
        }
        
    def setup_performance_mode(self):
        """Set parameters according to performance mode"""
        modes = {
            "high_fps": {
                "quality": 30,
                "target_packet_size": 975,
                "webp_method": 4,  # Faster compression
                "fps_delay": 0.026,  # ~38fps
                "description": "High FPS priority (38fps)"
            },
            "balanced": {
                "quality": 50,
                "target_packet_size": 1261,
                "webp_method": 6,
                "fps_delay": 0.067,  # ~15fps
                "description": "Balanced settings (15fps)"
            },
            "high_quality": {
                "quality": 70,
                "target_packet_size": 1653,
                "webp_method": 6,
                "fps_delay": 0.088,  # ~11fps
                "description": "High quality priority (11fps)"
            },
            "ultra_fast": {
                "quality": 30,
                "target_packet_size": 975,
                "webp_method": 0,  # Fastest compression
                "fps_delay": 0.02,  # ~50fps
                "description": "Ultra fast mode (50fps)"
            }
        }
        
        if self.performance_mode not in modes:
            self.performance_mode = "balanced"
        
        config = modes[self.performance_mode]
        self.current_quality = config["quality"]
        self.target_packet_size = config["target_packet_size"]
        self.webp_method = config["webp_method"]
        self.current_fps_delay = config["fps_delay"]
        self.mode_description = config["description"]
        
        # 🚀 Wireless mode performance optimization
        if self.transmission_mode == 'wireless':
            # Adjust performance parameters based on wireless speed
            speed_multiplier = self.baud_rate / 300000  # Multiplier relative to UART baseline speed
            
            if speed_multiplier > 1.0:
                # Smart frame rate adjustment: Not overly aggressive, ensure stability
                if speed_multiplier >= 3.0:  # 1MHz and above
                    # High-speed wireless: Moderate improvement, avoid over-optimization
                    target_fps = min(30, 15 * min(speed_multiplier / 2, 2.0))
                    self.current_fps_delay = max(0.02, 1.0 / target_fps)
                else:
                    # Medium-speed wireless: Conservative improvement
                    self.current_fps_delay = max(0.03, self.current_fps_delay / speed_multiplier)
                
                # Improve quality and packet size limits
                self.current_quality = min(85, int(self.current_quality * min(speed_multiplier, 1.5)))
                self.target_packet_size = int(self.target_packet_size * min(speed_multiplier, 2.0))
                
                # Update description
                improved_fps = 1.0 / self.current_fps_delay
                self.mode_description = f"{config['description']} → Wireless optimized ({improved_fps:.0f}fps, Q{self.current_quality})"
                
                print(f"🌐 Wireless mode performance enhancement:")
                print(f"   Speed multiplier: {speed_multiplier:.1f}x")
                print(f"   FPS optimization: {1.0/config['fps_delay']:.0f} → {improved_fps:.0f} fps")
                print(f"   Quality optimization: Q{config['quality']} → Q{self.current_quality}")
                print(f"   Packet size limit: {config['target_packet_size']} → {self.target_packet_size}B")
                print(f"   Delay setting: {self.current_fps_delay*1000:.1f}ms")
        
        print(f"🎯 Performance mode: {self.mode_description}")
        print(f"   Quality: Q{self.current_quality}")
        print(f"   Target packet size: {self.target_packet_size}B")
        print(f"   Compression method: {self.webp_method}")
        print(f"🚀 Transmission mode: {self.transmission_mode.upper()}")
        if self.transmission_mode == 'wireless':
            print(f"   Wireless speed: {self.baud_rate/1000}K bps")
        else:
            print(f"   UART speed: {self.baud_rate} bps")
        
    def init_devices(self):
        """Initialize devices"""
        print("🚀 Initializing WebP video sender...")
        print("📊 Sender features:")
        print("- Performance configuration based on actual test data")
        print("- Grayscale images reduce data by 67%")
        print("- WebP compression ratio up to 104x")
        print("- Smart dynamic quality adjustment")
        print(f"- Supports {self.transmission_mode.upper()} transmission mode")
        
        # Initialize camera
        self.cap = cv2.VideoCapture(CAMERA_INDEX)
        if not self.cap.isOpened():
            print("❌ Camera initialization failed")
            return False
        
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
        self.cap.set(cv2.CAP_PROP_FPS, 30)
        print(f"✅ Camera initialization successful ({FRAME_WIDTH}x{FRAME_HEIGHT} grayscale)")
        
        # Initialize communication according to transmission mode
        if self.transmission_mode == 'uart':
            return self.init_uart()
        else:
            return self.init_wireless()
    
    def init_uart(self):
        """Initialize UART serial port"""
        try:
            self.ser_sender = serial.Serial(SENDER_PORT, self.baud_rate, timeout=0.5)
            
            # Clear buffers
            self.ser_sender.reset_input_buffer()
            self.ser_sender.reset_output_buffer()
            
            print(f"✅ Sender serial port initialization successful ({SENDER_PORT} @ {self.baud_rate}bps)")
            return True
        except Exception as e:
            print(f"❌ Sender serial port initialization failed: {e}")
            print(f"Please check if serial port {SENDER_PORT} is available")
            return False
    
    def init_wireless(self):
        """Initialize wireless connection"""
        try:
            # Create TCP server socket
            self.wireless_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.wireless_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.wireless_socket.bind((WIRELESS_HOST, WIRELESS_PORT))
            self.wireless_socket.listen(1)
            
            print(f"🌐 Wireless server started, waiting for connection...")
            print(f"   Address: {WIRELESS_HOST}:{WIRELESS_PORT}")
            print(f"   Speed: {self.baud_rate/1000}K bps")
            
            # Wait for client connection
            self.client_socket, client_address = self.wireless_socket.accept()
            print(f"✅ Client connected: {client_address}")
            
            return True
        except Exception as e:
            print(f"❌ Wireless initialization failed: {e}")
            return False
    
    def encode_frame_webp(self, frame):
        """Optimized WebP encoding"""
        try:
            # Convert to PIL Image
            pil_image = Image.fromarray(frame)
            
            # WebP compression (using optimized parameters)
            buffer = io.BytesIO()
            pil_image.save(
                buffer, 
                format='WebP', 
                quality=self.current_quality,
                method=self.webp_method,
                lossless=False,
                exact=False  # Allow quality adjustment for better compression
            )
            
            webp_data = buffer.getvalue()
            
            # Calculate compression ratio (for statistics only)
            if len(self.stats['compression_ratios']) % 10 == 0:  # Calculate every 10 frames
                original_size = frame.nbytes
                webp_size = len(webp_data)
                compression_ratio = original_size / webp_size
                self.stats['compression_ratios'].append(compression_ratio)
            
            self.stats['packet_sizes'].append(len(webp_data))
            
            return webp_data
            
        except Exception as e:
            print(f"❌ WebP encoding failed: {e}")
            return None
    
    def calculate_frame_hash(self, frame_data):
        """Calculate frame data hash for verification"""
        return hashlib.md5(frame_data).digest()[:4]
    
    def send_packet(self, packet_data, packet_type=PACKET_TYPE):
        """Send data packet"""
        try:
            # Protocol: Magic(4) + FrameID(4) + Length(4) + Type(8) + Hash(4) + Data
            magic = PROTOCOL_MAGIC
            frame_id = struct.pack('<I', self.frame_counter)
            length = struct.pack('<I', len(packet_data))
            type_bytes = packet_type.ljust(8)[:8].encode('ascii')
            packet_hash = self.calculate_frame_hash(packet_data)
            
            packet = magic + frame_id + length + type_bytes + packet_hash + packet_data
            
            # Send data according to transmission mode
            if self.transmission_mode == 'uart':
                # UART mode
                self.ser_sender.write(packet)
                self.ser_sender.flush()
            else:
                # Wireless mode - Control UART rate
                if self.wireless_controller:
                    delay = self.wireless_controller.calculate_delay(len(packet))
                    if delay > 0:
                        time.sleep(delay)
                
                # Send data
                self.client_socket.sendall(packet)
            
            self.stats['frames_sent'] += 1
            self.stats['bytes_sent'] += len(packet)
            
            return True
            
        except Exception as e:
            print(f"❌ Send failed: {e}")
            self.stats['errors'] += 1
            self.error_count += 1
            return False
    
    def adjust_quality_smart(self):
        """Smart quality adjustment"""
        if len(self.frame_buffer) >= 10:
            recent_frames = list(self.frame_buffer)[-10:]
            success_rate = sum(1 for f in recent_frames if f['success']) / len(recent_frames)
            avg_size = sum(f['size'] for f in recent_frames) / len(recent_frames)
            
            # Calculate actual frame rate
            if len(self.stats['fps_history']) >= 5:
                recent_fps = np.mean(list(self.stats['fps_history'])[-5:])
            else:
                recent_fps = 0
            
            # Get statistics
            avg_compression = np.mean(list(self.stats['compression_ratios'])) if self.stats['compression_ratios'] else 1.0
            avg_packet_size = np.mean(list(self.stats['packet_sizes'])) if self.stats['packet_sizes'] else 2000
            
            # 🌐 Wireless mode smart adjustment strategy
            if self.transmission_mode == 'wireless':
                # Wireless mode: More relaxed packet size limits, more aggressive optimization
                target_fps = 1.0 / self.current_fps_delay  # Target frame rate
                
                # Mainly adjust based on frame rate and success rate, packet size as secondary factor
                if success_rate < 0.9 or recent_fps < target_fps * 0.7:
                    # Insufficient performance, reduce quality
                    self.current_quality = max(25, self.current_quality - 2)
                    # Don't easily increase delay in wireless mode
                    if success_rate < 0.8:
                        self.current_fps_delay = min(self.current_fps_delay * 1.2, 0.1)
                    print(f"🌐 Wireless optimization - Reduce quality: Q{self.current_quality} (Target FPS:{target_fps:.0f}fps)")
                elif success_rate > 0.98 and recent_fps > target_fps * 0.9 and avg_packet_size < self.target_packet_size * 1.5:
                    # Good performance, can improve quality
                    max_quality = 85  # Wireless mode allows higher quality
                    self.current_quality = min(max_quality, self.current_quality + 1)
                    # Try to improve frame rate
                    self.current_fps_delay = max(0.01, self.current_fps_delay * 0.95)
                    print(f"🌐 Wireless optimization - Improve quality: Q{self.current_quality}")
            else:
                # UART mode: Original conservative adjustment strategy
                if success_rate < 0.8 or avg_packet_size > self.target_packet_size * 1.2:
                    # Reduce quality
                    self.current_quality = max(20, self.current_quality - 3)
                    self.current_fps_delay = min(0.2, self.current_fps_delay + 0.01)
                    print(f"📉 Reduce quality: Q{self.current_quality}")
                elif success_rate > 0.95 and avg_packet_size < self.target_packet_size * 0.8:
                    # Improve quality
                    max_quality = 80 if self.performance_mode == "high_quality" else 60
                    self.current_quality = min(max_quality, self.current_quality + 2)
                    self.current_fps_delay = max(0.02, self.current_fps_delay - 0.005)
                    print(f"📈 Improve quality: Q{self.current_quality}")
            
            print(f"📊 Send status: Q={self.current_quality}, Compression={avg_compression:.1f}x, "
                  f"Packet size={avg_packet_size:.0f}B, FPS={recent_fps:.1f}fps, "
                  f"Success rate={success_rate:.2%}")
    
    def sender_thread(self):
        """Sender thread"""
        print("🚀 WebP sender thread started")
        last_fps_time = time.time()
        frame_count_for_fps = 0
        
        while self.running:
            try:
                # Check error recovery
                if time.time() - self.last_successful_time > 2.0 or self.error_count > 5:
                    self.enter_recovery_mode()
                elif self.recovery_mode and self.error_count == 0:
                    self.exit_recovery_mode()
                
                # Capture frame
                ret, frame = self.cap.read()
                if not ret:
                    time.sleep(0.01)
                    continue
                
                # Preprocessing (convert to grayscale to reduce data)
                frame_resized = cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT))
                gray_frame = cv2.cvtColor(frame_resized, cv2.COLOR_BGR2GRAY)
                
                # WebP encoding
                encoded_data = self.encode_frame_webp(gray_frame)
                
                if encoded_data:
                    # Send
                    if self.send_packet(encoded_data):
                        self.frame_counter += 1
                        self.successful_frames += 1
                        frame_count_for_fps += 1
                        self.last_successful_time = time.time()
                        self.error_count = 0
                        
                        # Record statistics
                        self.frame_buffer.append({
                            'id': self.frame_counter,
                            'size': len(encoded_data),
                            'time': time.time(),
                            'success': True
                        })
                        
                        # Calculate frame rate
                        current_time = time.time()
                        if current_time - last_fps_time >= 1.0:
                            fps = frame_count_for_fps / (current_time - last_fps_time)
                            self.stats['fps_history'].append(fps)
                            last_fps_time = current_time
                            frame_count_for_fps = 0
                    else:
                        self.failed_frames += 1
                
                # Smart quality adjustment
                if self.frame_counter % 20 == 0:
                    self.adjust_quality_smart()
                
                time.sleep(self.current_fps_delay)
                
            except Exception as e:
                print(f"❌ Sender thread error: {e}")
                self.error_count += 1
                time.sleep(0.1)
    
    def enter_recovery_mode(self):
        """Enter recovery mode"""
        if not self.recovery_mode:
            self.recovery_mode = True
            self.stats['recoveries'] += 1
            print("🔄 Entering recovery mode...")
            
            try:
                if self.transmission_mode == 'uart' and self.ser_sender:
                    self.ser_sender.reset_input_buffer()
                    self.ser_sender.reset_output_buffer()
            except:
                pass
            
            # Reduce quality and frame rate
            self.current_quality = max(20, self.current_quality - 15)
            self.current_fps_delay = min(0.3, self.current_fps_delay + 0.05)
    
    def exit_recovery_mode(self):
        """Exit recovery mode"""
        if self.recovery_mode:
            self.recovery_mode = False
            print("✅ Exiting recovery mode")
    
    def start(self):
        """Start sender"""
        print("=== WebP Video Sender ===")
        print("🎯 Sender features:")
        print("- Performance configuration based on actual test data")
        print("- Grayscale images reduce data by 67%")
        print("- WebP compression ratio up to 104x")
        print("- Smart dynamic quality adjustment")
        print("- Real-time frame rate monitoring")
        print()
        if self.transmission_mode == 'uart':
            print(f"📡 UART configuration: {SENDER_PORT} @ {self.baud_rate}bps")
        else:
            print(f"🌐 Wireless configuration: {WIRELESS_HOST}:{WIRELESS_PORT} @ {self.baud_rate/1000}K bps")
        print(f"📹 Camera configuration: Index{CAMERA_INDEX}, {FRAME_WIDTH}x{FRAME_HEIGHT}")
        print()
        
        if not self.init_devices():
            return
        
        self.running = True
        self.last_successful_time = time.time()
        
        # Start sender thread
        sender = threading.Thread(target=self.sender_thread, daemon=True)
        sender.start()
        
        print("✅ Sender thread started")
        print("📡 Starting WebP video stream transmission...")
        print("Press Ctrl+C to exit")
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
        success_rate = self.successful_frames / max(1, self.successful_frames + self.failed_frames)
        avg_compression = np.mean(list(self.stats['compression_ratios'])) if self.stats['compression_ratios'] else 1.0
        avg_packet_size = np.mean(list(self.stats['packet_sizes'])) if self.stats['packet_sizes'] else 0
        current_fps = np.mean(list(self.stats['fps_history'])[-5:]) if len(self.stats['fps_history']) >= 5 else 0
        
        print(f"📊 Send statistics - Mode:{self.performance_mode} Q:{self.current_quality} "
              f"Compression:{avg_compression:.1f}x FPS:{current_fps:.1f}fps "
              f"Packet size:{avg_packet_size:.0f}B Sent:{self.stats['frames_sent']} "
              f"Success rate:{success_rate:.1%} Status:{'Recovery' if self.recovery_mode else 'Normal'}")
    
    def stop(self):
        """Stop sender"""
        print("🛑 Stopping WebP video sender...")
        self.running = False
        
        if self.cap:
            self.cap.release()
        
        # Clean up connection according to transmission mode
        if self.transmission_mode == 'uart':
            if self.ser_sender:
                self.ser_sender.close()
        else:
            try:
                if hasattr(self, 'client_socket'):
                    self.client_socket.close()
                if self.wireless_socket:
                    self.wireless_socket.close()
            except:
                pass
        
        print("✅ Sender stopped")

def main():
    """Main function"""
    import sys
    
    # Get transmission mode
    transmission_mode, baud_rate = select_transmission_mode()
    
    # Support command line parameter selection of performance mode
    performance_modes = ["high_fps", "balanced", "high_quality", "ultra_fast"]
    
    if len(sys.argv) > 1 and sys.argv[1] in performance_modes:
        mode = sys.argv[1]
    else:
        mode = PERFORMANCE_MODE  # Use configured default mode
    
    print(f"Startup mode: {mode}")
    print("Available modes: high_fps, balanced, high_quality, ultra_fast")
    print("Usage: python webp_sender.py [mode]")
    print()
    
    sender = WebPSender(performance_mode=mode, transmission_mode=transmission_mode, baud_rate=baud_rate)
    sender.start()

if __name__ == "__main__":
    main() 