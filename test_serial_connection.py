#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
串口连接测试程序
"""

import serial
import time
import threading

def test_serial_connection():
    """测试串口连接"""
    print("=== 串口连接测试 ===")
    
    # 测试发送端串口 (COM7)
    print("\n1. 测试发送端串口 COM7...")
    try:
        ser_sender = serial.Serial(
            port='COM7',
            baudrate=300000,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=1.0
        )
        print("✅ COM7 连接成功")
        print(f"   - 端口: {ser_sender.port}")
        print(f"   - 波特率: {ser_sender.baudrate}")
        print(f"   - 是否打开: {ser_sender.is_open}")
        ser_sender.close()
    except Exception as e:
        print(f"❌ COM7 连接失败: {e}")
        return False
    
    # 测试接收端串口 (COM8)
    print("\n2. 测试接收端串口 COM8...")
    try:
        ser_receiver = serial.Serial(
            port='COM8',
            baudrate=300000,
            bytesize=serial.EIGHTBITS,
            parity=serial.PARITY_NONE,
            stopbits=serial.STOPBITS_ONE,
            timeout=1.0
        )
        print("✅ COM8 连接成功")
        print(f"   - 端口: {ser_receiver.port}")
        print(f"   - 波特率: {ser_receiver.baudrate}")
        print(f"   - 是否打开: {ser_receiver.is_open}")
        ser_receiver.close()
    except Exception as e:
        print(f"❌ COM8 连接失败: {e}")
        return False
    
    return True

def test_serial_communication():
    """测试串口通信"""
    print("\n=== 串口通信测试 ===")
    print("这个测试会从COM7发送数据到COM8")
    print("请确保你的USB-to-TTL设备已正确连接")
    
    try:
        # 打开两个串口
        ser_sender = serial.Serial('COM7', 300000, timeout=1.0)
        ser_receiver = serial.Serial('COM8', 300000, timeout=1.0)
        
        print("✅ 两个串口都已打开")
        
        # 清空缓冲区
        ser_sender.reset_input_buffer()
        ser_sender.reset_output_buffer()
        ser_receiver.reset_input_buffer()
        ser_receiver.reset_output_buffer()
        
        # 发送测试数据
        test_message = b"Hello UART Test 12345"
        print(f"\n📤 从COM7发送: {test_message}")
        ser_sender.write(test_message)
        ser_sender.flush()  # 确保数据发送完毕
        
        # 等待一下
        time.sleep(0.1)
        
        # 尝试接收
        print("📥 在COM8等待接收...")
        received_data = ser_receiver.read(len(test_message))
        
        if received_data:
            print(f"✅ COM8接收到: {received_data}")
            if received_data == test_message:
                print("🎉 数据完全匹配！串口通信正常")
                result = True
            else:
                print("⚠️  数据不匹配，可能有传输错误")
                result = False
        else:
            print("❌ COM8没有接收到任何数据")
            print("   可能原因:")
            print("   1. USB-to-TTL设备没有正确连接")
            print("   2. 线路连接错误 (TX-RX, RX-TX)")
            print("   3. 波特率不匹配")
            result = False
        
        # 关闭串口
        ser_sender.close()
        ser_receiver.close()
        
        return result
        
    except Exception as e:
        print(f"❌ 串口通信测试失败: {e}")
        return False

def main():
    """主函数"""
    print("开始串口测试...")
    
    # 测试连接
    if not test_serial_connection():
        print("\n❌ 串口连接测试失败，请检查设备")
        return
    
    # 测试通信
    if test_serial_communication():
        print("\n🎉 串口测试完全成功！")
        print("你的UART连接工作正常，可以进行视频传输")
    else:
        print("\n❌ 串口通信测试失败")
        print("请检查:")
        print("1. USB-to-TTL设备是否正确连接")
        print("2. 线路连接: 设备1的TX连接设备2的RX，设备1的RX连接设备2的TX")
        print("3. 共同接地 (GND连接)")

if __name__ == "__main__":
    main() 