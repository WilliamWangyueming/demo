#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebP Video Sender
WebP video transmission program optimized for UART serial communication
Supports both wired UART, wireless transmission, and hybrid modes
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
    print("1. Wired UART (400,000 bps)")
    print("2. Wireless transmission (UART rate)")
    print("3. Hybrid mode (Wireless video + UART handshaking)")
    
    while True:
        choice = input("Please enter choice (1, 2, or 3): ").strip()
        if choice == '1':
            return 'uart', 400000
        elif choice == '2':
            return select_wireless_speed()
        elif choice == '3':
            return 'hybrid', 400000
        else:
            print("❌ Invalid choice, please enter 1, 2, or 3")

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
PROTOCOL_MAGIC = b'WP'      # 缩短魔术字节为2字节
PACKET_TYPE = "WEBP"        # Packet type

# 优化协议设置
USE_SIMPLIFIED_PROTOCOL = True  # 使用简化协议以减少开销
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
        
        # Hybrid mode
        self.handshake_thread = None
        self.handshake_running = False
        self.handshake_counter = 0
        self.handshake_interval = 0.05  # 设置为50ms，提供适中的频率
        self.handshake_buffer = bytearray()  # 用于存储预生成的握手包
        
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
            'fps_history': deque(maxlen=30),
            'handshakes_sent': 0
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
        elif self.transmission_mode == 'wireless':
            return self.init_wireless()
        else:  # hybrid mode
            uart_success = self.init_uart()
            wireless_success = self.init_wireless()
            return uart_success and wireless_success
    
    def init_uart(self):
        """Initialize UART serial port"""
        try:
            # Optimize UART settings for higher performance
            self.ser_sender = serial.Serial(
                SENDER_PORT, 
                self.baud_rate, 
                timeout=0.5,
                write_timeout=1.0,
                # Disable software flow control for better throughput
                xonxoff=False,
                # Enable hardware flow control if your hardware supports it
                rtscts=False,
                dsrdtr=False
            )
            
            # Clear buffers
            self.ser_sender.reset_input_buffer()
            self.ser_sender.reset_output_buffer()
            
            print(f"✅ Sender serial port initialization successful ({SENDER_PORT} @ {self.baud_rate}bps)")
            
            # Apply UART speed optimizations
            self._apply_uart_speed_optimizations()
            
            # 如果是hybrid模式，预生成一些握手包
            if self.transmission_mode == 'hybrid':
                self._prepare_handshake_packets()
            
            return True
        except Exception as e:
            print(f"❌ Sender serial port initialization failed: {e}")
            print(f"Please check if serial port {SENDER_PORT} is available")
            return False
    
    def _apply_uart_speed_optimizations(self):
        """Apply optimizations based on UART speed"""
        if self.transmission_mode != 'uart':
            return
            
        # Calculate speed multiplier relative to baseline 300K
        speed_multiplier = self.baud_rate / 300000
        
        if speed_multiplier > 1.0:
            print(f"🚀 UART speed optimization: {speed_multiplier:.1f}x multiplier detected")
            
            # Adjust frame rate based on speed
            if speed_multiplier >= 1.3:  # 400K+
                # 提高帧率，降低延迟
                target_fps = min(30, 15 * min(speed_multiplier, 2.0))
                self.current_fps_delay = max(0.02, 1.0 / target_fps)
                
                # 降低初始质量以减小包大小
                self.current_quality = min(60, int(self.current_quality * min(speed_multiplier, 1.2)))
                
                # 设置更合理的目标包大小
                self.target_packet_size = int(1500 * min(speed_multiplier, 1.5))
                
                # Update description
                improved_fps = 1.0 / self.current_fps_delay
                base_description = self.mode_description
                self.mode_description = f"{base_description} → UART optimized ({improved_fps:.0f}fps, Q{self.current_quality})"
                
                print(f"   FPS optimization: {15:.0f} → {improved_fps:.0f} fps")
                print(f"   Quality optimization: Q{50} → Q{self.current_quality}")
                print(f"   Packet size limit: {1261} → {self.target_packet_size}B")
                print(f"   Delay setting: {self.current_fps_delay*1000:.1f}ms")
    
    def _prepare_handshake_packets(self):
        """预生成握手包，提高发送效率"""
        if self.transmission_mode != 'hybrid':
            return
            
        print("🤝 Preparing handshake packets...")
        
        # 预生成10个握手包
        for i in range(10):
            if USE_SIMPLIFIED_PROTOCOL:
                magic = PROTOCOL_MAGIC
                hs_marker = b'HS'
                counter = struct.pack('<H', i % 65536)
                packet = magic + hs_marker + counter
            else:
                magic = PROTOCOL_MAGIC
                handshake_id = struct.pack('<I', i)
                timestamp = struct.pack('<I', int(time.time() * 1000) % 1000000)
                type_bytes = "HNDSHK".ljust(8)[:8].encode('ascii')
                payload = f"HANDSHAKE-{i}".encode('ascii')
                length = struct.pack('<I', len(payload))
                packet_hash = self.calculate_frame_hash(payload)
                packet = magic + handshake_id + length + type_bytes + packet_hash + payload
                
            self.handshake_buffer += packet
        
        print(f"✅ Prepared {len(self.handshake_buffer)} bytes of handshake data")
    
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
        if USE_SIMPLIFIED_PROTOCOL:
            # 使用简单的校验和代替MD5哈希，减少计算开销
            checksum = 0
            # 每1024字节采样一次以加快计算速度
            for i in range(0, len(frame_data), 1024):
                chunk = frame_data[i:i+1024]
                checksum = (checksum + sum(chunk)) & 0xFFFFFFFF
            return struct.pack('<I', checksum)
        else:
            # 原始MD5哈希方法
            return hashlib.md5(frame_data).digest()[:4]
    
    def send_packet(self, packet_data, packet_type=PACKET_TYPE):
        """Send data packet"""
        try:
            if USE_SIMPLIFIED_PROTOCOL:
                # 简化的协议头: Magic(2) + Length(2) + Hash(4) + Data
                # 总共减少了10字节的头部开销
                magic = PROTOCOL_MAGIC
                # 使用2字节表示长度，最大支持65535字节
                length = struct.pack('<H', len(packet_data))
                packet_hash = self.calculate_frame_hash(packet_data)
                
                # 组装简化的数据包
                packet = magic + length + packet_hash + packet_data
            else:
                # 原始协议: Magic(4) + FrameID(4) + Length(4) + Type(8) + Hash(4) + Data
                magic = PROTOCOL_MAGIC
                frame_id = struct.pack('<I', self.frame_counter)
                length = struct.pack('<I', len(packet_data))
                type_bytes = packet_type.ljust(8)[:8].encode('ascii')
                packet_hash = self.calculate_frame_hash(packet_data)
                
                # 组装完整的数据包
                packet = magic + frame_id + length + type_bytes + packet_hash + packet_data
            
            # Send data according to transmission mode
            if self.transmission_mode == 'uart':
                # UART mode - Send entire packet at once instead of byte by byte
                # This is crucial for reducing TX blinking and improving efficiency
                bytes_written = self.ser_sender.write(packet)
                
                # Only flush after complete packet
                self.ser_sender.flush()
                
                if bytes_written != len(packet):
                    print(f"⚠️ Incomplete send: {bytes_written}/{len(packet)} bytes")
                    return False
            elif self.transmission_mode == 'wireless':
                # Wireless mode - Control UART rate
                if self.wireless_controller:
                    delay = self.wireless_controller.calculate_delay(len(packet))
                    if delay > 0:
                        time.sleep(delay)
                
                # Send data
                self.client_socket.sendall(packet)
            else:  # hybrid mode - send video data over wireless
                # Control UART rate for wireless
                if self.wireless_controller:
                    delay = self.wireless_controller.calculate_delay(len(packet))
                    if delay > 0:
                        time.sleep(delay)
                
                # Send data over wireless
                self.client_socket.sendall(packet)
            
            self.stats['frames_sent'] += 1
            self.stats['bytes_sent'] += len(packet)
            
            return True
            
        except Exception as e:
            print(f"❌ Send failed: {e}")
            self.stats['errors'] += 1
            self.error_count += 1
            return False
    
    def send_handshake_packet(self):
        """Send handshake packet over UART in hybrid mode"""
        try:
            # 使用预生成的握手包或生成新的
            if len(self.handshake_buffer) > 0 and self.handshake_counter % 10 < 5:
                # 使用预生成的握手包，每10次使用5次
                packet_index = self.handshake_counter % 10
                if USE_SIMPLIFIED_PROTOCOL:
                    packet_size = 6  # Magic(2) + 'HS'(2) + Counter(2)
                else:
                    # 计算原始协议的包大小
                    packet_size = 24 + len(f"HANDSHAKE-{packet_index}".encode('ascii'))
                
                packet = self.handshake_buffer[packet_index * packet_size:(packet_index + 1) * packet_size]
            else:
                # 生成新的握手包
                if USE_SIMPLIFIED_PROTOCOL:
                    # 简化协议: Magic(2) + 'HS'(2) + Counter(2)
                    magic = PROTOCOL_MAGIC
                    hs_marker = b'HS'
                    counter = struct.pack('<H', self.handshake_counter % 65536)
                    packet = magic + hs_marker + counter
                else:
                    # 原始握手包格式
                    magic = PROTOCOL_MAGIC
                    handshake_id = struct.pack('<I', self.handshake_counter)
                    timestamp = struct.pack('<I', int(time.time() * 1000) % 1000000)
                    type_bytes = "HNDSHK".ljust(8)[:8].encode('ascii')
                    
                    # Simple payload with counter
                    payload = f"HANDSHAKE-{self.handshake_counter}".encode('ascii')
                    length = struct.pack('<I', len(payload))
                    packet_hash = self.calculate_frame_hash(payload)
                    
                    packet = magic + handshake_id + length + type_bytes + packet_hash + payload
            
            # 发送前确保串口可用
            if self.ser_sender and self.ser_sender.is_open:
                # 使用写入优先级
                self.ser_sender.write(packet)
                self.ser_sender.flush()
                
                self.handshake_counter += 1
                self.stats['handshakes_sent'] += 1
                return True
            return False
        except Exception as e:
            print(f"❌ Handshake send failed: {e}")
            return False
    
    def handshake_thread_func(self):
        """Thread function for sending handshake packets at regular intervals in hybrid mode"""
        print(f"🤝 Starting handshake thread with {self.handshake_interval*1000:.1f}ms interval")
        
        # 使用更稳定的计时方法
        next_time = time.time()
        
        # 错误计数和恢复机制
        error_count = 0
        last_success_time = time.time()
        
        # 动态调整发送间隔
        dynamic_interval = self.handshake_interval
        min_interval = 0.03  # 最小30ms
        max_interval = 0.1   # 最大100ms
        
        while self.handshake_running:
            try:
                current_time = time.time()
                if current_time >= next_time:
                    if self.send_handshake_packet():
                        error_count = 0
                        last_success_time = current_time
                        
                        # 成功发送后，可以适当增加间隔，减少带宽占用
                        if dynamic_interval < self.handshake_interval:
                            dynamic_interval = min(self.handshake_interval, dynamic_interval * 1.1)
                    else:
                        error_count += 1
                        # 发送失败时，减少间隔，增加尝试频率
                        dynamic_interval = max(min_interval, dynamic_interval * 0.8)
                        
                        # 如果连续失败超过5次，尝试重置串口
                        if error_count > 5 and (current_time - last_success_time) > 1.0:
                            print("⚠️ Handshake sending failed multiple times, attempting recovery...")
                            try:
                                if self.ser_sender and self.ser_sender.is_open:
                                    self.ser_sender.reset_output_buffer()
                            except:
                                pass
                            error_count = 0
                    
                    # 计算下一次发送时间，使用动态间隔
                    next_time = current_time + dynamic_interval
                else:
                    # 短暂休眠，避免CPU占用过高
                    sleep_time = min(0.001, (next_time - current_time) / 2)
                    time.sleep(sleep_time)
            except Exception as e:
                print(f"❌ Handshake thread error: {e}")
                time.sleep(0.01)  # 出错时短暂休眠
    
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
            
            # UART模式专用优化策略
            if self.transmission_mode == 'uart':
                target_fps = 1.0 / self.current_fps_delay  # 目标帧率
                
                # 主要根据包大小调整质量，避免过度增加延迟
                if avg_packet_size > self.target_packet_size * 1.5:
                    # 包过大，降低质量但不增加延迟
                    self.current_quality = max(20, self.current_quality - 3)
                    print(f"📉 Reduce quality: Q{self.current_quality} (packet size too large)")
                elif success_rate < 0.9:
                    # 传输成功率低，轻微增加延迟
                    self.current_quality = max(20, self.current_quality - 3)
                    self.current_fps_delay = min(0.15, self.current_fps_delay * 1.05)
                    print(f"📉 Reduce quality: Q{self.current_quality} (low success rate)")
                elif avg_packet_size < self.target_packet_size * 0.7 and success_rate > 0.95:
                    # 包较小且成功率高，可以提高质量或降低延迟
                    if recent_fps < target_fps * 0.8:
                        # 帧率不足，降低延迟
                        self.current_fps_delay = max(0.02, self.current_fps_delay * 0.95)
                        print(f"📈 Improve FPS: delay {self.current_fps_delay*1000:.1f}ms")
                    else:
                        # 帧率足够，提高质量
                        self.current_quality = min(70, self.current_quality + 2)
                        print(f"📈 Improve quality: Q{self.current_quality}")
            
            # 🌐 Wireless mode smart adjustment strategy
            elif self.transmission_mode == 'wireless':
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
        """Start transmission"""
        if not self.init_devices():
            print("❌ Device initialization failed")
            return False
        
        self.running = True
        
        # Start sender thread
        self.sender_thread_obj = threading.Thread(target=self.sender_thread)
        self.sender_thread_obj.daemon = True
        self.sender_thread_obj.start()
        
        # Start handshake thread for hybrid mode
        if self.transmission_mode == 'hybrid':
            self.handshake_running = True
            self.handshake_thread = threading.Thread(target=self.handshake_thread_func)
            self.handshake_thread.daemon = True
            self.handshake_thread.start()
            print(f"🤝 Handshake thread started - sending at {1000/self.handshake_interval:.1f}Hz")
            print(f"🔄 Hybrid mode: Video over wireless + UART handshaking")
        
        print("🚀 WebP sender started successfully")
        print("📊 Performance mode: " + self.mode_description)
        print("📷 Camera resolution: " + str(FRAME_WIDTH) + "x" + str(FRAME_HEIGHT))
        print("🔄 Transmission mode: " + self.transmission_mode.upper())
        
        return True
    
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
        """Stop transmission"""
        print("🛑 Stopping WebP sender...")
        self.running = False
        
        # Stop handshake thread for hybrid mode
        if self.transmission_mode == 'hybrid' and self.handshake_running:
            self.handshake_running = False
            if self.handshake_thread:
                self.handshake_thread.join(timeout=1.0)
        
        # Stop sender thread
        if hasattr(self, 'sender_thread_obj') and self.sender_thread_obj.is_alive():
            self.sender_thread_obj.join(timeout=1.0)
        
        # Release camera
        if self.cap is not None:
            self.cap.release()
        
        # Close serial port
        if self.ser_sender is not None:
            self.ser_sender.close()
        
        # Close wireless socket
        if self.wireless_socket is not None:
            self.wireless_socket.close()
        
        print("✅ WebP sender stopped successfully")
        self.print_stats()
        
        return True

def main():
    """Main function"""
    print("=" * 60)
    print("WebP Video Sender - UART/Wireless Optimized Video Transmission")
    print("=" * 60)
    
    # Select transmission mode
    transmission_mode, baud_rate = select_transmission_mode()
    
    # Create WebP sender
    sender = WebPSender(transmission_mode=transmission_mode, baud_rate=baud_rate)
    
    # Start transmission
    if not sender.start():
        print("❌ Transmission start failed")
        return
    
    # Wait for user to stop
    try:
        while True:
            time.sleep(1)
            sender.print_stats()
    except KeyboardInterrupt:
        print("\n🛑 User interrupted")
    finally:
        sender.stop()

if __name__ == "__main__":
    main() 