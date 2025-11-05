# Aruba License Monitor

这是一个用于监控Aruba控制器license使用情况的Web应用程序，提供实时License摘要、告警通知和可视化监控功能。

## 功能特性

### 🌐 Web界面
- **配置页面**: 设置License Server、SMTP、Syslog等参数
- **结果页面**: 实时显示License使用情况和摘要，支持自动刷新
- **响应式设计**: 支持桌面和移动设备访问
- **License摘要**: 显示AP、PEF、RFP、MM、MC-VA-RW的可用数量

### 📊 监控功能
- 连接到Aruba控制器执行`show license-usage`和`show license summary`命令
- 自动轮询更新License使用情况
- 实时计算License可用数量（Total Installed - Used）
- 可视化显示License使用率和状态
- 支持自定义查询间隔（默认86400分钟，即24小时）

### 🚨 智能告警
- **阈值告警**: 为每个客户端设置AP值告警门限
- **邮件通知**: 支持SMTP配置，自动发送License告警
- **Syslog通知**: 支持发送到Syslog服务器
- **实时监控**: 自动检测超阈值情况并发送通知

### 💾 数据管理
- 自动保存License数据到JSON文件
- 支持历史数据查看
- 完整的错误处理和日志记录
- 告警设置自动保存

## 安装依赖

```bash
pip install -r requirements.txt
```

## 快速开始

### 1. 启动Web应用

```bash
python run_web.py
```

### 2. 访问Web界面

- **结果页面**: http://localhost:5005
- **配置页面**: http://localhost:5005/config

### 3. 配置License Server

1. 访问配置页面
2. 输入控制器IP地址、用户名、密码
3. 设置查询间隔（默认86400分钟，即24小时）
4. 配置SMTP和Syslog（可选）
5. 保存配置

### 4. 查看结果

访问结果页面查看License使用情况，系统会自动开始轮询更新。

### 5. 设置告警

1. 在结果页面中，为每个客户端设置告警门限
2. 选择邮件通知和/或Syslog通知
3. 当AP值超过门限时，系统会自动发送告警

## 配置说明

### License Server配置
- **控制器IP**: Aruba控制器的IP地址
- **用户名/密码**: 登录凭据
- **查询间隔**: 轮询间隔（分钟），默认86400分钟（24小时）

### SMTP邮件配置
- **SMTP服务器**: 邮件服务器地址
- **端口**: 通常为587或465
- **认证信息**: 用户名和密码
- **收件人**: 多个邮箱用逗号分隔

### Syslog配置
- **Syslog服务器**: Syslog服务器IP
- **端口**: 通常为514

### 告警配置
- **告警门限**: 为每个客户端设置AP值告警门限
- **邮件通知**: 启用/禁用邮件告警通知
- **Syslog通知**: 启用/禁用Syslog告警通知
- **自动保存**: 告警设置自动保存到配置文件

## 文件结构

```
License_Mon/
├── app.py                 # 主Web应用
├── run_web.py            # 启动脚本
├── aruba_license_monitor.py  # 原始命令行工具
├── requirements.txt      # 依赖包
├── README.md            # 说明文档
├── data/               # 数据目录
│   ├── config.json     # 配置文件
│   └── license_usage_*.json  # License数据文件
└── templates/          # HTML模板
    ├── base.html       # 基础模板
    ├── config.html     # 配置页面
    └── results.html    # 结果页面
```

## API接口

### 配置接口
- `POST /api/config` - 保存配置
- `GET /api/status` - 获取系统状态

### 数据接口
- `GET /api/license` - 获取License数据
- `POST /api/refresh` - 手动刷新数据

### 告警接口
- `GET /api/get-alert-settings` - 获取告警设置
- `POST /api/save-alert-settings` - 保存告警设置
- `POST /api/send-alert` - 发送告警通知

## License摘要功能

### 📊 实时摘要显示
系统会自动计算并显示以下License类型的可用数量：
- **AP可用**: Access Points可用数量
- **PEF可用**: Policy Enforcement Firewall可用数量  
- **RFP可用**: RF Protect可用数量
- **MM可用**: Mobility Manager可用数量
- **MC-VA-RW可用**: Controller Virtual Appliance可用数量
- **总客户端数**: 连接的客户端总数

### 🧮 计算公式
```
可用数量 = Total Installed - 已使用数量
```

### 🔄 自动更新
- 每次轮询时自动更新摘要数据
- 手动刷新时立即更新摘要
- 实时反映License使用情况

## 使用示例

### 命令行模式（原始功能）
```bash
python aruba_license_monitor.py
# 选择选项 1 或 2
```

### Web模式（推荐）
```bash
python run_web.py
# 然后访问 http://localhost:5005
```

## 注意事项

1. **网络连接**: 确保能够访问Aruba控制器
2. **认证信息**: 使用正确的用户名和密码
3. **SSL设置**: 某些环境可能需要调整SSL验证
4. **防火墙**: 确保Web端口5005可访问
5. **数据备份**: 重要数据会自动保存到`data/`目录

## 错误处理

程序包含完整的错误处理机制：
- 网络连接错误自动重试
- 认证失败提示
- 命令执行失败处理
- 自动登出保护
- 轮询异常恢复

## 系统要求

- Python 3.7+
- 网络连接到Aruba控制器
- 现代Web浏览器（支持JavaScript）
- 邮件服务器（可选，用于告警通知）
- Syslog服务器（可选，用于告警通知）

## 技术改进详情

### 重复告警问题解决
- **问题**：系统在Flask调试模式下会启动多个轮询线程，导致重复发送告警
- **解决方案**：实现基于文件锁的进程级保护机制
- **技术细节**：
  - 使用`fcntl`模块实现跨进程文件锁
  - 锁文件路径：`/tmp/aruba_license_monitor.lock`
  - 线程启动时检查锁，获取失败则退出
  - 线程结束时自动释放锁

### 配置管理优化
- **问题**：配置保存时会丢失告警设置（`alert_settings`）
- **解决方案**：在配置保存时保留现有告警设置
- **技术细节**：
  ```python
  # 保留现有的告警设置，避免丢失
  if 'alert_settings' in config_data:
      new_config['alert_settings'] = config_data['alert_settings']
  ```

### 轮询间隔实时生效
- **问题**：修改轮询间隔后需要重启程序才能生效
- **解决方案**：配置保存时自动重启轮询线程
- **技术细节**：
  - 停止现有轮询线程
  - 释放文件锁
  - 启动新的轮询线程
  - 新线程使用最新配置

### 代码质量提升
- **注释完善**：为所有Python文件添加详细的中文注释
- **错误处理**：增强异常处理和调试信息
- **代码结构**：优化函数组织和变量命名
- **文档更新**：完善README和.gitignore文件

## 更新日志

### v2.1.0 (最新 - 2025-10-15)
- ✅ **代码注释完善**：为所有Python文件添加详细的中文注释
- ✅ **重复告警修复**：使用文件锁机制彻底解决重复告警问题
- ✅ **配置保存优化**：修复配置保存时告警设置丢失的问题
- ✅ **轮询间隔实时生效**：修改轮询间隔后无需重启程序即可生效
- ✅ **线程管理优化**：添加线程跟踪机制，防止多线程冲突
- ✅ **Flask调试模式兼容**：在调试模式下也能正常工作
- ✅ **文件锁机制**：跨进程保护，确保只有一个轮询线程运行
- ✅ **.gitignore更新**：完善忽略规则，保护敏感数据

### v2.0.0
- ✅ 新增License摘要功能，实时显示可用数量
- ✅ 新增智能告警系统，支持阈值告警
- ✅ 新增邮件和Syslog通知功能
- ✅ 优化轮询间隔，默认86400分钟（24小时）
- ✅ 改进用户界面，移除重复信息
- ✅ 完善错误处理和调试信息

### v1.0.0
- ✅ 基础Web界面
- ✅ License使用情况监控
- ✅ 自动轮询功能
- ✅ 数据保存功能
