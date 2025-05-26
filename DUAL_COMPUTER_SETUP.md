# 双机WebP视频传输配置指南

## 🎯 系统架构

```
发送端电脑                    接收端电脑
┌─────────────────┐          ┌─────────────────┐
│  webp_sender.py │          │ webp_receiver.py│
│                 │          │                 │
│  📹 摄像头       │          │  📺 显示器       │
│  📡 COM7        │ =======> │  📡 COM8        │
│                 │  UART    │                 │
└─────────────────┘  300kbps └─────────────────┘
```

## 🔧 配置步骤

### 1. 发送端电脑配置

#### 编辑 `webp_sender.py` 配置参数：
```python
# ==================== 配置参数 ====================
# 串口配置
SENDER_PORT = 'COM7'        # 修改为实际的发送端串口
BAUD_RATE = 300000          # 波特率 300kbps

# 摄像头配置
CAMERA_INDEX = 0            # 摄像头索引 (通常为0)
FRAME_WIDTH = 320           # 帧宽度
FRAME_HEIGHT = 240          # 帧高度

# 性能模式配置
PERFORMANCE_MODE = "balanced"  # 可选: high_fps, balanced, high_quality, ultra_fast
```

#### 常见串口配置：
- **Windows**: `COM1`, `COM2`, `COM3`, ...
- **Linux**: `/dev/ttyUSB0`, `/dev/ttyUSB1`, `/dev/ttyACM0`, ...
- **macOS**: `/dev/cu.usbserial-*`, `/dev/cu.usbmodem*`

### 2. 接收端电脑配置

#### 编辑 `webp_receiver.py` 配置参数：
```python
# ==================== 配置参数 ====================
# 串口配置
RECEIVER_PORT = 'COM8'      # 修改为实际的接收端串口
BAUD_RATE = 300000          # 波特率 300kbps (必须与发送端一致)

# 显示配置
WINDOW_NAME = 'WebP Video Receiver'  # 显示窗口名称
SHOW_STATS = True           # 是否显示统计信息
AUTO_RESIZE = True          # 是否自动调整窗口大小

# 缓冲配置
FRAME_BUFFER_SIZE = 3       # 帧缓冲区大小
STATS_BUFFER_SIZE = 50      # 统计缓冲区大小
```

### 3. 硬件连接

#### UART连接方式：
```
发送端 USB-TTL    <==>    接收端 USB-TTL
    TX (发送)     ------>     RX (接收)
    RX (接收)     <------     TX (发送)
    GND (地)      ------      GND (地)
```

#### 注意事项：
- 确保两端波特率一致 (300000)
- 检查TX/RX交叉连接
- 确保共地连接
- 使用质量好的USB-TTL转换器

## 🚀 运行步骤

### 1. 安装依赖 (两台电脑都需要)
```bash
pip install -r requirements.txt
```

### 2. 测试串口连接
```bash
# 发送端电脑
python test_serial_connection.py

# 接收端电脑  
python test_serial_connection.py
```

### 3. 启动系统

#### 先启动接收端：
```bash
# 接收端电脑
python webp_receiver.py
```

#### 再启动发送端：
```bash
# 发送端电脑 - 默认平衡模式
python webp_sender.py

# 或选择其他性能模式
python webp_sender.py high_fps      # 高帧率模式
python webp_sender.py high_quality  # 高画质模式
python webp_sender.py ultra_fast    # 极速模式
```

## 📊 性能模式选择

| 模式 | 帧率 | 质量 | 包大小 | 适用场景 |
|------|------|------|--------|----------|
| ultra_fast | 50fps | Q30 | 975B | 低延迟要求 |
| high_fps | 38fps | Q30 | 975B | 实时监控 |
| balanced | 15fps | Q50 | 1261B | 一般应用 |
| high_quality | 11fps | Q70 | 1653B | 图像分析 |

## 🛠️ 故障排除

### 1. 串口问题

#### 查看可用串口：
```python
import serial.tools.list_ports
ports = serial.tools.list_ports.comports()
for port in ports:
    print(f"{port.device}: {port.description}")
```

#### 常见错误：
- `Serial port not found`: 检查串口名称是否正确
- `Permission denied`: Linux/macOS需要串口权限
- `Port already in use`: 关闭其他占用串口的程序

### 2. 摄像头问题

#### 测试摄像头：
```python
import cv2
cap = cv2.VideoCapture(0)  # 尝试不同索引 0,1,2...
if cap.isOpened():
    print("摄像头可用")
else:
    print("摄像头不可用")
cap.release()
```

### 3. 网络延迟问题

#### 优化建议：
- 使用 `ultra_fast` 或 `high_fps` 模式
- 减小 `FRAME_BUFFER_SIZE` 到 1-2
- 检查UART连接质量
- 确保USB-TTL转换器支持300kbps

### 4. 画质问题

#### 优化建议：
- 使用 `high_quality` 模式
- 增大 `FRAME_WIDTH` 和 `FRAME_HEIGHT`
- 检查光照条件
- 确保摄像头焦距正确

## 📋 配置检查清单

### 发送端检查：
- [ ] 串口名称正确 (`SENDER_PORT`)
- [ ] 摄像头索引正确 (`CAMERA_INDEX`)
- [ ] 摄像头工作正常
- [ ] 串口连接正常
- [ ] 性能模式合适

### 接收端检查：
- [ ] 串口名称正确 (`RECEIVER_PORT`)
- [ ] 波特率一致 (`BAUD_RATE`)
- [ ] 显示配置合适
- [ ] 串口连接正常

### 硬件检查：
- [ ] TX/RX交叉连接
- [ ] GND共地连接
- [ ] USB-TTL转换器工作正常
- [ ] 线缆连接牢固

## 🎯 最佳实践

### 1. 启动顺序
1. 先启动接收端 (`webp_receiver.py`)
2. 等待显示 "NO SIGNAL" 窗口
3. 再启动发送端 (`webp_sender.py`)
4. 观察连接建立

### 2. 性能调优
- 从 `balanced` 模式开始测试
- 根据实际需求调整模式
- 观察统计信息进行优化
- 定期运行性能分析工具

### 3. 监控指标
- **发送端**: 帧率、压缩比、包大小、成功率
- **接收端**: 帧率、解码成功率、显示延迟
- **整体**: 端到端延迟、错误率

### 4. 错误恢复
- 系统具有自动错误恢复功能
- 发送端会自动调整质量
- 接收端会显示连接状态
- 出现问题时重启程序即可

## 📞 技术支持

### 常用命令：
```bash
# 查看串口设备 (Linux)
ls /dev/tty*

# 查看USB设备 (Linux)
lsusb

# 查看串口设备 (Windows)
mode

# 测试串口通信
python test_serial_connection.py
```

### 日志分析：
- 发送端显示发送统计和质量调整
- 接收端显示接收统计和解码状态
- 注意观察错误信息和恢复过程

通过这个双机配置，你可以实现稳定的300kbps WebP视频传输！ 