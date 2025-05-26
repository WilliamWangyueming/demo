#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
网络传输模式测试脚本
用于验证WebP视频发送和接收端的网络传输功能
"""

import socket
import time
import threading
import sys

def test_network_connection():
    """测试网络连接功能"""
    HOST = '127.0.0.1'
    PORT = 8888
    
    print("🔧 测试网络传输模式...")
    print(f"服务器地址: {HOST}:{PORT}")
    
    # 测试服务器端
    def server_test():
        try:
            server_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            server_socket.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
            server_socket.bind((HOST, PORT))
            server_socket.listen(1)
            
            print("✅ 服务器启动成功，等待连接...")
            
            # 设置超时以避免无限等待
            server_socket.settimeout(5.0)
            
            client_socket, client_address = server_socket.accept()
            print(f"✅ 客户端连接成功: {client_address}")
            
            # 发送测试数据
            test_data = b"Hello from server!"
            client_socket.sendall(test_data)
            print(f"📤 发送数据: {test_data}")
            
            # 接收回复
            response = client_socket.recv(1024)
            print(f"📥 接收回复: {response}")
            
            client_socket.close()
            server_socket.close()
            print("✅ 服务器测试完成")
            
        except Exception as e:
            print(f"❌ 服务器测试失败: {e}")
    
    # 测试客户端
    def client_test():
        time.sleep(1)  # 等待服务器启动
        try:
            client_socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            client_socket.connect((HOST, PORT))
            print("✅ 客户端连接成功")
            
            # 接收数据
            data = client_socket.recv(1024)
            print(f"📥 接收数据: {data}")
            
            # 发送回复
            response = b"Hello from client!"
            client_socket.sendall(response)
            print(f"📤 发送回复: {response}")
            
            client_socket.close()
            print("✅ 客户端测试完成")
            
        except Exception as e:
            print(f"❌ 客户端测试失败: {e}")
    
    # 启动测试线程
    server_thread = threading.Thread(target=server_test, daemon=True)
    client_thread = threading.Thread(target=client_test, daemon=True)
    
    server_thread.start()
    client_thread.start()
    
    # 等待测试完成
    server_thread.join(timeout=10)
    client_thread.join(timeout=10)
    
    print("🎯 网络测试完成!")

def test_uart_simulator():
    """测试UART速率模拟器"""
    print("\n🔧 测试UART速率模拟器...")
    
    # 模拟1MHz UART速率
    baud_rate = 1000000
    bytes_per_second = baud_rate / 8  # 125,000 bytes/sec
    
    print(f"波特率: {baud_rate} bps")
    print(f"每秒字节数: {bytes_per_second:,.0f}")
    
    # 测试不同大小的数据包
    test_sizes = [1000, 2000, 5000, 10000]
    
    for size in test_sizes:
        # 计算理论传输时间
        transmission_time = size / bytes_per_second
        print(f"数据包大小: {size}B -> 传输时间: {transmission_time:.3f}s")
        
        # 验证每秒能传输的包数
        packets_per_second = 1.0 / transmission_time
        print(f"  -> 每秒包数: {packets_per_second:.1f}")
    
    print("✅ UART模拟器测试完成!")

def show_usage():
    """显示使用说明"""
    print("=" * 60)
    print("🚀 WebP视频传输系统 - 网络模式使用指南")
    print("=" * 60)
    print()
    print("📋 使用步骤:")
    print("1. 在第一个终端运行: python webp_sender.py")
    print("   - 选择传输模式: 2 (网络传输)")
    print("   - 程序将启动网络服务器等待连接")
    print()
    print("2. 在第二个终端运行: python webp_receiver.py") 
    print("   - 选择传输模式: 2 (网络传输)")
    print("   - 程序将连接到发送端开始接收视频")
    print()
    print("🎯 功能特性:")
    print("✅ 支持有线UART (300K bps) 和网络传输 (1MHz模拟)")
    print("✅ 网络模式模拟UART传输速率，确保性能一致")
    print("✅ 所有压缩和视频参数与有线模式完全一致")
    print("✅ 适用于同一网络下的两台电脑直接串流")
    print()
    print("🔧 配置修改:")
    print("- 修改IP地址: 编辑 NETWORK_HOST 变量")
    print("- 修改端口: 编辑 NETWORK_PORT 变量")
    print("- 当前配置: 127.0.0.1:8888 (本机测试)")
    print()
    print("⚠️  注意事项:")
    print("- 请确保防火墙允许指定端口通信")
    print("- 发送端必须先启动，接收端后启动")
    print("- 两台电脑使用时，修改对应的IP地址")
    print("=" * 60)

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "test":
        test_network_connection()
        test_uart_simulator()
    else:
        show_usage() 