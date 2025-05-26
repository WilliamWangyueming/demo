#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
WebP性能调优工具
帮助找到最佳的质量和性能平衡点
"""

import cv2
import numpy as np
import time
import io
from PIL import Image
import matplotlib.pyplot as plt

class WebPPerformanceTuner:
    def __init__(self):
        self.cap = None
        self.test_frames = []
        
    def init_camera(self):
        """初始化摄像头"""
        self.cap = cv2.VideoCapture(0)
        if not self.cap.isOpened():
            print("❌ 摄像头初始化失败")
            return False
        
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 320)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 240)
        print("✅ 摄像头初始化成功")
        return True
    
    def capture_test_frames(self, num_frames=5):
        """捕获测试帧"""
        print(f"📸 捕获{num_frames}个测试帧...")
        
        for i in range(num_frames):
            ret, frame = self.cap.read()
            if ret:
                frame_resized = cv2.resize(frame, (320, 240))
                gray_frame = cv2.cvtColor(frame_resized, cv2.COLOR_BGR2GRAY)
                self.test_frames.append(gray_frame)
                print(f"  帧 {i+1}/{num_frames} 已捕获")
                time.sleep(0.2)
        
        print(f"✅ 成功捕获{len(self.test_frames)}个测试帧")
    
    def test_quality_settings(self):
        """测试不同质量设置"""
        print("\n🧪 测试WebP质量设置...")
        
        quality_levels = [30, 40, 50, 60, 70, 80]
        results = []
        
        for quality in quality_levels:
            total_size = 0
            total_time = 0
            
            for frame in self.test_frames:
                # WebP压缩测试
                start_time = time.time()
                pil_image = Image.fromarray(frame)
                buffer = io.BytesIO()
                pil_image.save(buffer, format='WebP', quality=quality, method=6)
                webp_data = buffer.getvalue()
                compress_time = time.time() - start_time
                
                total_size += len(webp_data)
                total_time += compress_time
            
            avg_size = total_size / len(self.test_frames)
            avg_time = total_time / len(self.test_frames)
            original_size = 320 * 240  # 灰度图像大小
            compression_ratio = original_size / avg_size
            
            results.append({
                'quality': quality,
                'size': avg_size,
                'time': avg_time,
                'ratio': compression_ratio
            })
            
            print(f"  Q{quality}: 大小={avg_size:.0f}B, "
                  f"压缩比={compression_ratio:.1f}x, "
                  f"时间={avg_time*1000:.1f}ms")
        
        return results
    
    def test_method_settings(self, quality=50):
        """测试不同压缩方法"""
        print(f"\n🧪 测试WebP压缩方法 (质量={quality})...")
        
        methods = [0, 2, 4, 6]
        method_names = {0: "最快", 2: "快速", 4: "平衡", 6: "最佳"}
        results = []
        
        for method in methods:
            total_size = 0
            total_time = 0
            
            for frame in self.test_frames:
                start_time = time.time()
                pil_image = Image.fromarray(frame)
                buffer = io.BytesIO()
                pil_image.save(buffer, format='WebP', quality=quality, method=method)
                webp_data = buffer.getvalue()
                compress_time = time.time() - start_time
                
                total_size += len(webp_data)
                total_time += compress_time
            
            avg_size = total_size / len(self.test_frames)
            avg_time = total_time / len(self.test_frames)
            original_size = 320 * 240
            compression_ratio = original_size / avg_size
            
            results.append({
                'method': method,
                'name': method_names[method],
                'size': avg_size,
                'time': avg_time,
                'ratio': compression_ratio
            })
            
            print(f"  方法{method}({method_names[method]}): 大小={avg_size:.0f}B, "
                  f"压缩比={compression_ratio:.1f}x, "
                  f"时间={avg_time*1000:.1f}ms")
        
        return results
    
    def calculate_bandwidth_performance(self, results):
        """计算300kbps带宽下的性能"""
        print("\n📊 300kbps带宽性能分析...")
        
        bandwidth_bps = 300000  # 300kbps
        overhead = 24  # 协议头开销
        
        for result in results:
            packet_size = result['size'] + overhead
            max_fps = bandwidth_bps / (packet_size * 8)  # 转换为比特
            
            result['packet_size'] = packet_size
            result['max_fps'] = max_fps
            
            print(f"  Q{result['quality']}: 包大小={packet_size:.0f}B, "
                  f"最大帧率={max_fps:.1f}fps")
    
    def recommend_settings(self, quality_results):
        """推荐最佳设置"""
        print("\n💡 推荐设置:")
        
        # 找出不同场景的最佳设置
        high_fps = max(quality_results, key=lambda x: x['max_fps'])
        balanced = min(quality_results, key=lambda x: abs(x['max_fps'] - 15))  # 目标15fps
        high_quality = max([r for r in quality_results if r['max_fps'] >= 10], 
                          key=lambda x: x['quality'])
        
        print(f"🚀 最高帧率: Q{high_fps['quality']} - {high_fps['max_fps']:.1f}fps")
        print(f"⚖️  平衡设置: Q{balanced['quality']} - {balanced['max_fps']:.1f}fps")
        print(f"🎨 最佳画质: Q{high_quality['quality']} - {high_quality['max_fps']:.1f}fps")
        
        return {
            'high_fps': high_fps,
            'balanced': balanced,
            'high_quality': high_quality
        }
    
    def generate_config_code(self, recommendations):
        """生成配置代码"""
        print("\n📝 配置代码:")
        
        scenarios = [
            ('高帧率优先', recommendations['high_fps']),
            ('平衡设置', recommendations['balanced']),
            ('高画质优先', recommendations['high_quality'])
        ]
        
        for name, config in scenarios:
            print(f"\n# {name}")
            print(f"current_quality = {config['quality']}")
            print(f"target_packet_size = {int(config['packet_size'])}")
            print(f"webp_method = 6  # 可调整为4以提升速度")
            print(f"# 预期帧率: {config['max_fps']:.1f}fps")
    
    def run_full_analysis(self):
        """运行完整分析"""
        print("=== WebP性能调优分析 ===")
        
        if not self.init_camera():
            return
        
        # 捕获测试帧
        self.capture_test_frames(5)
        
        # 测试质量设置
        quality_results = self.test_quality_settings()
        
        # 测试压缩方法
        method_results = self.test_method_settings()
        
        # 计算带宽性能
        self.calculate_bandwidth_performance(quality_results)
        
        # 推荐设置
        recommendations = self.recommend_settings(quality_results)
        
        # 生成配置代码
        self.generate_config_code(recommendations)
        
        # 额外建议
        self.print_optimization_tips()
        
        self.cap.release()
    
    def print_optimization_tips(self):
        """打印优化建议"""
        print("\n🎯 性能优化建议:")
        print("1. 带宽限制场景:")
        print("   - 使用Q30-40获得最高帧率")
        print("   - 设置较小的target_packet_size")
        print("   - 考虑使用method=4而非6")
        
        print("\n2. 画质优先场景:")
        print("   - 使用Q60-70获得更好画质")
        print("   - 接受较低的帧率(8-12fps)")
        print("   - 使用method=6获得最佳压缩")
        
        print("\n3. 实时性要求:")
        print("   - 使用Q40-50平衡设置")
        print("   - 目标15fps左右")
        print("   - 启用动态质量调整")
        
        print("\n4. 系统优化:")
        print("   - 确保串口缓冲区及时清空")
        print("   - 监控错误率，及时进入恢复模式")
        print("   - 使用多线程避免阻塞")

def main():
    """主函数"""
    tuner = WebPPerformanceTuner()
    tuner.run_full_analysis()

if __name__ == "__main__":
    main() 