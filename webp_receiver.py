#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebP视频接收端
专为UART串口通信优化的WebP视频接收程序
支持有线UART和网络传输两种模式
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

# ==================== 传输模式选择 ====================
def select_transmission_mode():
    """选择传输模式"""
    print("🔧 请选择传输模式:")
    print("1. 有线UART (300,000 bps)")
    print("2. 网络传输 (模拟1MHz UART)")
    
    while True:
        choice = input("请输入选择 (1或2): ").strip()
        if choice == '1':
            return 'uart', 300000
        elif choice == '2':
            return 'network', 1000000  # 1MHz模拟速率
        else:
            print("❌ 无效选择，请输入1或2")

# 默认配置 (将在主函数中选择)
TRANSMISSION_MODE = 'uart'
BAUD_RATE = 300000

# ==================== 配置参数 ====================
# 串口配置 (UART模式)
RECEIVER_PORT = 'COM8'      # 接收端串口 (根据实际情况修改)

# 网络配置 (网络模式)
NETWORK_HOST = '127.0.0.1'  # 服务器IP (同一台电脑测试用localhost)
NETWORK_PORT = 8888         # 网络端口

# 显示配置
WINDOW_NAME = 'WebP Video Receiver'  # 显示窗口名称
SHOW_STATS = True           # 是否显示统计信息
AUTO_RESIZE = True          # 是否自动调整窗口大小

# 缓冲配置
FRAME_BUFFER_SIZE = 3       # 帧缓冲区大小
STATS_BUFFER_SIZE = 50      # 统计缓冲区大小

# 高级配置 (一般不需要修改)
PROTOCOL_MAGIC = b'WEBP'    # 协议魔数 (必须与发送端一致)
PACKET_TYPE = "WEBP"        # 数据包类型
RECEIVE_TIMEOUT = 0.05      # 接收超时时间
# ================================================

class WebPReceiver:
    def __init__(self, transmission_mode=None, baud_rate=None):
        self.running = False
        
        # 传输相关
        self.transmission_mode = transmission_mode or TRANSMISSION_MODE
        self.baud_rate = baud_rate or BAUD_RATE
        
        # 串口 (UART模式)
        self.ser_receiver = None
        
        # 网络 (网络模式)
        self.network_socket = None
        
        # 智能缓冲
        self.received_frames = queue.Queue(maxsize=FRAME_BUFFER_SIZE)
        
        # 错误恢复
        self.last_successful_time = time.time()
        self.error_count = 0
        
        # 统计信息
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
        """初始化设备"""
        print("🚀 初始化WebP视频接收端...")
        print("📊 接收端特性:")
        print("- WebP解码显示")
        print("- 智能缓冲防丢帧")
        print("- 实时统计监控")
        print("- 错误自动恢复")
        print(f"- 支持{self.transmission_mode.upper()}传输模式")
        
        # 根据传输模式初始化通信
        if self.transmission_mode == 'uart':
            return self.init_uart()
        else:
            return self.init_network()
    
    def init_uart(self):
        """初始化UART串口"""
        try:
            self.ser_receiver = serial.Serial(RECEIVER_PORT, self.baud_rate, timeout=RECEIVE_TIMEOUT)
            
            # 清空缓冲区
            self.ser_receiver.reset_input_buffer()
            self.ser_receiver.reset_output_buffer()
            
            print(f"✅ 接收端串口初始化成功 ({RECEIVER_PORT} @ {self.baud_rate}bps)")
            return True
        except Exception as e:
            print(f"❌ 接收端串口初始化失败: {e}")
            print(f"请检查串口 {RECEIVER_PORT} 是否可用")
            return False
    
    def init_network(self):
        """初始化网络连接"""
        try:
            # 创建TCP客户端socket
            self.network_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            
            print(f"🌐 正在连接网络发送端...")
            print(f"   地址: {NETWORK_HOST}:{NETWORK_PORT}")
            print(f"   模拟速率: {self.baud_rate/1000}K bps")
            
            # 连接到服务器
            self.network_socket.connect((NETWORK_HOST, NETWORK_PORT))
            print(f"✅ 已连接到发送端: {NETWORK_HOST}:{NETWORK_PORT}")
            
            # 设置接收超时
            self.network_socket.settimeout(RECEIVE_TIMEOUT)
            
            return True
        except Exception as e:
            print(f"❌ 网络连接失败: {e}")
            return False
    
    def decode_frame_webp(self, webp_data):
        """WebP解码帧"""
        try:
            # 使用PIL解码WebP
            pil_image = Image.open(io.BytesIO(webp_data))
            frame = np.array(pil_image)
            
            # 确保是灰度图像
            if len(frame.shape) == 3:
                frame = cv2.cvtColor(frame, cv2.COLOR_RGB2GRAY)
            
            return frame
            
        except Exception as e:
            print(f"❌ WebP解码失败: {e}")
            return None
    
    def calculate_frame_hash(self, frame_data):
        """计算帧数据哈希用于验证"""
        return hashlib.md5(frame_data).digest()[:4]
    
    def receive_packet(self):
        """接收数据包"""
        try:
            # 根据传输模式选择接收方法
            if self.transmission_mode == 'uart':
                return self.receive_packet_uart()
            else:
                return self.receive_packet_network()
        except Exception as e:
            print(f"❌ 接收失败: {e}")
            self.stats['errors'] += 1
            self.error_count += 1
            return None, None
    
    def receive_packet_uart(self):
        """UART方式接收数据包"""
        # 查找魔数
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
        
        # 确保有完整的头部 (4+4+4+8+4=24)
        while len(buffer) < 24:
            byte = self.ser_receiver.read(1)
            if not byte:
                return None, None
            buffer.extend(byte)
        
        # 解析头部
        frame_id = struct.unpack('<I', buffer[4:8])[0]
        packet_length = struct.unpack('<I', buffer[8:12])[0]
        packet_type = buffer[12:20].decode('ascii').strip()
        expected_hash = buffer[20:24]
        
        # 验证包长度
        if packet_length > 10000 or packet_length < 50:
            print(f"⚠️  异常包长度: {packet_length}")
            return None, None
        
        # 读取剩余数据
        remaining = packet_length - (len(buffer) - 24)
        while remaining > 0:
            chunk = self.ser_receiver.read(min(remaining, 1024))
            if not chunk:
                print(f"⚠️  数据不完整: 还需{remaining}字节")
                return None, None
            buffer.extend(chunk)
            remaining -= len(chunk)
        
        # 提取包数据
        packet_data = bytes(buffer[24:24+packet_length])
        
        # 验证哈希
        actual_hash = self.calculate_frame_hash(packet_data)
        if actual_hash != expected_hash:
            print(f"⚠️  包{frame_id}哈希校验失败")
            self.stats['errors'] += 1
            return None, None
        
        self.stats['frames_received'] += 1
        self.stats['bytes_received'] += len(packet_data)
        self.stats['packet_sizes'].append(len(packet_data))
        self.last_successful_time = time.time()
        self.error_count = 0
        
        return packet_data, packet_type
    
    def receive_packet_network(self):
        """网络方式接收数据包"""
        # 查找魔数
        buffer = bytearray()
        magic_found = False
        
        start_time = time.time()
        while not magic_found and (time.time() - start_time) < 0.1:
            try:
                byte = self.network_socket.recv(1)
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
        
        # 确保有完整的头部 (4+4+4+8+4=24)
        while len(buffer) < 24:
            try:
                byte = self.network_socket.recv(1)
                if not byte:
                    return None, None
                buffer.extend(byte)
            except Exception:
                return None, None
        
        # 解析头部
        frame_id = struct.unpack('<I', buffer[4:8])[0]
        packet_length = struct.unpack('<I', buffer[8:12])[0]
        packet_type = buffer[12:20].decode('ascii').strip()
        expected_hash = buffer[20:24]
        
        # 验证包长度
        if packet_length > 10000 or packet_length < 50:
            print(f"⚠️  异常包长度: {packet_length}")
            return None, None
        
        # 读取剩余数据
        remaining = packet_length - (len(buffer) - 24)
        while remaining > 0:
            try:
                chunk = self.network_socket.recv(min(remaining, 1024))
                if not chunk:
                    print(f"⚠️  数据不完整: 还需{remaining}字节")
                    return None, None
                buffer.extend(chunk)
                remaining -= len(chunk)
            except Exception:
                print(f"⚠️  网络接收中断: 还需{remaining}字节")
                return None, None
        
        # 提取包数据
        packet_data = bytes(buffer[24:24+packet_length])
        
        # 验证哈希
        actual_hash = self.calculate_frame_hash(packet_data)
        if actual_hash != expected_hash:
            print(f"⚠️  包{frame_id}哈希校验失败")
            self.stats['errors'] += 1
            return None, None
        
        self.stats['frames_received'] += 1
        self.stats['bytes_received'] += len(packet_data)
        self.stats['packet_sizes'].append(len(packet_data))
        self.last_successful_time = time.time()
        self.error_count = 0
        
        return packet_data, packet_type
    
    def receiver_thread(self):
        """接收线程"""
        print("🚀 WebP接收线程启动")
        
        while self.running:
            try:
                packet_data, packet_type = self.receive_packet()
                if packet_data and packet_type == PACKET_TYPE:
                    # WebP解码
                    frame = self.decode_frame_webp(packet_data)
                    if frame is not None:
                        # 计算压缩比
                        original_size = frame.nbytes
                        compressed_size = len(packet_data)
                        compression_ratio = original_size / compressed_size
                        self.stats['compression_ratios'].append(compression_ratio)
                        
                        # 非阻塞放入队列
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
                print(f"❌ 接收线程错误: {e}")
                time.sleep(0.01)
    
    def display_thread(self):
        """显示线程"""
        print("🚀 WebP显示线程启动")
        
        try:
            if AUTO_RESIZE:
                cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_AUTOSIZE)
            else:
                cv2.namedWindow(WINDOW_NAME, cv2.WINDOW_NORMAL)
            
            print(f"✅ OpenCV窗口创建成功: {WINDOW_NAME}")
        except Exception as e:
            print(f"❌ OpenCV窗口创建失败: {e}")
            return
        
        last_fps_time = time.time()
        frame_count_for_fps = 0
        
        while self.running:
            try:
                frame = self.received_frames.get(timeout=0.5)
                
                if frame is not None:
                    # 转换为彩色用于显示信息
                    frame_bgr = cv2.cvtColor(frame, cv2.COLOR_GRAY2BGR)
                    
                    # 添加状态信息
                    if SHOW_STATS:
                        self.add_status_overlay(frame_bgr)
                    
                    # 显示
                    cv2.imshow(WINDOW_NAME, frame_bgr)
                    self.stats['frames_displayed'] += 1
                    frame_count_for_fps += 1
                    
                    # 计算显示帧率
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
                print(f"❌ 显示线程错误: {e}")
                time.sleep(0.1)
        
        cv2.destroyAllWindows()
    
    def add_status_overlay(self, frame):
        """添加状态信息覆盖层"""
        font = cv2.FONT_HERSHEY_SIMPLEX
        font_scale = 0.4
        thickness = 1
        
        avg_compression = np.mean(list(self.stats['compression_ratios'])) if self.stats['compression_ratios'] else 1.0
        avg_packet_size = np.mean(list(self.stats['packet_sizes'])) if self.stats['packet_sizes'] else 0
        current_fps = np.mean(list(self.stats['fps_history'])[-3:]) if len(self.stats['fps_history']) >= 3 else 0
        
        # 根据传输模式显示不同信息
        if self.transmission_mode == 'uart':
            port_info = f"Port: {RECEIVER_PORT}"
        else:
            port_info = f"Network: {NETWORK_HOST}:{NETWORK_PORT}"
            
        info_lines = [
            f"Receiver: WebP",
            port_info,
            f"Compression: {avg_compression:.1f}x",
            f"FPS: {current_fps:.1f}",
            f"Packet: {avg_packet_size:.0f}B",
            f"Received: {self.stats['frames_received']}",
            f"Displayed: {self.stats['frames_displayed']}",
            f"Errors: {self.stats['errors']}"
        ]
        
        color = (0, 255, 0)  # 绿色
        
        for i, line in enumerate(info_lines):
            y = 15 + i * 15
            cv2.putText(frame, line, (5, y), font, font_scale, color, thickness)
    
    def show_no_signal(self):
        """显示无信号状态"""
        no_signal = np.zeros((240, 320, 3), dtype=np.uint8)
        cv2.putText(no_signal, "NO SIGNAL", (80, 120), cv2.FONT_HERSHEY_SIMPLEX, 1, (0, 0, 255), 2)
        
        if self.transmission_mode == 'uart':
            wait_text = f"Waiting on {RECEIVER_PORT}"
        else:
            wait_text = f"Waiting on {NETWORK_HOST}:{NETWORK_PORT}"
            
        cv2.putText(no_signal, wait_text, (50, 150), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)
        cv2.imshow(WINDOW_NAME, no_signal)
        cv2.waitKey(100)
    
    def start(self):
        """启动接收端"""
        print("=== WebP视频接收端 ===")
        print("🎯 接收端特性:")
        print("- WebP解码显示")
        print("- 智能缓冲防丢帧")
        print("- 实时统计监控")
        print("- 错误自动恢复")
        print()
        if self.transmission_mode == 'uart':
            print(f"📡 串口配置: {RECEIVER_PORT} @ {self.baud_rate}bps")
        else:
            print(f"🌐 网络配置: {NETWORK_HOST}:{NETWORK_PORT} @ {self.baud_rate/1000}K bps (模拟UART)")
        print(f"📺 显示配置: {WINDOW_NAME}")
        print()
        
        if not self.init_devices():
            return
        
        self.running = True
        self.last_successful_time = time.time()
        
        # 启动线程
        receiver = threading.Thread(target=self.receiver_thread, daemon=True)
        display = threading.Thread(target=self.display_thread, daemon=True)
        
        receiver.start()
        display.start()
        
        print("✅ 所有线程已启动")
        print("📺 WebP视频窗口应该已打开")
        print("按 'q' 键或 Ctrl+C 退出")
        print()
        
        try:
            while self.running:
                time.sleep(5)
                self.print_stats()
        except KeyboardInterrupt:
            print("\n收到停止信号...")
        
        self.stop()
    
    def print_stats(self):
        """打印统计信息"""
        avg_compression = np.mean(list(self.stats['compression_ratios'])) if self.stats['compression_ratios'] else 1.0
        avg_packet_size = np.mean(list(self.stats['packet_sizes'])) if self.stats['packet_sizes'] else 0
        current_fps = np.mean(list(self.stats['fps_history'])[-5:]) if len(self.stats['fps_history']) >= 5 else 0
        
        print(f"📊 接收统计 - 压缩比:{avg_compression:.1f}x 帧率:{current_fps:.1f}fps "
              f"包大小:{avg_packet_size:.0f}B 接收:{self.stats['frames_received']} "
              f"显示:{self.stats['frames_displayed']} 错误:{self.stats['errors']}")
    
    def stop(self):
        """停止接收端"""
        print("🛑 停止WebP视频接收端...")
        self.running = False
        
        # 根据传输模式清理连接
        if self.transmission_mode == 'uart':
            if self.ser_receiver:
                self.ser_receiver.close()
        else:
            if self.network_socket:
                try:
                    self.network_socket.close()
                except:
                    pass
        
        cv2.destroyAllWindows()
        print("✅ 接收端已停止")

def main():
    """主函数"""
    # 获取传输模式
    transmission_mode, baud_rate = select_transmission_mode()
    
    print("启动WebP视频接收端")
    print("使用方法: python webp_receiver.py")
    print()
    
    receiver = WebPReceiver(transmission_mode=transmission_mode, baud_rate=baud_rate)
    receiver.start()

if __name__ == "__main__":
    main() 