#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Aruba License Monitor Web Application Launcher
Aruba License监控Web应用启动器

功能：
1. 检查并创建必要的目录结构
2. 加载应用配置
3. 启动Flask Web服务器
4. 提供用户友好的启动信息
"""

import os
import sys
from app import app, load_config

def main():
    """
    主函数
    
    执行以下操作：
    1. 检查并创建必要的目录结构
    2. 加载应用配置
    3. 显示启动信息
    4. 启动Flask Web服务器
    """
    print("=" * 60)
    print("Aruba License Monitor Web Application")
    print("=" * 60)
    print("正在启动Web应用程序...")
    
    # 检查并创建必要的目录
    required_dirs = ['data', 'templates', 'static']
    for dir_name in required_dirs:
        if not os.path.exists(dir_name):
            os.makedirs(dir_name)
            print(f"创建目录: {dir_name}")
    
    # 加载应用配置
    load_config()
    
    print("Web应用程序配置:")
    print(f"- 主机: 0.0.0.0")
    print(f"- 端口: 5005")
    print(f"- 调试模式: 开启")
    print("=" * 60)
    print("访问地址:")
    print("http://localhost:5005 - 结果页面")
    print("http://localhost:5005/config - 配置页面")
    print("=" * 60)
    print("按 Ctrl+C 停止服务器")
    print("=" * 60)
    
    try:
        # 启动Flask应用
        app.run(host='0.0.0.0', port=5005, debug=True)
    except KeyboardInterrupt:
        print("\n服务器已停止")
    except Exception as e:
        print(f"启动失败: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()
