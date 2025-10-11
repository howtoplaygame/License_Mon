#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Aruba License Monitor - API Client
Aruba控制器License监控API客户端

主要功能：
1. 连接到Aruba控制器进行认证
2. 执行show license-usage命令获取License使用情况
3. 执行show license summary命令获取License摘要
4. 提供完整的错误处理和重试机制
5. 支持SSL连接和会话管理
"""

import os
import json
import time
import datetime
import requests
from typing import Dict, Any, List, Optional, Tuple
from flask import Blueprint, request, jsonify

# 创建蓝图
topn_api = Blueprint('topn_api', __name__)

# 禁用SSL警告
requests.packages.urllib3.disable_warnings()

# 存储客户端实例的字典
clients = {}

# 确保数据目录存在
os.makedirs('data', exist_ok=True)

class ArubaAPIClient:
    """
    Aruba API客户端类
    
    用于与Aruba控制器进行API交互，支持：
    - 用户认证和会话管理
    - show命令执行
    - SSL连接处理
    - 错误处理和重试机制
    """
    
    def __init__(self, mcr_ip: str, verify_ssl: bool = False):
        """
        初始化Aruba API客户端
        
        参数:
            mcr_ip: Aruba控制器的IP地址
            verify_ssl: 是否验证SSL证书，默认为False（用于自签名证书）
        """
        self.mcr_ip = mcr_ip
        self.base_url = f"https://{mcr_ip}:4343/v1"
        self.verify_ssl = verify_ssl
        self.session = requests.Session()
        self.uid_aruba = None
        self.cookies = None
        
    def login(self, username: str, password: str) -> Dict[str, Any]:
        """
        登录到Aruba设备
        
        参数:
            username: 用户名
            password: 密码
            
        返回:
            登录响应的JSON数据
        """
        url = f"{self.base_url}/api/login"
        data = {
            "username": username,
            "password": password
        }
        
        try:
            response = self.session.post(url, data=data, verify=self.verify_ssl)
            response.raise_for_status()
            
            result = response.json()
            if result.get("_global_result", {}).get("status") == "0":
                self.uid_aruba = result["_global_result"]["UIDARUBA"]
                self.cookies = self.session.cookies
                return {"status": "success", "message": "登录成功"}
            else:
                return {"status": "error", "message": f"登录失败: {result}"}
        except requests.exceptions.RequestException as e:
            return {"status": "error", "message": f"登录请求异常: {e}"}
            
    def logout(self) -> Dict[str, Any]:
        """
        从Aruba设备登出
        
        返回:
            登出响应的JSON数据
        """
        if not self.uid_aruba:
            return {"status": "error", "message": "未登录"}
            
        url = f"{self.base_url}/api/logout"
        
        try:
            response = self.session.get(url, verify=self.verify_ssl)
            response.raise_for_status()
            
            result = response.json()
            if result.get("_global_result", {}).get("status") == "0":
                self.uid_aruba = None
                self.cookies = None
                return {"status": "success", "message": "登出成功"}
            else:
                return {"status": "error", "message": f"登出失败: {result}"}
        except requests.exceptions.RequestException as e:
            return {"status": "error", "message": f"登出请求异常: {e}"}
            
    def show_command(self, command: str) -> Dict[str, Any]:
        """
        执行show命令
        
        参数:
            command: 要执行的show命令
            
        返回:
            命令执行结果的JSON数据
        """
        if not self.uid_aruba:
            return {"status": "error", "message": "未登录，请先调用login方法"}
            
        url = f"{self.base_url}/configuration/showcommand"
        params = {
            "command": command,
            "UIDARUBA": self.uid_aruba
        }
        
        try:
            response = self.session.get(url, params=params, verify=self.verify_ssl)
            response.raise_for_status()
            
            return {"status": "success", "data": response.json()}
        except requests.exceptions.RequestException as e:
            return {"status": "error", "message": f"执行show命令异常: {e}"}


def get_client_key(controller_ip: str, username: str) -> str:
    """
    生成客户端实例的唯一键
    
    参数:
        controller_ip: 控制器IP地址
        username: 用户名
        
    返回:
        客户端键
    """
    return f"{controller_ip}_{username}"


def logout():
    """登出API"""
    data = request.json
    
    if not data:
        return jsonify({"status": "error", "message": "请求数据为空"})
        
    controller_ip = data.get('controller_ip')
    username = data.get('username')
    
    if not all([controller_ip, username]):
        return jsonify({"status": "error", "message": "缺少必要参数"})
        
    # 获取客户端实例
    client_key = get_client_key(controller_ip, username)
    
    if client_key not in clients:
        return jsonify({"status": "error", "message": "客户端不存在"})
        
    # 登出
    logout_result = clients[client_key]["client"].logout()
    
    # 删除客户端实例
    del clients[client_key]
    
    return jsonify(logout_result)


def get_license_usage_example():
    """
    示例：获取license使用情况的完整流程
    演示如何登录、执行show license-usage命令、然后登出
    """
    # 配置参数
    controller_ip = "10.0.60.60"  # 替换为实际的控制器IP
    username = "admin"  # 替换为实际的用户名
    password = "a1ruba123"  # 替换为实际的密码
    
    print("=" * 50)
    print("Aruba License Usage Monitor - 示例")
    print("=" * 50)
    

    # 创建API客户端
    client = ArubaAPIClient(controller_ip, verify_ssl=False)
    
    try:
        # 步骤1: 登录
        print("步骤1: 正在登录到Aruba控制器...")
        login_result = client.login(username, password)
        
        if login_result["status"] != "success":
            print(f"❌ 登录失败: {login_result['message']}")
            return False
            
        print(f"✅ {login_result['message']}")
        
        # 步骤2: 执行show license-usage命令
        print("\n步骤2: 正在执行 'show license-usage' 命令...")
        command_result = client.show_command("show license-usage")
        
        if command_result["status"] != "success":
            print(f"❌ 命令执行失败: {command_result['message']}")
            return False
            
        print("✅ 命令执行成功")
        
        # 保存结果到文件
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"data/license_usage_{timestamp}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(command_result["data"], f, indent=2, ensure_ascii=False)
        
        print(f"📄 结果已保存到: {filename}")
        
        # 显示部分结果
        print("\n📊 License使用情况摘要:")
        print("-" * 30)
        
        # 解析并显示license信息
        data = command_result["data"]
        if "_data" in data:
            for item in data["_data"]:
                if "License" in item:
                    license_info = item["License"]
                    print(f"License类型: {license_info.get('Type', 'N/A')}")
                    print(f"已使用: {license_info.get('Used', 'N/A')}")
                    print(f"总数: {license_info.get('Total', 'N/A')}")
                    print(f"剩余: {license_info.get('Available', 'N/A')}")
                    print("-" * 30)
        
        # 步骤3: 登出
        print("\n步骤3: 正在登出...")
        logout_result = client.logout()
        
        if logout_result["status"] != "success":
            print(f"⚠️  登出失败: {logout_result['message']}")
        else:
            print(f"✅ {logout_result['message']}")
        
        return True
        
    except Exception as e:
        print(f"❌ 发生异常: {e}")
        # 确保登出
        try:
            client.logout()
        except:
            pass
        return False


def interactive_license_check():
    """
    交互式license检查工具
    允许用户输入参数并执行license检查
    """
    print("=" * 60)
    print("Aruba License Usage Monitor - 交互式工具")
    print("=" * 60)
    
    # 获取用户输入
    controller_ip = input("请输入控制器IP地址: ").strip()
    username = input("请输入用户名: ").strip()
    password = input("请输入密码: ").strip()
    
    if not all([controller_ip, username, password]):
        print("❌ 参数不完整，退出")
        return
    
    # 创建API客户端
    client = ArubaAPIClient(controller_ip, verify_ssl=False)
    
    try:
        # 登录
        print(f"\n正在连接到 {controller_ip}...")
        login_result = client.login(username, password)
        
        if login_result["status"] != "success":
            print(f"❌ 登录失败: {login_result['message']}")
            return
            
        print("✅ 登录成功")
        
        # 执行license-usage命令
        print("正在获取license使用情况...")
        command_result = client.show_command("show license-usage")
        
        if command_result["status"] != "success":
            print(f"❌ 获取license信息失败: {command_result['message']}")
            return
            
        print("✅ 获取license信息成功")
        
        # 保存结果
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"data/license_usage_{controller_ip}_{timestamp}.json"
        
        with open(filename, 'w', encoding='utf-8') as f:
            json.dump(command_result["data"], f, indent=2, ensure_ascii=False)
        
        print(f"📄 结果已保存到: {filename}")
        
        # 显示license信息
        print("\n📊 License使用情况:")
        print("=" * 40)
        
        data = command_result["data"]
        if "_data" in data:
            for item in data["_data"]:
                if "License" in item:
                    license_info = item["License"]
                    print(f"类型: {license_info.get('Type', 'N/A')}")
                    print(f"已使用: {license_info.get('Used', 'N/A')}")
                    print(f"总数: {license_info.get('Total', 'N/A')}")
                    print(f"可用: {license_info.get('Available', 'N/A')}")
                    print("-" * 40)
        
        # 登出
        print("\n正在登出...")
        logout_result = client.logout()
        print(f"✅ {logout_result['message']}")
        
    except Exception as e:
        print(f"❌ 发生异常: {e}")
        try:
            client.logout()
        except:
            pass


if __name__ == "__main__":
    print("Aruba License Usage Monitor")
    print("1. 运行示例 (使用预设参数)")
    print("2. 交互式检查 (输入自定义参数)")
    
    choice = input("\n请选择 (1/2): ").strip()
    
    if choice == "1":
        get_license_usage_example()
    elif choice == "2":
        interactive_license_check()
    else:
        print("无效选择，退出")
