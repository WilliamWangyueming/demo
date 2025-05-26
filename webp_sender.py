#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebP视频发送端
专为UART串口通信优化的WebP视频发送程序
支持有线UART和网络传输两种模式
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
SENDER_PORT = 'COM7'        # 发送端串口 (根据实际情况修改)

# 网络配置 (网络模式)
NETWORK_HOST = '127.0.0.1'  # 服务器IP (同一台电脑测试用localhost)
NETWORK_PORT = 8888         # 网络端口

# 摄像头配置
CAMERA_INDEX = 0            # 摄像头索引 (通常为0)
FRAME_WIDTH = 320           # 帧宽度
FRAME_HEIGHT = 240          # 帧高度

# 性能模式配置 (可选: high_fps, balanced, high_quality, ultra_fast)
PERFORMANCE_MODE = "balanced"

# 高级配置 (一般不需要修改)
PROTOCOL_MAGIC = b'WEBP'    # 协议魔数
PACKET_TYPE = "WEBP"        # 数据包类型
# ================================================

class NetworkUARTSimulator:
    """网络UART模拟器 - 模拟1MHz UART传输速率"""
    
    def __init__(self, baud_rate):
        self.baud_rate = baud_rate
        self.bytes_per_second = baud_rate / 8  # 每秒字节数
        self.last_send_time = time.time()
        self.bytes_sent_this_second = 0
        
    def calculate_delay(self, data_size):
        """计算传输延迟以模拟UART速率"""
        current_time = time.time()
        
        # 如果是新的一秒，重置计数器
        if current_time - self.last_send_time >= 1.0:
            self.last_send_time = current_time
            self.bytes_sent_this_second = 0
        
        # 计算当前秒内还能发送多少字节
        remaining_bytes = self.bytes_per_second - self.bytes_sent_this_second
        
        if data_size <= remaining_bytes:
            # 可以立即发送
            self.bytes_sent_this_second += data_size
            return 0
        else:
            # 需要等待到下一秒
            wait_time = 1.0 - (current_time - self.last_send_time)
            return wait_time

class WebPSender:
    def __init__(self, performance_mode=PERFORMANCE_MODE, transmission_mode=None, baud_rate=None):
        self.running = False
        self.frame_counter = 0
        self.successful_frames = 0
        self.failed_frames = 0
        
        # 传输相关
        self.transmission_mode = transmission_mode or TRANSMISSION_MODE
        self.baud_rate = baud_rate or BAUD_RATE
        
        # 串口 (UART模式)
        self.ser_sender = None
        
        # 网络 (网络模式)
        self.network_socket = None
        self.network_simulator = None
        if self.transmission_mode == 'network':
            self.network_simulator = NetworkUARTSimulator(self.baud_rate)
        
        # 摄像头
        self.cap = None
        
        # 智能缓冲
        self.frame_buffer = deque(maxlen=100)
        
        # 性能模式配置
        self.performance_mode = performance_mode
        self.setup_performance_mode()
        
        # 错误恢复
        self.last_successful_time = time.time()
        self.error_count = 0
        self.recovery_mode = False
        
        # 统计信息
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
        """根据性能模式设置参数"""
        modes = {
            "high_fps": {
                "quality": 30,
                "target_packet_size": 975,
                "webp_method": 4,  # 更快的压缩
                "fps_delay": 0.026,  # ~38fps
                "description": "高帧率优先 (38fps)"
            },
            "balanced": {
                "quality": 50,
                "target_packet_size": 1261,
                "webp_method": 6,
                "fps_delay": 0.067,  # ~15fps
                "description": "平衡设置 (15fps)"
            },
            "high_quality": {
                "quality": 70,
                "target_packet_size": 1653,
                "webp_method": 6,
                "fps_delay": 0.088,  # ~11fps
                "description": "高画质优先 (11fps)"
            },
            "ultra_fast": {
                "quality": 30,
                "target_packet_size": 975,
                "webp_method": 0,  # 最快压缩
                "fps_delay": 0.02,  # ~50fps
                "description": "极速模式 (50fps)"
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
        
        print(f"🎯 性能模式: {self.mode_description}")
        print(f"   质量: Q{self.current_quality}")
        print(f"   目标包大小: {self.target_packet_size}B")
        print(f"   压缩方法: {self.webp_method}")
        print(f"🚀 传输模式: {self.transmission_mode.upper()}")
        if self.transmission_mode == 'network':
            print(f"   网络速率: {self.baud_rate/1000}K bps (模拟UART)")
        else:
            print(f"   UART速率: {self.baud_rate} bps")
        
    def init_devices(self):
        """初始化设备"""
        print("🚀 初始化WebP视频发送端...")
        print("📊 发送端特性:")
        print("- 基于实测数据的性能配置")
        print("- 黑白图像减少67%数据量")
        print("- WebP压缩比高达104倍")
        print("- 智能动态质量调整")
        print(f"- 支持{self.transmission_mode.upper()}传输模式")
        
        # 初始化摄像头
        self.cap = cv2.VideoCapture(CAMERA_INDEX)
        if not self.cap.isOpened():
            print("❌ 摄像头初始化失败")
            return False
        
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)
        self.cap.set(cv2.CAP_PROP_FPS, 30)
        print(f"✅ 摄像头初始化成功 ({FRAME_WIDTH}x{FRAME_HEIGHT} 灰度)")
        
        # 根据传输模式初始化通信
        if self.transmission_mode == 'uart':
            return self.init_uart()
        else:
            return self.init_network()
    
    def init_uart(self):
        """初始化UART串口"""
        try:
            self.ser_sender = serial.Serial(SENDER_PORT, self.baud_rate, timeout=0.5)
            
            # 清空缓冲区
            self.ser_sender.reset_input_buffer()
            self.ser_sender.reset_output_buffer()
            
            print(f"✅ 发送端串口初始化成功 ({SENDER_PORT} @ {self.baud_rate}bps)")
            return True
        except Exception as e:
            print(f"❌ 发送端串口初始化失败: {e}")
            print(f"请检查串口 {SENDER_PORT} 是否可用")
            return False
    
    def init_network(self):
        """初始化网络连接"""
        try:
            # 创建TCP服务器socket
            self.network_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.network_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            self.network_socket.bind((NETWORK_HOST, NETWORK_PORT))
            self.network_socket.listen(1)
            
            print(f"🌐 网络服务器已启动，等待连接...")
            print(f"   地址: {NETWORK_HOST}:{NETWORK_PORT}")
            print(f"   模拟速率: {self.baud_rate/1000}K bps")
            
            # 等待客户端连接
            self.client_socket, client_address = self.network_socket.accept()
            print(f"✅ 客户端已连接: {client_address}")
            
            return True
        except Exception as e:
            print(f"❌ 网络初始化失败: {e}")
            return False
    
    def encode_frame_webp(self, frame):
        """优化的WebP编码"""
        try:
            # 转换为PIL Image
            pil_image = Image.fromarray(frame)
            
            # WebP压缩 (使用优化参数)
            buffer = io.BytesIO()
            pil_image.save(
                buffer, 
                format='WebP', 
                quality=self.current_quality,
                method=self.webp_method,
                lossless=False,
                exact=False  # 允许质量调整以获得更好压缩
            )
            
            webp_data = buffer.getvalue()
            
            # 计算压缩比 (仅用于统计)
            if len(self.stats['compression_ratios']) % 10 == 0:  # 每10帧计算一次
                original_size = frame.nbytes
                webp_size = len(webp_data)
                compression_ratio = original_size / webp_size
                self.stats['compression_ratios'].append(compression_ratio)
            
            self.stats['packet_sizes'].append(len(webp_data))
            
            return webp_data
            
        except Exception as e:
            print(f"❌ WebP编码失败: {e}")
            return None
    
    def calculate_frame_hash(self, frame_data):
        """计算帧数据哈希用于验证"""
        return hashlib.md5(frame_data).digest()[:4]
    
    def send_packet(self, packet_data, packet_type=PACKET_TYPE):
        """发送数据包"""
        try:
            # 协议：魔数(4) + 帧ID(4) + 长度(4) + 类型(8) + 哈希(4) + 数据
            magic = PROTOCOL_MAGIC
            frame_id = struct.pack('<I', self.frame_counter)
            length = struct.pack('<I', len(packet_data))
            type_bytes = packet_type.ljust(8)[:8].encode('ascii')
            packet_hash = self.calculate_frame_hash(packet_data)
            
            packet = magic + frame_id + length + type_bytes + packet_hash + packet_data
            
            # 根据传输模式发送数据
            if self.transmission_mode == 'uart':
                # UART模式
                self.ser_sender.write(packet)
                self.ser_sender.flush()
            else:
                # 网络模式 - 模拟UART速率
                if self.network_simulator:
                    delay = self.network_simulator.calculate_delay(len(packet))
                    if delay > 0:
                        time.sleep(delay)
                
                # 发送数据
                self.client_socket.sendall(packet)
            
            self.stats['frames_sent'] += 1
            self.stats['bytes_sent'] += len(packet)
            
            return True
            
        except Exception as e:
            print(f"❌ 发送失败: {e}")
            self.stats['errors'] += 1
            self.error_count += 1
            return False
    
    def adjust_quality_smart(self):
        """智能质量调整"""
        if len(self.frame_buffer) >= 10:
            recent_frames = list(self.frame_buffer)[-10:]
            success_rate = sum(1 for f in recent_frames if f['success']) / len(recent_frames)
            avg_size = sum(f['size'] for f in recent_frames) / len(recent_frames)
            
            # 计算实际帧率
            if len(self.stats['fps_history']) >= 5:
                recent_fps = np.mean(list(self.stats['fps_history'])[-5:])
            else:
                recent_fps = 0
            
            # 获取统计信息
            avg_compression = np.mean(list(self.stats['compression_ratios'])) if self.stats['compression_ratios'] else 1.0
            avg_packet_size = np.mean(list(self.stats['packet_sizes'])) if self.stats['packet_sizes'] else 2000
            
            # 智能调整策略
            if success_rate < 0.8 or avg_packet_size > self.target_packet_size * 1.2:
                # 降低质量
                self.current_quality = max(20, self.current_quality - 3)
                self.current_fps_delay = min(0.2, self.current_fps_delay + 0.01)
                print(f"📉 降低质量: Q{self.current_quality}")
            elif success_rate > 0.95 and avg_packet_size < self.target_packet_size * 0.8:
                # 提高质量
                max_quality = 80 if self.performance_mode == "high_quality" else 60
                self.current_quality = min(max_quality, self.current_quality + 2)
                self.current_fps_delay = max(0.02, self.current_fps_delay - 0.005)
                print(f"📈 提高质量: Q{self.current_quality}")
            
            print(f"📊 发送状态: Q={self.current_quality}, 压缩比={avg_compression:.1f}x, "
                  f"包大小={avg_packet_size:.0f}B, 帧率={recent_fps:.1f}fps, "
                  f"成功率={success_rate:.2%}")
    
    def sender_thread(self):
        """发送线程"""
        print("🚀 WebP发送线程启动")
        last_fps_time = time.time()
        frame_count_for_fps = 0
        
        while self.running:
            try:
                # 检查错误恢复
                if time.time() - self.last_successful_time > 2.0 or self.error_count > 5:
                    self.enter_recovery_mode()
                elif self.recovery_mode and self.error_count == 0:
                    self.exit_recovery_mode()
                
                # 捕获帧
                ret, frame = self.cap.read()
                if not ret:
                    time.sleep(0.01)
                    continue
                
                # 预处理 (转换为灰度以减少数据量)
                frame_resized = cv2.resize(frame, (FRAME_WIDTH, FRAME_HEIGHT))
                gray_frame = cv2.cvtColor(frame_resized, cv2.COLOR_BGR2GRAY)
                
                # WebP编码
                encoded_data = self.encode_frame_webp(gray_frame)
                
                if encoded_data:
                    # 发送
                    if self.send_packet(encoded_data):
                        self.frame_counter += 1
                        self.successful_frames += 1
                        frame_count_for_fps += 1
                        self.last_successful_time = time.time()
                        self.error_count = 0
                        
                        # 记录统计
                        self.frame_buffer.append({
                            'id': self.frame_counter,
                            'size': len(encoded_data),
                            'time': time.time(),
                            'success': True
                        })
                        
                        # 计算帧率
                        current_time = time.time()
                        if current_time - last_fps_time >= 1.0:
                            fps = frame_count_for_fps / (current_time - last_fps_time)
                            self.stats['fps_history'].append(fps)
                            last_fps_time = current_time
                            frame_count_for_fps = 0
                    else:
                        self.failed_frames += 1
                
                # 智能调整质量
                if self.frame_counter % 20 == 0:
                    self.adjust_quality_smart()
                
                time.sleep(self.current_fps_delay)
                
            except Exception as e:
                print(f"❌ 发送线程错误: {e}")
                self.error_count += 1
                time.sleep(0.1)
    
    def enter_recovery_mode(self):
        """进入恢复模式"""
        if not self.recovery_mode:
            self.recovery_mode = True
            self.stats['recoveries'] += 1
            print("🔄 进入恢复模式...")
            
            try:
                if self.transmission_mode == 'uart' and self.ser_sender:
                    self.ser_sender.reset_input_buffer()
                    self.ser_sender.reset_output_buffer()
            except:
                pass
            
            # 降低质量和帧率
            self.current_quality = max(20, self.current_quality - 15)
            self.current_fps_delay = min(0.3, self.current_fps_delay + 0.05)
    
    def exit_recovery_mode(self):
        """退出恢复模式"""
        if self.recovery_mode:
            self.recovery_mode = False
            print("✅ 退出恢复模式")
    
    def start(self):
        """启动发送端"""
        print("=== WebP视频发送端 ===")
        print("🎯 发送端特性:")
        print("- 基于实测数据的性能配置")
        print("- 黑白图像减少67%数据量")
        print("- WebP压缩比高达104倍")
        print("- 智能动态质量调整")
        print("- 实时帧率监控")
        print()
        if self.transmission_mode == 'uart':
            print(f"📡 UART配置: {SENDER_PORT} @ {self.baud_rate}bps")
        else:
            print(f"🌐 网络配置: {NETWORK_HOST}:{NETWORK_PORT} @ {self.baud_rate/1000}K bps (模拟UART)")
        print(f"📹 摄像头配置: 索引{CAMERA_INDEX}, {FRAME_WIDTH}x{FRAME_HEIGHT}")
        print()
        
        if not self.init_devices():
            return
        
        self.running = True
        self.last_successful_time = time.time()
        
        # 启动发送线程
        sender = threading.Thread(target=self.sender_thread, daemon=True)
        sender.start()
        
        print("✅ 发送线程已启动")
        print("📡 开始发送WebP视频流...")
        print("按 Ctrl+C 退出")
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
        success_rate = self.successful_frames / max(1, self.successful_frames + self.failed_frames)
        avg_compression = np.mean(list(self.stats['compression_ratios'])) if self.stats['compression_ratios'] else 1.0
        avg_packet_size = np.mean(list(self.stats['packet_sizes'])) if self.stats['packet_sizes'] else 0
        current_fps = np.mean(list(self.stats['fps_history'])[-5:]) if len(self.stats['fps_history']) >= 5 else 0
        
        print(f"📊 发送统计 - 模式:{self.performance_mode} Q:{self.current_quality} "
              f"压缩比:{avg_compression:.1f}x 帧率:{current_fps:.1f}fps "
              f"包大小:{avg_packet_size:.0f}B 发送:{self.stats['frames_sent']} "
              f"成功率:{success_rate:.1%} 状态:{'恢复' if self.recovery_mode else '正常'}")
    
    def stop(self):
        """停止发送端"""
        print("🛑 停止WebP视频发送端...")
        self.running = False
        
        if self.cap:
            self.cap.release()
        
        # 根据传输模式清理连接
        if self.transmission_mode == 'uart':
            if self.ser_sender:
                self.ser_sender.close()
        else:
            try:
                if hasattr(self, 'client_socket'):
                    self.client_socket.close()
                if self.network_socket:
                    self.network_socket.close()
            except:
                pass
        
        print("✅ 发送端已停止")

def main():
    """主函数"""
    import sys
    
    # 获取传输模式
    transmission_mode, baud_rate = select_transmission_mode()
    
    # 支持命令行参数选择性能模式
    performance_modes = ["high_fps", "balanced", "high_quality", "ultra_fast"]
    
    if len(sys.argv) > 1 and sys.argv[1] in performance_modes:
        mode = sys.argv[1]
    else:
        mode = PERFORMANCE_MODE  # 使用配置的默认模式
    
    print(f"启动模式: {mode}")
    print("可用模式: high_fps, balanced, high_quality, ultra_fast")
    print("使用方法: python webp_sender.py [mode]")
    print()
    
    sender = WebPSender(performance_mode=mode, transmission_mode=transmission_mode, baud_rate=baud_rate)
    sender.start()

if __name__ == "__main__":
    main() 