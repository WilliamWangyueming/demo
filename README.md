# WebP Video Transmission System

A high-performance WebP video transmission system optimized for UART serial communication, supporting both wired UART and wireless transmission modes.

## ✨ Features

### 🚀 Core Capabilities
- **Dual Mode Support**: Wired UART (300K bps) and Wireless transmission (up to 5MHz)
- **Advanced Compression**: WebP encoding with compression ratios up to 104x
- **Smart Optimization**: Dynamic quality adjustment and intelligent performance scaling
- **Real-time Monitoring**: Live statistics display and frame rate monitoring
- **Error Recovery**: Automatic error detection and recovery mechanisms

### 📊 Performance Highlights
- **Ultra-low Latency**: Optimized for real-time video streaming
- **Data Efficiency**: Grayscale conversion reduces data by 67%
- **Smart Buffering**: Prevents frame loss with intelligent queue management
- **Adaptive Quality**: Dynamic quality adjustment based on transmission conditions

## 🛠️ System Requirements

### Hardware
- **Camera**: USB camera (index 0 by default)
- **Serial Ports**: For UART mode communication
- **Network**: For wireless mode communication

### Software Dependencies
```bash
pip install -r requirements.txt
```

Required packages:
- opencv-python>=4.5.0
- pyserial>=3.5
- pillow>=8.0.0
- numpy>=1.20.0

## 🚀 Quick Start

### 1. Installation
```bash
git clone <repository-url>
cd webp-video-transmission
pip install -r requirements.txt
```

### 2. Basic Usage

#### Sender (Video Source)
```bash
python webp_sender.py
```

#### Receiver (Display)
```bash
python webp_receiver.py
```

### 3. Mode Selection
When starting either program, you'll be prompted to select transmission mode:
1. **Wired UART** (300,000 bps) - Traditional serial communication
2. **Wireless transmission** - High-speed wireless mode with multiple speed options

## 📡 Transmission Modes

### UART Mode (Wired)
- **Speed**: 300,000 bps
- **Connection**: Direct serial cable connection
- **Ports**: COM7 (sender), COM8 (receiver) - configurable
- **Use Case**: Reliable point-to-point communication

### Wireless Mode
- **Speed Options**: 1MHz / 2MHz / 5MHz / Custom
- **Connection**: TCP/IP over WiFi/Ethernet
- **Port**: 8888 (configurable)
- **Use Case**: Flexible wireless communication

#### Wireless Speed Modes:
- **1MHz (Standard)**: Balanced performance, ~25fps
- **2MHz (High Speed)**: Enhanced FPS and quality, ~30fps  
- **5MHz (Ultra Speed)**: Maximum performance
- **Custom**: User-defined speed (100K-10M bps)

## ⚙️ Configuration

### Performance Modes
Available via command line parameter:
```bash
python webp_sender.py [mode]
```

**Available modes:**
- `balanced` - Default balanced settings (15→25fps wireless)
- `high_fps` - High frame rate priority (38→60fps wireless)
- `high_quality` - High quality priority (11→37fps wireless)  
- `ultra_fast` - Maximum speed mode (50→60fps wireless)

### Key Configuration Variables

#### Sender (`webp_sender.py`)
```python
# Serial Configuration
SENDER_PORT = 'COM7'

# Wireless Configuration  
WIRELESS_HOST = '127.0.0.1'
WIRELESS_PORT = 8888

# Camera Configuration
CAMERA_INDEX = 0
FRAME_WIDTH = 320
FRAME_HEIGHT = 240

# Performance Mode
PERFORMANCE_MODE = "balanced"
```

#### Receiver (`webp_receiver.py`)
```python
# Serial Configuration
RECEIVER_PORT = 'COM8'

# Wireless Configuration
WIRELESS_HOST = '127.0.0.1'  
WIRELESS_PORT = 8888

# Display Configuration
WINDOW_NAME = 'WebP Video Receiver'
SHOW_STATS = True
AUTO_RESIZE = True
```

## 🔧 Advanced Features

### Smart Quality Adjustment
The system automatically adjusts video quality based on:
- **Transmission success rate**
- **Actual frame rate vs. target**
- **Packet size optimization**
- **Network/UART conditions**

### Wireless Mode Optimizations
- **Intelligent Rate Control**: Mimics UART timing characteristics
- **Burst Transmission**: Allows temporary speed bursts for better performance
- **Adaptive Windowing**: Dynamic time windows for different speeds
- **Performance Scaling**: Automatic parameter optimization based on selected speed

### Error Recovery
- **Automatic Detection**: Monitors transmission health
- **Recovery Mode**: Reduces quality/speed when errors detected
- **Statistics Tracking**: Comprehensive performance monitoring

## 📊 Performance Statistics

### Real-time Monitoring
Both sender and receiver display live statistics:
- **Frame Rate**: Current FPS
- **Compression Ratio**: WebP compression efficiency
- **Packet Size**: Average data packet size
- **Success Rate**: Transmission reliability
- **Error Count**: Failed transmissions

### Video Overlay (Receiver)
The receiver displays real-time information overlay:
- Compression ratio
- Current FPS
- Packet size
- Frames received/displayed
- Error count

## 🌐 Wireless Setup

### Same Computer Testing
1. Start sender: `python webp_sender.py`
2. Select "2. Wireless transmission"
3. Choose speed (1MHz recommended for testing)
4. Start receiver: `python webp_receiver.py`
5. Select "2. Wireless transmission"
6. Choose same speed as sender

### Two Computer Setup
1. **Sender Computer**:
   - Modify `WIRELESS_HOST = '0.0.0.0'` (listen on all interfaces)
   - Run `python webp_sender.py`
   
2. **Receiver Computer**:
   - Modify `WIRELESS_HOST = '<sender_ip_address>'`
   - Run `python webp_receiver.py`

3. **Firewall**: Ensure port 8888 is allowed through firewall

## 🔍 Troubleshooting

### Common Issues

#### UART Mode
- **Port not found**: Check COM port numbers and availability
- **Permission denied**: Ensure ports aren't used by other applications
- **Connection timeout**: Verify cable connections and port settings

#### Wireless Mode  
- **Connection refused**: Check firewall settings and IP addresses
- **High latency**: Try lower speed settings or check network quality
- **Frame drops**: Increase buffer size or reduce quality settings

### Performance Optimization
- **Low FPS**: Reduce quality settings or try higher speed wireless mode
- **High latency**: Use wired mode or optimize network setup
- **Poor quality**: Increase quality settings or check camera configuration

## 📋 Protocol Specification

### Packet Format
```
[Magic(4)] [FrameID(4)] [Length(4)] [Type(8)] [Hash(4)] [Data(variable)]
```

- **Magic**: 'WEBP' (4 bytes)
- **FrameID**: Incrementing frame counter (4 bytes)
- **Length**: Data payload length (4 bytes)  
- **Type**: Packet type identifier (8 bytes)
- **Hash**: MD5 hash for verification (4 bytes)
- **Data**: WebP encoded frame data

### Communication Flow
1. **Sender**: Captures frame → WebP encode → Package → Transmit
2. **Receiver**: Receive → Verify → WebP decode → Display
3. **Flow Control**: Rate limiting based on selected transmission speed

## 🧪 Development

### Testing
- Use same-computer wireless testing for development
- Monitor statistics for performance analysis
- Adjust configuration variables for different use cases

### Extending
- Add new performance modes in `setup_performance_mode()`
- Modify compression parameters for different quality/speed tradeoffs
- Implement additional error recovery strategies

## 📝 License

This project is provided as-is for educational and research purposes.

## 🤝 Contributing

Feel free to submit issues and enhancement requests!

---

**Note**: This system is optimized for real-time video transmission scenarios where low latency and efficient bandwidth usage are crucial. The wireless mode provides significant performance improvements over traditional UART while maintaining protocol compatibility. 