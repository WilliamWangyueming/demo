#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebP Video Receiver
WebP video reception program optimized for UART serial communication
Supports both wired UART, wireless transmission, and hybrid modes
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
            return 'hybrid', 2000000  # 视频传输使用2MHz，握手信号使用400K
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
RECEIVER_PORT = 'COM8'      # Receiver port (modify according to actual situation)

# Wireless configuration (wireless mode)
WIRELESS_HOST = '127.0.0.1'  # Server IP (localhost for same computer testing)
WIRELESS_PORT = 8888         # Wireless port

# Connection role
WIRELESS_ROLE = 'client'     # 接收端作为客户端

# TCP Socket optimizations
TCP_NODELAY = True           # 禁用Nagle算法，减少延迟
TCP_BUFFER_SIZE = 524288     # 设置更大的接收缓冲区 (512KB)
SOCKET_TIMEOUT = 0.1         # Socket超时设置，100ms

# Display configuration
WINDOW_NAME = 'WebP Video Receiver'  # Display window name
SHOW_STATS = True           # Whether to show statistics
AUTO_RESIZE = True          # Whether to auto-resize window

# 图像配置
WIRELESS_FRAME_WIDTH = 640  # 无线模式帧宽度
WIRELESS_FRAME_HEIGHT = 480 # 无线模式帧高度
USE_COLOR_FOR_WIRELESS = True  # 无线模式使用彩色图像

# Buffer configuration
FRAME_BUFFER_SIZE = 3       # Frame buffer size
STATS_BUFFER_SIZE = 50      # Statistics buffer size

# Advanced configuration (generally no need to modify)
PROTOCOL_MAGIC = b'WP'      # 缩短魔术字节为2字节
PACKET_TYPE = "WEBP"        # Packet type
RECEIVE_TIMEOUT = 0.05      # Receive timeout

# 优化协议设置
USE_SIMPLIFIED_PROTOCOL = True  # 使用简化协议以减少开销
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
        
        # Hybrid mode
        self.handshake_thread = None
        self.handshake_running = False
        self.last_handshake_time = time.time()  # 初始化为当前时间而不是0
        self.handshake_timeout = 0.5  # 减少到0.5秒，确保快速检测到断开
        self.handshake_active = False
        self.handshake_counter = 0
        self.last_handshake_id = 0
        self.handshake_health = 100  # 握手连接健康度(0-100)
        self.connection_state = "INITIALIZING"  # 连接状态: INITIALIZING, GOOD, DEGRADED, LOST
        
        # Frame buffer for hybrid mode
        self.hybrid_frame_buffer = deque(maxlen=30)  # 存储最近30帧，约1-2秒的视频
        self.pending_frames = deque(maxlen=5)
        
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
            'fps_history': deque(maxlen=30),
            'handshakes_received': 0,
            'frames_skipped': 0  # 新增：因handshake不活跃而跳过的帧数
        }
        
        # 性能优化标志
        self.is_high_performance = False
        self.is_1mhz_mode = False
        self.is_high_speed = False  # 高速模式 (>=2MHz)
        
        # 添加解码和显示优化的配置
        if baud_rate == 1000000:
            self.is_1mhz_mode = True
            self.is_high_performance = True
            print("🔥 1MHz HIGH PERFORMANCE MODE ENABLED")
        elif baud_rate >= 2000000:
            self.is_high_speed = True
            self.is_high_performance = True
            print(f"⚡ {baud_rate/1000000:.1f}MHz HIGH SPEED MODE ENABLED")
        elif baud_rate >= 500000:
            self.is_high_performance = True
            print("🚀 HIGH PERFORMANCE MODE ENABLED")
            
        # Buffer configuration - 高性能模式使用更大的缓冲区
        if self.is_high_speed:
            self.frame_buffer_size = 10  # 高速模式使用更大的帧缓冲区
        elif self.is_high_performance:
            self.frame_buffer_size = 5   # 高性能模式使用中等帧缓冲区
        else:
            self.frame_buffer_size = FRAME_BUFFER_SIZE
        
        # 接收缓冲区 - 用于提高1MHz接收效率
        if self.is_1mhz_mode:
            self.recv_buffer = bytearray(65536)  # 64KB接收缓冲区
            self.recv_buffer_pos = 0
        
        # 无线模式的彩色图像支持
        self.is_wireless_mode = self.transmission_mode in ['wireless', 'hybrid']
        self.use_color = self.is_wireless_mode and USE_COLOR_FOR_WIRELESS
        self.high_res = self.is_wireless_mode
        
        if self.high_res:
            self.frame_width = WIRELESS_FRAME_WIDTH
            self.frame_height = WIRELESS_FRAME_HEIGHT
            print(f"- Higher resolution support: {self.frame_width}x{self.frame_height}")
        
        if self.use_color:
            print("- Color image support enabled")
        
    def init_devices(self):
        """Initialize devices"""
        print("🚀 Initializing WebP video receiver...")
        print("📊 Receiver features:")
        print("- WebP decoding and display")
        print("- Smart buffering to prevent frame loss")
        print("- Real-time statistics monitoring")
        print("- Automatic error recovery")
        print(f"- Supports {self.transmission_mode.upper()} transmission mode")
        
        # 无线模式的彩色图像支持
        self.is_wireless_mode = self.transmission_mode in ['wireless', 'hybrid']
        self.use_color = self.is_wireless_mode and USE_COLOR_FOR_WIRELESS
        self.high_res = self.is_wireless_mode
        
        if self.high_res:
            self.frame_width = WIRELESS_FRAME_WIDTH
            self.frame_height = WIRELESS_FRAME_HEIGHT
            print(f"- Higher resolution support: {self.frame_width}x{self.frame_height}")
        
        if self.use_color:
            print("- Color image support enabled")
        
        if self.is_1mhz_mode:
            print("🔥 1MHz OPTIMIZED MODE: Enhanced for maximum frame rate")
            print("- Optimized receive buffer management")
            print("- Faster decode and render pipeline")
            print("- Bandwidth efficiency monitoring")
        
        # Initialize communication according to transmission mode
        if self.transmission_mode == 'uart':
            return self.init_uart(self.baud_rate)  # 使用当前设置的波特率
        elif self.transmission_mode == 'wireless':
            return self.init_wireless()
        else:  # hybrid mode
            uart_success = self.init_uart(400000)  # 握手信号使用400K
            wireless_success = self.init_wireless()
            return uart_success and wireless_success
    
    def init_uart(self, baud_rate):
        """Initialize UART serial port"""
        try:
            # Optimize UART settings for higher performance
            self.ser_receiver = serial.Serial(
                RECEIVER_PORT, 
                baud_rate, 
                timeout=RECEIVE_TIMEOUT,
                # Disable software flow control for better throughput
                xonxoff=False,
                # Enable hardware flow control if your hardware supports it
                rtscts=False,
                dsrdtr=False
            )
            
            # Clear buffers
            self.ser_receiver.reset_input_buffer()
            self.ser_receiver.reset_output_buffer()
            
            print(f"✅ Receiver serial port initialization successful ({RECEIVER_PORT} @ {baud_rate}bps)")
            
            return True
        except Exception as e:
            print(f"❌ Receiver serial port initialization failed: {e}")
            print(f"Please check if serial port {RECEIVER_PORT} is available")
            return False
    
    def init_wireless(self):
        """Initialize wireless connection"""
        try:
            # 创建TCP客户端socket并进行优化
            self.wireless_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            
            # 优化socket配置 - 对于高性能模式
            if self.is_high_performance:
                # 设置更大的接收缓冲区
                self.wireless_socket.setsockopt(socket.SOL_SOCKET, socket.SO_RCVBUF, TCP_BUFFER_SIZE)
                # 禁用Nagle算法，减少延迟
                self.wireless_socket.setsockopt(socket.IPPROTO_TCP, socket.TCP_NODELAY, 1)
                # 设置超时
                self.wireless_socket.settimeout(SOCKET_TIMEOUT)
                print("🔧 Socket optimized for high performance")
                print(f"   - Receive buffer: {TCP_BUFFER_SIZE/1024:.0f}KB")
                print(f"   - TCP_NODELAY: {TCP_NODELAY}")
                print(f"   - Timeout: {SOCKET_TIMEOUT*1000:.0f}ms")
            
            print(f"🌐 Connecting to wireless sender...")
            print(f"   Address: {WIRELESS_HOST}:{WIRELESS_PORT}")
            print(f"   Speed: {self.baud_rate/1000}K bps")
            
            # Connect to server
            self.wireless_socket.settimeout(10.0)  # 设置更长的连接超时时间
            print("   Trying to connect to sender... (10s timeout)")
            
            try:
                self.wireless_socket.connect((WIRELESS_HOST, WIRELESS_PORT))
            except ConnectionRefusedError:
                print("❌ Connection refused. Make sure the sender is running first.")
                return False
            except socket.timeout:
                print("❌ Connection timed out. Make sure the sender is running.")
                return False
            
            # 对于高速模式，设置非阻塞模式
            if self.is_high_speed:
                self.wireless_socket.setblocking(False)
                print("   - Non-blocking mode enabled")
            
            print(f"✅ Connected to sender: {WIRELESS_HOST}:{WIRELESS_PORT}")
            
            # Set receive timeout
            if not self.is_high_speed:  # 非高速模式使用超时
                self.wireless_socket.settimeout(RECEIVE_TIMEOUT)
            
            return True
        except Exception as e:
            print(f"❌ Wireless connection failed: {e}")
            return False
    
    def decode_frame_webp(self, webp_data):
        """WebP frame decoding"""
        try:
            # 使用优化的解码方法
            if self.is_high_performance:
                # 优化解码过程
                start_time = time.time()
                
                # 使用PIL进行快速解码
                pil_image = Image.open(io.BytesIO(webp_data))
                frame = np.array(pil_image)
                
                # 检查是否为彩色图像
                if len(frame.shape) == 3 and self.use_color:
                    # 彩色图像，可能需要颜色空间转换
                    if frame.shape[2] == 3:  # RGB
                        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                elif len(frame.shape) == 3 and not self.use_color:
                    # 不需要彩色但收到了彩色图像，转换为灰度
                    frame = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
                elif len(frame.shape) == 2 and self.use_color:
                    # 需要彩色但收到了灰度图，转换为彩色
                    frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
                
                decode_time = (time.time() - start_time) * 1000
                if decode_time > 10:  # 超过10ms记录一下
                    print(f"⚠️ Slow decode: {decode_time:.1f}ms for {len(webp_data)} bytes")
                
                return frame
            else:
                # 标准解码方法
                pil_image = Image.open(io.BytesIO(webp_data))
                frame = np.array(pil_image)
                
                # 处理颜色转换
                if len(frame.shape) == 3 and self.use_color:
                    # 彩色图像处理
                    if frame.shape[2] == 3:  # RGB
                        frame = cv2.cvtColor(frame, cv2.COLOR_RGB2BGR)
                elif len(frame.shape) == 3 and not self.use_color:
                    # 转换为灰度
                    frame = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
                elif len(frame.shape) == 2 and self.use_color:
                    # 转换为彩色
                    frame = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
                
                return frame
            
        except Exception as e:
            print(f"❌ WebP decoding failed: {e}")
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
        try:
            # Find magic number with optimized reading strategy
            buffer = bytearray()
            magic_found = False
            
            # First try to read a larger chunk to reduce individual reads
            initial_chunk = self.ser_receiver.read(min(256, max(64, self.ser_receiver.in_waiting)))
            if not initial_chunk:
                return None, None
                
            buffer.extend(initial_chunk)
            
            # Look for magic number in the initial chunk
            magic_pos = buffer.find(PROTOCOL_MAGIC)
            if magic_pos != -1:
                buffer = buffer[magic_pos:]
                magic_found = True
            
            # If not found, continue with smaller reads
            start_time = time.time()
            while not magic_found and (time.time() - start_time) < 0.1:
                # Read multiple bytes at once instead of byte-by-byte
                chunk = self.ser_receiver.read(64)
                if not chunk:
                    break
                    
                buffer.extend(chunk)
                
                if len(buffer) >= len(PROTOCOL_MAGIC):
                    magic_pos = buffer.find(PROTOCOL_MAGIC)
                    if magic_pos != -1:
                        buffer = buffer[magic_pos:]
                        magic_found = True
            
            if not magic_found:
                return None, None
            
            if USE_SIMPLIFIED_PROTOCOL:
                # 简化协议: Magic(2) + Length(2) + Hash(4) + Data
                # 确保我们有足够的数据来读取头部
                header_size = len(PROTOCOL_MAGIC) + 2 + 4  # Magic + Length + Hash
                
                # 读取完整的头部
                while len(buffer) < header_size:
                    chunk = self.ser_receiver.read(header_size - len(buffer))
                    if not chunk:
                        return None, None
                    buffer.extend(chunk)
                
                # 解析简化的头部
                packet_length = struct.unpack('<H', buffer[len(PROTOCOL_MAGIC):len(PROTOCOL_MAGIC)+2])[0]
                expected_hash = buffer[len(PROTOCOL_MAGIC)+2:len(PROTOCOL_MAGIC)+2+4]
                
                # 验证包长度
                if packet_length > 10000 or packet_length < 50:
                    print(f"⚠️  Abnormal packet length: {packet_length}")
                    return None, None
                
                # 读取剩余数据
                remaining = packet_length - (len(buffer) - header_size)
                if remaining > 0:
                    data_chunk = self.ser_receiver.read(remaining)
                    if len(data_chunk) != remaining:
                        print(f"⚠️  Incomplete data: received {len(data_chunk)} of {remaining} bytes")
                        return None, None
                    buffer.extend(data_chunk)
                
                # 提取数据包数据
                packet_data = bytes(buffer[header_size:header_size+packet_length])
                
                # 验证哈希
                actual_hash = self.calculate_frame_hash(packet_data)
                if actual_hash != expected_hash:
                    print("⚠️  Packet hash verification failed")
                    self.stats['errors'] += 1
                    return None, None
                
                # 假设所有包都是WEBP类型
                packet_type = PACKET_TYPE
                
            else:
                # 原始协议处理
                # Ensure complete header (4+4+4+8+4=24)
                while len(buffer) < 24:
                    # Read the remaining header bytes at once
                    remaining_header = 24 - len(buffer)
                    chunk = self.ser_receiver.read(remaining_header)
                    if not chunk:
                        return None, None
                    buffer.extend(chunk)
                
                # Parse header
                frame_id = struct.unpack('<I', buffer[4:8])[0]
                packet_length = struct.unpack('<I', buffer[8:12])[0]
                packet_type = buffer[12:20].decode('ascii').strip()
                expected_hash = buffer[20:24]
                
                # Verify packet length
                if packet_length > 10000 or packet_length < 50:
                    print(f"⚠️  Abnormal packet length: {packet_length}")
                    return None, None
                
                # Read remaining data - optimize by reading larger chunks
                remaining = packet_length - (len(buffer) - 24)
                
                # Try to read all remaining data at once if possible
                if remaining > 0:
                    data_chunk = self.ser_receiver.read(remaining)
                    if len(data_chunk) != remaining:
                        print(f"⚠️  Incomplete data: received {len(data_chunk)} of {remaining} bytes")
                        return None, None
                    buffer.extend(data_chunk)
                
                # Extract packet data
                packet_data = bytes(buffer[24:24+packet_length])
                
                # Verify hash
                actual_hash = self.calculate_frame_hash(packet_data)
                if actual_hash != expected_hash:
                    print(f"⚠️  Packet hash verification failed")
                    self.stats['errors'] += 1
                    return None, None
            
            self.stats['frames_received'] += 1
            self.stats['bytes_received'] += len(packet_data)
            self.stats['packet_sizes'].append(len(packet_data))
            self.last_successful_time = time.time()
            self.error_count = 0
            
            return packet_data, packet_type
        except Exception as e:
            print(f"❌ UART receive error: {e}")
            self.stats['errors'] += 1
            return None, None
    
    def receive_packet_wireless(self):
        """Wireless method to receive data packet"""
        try:
            # 1MHz模式使用特殊优化的接收方法
            if self.is_1mhz_mode:
                return self._receive_packet_wireless_optimized()
            
            # 普通模式使用原始接收方法
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
                    
                    if len(buffer) >= len(PROTOCOL_MAGIC):
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
            
            if USE_SIMPLIFIED_PROTOCOL:
                # 简化协议: Magic(2) + Length(2) + Hash(4) + Data
                # 确保我们有足够的数据来读取头部
                header_size = len(PROTOCOL_MAGIC) + 2 + 4  # Magic + Length + Hash
                
                # 读取完整的头部
                while len(buffer) < header_size:
                    try:
                        chunk = self.wireless_socket.recv(header_size - len(buffer))
                        if not chunk:
                            return None, None
                        buffer.extend(chunk)
                    except Exception:
                        return None, None
                
                # 解析简化的头部
                packet_length = struct.unpack('<H', buffer[len(PROTOCOL_MAGIC):len(PROTOCOL_MAGIC)+2])[0]
                expected_hash = buffer[len(PROTOCOL_MAGIC)+2:len(PROTOCOL_MAGIC)+2+4]
                
                # 验证包长度
                if packet_length > 10000 or packet_length < 50:
                    print(f"⚠️  Abnormal packet length: {packet_length}")
                    return None, None
                
                # 读取剩余数据
                remaining = packet_length - (len(buffer) - header_size)
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
                
                # 提取数据包数据
                packet_data = bytes(buffer[header_size:header_size+packet_length])
                
                # 验证哈希
                actual_hash = self.calculate_frame_hash(packet_data)
                if actual_hash != expected_hash:
                    print("⚠️  Packet hash verification failed")
                    self.stats['errors'] += 1
                    return None, None
                
                # 假设所有包都是WEBP类型
                packet_type = PACKET_TYPE
                
            else:
                # 原始协议处理
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
                    print("⚠️  Packet hash verification failed")
                    self.stats['errors'] += 1
                    return None, None
            
            self.stats['frames_received'] += 1
            self.stats['bytes_received'] += len(packet_data)
            self.stats['packet_sizes'].append(len(packet_data))
            self.last_successful_time = time.time()
            self.error_count = 0
            
            return packet_data, packet_type
        except Exception as e:
            print(f"❌ Wireless receive error: {e}")
            self.stats['errors'] += 1
            return None, None
    
    def _receive_packet_wireless_optimized(self):
        """优化的无线数据包接收方法 - 专为1MHz模式设计"""
        try:
            # 高速模式 (>=2MHz) 使用特殊优化
            if self.is_high_speed:
                try:
                    # 尝试非阻塞接收
                    try:
                        chunk = self.wireless_socket.recv(65536)  # 尝试一次性接收大量数据
                    except socket.error as e:
                        if str(e).find('10035') >= 0:  # WSAEWOULDBLOCK
                            # 没有数据可用，不是错误
                            return None, None
                        else:
                            # 其他错误
                            raise e
                    
                    if not chunk:
                        return None, None
                    
                    # 添加到缓冲区
                    self.recv_buffer[self.recv_buffer_pos:self.recv_buffer_pos+len(chunk)] = chunk
                    self.recv_buffer_pos += len(chunk)
                    
                    # 查找完整的包
                    return self._find_packet_in_buffer()
                    
                except Exception as e:
                    if not str(e).find('10035') >= 0:  # 不是WSAEWOULDBLOCK
                        print(f"⚠️ High speed receive error: {e}")
                    return None, None
            
            # 1MHz模式优化
            try:
                # 将数据接收到缓冲区
                self.wireless_socket.settimeout(0.01)  # 10ms超时，减少等待时间
                bytes_received = self.wireless_socket.recv_into(
                    memoryview(self.recv_buffer)[self.recv_buffer_pos:], 
                    len(self.recv_buffer) - self.recv_buffer_pos
                )
                
                if bytes_received <= 0:
                    return None, None
                
                # 更新缓冲区位置
                self.recv_buffer_pos += bytes_received
                
                # 如果缓冲区将满，重置
                if self.recv_buffer_pos > 60000:  # 接近缓冲区上限
                    # 在重置前尝试查找一个完整的包
                    packet_data, packet_type = self._find_packet_in_buffer()
                    if packet_data:
                        return packet_data, packet_type
                    
                    # 如果没有找到完整包，将最后100字节保留到缓冲区开头
                    last_bytes = self.recv_buffer[self.recv_buffer_pos-100:self.recv_buffer_pos]
                    self.recv_buffer[0:100] = last_bytes
                    self.recv_buffer_pos = 100
                    return None, None
                
                # 尝试在缓冲区中查找一个完整的数据包
                return self._find_packet_in_buffer()
                
            except socket.timeout:
                # 超时但缓冲区可能有数据，尝试解析
                if self.recv_buffer_pos > 0:
                    return self._find_packet_in_buffer()
                return None, None
            except Exception as e:
                print(f"⚠️ Socket receive warning: {e}")
                return None, None
        
        except Exception as e:
            print(f"❌ Optimized wireless receive error: {e}")
            self.stats['errors'] += 1
            return None, None
    
    def _find_packet_in_buffer(self):
        """在接收缓冲区中查找完整的数据包"""
        # 在缓冲区中查找魔术字节
        buffer_view = memoryview(self.recv_buffer)[:self.recv_buffer_pos]
        buffer_bytes = bytes(buffer_view)
        magic_pos = buffer_bytes.find(PROTOCOL_MAGIC)
        
        if magic_pos == -1:
            return None, None
        
        # 找到魔术字节，开始解析
        if USE_SIMPLIFIED_PROTOCOL:
            # 简化协议: Magic(2) + Length(2) + Hash(4) + Data
            header_size = len(PROTOCOL_MAGIC) + 2 + 4  # Magic + Length + Hash
            
            # 确保有足够的数据解析头部
            if magic_pos + header_size > self.recv_buffer_pos:
                # 将找到的不完整包移到缓冲区开头
                incomplete_data = self.recv_buffer[magic_pos:self.recv_buffer_pos]
                self.recv_buffer[0:len(incomplete_data)] = incomplete_data
                self.recv_buffer_pos = len(incomplete_data)
                return None, None
            
            # 解析包长度
            length_bytes = buffer_bytes[magic_pos+len(PROTOCOL_MAGIC):magic_pos+len(PROTOCOL_MAGIC)+2]
            packet_length = struct.unpack('<H', length_bytes)[0]
            
            # 验证包长度
            if packet_length > 10000 or packet_length < 50:
                # 无效的包长度，丢弃这个魔术字节
                new_buffer = buffer_bytes[magic_pos+len(PROTOCOL_MAGIC):]
                new_magic_pos = new_buffer.find(PROTOCOL_MAGIC)
                if new_magic_pos != -1:
                    # 在剩余数据中找到了新的魔术字节
                    self.recv_buffer[0:len(new_buffer)-new_magic_pos] = new_buffer[new_magic_pos:]
                    self.recv_buffer_pos = len(new_buffer) - new_magic_pos
                else:
                    # 没有找到新的魔术字节，清空缓冲区
                    self.recv_buffer_pos = 0
                return None, None
            
            # 检查是否有完整的包
            total_packet_size = magic_pos + header_size + packet_length
            if total_packet_size > self.recv_buffer_pos:
                # 包不完整，继续等待数据
                return None, None
            
            # 提取哈希值和数据
            expected_hash = buffer_bytes[magic_pos+len(PROTOCOL_MAGIC)+2:magic_pos+len(PROTOCOL_MAGIC)+2+4]
            packet_data = buffer_bytes[magic_pos+header_size:magic_pos+header_size+packet_length]
            
            # 验证哈希
            actual_hash = self.calculate_frame_hash(packet_data)
            if actual_hash != expected_hash:
                # 哈希验证失败，丢弃这个包
                new_buffer = buffer_bytes[magic_pos+len(PROTOCOL_MAGIC):]
                new_magic_pos = new_buffer.find(PROTOCOL_MAGIC)
                if new_magic_pos != -1:
                    # 在剩余数据中找到了新的魔术字节
                    self.recv_buffer[0:len(new_buffer)-new_magic_pos] = new_buffer[new_magic_pos:]
                    self.recv_buffer_pos = len(new_buffer) - new_magic_pos
                else:
                    # 没有找到新的魔术字节，将指针移动到当前包之后
                    remaining = buffer_bytes[total_packet_size:]
                    self.recv_buffer[0:len(remaining)] = remaining
                    self.recv_buffer_pos = len(remaining)
                self.stats['errors'] += 1
                return None, None
            
            # 更新接收缓冲区 - 移除已处理的包
            remaining = buffer_bytes[total_packet_size:]
            self.recv_buffer[0:len(remaining)] = remaining
            self.recv_buffer_pos = len(remaining)
            
            # 更新统计信息
            self.stats['frames_received'] += 1
            self.stats['bytes_received'] += len(packet_data)
            self.stats['packet_sizes'].append(len(packet_data))
            self.last_successful_time = time.time()
            self.error_count = 0
            
            return packet_data, PACKET_TYPE
        else:
            # 原始协议处理 - 简化起见，不再详细实现
            # 如果需要支持原始协议，可以参考上面的逻辑进行实现
            
            return None, None
    
    def receive_handshake_packet(self):
        """Receive handshake packet over UART in hybrid mode"""
        try:
            # 检查串口是否可用
            if not self.ser_receiver or not self.ser_receiver.is_open:
                return False
            
            # 检查是否有数据可读
            if self.ser_receiver.in_waiting == 0:
                return False
            
            # Find magic number with optimized reading strategy
            buffer = bytearray()
            magic_found = False
            
            # First try to read a larger chunk
            initial_chunk = self.ser_receiver.read(min(64, max(32, self.ser_receiver.in_waiting)))
            if not initial_chunk:
                return False
                
            buffer.extend(initial_chunk)
            
            # Look for magic number in the initial chunk
            magic_pos = buffer.find(PROTOCOL_MAGIC)
            if magic_pos != -1:
                buffer = buffer[magic_pos:]
                magic_found = True
            
            # If not found, continue with smaller reads
            start_time = time.time()
            while not magic_found and (time.time() - start_time) < 0.1:
                # Read multiple bytes at once
                chunk = self.ser_receiver.read(32)
                if not chunk:
                    break
                    
                buffer.extend(chunk)
                
                if len(buffer) >= len(PROTOCOL_MAGIC):
                    magic_pos = buffer.find(PROTOCOL_MAGIC)
                    if magic_pos != -1:
                        buffer = buffer[magic_pos:]
                        magic_found = True
            
            if not magic_found:
                return False
            
            if USE_SIMPLIFIED_PROTOCOL:
                # 简化协议: Magic(2) + 'HS'(2) + Counter(2)
                # 确保我们有足够的数据来读取握手包
                handshake_size = len(PROTOCOL_MAGIC) + 2 + 2  # Magic + HS + Counter
                
                # 读取完整的握手包
                while len(buffer) < handshake_size:
                    chunk = self.ser_receiver.read(handshake_size - len(buffer))
                    if not chunk:
                        return False
                    buffer.extend(chunk)
                
                # 验证是否是握手包
                hs_marker = buffer[len(PROTOCOL_MAGIC):len(PROTOCOL_MAGIC)+2]
                if hs_marker != b'HS':
                    return False
                
                # 提取计数器
                counter_bytes = buffer[len(PROTOCOL_MAGIC)+2:len(PROTOCOL_MAGIC)+2+2]
                handshake_id = struct.unpack('<H', counter_bytes)[0]
                
                # 更新握手状态
                self.last_handshake_time = time.time()
                self.handshake_active = True
                self.handshake_counter = handshake_id
                self.stats['handshakes_received'] += 1
                
                # 收到handshake后处理待显示的帧
                self.process_pending_frames()
                
                return True
                
            else:
                # 原始握手包处理
                # Ensure complete header (4+4+4+8+4=24)
                while len(buffer) < 24:
                    # Read the remaining header bytes at once
                    remaining_header = 24 - len(buffer)
                    chunk = self.ser_receiver.read(remaining_header)
                    if not chunk:
                        return False
                    buffer.extend(chunk)
                
                # Parse header
                handshake_id = struct.unpack('<I', buffer[4:8])[0]
                packet_length = struct.unpack('<I', buffer[8:12])[0]
                packet_type = buffer[12:20].decode('ascii').strip()
                expected_hash = buffer[20:24]
                
                # Verify it's a handshake packet
                if packet_type != "HNDSHK":
                    return False
                
                # Verify packet length
                if packet_length > 1000 or packet_length < 5:
                    print(f"⚠️  Abnormal handshake packet length: {packet_length}")
                    return False
                
                # Read remaining data - optimize by reading all at once
                remaining = packet_length - (len(buffer) - 24)
                if remaining > 0:
                    data_chunk = self.ser_receiver.read(remaining)
                    if len(data_chunk) != remaining:
                        return False
                    buffer.extend(data_chunk)
                
                # Extract packet data
                packet_data = bytes(buffer[24:24+packet_length])
                
                # Verify hash
                actual_hash = self.calculate_frame_hash(packet_data)
                if actual_hash != expected_hash:
                    print(f"⚠️  Handshake {handshake_id} hash verification failed")
                    return False
                
                # Update handshake status
                self.last_handshake_time = time.time()
                self.handshake_active = True
                self.handshake_counter = handshake_id
                self.stats['handshakes_received'] += 1
                
                # 收到handshake后处理待显示的帧
                self.process_pending_frames()
                
                return True
            
        except Exception as e:
            print(f"❌ Handshake receive error: {e}")
            return False

    def process_pending_frames(self):
        """处理待显示的帧队列"""
        if not self.pending_frames or not self.handshake_active:
            return
            
        # 将所有待处理帧放入显示队列
        frames_processed = 0
        current_time = time.time()
        
        # 只处理不超过100ms的帧，太旧的帧直接丢弃
        while self.pending_frames:
            frame_data = self.pending_frames.popleft()
            frame_age = current_time - frame_data['timestamp']
            
            # 如果帧太旧，就丢弃
            if frame_age > 0.1:  # 100ms
                self.stats['frames_skipped'] += 1
                continue
                
            # 将帧放入显示队列
            try:
                self.received_frames.put_nowait(frame_data['frame'])
                frames_processed += 1
            except queue.Full:
                try:
                    self.received_frames.get_nowait()
                    self.received_frames.put_nowait(frame_data['frame'])
                    frames_processed += 1
                except queue.Empty:
                    pass
        
        if frames_processed > 0:
            print(f"✅ Processed {frames_processed} pending frames")

    def handshake_thread_func(self):
        """Thread function for receiving handshake packets in hybrid mode"""
        print("🤝 Starting handshake monitoring thread")
        
        last_status_print = time.time()
        status_interval = 1.0  # 每秒最多打印一次状态
        
        # 健康度计算参数
        health_decay_rate = 10  # 每100ms衰减的健康度 - 增加衰减速率
        health_recovery_rate = 30  # 每次收到握手包恢复的健康度 - 增加恢复速率
        last_health_update = time.time()
        
        # 初始化连接状态为初始化中
        self.connection_state = "INITIALIZING"
        self.handshake_health = 50  # 初始健康度设为50
        
        while self.handshake_running:
            try:
                current_time = time.time()
                
                # 尝试接收握手包
                if self.receive_handshake_packet():
                    # 成功接收到握手包
                    self.last_handshake_time = current_time
                    
                    # 恢复健康度
                    self.handshake_health = min(100, self.handshake_health + health_recovery_rate)
                    
                    # 更新连接状态
                    if not self.handshake_active:
                        self.handshake_active = True
                        print("✅ Handshake connection established")
                    
                    if self.connection_state != "GOOD" and self.handshake_health > 80:
                        old_state = self.connection_state
                        self.connection_state = "GOOD"
                        print(f"📈 Connection state: {old_state} → GOOD (Health: {self.handshake_health}%)")
                    
                    # 收到握手包后立即处理待显示的帧
                    self.process_pending_frames()
                else:
                    # 计算健康度衰减
                    time_since_update = current_time - last_health_update
                    decay = int(health_decay_rate * (time_since_update * 10))  # 每100ms衰减
                    if decay > 0:
                        self.handshake_health = max(0, self.handshake_health - decay)
                        last_health_update = current_time
                    
                    # 计算自上次握手包以来的时间
                    time_since_last_handshake = current_time - self.last_handshake_time
                    
                    # 根据健康度和握手超时更新连接状态
                    if time_since_last_handshake > self.handshake_timeout:
                        # 超时，强制降低健康度
                        self.handshake_health = max(0, self.handshake_health - 30)  # 大幅降低健康度
                    
                    # 根据健康度更新连接状态
                    if self.handshake_health <= 0:
                        if self.connection_state != "LOST":
                            old_state = self.connection_state
                            self.connection_state = "LOST"
                            self.handshake_active = False
                            print(f"📉 Connection state: {old_state} → LOST (Health: 0%)")
                            
                            # 连接丢失时清空待显示帧队列
                            self.pending_frames.clear()
                    elif self.handshake_health < 50:
                        if self.connection_state != "DEGRADED":
                            old_state = self.connection_state
                            self.connection_state = "DEGRADED"
                            print(f"⚠️ Connection state: {old_state} → DEGRADED (Health: {self.handshake_health}%)")
                
                # 定期打印状态
                if current_time - last_status_print > status_interval:
                    time_since_last = (current_time - self.last_handshake_time) * 1000  # 转换为毫秒
                    print(f"🤝 Connection: {self.connection_state}, Health: {self.handshake_health}%, " +
                          f"Time since last handshake: {time_since_last:.0f}ms")
                    last_status_print = current_time
                
                # 短暂休眠
                time.sleep(0.01)
                
            except Exception as e:
                print(f"❌ Handshake thread error: {e}")
                time.sleep(0.05)

    def receiver_thread(self):
        """Receiver thread"""
        print("🚀 WebP receiver thread started")
        
        # 高性能模式性能监控
        if self.is_high_performance:
            last_perf_print = time.time()
            frames_since_last = 0
            bytes_since_last = 0
            
            # 高速模式使用更频繁的性能打印
            if self.is_high_speed:
                perf_interval = 3.0  # 每3秒打印一次性能信息
            else:
                perf_interval = 5.0  # 每5秒打印一次性能信息
        
        while self.running:
            try:
                packet_data, packet_type = self.receive_packet()
                if packet_data and packet_type == PACKET_TYPE:
                    # 性能统计
                    if self.is_high_performance:
                        frames_since_last += 1
                        bytes_since_last += len(packet_data)
                        
                        # 定期打印性能信息
                        current_time = time.time()
                        if current_time - last_perf_print >= perf_interval:
                            elapsed = current_time - last_perf_print
                            fps = frames_since_last / elapsed
                            bps = bytes_since_last * 8 / elapsed
                            utilization = 0
                            if self.baud_rate > 0:
                                utilization = (bps / self.baud_rate) * 100
                            
                            if self.is_high_speed:
                                print(f"⚡ Performance: {fps:.1f} fps, {bps/1000:.0f} kbps ({utilization:.1f}% of {self.baud_rate/1000:.0f}K)")
                            else:
                                print(f"📊 Performance: {fps:.1f} fps, {bps/1000:.0f} kbps ({utilization:.1f}% of {self.baud_rate/1000:.0f}K)")
                            
                            frames_since_last = 0
                            bytes_since_last = 0
                            last_perf_print = current_time
                    
                    # WebP decoding
                    frame = self.decode_frame_webp(packet_data)
                    if frame is not None:
                        # Calculate compression ratio
                        original_size = frame.nbytes
                        compressed_size = len(packet_data)
                        compression_ratio = original_size / compressed_size
                        self.stats['compression_ratios'].append(compression_ratio)
                        
                        # 处理不同模式下的帧
                        if self.transmission_mode == 'hybrid':
                            # Hybrid模式：所有帧都进入缓冲区
                            frame_data = {
                                'frame': frame,
                                'timestamp': time.time(),
                                'size': compressed_size
                            }
                            
                            # 添加到hybrid缓冲区
                            self.hybrid_frame_buffer.append(frame_data)
                            
                            # 根据连接状态决定是否显示
                            if self.connection_state == "GOOD":
                                # 连接正常，直接显示帧
                                try:
                                    self.received_frames.put_nowait(frame)
                                except queue.Full:
                                    try:
                                        self.received_frames.get_nowait()
                                        self.received_frames.put_nowait(frame)
                                    except queue.Empty:
                                        pass
                            elif self.connection_state == "DEGRADED":
                                # 连接降级状态，将帧放入待处理队列
                                self.pending_frames.append(frame_data)
                            else:  # LOST 或 INITIALIZING
                                # 连接丢失或初始化中，不显示帧
                                pass
                        else:
                            # 非Hybrid模式：直接放入显示队列
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
            
            # 如果是高分辨率模式，可以设置初始窗口大小
            if self.high_res:
                cv2.resizeWindow(WINDOW_NAME, self.frame_width, self.frame_height)
            
            print(f"✅ OpenCV window created successfully: {WINDOW_NAME}")
        except Exception as e:
            print(f"❌ OpenCV window creation failed: {e}")
            return
        
        last_fps_time = time.time()
        frame_count_for_fps = 0
        last_no_signal_time = 0
        no_signal_interval = 0.5  # 每500ms最多显示一次无信号
        
        # 上一帧显示状态
        last_frame_time = time.time()
        
        # 高性能模式优化
        if self.is_high_performance:
            # 预分配内存，避免频繁分配
            last_frame = None
            
            # 高速模式使用最短的等待时间
            if self.is_high_speed:
                wait_key_delay = 1
            else:
                wait_key_delay = 1
        else:
            wait_key_delay = 1
        
        while self.running:
            try:
                current_time = time.time()
                
                # 在hybrid模式下，只有在连接完全丢失时才显示无信号
                if self.transmission_mode == 'hybrid':
                    if self.connection_state == "LOST":
                        # 连接已丢失，显示无信号
                        if current_time - last_no_signal_time >= no_signal_interval:
                            self.show_no_signal("CONNECTION LOST")
                            last_no_signal_time = current_time
                        time.sleep(0.05)  # 减少CPU使用
                        continue
                    
                    # 连接降级但未丢失，继续尝试显示帧
                    if self.connection_state == "DEGRADED":
                        # 在降级状态下，可以显示一个警告标志在画面上
                        pass
                
                # 尝试获取帧
                try:
                    frame = self.received_frames.get(timeout=0.1)
                    last_frame_time = current_time
                except queue.Empty:
                    # 如果超过1秒没有帧，显示无信号
                    if current_time - last_frame_time > 1.0:
                        if self.transmission_mode == 'hybrid':
                            if self.connection_state == "LOST":
                                self.show_no_signal("CONNECTION LOST")
                            else:
                                self.show_no_signal("NO DATA")
                        else:
                            self.show_no_signal()
                    continue
                
                if frame is not None:
                    # 显示帧处理 - 高性能模式优化
                    if self.is_high_performance:
                        # 检查是否需要颜色转换
                        if len(frame.shape) == 2 and self.use_color:
                            # 灰度图转BGR
                            frame_bgr = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
                        elif len(frame.shape) == 3 and not self.use_color:
                            # BGR转灰度
                            frame_bgr = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                            # 再转回BGR用于显示
                            frame_bgr = cv2.cvtColor(frame_bgr, cv2.COLOR_GRAY2BGR)
                        elif len(frame.shape) == 3 and frame.shape[2] == 3:
                            # 已经是BGR格式
                            frame_bgr = frame
                        else:
                            # 默认转换
                            frame_bgr = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
                    else:
                        # 标准转换
                        if len(frame.shape) == 2:
                            frame_bgr = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
                        else:
                            frame_bgr = frame
                    
                    # Add status information
                    if SHOW_STATS:
                        self.add_status_overlay(frame_bgr)
                    
                    # 在hybrid模式下，根据连接状态添加指示器
                    if self.transmission_mode == 'hybrid':
                        if self.connection_state == "DEGRADED":
                            # 在画面右上角添加警告标志
                            cv2.circle(frame_bgr, (frame_bgr.shape[1] - 15, 15), 8, (0, 165, 255), -1)
                            cv2.putText(frame_bgr, "!", (frame_bgr.shape[1] - 18, 19), 
                                      cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 2)
                    
                    # Display
                    cv2.imshow(WINDOW_NAME, frame_bgr)
                    
                    # 更新上一帧
                    if self.is_high_performance:
                        last_frame = frame
                    
                    self.stats['frames_displayed'] += 1
                    frame_count_for_fps += 1
                    
                    # Calculate display frame rate
                    if current_time - last_fps_time >= 1.0:
                        fps = frame_count_for_fps / (current_time - last_fps_time)
                        self.stats['fps_history'].append(fps)
                        last_fps_time = current_time
                        frame_count_for_fps = 0
                    
                    if cv2.waitKey(wait_key_delay) & 0xFF == ord('q'):
                        self.running = False
                        break
                
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
        
        # 高性能模式下的优化状态显示
        if self.is_high_performance:
            info_lines = [
                f"FPS: {current_fps:.1f}",
                f"Packet: {avg_packet_size:.0f}B",
                f"Compress: {avg_compression:.1f}x",
                f"Rcv: {self.stats['frames_received']}",
            ]
            
            # 对于1MHz模式，添加额外信息
            if self.is_1mhz_mode:
                # 计算有效带宽利用率
                if current_fps > 0 and avg_packet_size > 0:
                    effective_bitrate = current_fps * avg_packet_size * 8  # bps
                    utilization = (effective_bitrate / 1000000) * 100  # 相对于1MHz的百分比
                    info_lines.append(f"Rate: {effective_bitrate/1000:.0f}kbps ({utilization:.0f}%)")
        else:
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
    
    def show_no_signal(self, message=None):
        """Show no signal status"""
        no_signal = np.zeros((240, 320, 3), dtype=np.uint8)
        
        # 如果是高分辨率模式，创建更大的画布
        if hasattr(self, 'high_res') and self.high_res:
            no_signal = np.zeros((480, 640, 3), dtype=np.uint8)
        
        # 在画布中央显示"NO SIGNAL"
        h, w = no_signal.shape[:2]
        text_size = cv2.getTextSize("NO SIGNAL", cv2.FONT_HERSHEY_SIMPLEX, 1, 2)[0]
        text_x = (w - text_size[0]) // 2
        text_y = (h + text_size[1]) // 2
        cv2.putText(no_signal, "NO SIGNAL", (text_x, text_y), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
        
        if message:
            # 在主消息下方显示附加消息
            msg_size = cv2.getTextSize(message, cv2.FONT_HERSHEY_SIMPLEX, 0.5, 1)[0]
            msg_x = (w - msg_size[0]) // 2
            msg_y = text_y + 30
            cv2.putText(no_signal, message, (msg_x, msg_y), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            
            # 在hybrid模式下，显示更多信息
            if self.transmission_mode == 'hybrid':
                time_since_last = time.time() - self.last_handshake_time
                time_text = f"Last handshake: {time_since_last*1000:.0f}ms ago"
                cv2.putText(no_signal, time_text, 
                           (50, msg_y + 30), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
                health_text = f"Connection health: {self.handshake_health}%"
                cv2.putText(no_signal, health_text, 
                           (50, msg_y + 60), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
                
                # 显示缓冲区状态
                buffer_status = f"Buffer: {len(self.hybrid_frame_buffer)}/30 frames"
                cv2.putText(no_signal, buffer_status, 
                           (50, msg_y + 90), cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 255, 255), 1)
        elif self.transmission_mode == 'uart':
            wait_text = "Waiting for UART"
            cv2.putText(no_signal, wait_text, (70, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        elif self.transmission_mode == 'wireless':
            wait_text = "Waiting for Wireless"
            cv2.putText(no_signal, wait_text, (70, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        else:  # hybrid mode
            wait_text = "Waiting for Hybrid Connection"
            cv2.putText(no_signal, wait_text, (50, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
            
        cv2.imshow(WINDOW_NAME, no_signal)
        cv2.waitKey(1)  # 减少等待时间，提高响应速度
    
    def start(self):
        """Start reception"""
        if not self.init_devices():
            print("❌ Device initialization failed")
            return False
        
        self.running = True
        
        # Start receiver thread
        self.receiver_thread_obj = threading.Thread(target=self.receiver_thread)
        self.receiver_thread_obj.daemon = True
        self.receiver_thread_obj.start()
        
        # Start handshake thread for hybrid mode
        if self.transmission_mode == 'hybrid':
            self.handshake_running = True
            self.handshake_thread = threading.Thread(target=self.handshake_thread_func)
            self.handshake_thread.daemon = True
            self.handshake_thread.start()
        
        # Start display thread
        self.display_thread_obj = threading.Thread(target=self.display_thread)
        self.display_thread_obj.daemon = True
        self.display_thread_obj.start()
        
        print("🚀 WebP receiver started successfully")
        print("🔄 Transmission mode: " + self.transmission_mode.upper())
        
        return True
    
    def print_stats(self):
        """Print statistics"""
        avg_compression = np.mean(list(self.stats['compression_ratios'])) if self.stats['compression_ratios'] else 1.0
        avg_packet_size = np.mean(list(self.stats['packet_sizes'])) if self.stats['packet_sizes'] else 0
        current_fps = np.mean(list(self.stats['fps_history'])[-5:]) if len(self.stats['fps_history']) >= 5 else 0
        
        print(f"📊 Receive statistics - Compression:{avg_compression:.1f}x FPS:{current_fps:.1f}fps "
              f"Packet size:{avg_packet_size:.0f}B Received:{self.stats['frames_received']} "
              f"Displayed:{self.stats['frames_displayed']} Errors:{self.stats['errors']}")
    
    def stop(self):
        """Stop reception"""
        print("🛑 Stopping WebP receiver...")
        self.running = False
        
        # Stop handshake thread for hybrid mode
        if self.transmission_mode == 'hybrid' and self.handshake_running:
            self.handshake_running = False
            if self.handshake_thread:
                self.handshake_thread.join(timeout=1.0)
        
        # Stop threads
        if hasattr(self, 'receiver_thread_obj') and self.receiver_thread_obj.is_alive():
            self.receiver_thread_obj.join(timeout=1.0)
        
        if hasattr(self, 'display_thread_obj') and self.display_thread_obj.is_alive():
            self.display_thread_obj.join(timeout=1.0)
        
        # Close serial port
        if self.ser_receiver is not None:
            self.ser_receiver.close()
        
        # Close wireless socket
        if self.wireless_socket is not None:
            self.wireless_socket.close()
        
        print("✅ WebP receiver stopped successfully")
        self.print_stats()
        
        return True

def main():
    """Main function"""
    print("=" * 60)
    print("WebP Video Receiver - UART/Wireless Optimized Video Reception")
    print("=" * 60)
    
    # Select transmission mode
    transmission_mode, baud_rate = select_transmission_mode()
    
    # Create WebP receiver
    receiver = WebPReceiver(transmission_mode=transmission_mode, baud_rate=baud_rate)
    
    # Start reception
    if not receiver.start():
        print("❌ Reception start failed")
        return
    
    # Wait for user to stop
    try:
        while True:
            time.sleep(1)
            receiver.print_stats()
    except KeyboardInterrupt:
        print("\n🛑 User interrupted")
    finally:
        receiver.stop()

if __name__ == "__main__":
    main() 