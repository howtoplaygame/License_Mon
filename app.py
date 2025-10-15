#!/usr/bin/env python
# -*- coding: utf-8 -*-

"""
Aruba License Monitor Web Application
Web界面用于配置和监控Aruba License使用情况

主要功能：
1. 配置管理：License Server、SMTP、Syslog配置
2. License监控：实时获取和显示License使用情况
3. 智能告警：基于阈值的邮件和Syslog通知
4. License摘要：计算并显示各类型License的可用数量
"""

import os
import json
import time
import datetime
import threading
import smtplib
import socket
import fcntl
import tempfile
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Dict, Any, List, Optional
from flask import Flask, render_template, request, jsonify, redirect, url_for
import requests

# 禁用SSL警告
requests.packages.urllib3.disable_warnings()

app = Flask(__name__)
app.secret_key = 'aruba_license_monitor_secret_key'

# 全局变量
config_data = {}          # 存储应用配置数据
license_data = {}         # 存储License使用数据
polling_thread = None     # 后台轮询线程对象
polling_active = False    # 轮询状态标志
notification_manager = None  # 通知管理器对象
active_threads = set()    # 跟踪活跃的轮询线程ID
lock_file_path = os.path.join(tempfile.gettempdir(), 'aruba_license_monitor.lock')

# 确保数据目录存在
os.makedirs('data', exist_ok=True)
os.makedirs('templates', exist_ok=True)
os.makedirs('static', exist_ok=True)

class ArubaAPIClient:
    """Aruba API客户端类，用于与Aruba设备进行API交互"""
    
    def __init__(self, mcr_ip: str, verify_ssl: bool = False):
        self.mcr_ip = mcr_ip
        self.base_url = f"https://{mcr_ip}:4343/v1"
        self.verify_ssl = verify_ssl
        self.session = requests.Session()
        self.uid_aruba = None
        self.cookies = None
        
    def login(self, username: str, password: str) -> Dict[str, Any]:
        """登录到Aruba设备"""
        url = f"{self.base_url}/api/login"
        data = {"username": username, "password": password}
        
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
        """从Aruba设备登出"""
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
        """执行show命令"""
        if not self.uid_aruba:
            return {"status": "error", "message": "未登录，请先调用login方法"}
            
        url = f"{self.base_url}/configuration/showcommand"
        params = {"command": command, "UIDARUBA": self.uid_aruba}
        
        try:
            response = self.session.get(url, params=params, verify=self.verify_ssl)
            response.raise_for_status()
            return {"status": "success", "data": response.json()}
        except requests.exceptions.RequestException as e:
            return {"status": "error", "message": f"执行show命令异常: {e}"}


class NotificationManager:
    """通知管理器，处理邮件和syslog通知"""
    
    def __init__(self):
        self.smtp_config = {}
        self.syslog_config = {}
    
    def configure_smtp(self, smtp_server: str, smtp_port: int, username: str, password: str, 
                      from_email: str, to_emails: List[str]):
        """配置SMTP设置"""
        self.smtp_config = {
            'server': smtp_server,
            'port': smtp_port,
            'username': username,
            'password': password,
            'from_email': from_email,
            'to_emails': to_emails
        }
    
    def configure_syslog(self, syslog_server: str, syslog_port: int):
        """配置Syslog设置"""
        self.syslog_config = {
            'server': syslog_server,
            'port': syslog_port
        }
    
    def send_email(self, subject: str, body: str) -> bool:
        """发送邮件通知"""
        if not self.smtp_config:
            print("SMTP配置未设置")
            return False
        
        try:
            msg = MIMEMultipart()
            msg['From'] = self.smtp_config['from_email']
            msg['To'] = ', '.join(self.smtp_config['to_emails'])
            msg['Subject'] = subject
            
            msg.attach(MIMEText(body, 'plain', 'utf-8'))
            
            # 根据端口选择SSL或普通连接
            if self.smtp_config['port'] == 465:
                # 使用SSL连接
                server = smtplib.SMTP_SSL(self.smtp_config['server'], self.smtp_config['port'])
            else:
                # 使用普通连接然后启动TLS
                server = smtplib.SMTP(self.smtp_config['server'], self.smtp_config['port'])
                server.starttls()
            
            server.login(self.smtp_config['username'], self.smtp_config['password'])
            server.send_message(msg)
            server.quit()
            print(f"邮件发送成功: {subject}")
            return True
        except Exception as e:
            print(f"邮件发送失败: {e}")
            return False
    
    def send_syslog(self, message: str) -> bool:
        """发送Syslog消息"""
        if not self.syslog_config:
            return False
        
        try:
            sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            sock.sendto(message.encode('utf-8'), (self.syslog_config['server'], self.syslog_config['port']))
            sock.close()
            return True
        except Exception as e:
            print(f"Syslog发送失败: {e}")
            return False


# 全局通知管理器
notification_manager = NotificationManager()


def acquire_polling_lock():
    """获取轮询锁，防止重复启动"""
    try:
        # 尝试创建并锁定文件
        lock_file = open(lock_file_path, 'w')
        fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
        lock_file.write(str(os.getpid()))
        lock_file.flush()
        return lock_file
    except (IOError, OSError):
        # 锁已被其他进程持有
        return None


def release_polling_lock(lock_file):
    """释放轮询锁"""
    if lock_file:
        try:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)
            lock_file.close()
            if os.path.exists(lock_file_path):
                os.remove(lock_file_path)
        except:
            pass


def load_config():
    """
    加载配置文件
    
    从data/config.json文件中加载应用配置，包括：
    - License Server配置（IP、用户名、密码）
    - 轮询间隔设置
    - SMTP邮件配置
    - Syslog配置
    - 告警设置
    """
    global config_data
    config_file = 'data/config.json'
    if os.path.exists(config_file):
        try:
            with open(config_file, 'r', encoding='utf-8') as f:
                config_data = json.load(f)
        except Exception as e:
            print(f"加载配置失败: {e}")
            config_data = {}


def save_config():
    """
    保存配置文件
    
    将当前配置数据保存到data/config.json文件中
    包括所有用户设置的配置项和告警设置
    """
    config_file = 'data/config.json'
    try:
        # 确保data目录存在
        os.makedirs('data', exist_ok=True)
        
        with open(config_file, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, indent=2, ensure_ascii=False)
        print(f"配置已保存到: {config_file}")
        print(f"配置内容: {config_data}")
    except Exception as e:
        print(f"保存配置失败: {e}")
        raise e


def get_license_usage(controller_ip: str, username: str, password: str) -> Dict[str, Any]:
    """获取license使用情况"""
    client = ArubaAPIClient(controller_ip, verify_ssl=False)
    
    try:
        # 登录
        login_result = client.login(username, password)
        if login_result["status"] != "success":
            return {"status": "error", "message": f"登录失败: {login_result['message']}"}
        
        # 执行show license-usage命令
        usage_result = client.show_command("show license-usage")
        if usage_result["status"] != "success":
            client.logout()
            return {"status": "error", "message": f"show license-usage命令执行失败: {usage_result['message']}"}
        
        # 执行show license summary命令
        summary_result = client.show_command("show license summary")
        if summary_result["status"] != "success":
            print(f"警告: show license summary命令执行失败: {summary_result['message']}")
            summary_data = {}
        else:
            summary_data = summary_result["data"]
        
        # 登出
        client.logout()
        
        # 合并数据
        combined_data = {
            "license_usage": usage_result["data"],
            "license_summary": summary_data
        }
        
        return {"status": "success", "data": combined_data}
        
    except Exception as e:
        return {"status": "error", "message": f"获取license信息异常: {e}"}


def polling_worker():
    """
    后台轮询工作线程
    
    在后台持续运行，定期执行以下操作：
    1. 连接到Aruba控制器获取License数据
    2. 保存数据到JSON文件
    3. 检查告警条件并发送通知
    4. 等待指定间隔后重复执行
    """
    global polling_active, license_data, config_data
    
    # 获取文件锁，防止重复启动
    lock_file = acquire_polling_lock()
    if not lock_file:
        print("轮询线程已在其他进程中运行，退出当前线程")
        return
    
    print(f"轮询线程启动，轮询间隔: {config_data.get('polling_interval', 86400)} 分钟")
    
    # 防止重复启动的检查
    if not polling_active:
        print("轮询线程已停止，退出")
        release_polling_lock(lock_file)
        return
    
    # 添加线程ID用于调试和跟踪
    import threading
    thread_id = threading.current_thread().ident
    print(f"轮询线程ID: {thread_id}")
    
    # 检查是否已有相同线程在运行
    if thread_id in active_threads:
        print(f"警告: 线程 {thread_id} 已在运行中，退出重复线程")
        release_polling_lock(lock_file)
        return
    
    # 注册当前线程
    active_threads.add(thread_id)
    print(f"注册轮询线程: {thread_id}")
    
    while polling_active:
        try:
            if config_data.get('controller_ip') and config_data.get('username') and config_data.get('password'):
                print(f"开始轮询查询 - {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
                
                # 获取license使用情况
                result = get_license_usage(
                    config_data['controller_ip'],
                    config_data['username'],
                    config_data['password']
                )
                
                if result["status"] == "success":
                    license_data = result["data"]
                    
                    # 保存到文件
                    timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
                    filename = f"data/license_usage_{timestamp}.json"
                    with open(filename, 'w', encoding='utf-8') as f:
                        json.dump(license_data, f, indent=2, ensure_ascii=False)
                    
                    print(f"License数据更新成功，检查告警条件...")
                    
                    # 检查告警条件（使用license_usage数据）
                    if "license_usage" in license_data:
                        check_license_alerts(license_data["license_usage"])
                    
                    # 发送通知（如果需要）
                    if config_data.get('enable_notifications', False):
                        send_notifications(license_data)
                
                else:
                    print(f"获取license信息失败: {result['message']}")
            
            # 等待下次轮询
            interval = config_data.get('polling_interval', 86400)  # 默认24小时
            print(f"等待 {interval} 分钟后下次轮询...")
            time.sleep(interval * 60)  # 转换为秒
            
        except Exception as e:
            print(f"轮询异常: {e}")
            time.sleep(60)  # 出错时等待1分钟再重试
    
    # 轮询线程结束时清理
    print(f"轮询线程 {thread_id} 结束，清理线程跟踪")
    active_threads.discard(thread_id)
    release_polling_lock(lock_file)


def check_license_alerts(license_data: Dict[str, Any]):
    """检查License告警条件"""
    try:
        print("检查License告警条件...")
        
        # 获取告警设置
        alert_settings = config_data.get('alert_settings', {})
        if not alert_settings:
            print("没有配置告警设置")
            return
        
        # 遍历所有License池
        for pool_name, pool_data in license_data.items():
            if pool_name.startswith('License Clients License Usage for pool'):
                print(f"检查池: {pool_name}")
                
                for client in pool_data:
                    if client.get('Hostname') and client.get('Hostname') != 'TOTAL':
                        hostname = client['Hostname']
                        ap_value = int(client.get('AP', 0))
                        
                        # 获取该主机的告警设置
                        client_settings = alert_settings.get(hostname)
                        if not client_settings:
                            continue
                        
                        threshold = client_settings.get('threshold', 0)
                        email_enabled = client_settings.get('email_enabled', False)
                        syslog_enabled = client_settings.get('syslog_enabled', False)
                        
                        print(f"检查 {hostname}: AP={ap_value}, 门限={threshold}")
                        
                        # 检查是否超过门限
                        if ap_value > threshold and threshold > 0:
                            print(f"⚠️  告警: {hostname} 的AP值 {ap_value} 超过门限 {threshold}")
                            
                            # 发送邮件告警
                            if email_enabled:
                                send_alert_notification(hostname, ap_value, threshold, 'email')
                            
                            # 发送Syslog告警
                            if syslog_enabled:
                                send_alert_notification(hostname, ap_value, threshold, 'syslog')
                        else:
                            print(f"✅ {hostname}: AP={ap_value} <= 门限={threshold}")
                            
    except Exception as e:
        print(f"检查告警条件失败: {e}")


def send_alert_notification(hostname: str, ap_value: int, threshold: int, alert_type: str):
    """发送告警通知"""
    try:
        # 生成告警消息
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        alert_message = f"Aruba License告警 - {timestamp}\n"
        alert_message += f"主机名: {hostname}\n"
        alert_message += f"AP值: {ap_value}\n"
        alert_message += f"告警门限: {threshold}\n"
        alert_message += f"控制器: {config_data.get('controller_ip', 'N/A')}\n"
        alert_message += f"告警类型: {alert_type}\n"
        
        if alert_type == 'email':
            if config_data.get('smtp_enabled', False):
                # 确保通知管理器已配置
                if not notification_manager.smtp_config:
                    # 配置SMTP
                    notification_manager.configure_smtp(
                        config_data['smtp_server'],
                        config_data['smtp_port'],
                        config_data['smtp_username'],
                        config_data['smtp_password'],
                        config_data['smtp_from'],
                        [config_data['smtp_to']]
                    )
                
                subject = f"Aruba License告警 - {hostname}"
                success = notification_manager.send_email(subject, alert_message)
                if success:
                    print(f"✅ 邮件告警发送成功: {hostname}")
                else:
                    print(f"❌ 邮件告警发送失败: {hostname}")
            else:
                print(f"❌ 邮件通知未启用")
                
        elif alert_type == 'syslog':
            if config_data.get('syslog_enabled', False):
                # 确保通知管理器已配置
                if not notification_manager.syslog_config:
                    # 配置Syslog
                    notification_manager.configure_syslog(
                        config_data['syslog_server'],
                        config_data['syslog_port']
                    )
                
                syslog_message = f"Aruba License Alert: {alert_message.replace(chr(10), ' ')}"
                success = notification_manager.send_syslog(syslog_message)
                if success:
                    print(f"✅ Syslog告警发送成功: {hostname}")
                else:
                    print(f"❌ Syslog告警发送失败: {hostname}")
            else:
                print(f"❌ Syslog通知未启用")
                
    except Exception as e:
        print(f"发送告警通知失败: {e}")


def send_notifications(license_data: Dict[str, Any]):
    """发送通知"""
    try:
        # 解析license信息
        license_info = []
        if "_data" in license_data:
            for item in license_data["_data"]:
                if "License" in item:
                    license_info.append(item["License"])
        
        if not license_info:
            return
        
        # 生成通知内容
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        subject = f"Aruba License Usage Report - {timestamp}"
        
        body = f"Aruba License使用情况报告\n"
        body += f"时间: {timestamp}\n"
        body += f"控制器: {config_data.get('controller_ip', 'N/A')}\n\n"
        
        for info in license_info:
            body += f"License类型: {info.get('Type', 'N/A')}\n"
            body += f"已使用: {info.get('Used', 'N/A')}\n"
            body += f"总数: {info.get('Total', 'N/A')}\n"
            body += f"可用: {info.get('Available', 'N/A')}\n"
            body += f"使用率: {calculate_usage_percentage(info)}%\n\n"
        
        # 发送邮件
        if config_data.get('smtp_enabled', False):
            notification_manager.send_email(subject, body)
        
        # 发送Syslog
        if config_data.get('syslog_enabled', False):
            syslog_message = f"Aruba License Usage: {body.replace(chr(10), ' ')}"
            notification_manager.send_syslog(syslog_message)
            
    except Exception as e:
        print(f"发送通知失败: {e}")


def calculate_usage_percentage(license_info: Dict[str, Any]) -> float:
    """计算license使用率"""
    try:
        used = int(license_info.get('Used', 0))
        total = int(license_info.get('Total', 1))
        if total > 0:
            return round((used / total) * 100, 2)
        return 0.0
    except:
        return 0.0


# Web路由
@app.route('/')
def index():
    """
    主页路由
    
    重定向到结果页面，提供统一的入口点
    """
    return redirect(url_for('results'))


@app.route('/config')
def config_page():
    """
    配置页面路由
    
    显示配置页面，用户可以设置：
    - License Server连接信息
    - 轮询间隔
    - SMTP邮件配置
    - Syslog配置
    """
    return render_template('config.html', config=config_data)


@app.route('/results')
def results():
    """
    结果页面路由
    
    显示License使用情况和摘要，包括：
    - License摘要（AP、PEF、RFP、MM、MC-VA-RW可用数量）
    - 详细的使用情况表格
    - 告警设置界面
    """
    return render_template('results.html', 
                         license_data=license_data, 
                         config=config_data)

@app.route('/debug')
def debug():
    """调试页面"""
    with open('test_js_debug.html', 'r', encoding='utf-8') as f:
        return f.read()


@app.route('/api/config', methods=['POST'])
def save_config_api():
    """
    保存配置API
    
    处理配置页面的表单提交，保存以下配置：
    - License Server连接信息
    - 轮询间隔设置
    - SMTP邮件配置
    - Syslog配置
    - 通知启用状态
    
    保存后自动启动轮询线程
    """
    global config_data, polling_thread, polling_active
    
    try:
        print("收到配置保存请求")
        print(f"请求数据: {request.form}")
        
        # 获取表单数据
        new_config = {
            'controller_ip': request.form.get('controller_ip', ''),
            'username': request.form.get('username', ''),
            'password': request.form.get('password', ''),
            'polling_interval': int(request.form.get('polling_interval', 86400)),
            'smtp_enabled': request.form.get('smtp_enabled') == 'on',
            'smtp_server': request.form.get('smtp_server', ''),
            'smtp_port': int(request.form.get('smtp_port', 587)),
            'smtp_username': request.form.get('smtp_username', ''),
            'smtp_password': request.form.get('smtp_password', ''),
            'smtp_from': request.form.get('smtp_from', ''),
            'smtp_to': request.form.get('smtp_to', ''),
            'syslog_enabled': request.form.get('syslog_enabled') == 'on',
            'syslog_server': request.form.get('syslog_server', ''),
            'syslog_port': int(request.form.get('syslog_port', 514)),
            'enable_notifications': request.form.get('enable_notifications') == 'on'
        }
        
        # 保留现有的告警设置，避免丢失
        if 'alert_settings' in config_data:
            new_config['alert_settings'] = config_data['alert_settings']
            print(f"保留现有告警设置: {config_data['alert_settings']}")
        
        print(f"解析后的配置: {new_config}")
        
        # 更新全局配置数据
        config_data = new_config
        
        # 保存配置到文件
        save_config()
        
        # 验证配置是否真的保存了
        if os.path.exists('data/config.json'):
            with open('data/config.json', 'r', encoding='utf-8') as f:
                saved_config = json.load(f)
            print(f"验证保存的配置: {saved_config}")
        else:
            print("警告: 配置文件不存在")
        
        # 配置通知管理器
        if config_data['smtp_enabled']:
            to_emails = [email.strip() for email in config_data['smtp_to'].split(',') if email.strip()]
            notification_manager.configure_smtp(
                config_data['smtp_server'],
                config_data['smtp_port'],
                config_data['smtp_username'],
                config_data['smtp_password'],
                config_data['smtp_from'],
                to_emails
            )
        
        if config_data['syslog_enabled']:
            notification_manager.configure_syslog(
                config_data['syslog_server'],
                config_data['syslog_port']
            )
        
        # 重启轮询线程以应用新配置
        if config_data.get('controller_ip'):
            if polling_active:
                print("停止现有轮询线程以应用新配置...")
                polling_active = False
                if polling_thread and polling_thread.is_alive():
                    polling_thread.join(timeout=5)  # 等待最多5秒
                
                # 释放文件锁，允许新线程启动
                print("释放轮询锁...")
                if os.path.exists(lock_file_path):
                    try:
                        os.remove(lock_file_path)
                    except:
                        pass
            
            print("启动新的轮询线程...")
            polling_active = True
            polling_thread = threading.Thread(target=polling_worker, daemon=True)
            polling_thread.start()
            print(f"轮询线程已重启，新间隔: {config_data.get('polling_interval', 86400)} 分钟")
        
        return jsonify({"status": "success", "message": "配置保存成功"})
        
    except Exception as e:
        print(f"保存配置异常: {e}")
        import traceback
        traceback.print_exc()
        return jsonify({"status": "error", "message": f"保存配置失败: {e}"})


@app.route('/api/license', methods=['GET'])
def get_license_api():
    """
    获取License信息API
    
    返回当前缓存的License数据，包括：
    - license_usage: 详细的使用情况数据
    - license_summary: License摘要数据
    - config: 当前配置信息
    """
    return jsonify({
        "status": "success",
        "data": license_data,
        "config": config_data
    })


@app.route('/api/refresh', methods=['POST'])
def refresh_license():
    """
    手动刷新License信息API
    
    立即连接到Aruba控制器获取最新License数据：
    1. 执行show license-usage命令
    2. 执行show license summary命令
    3. 检查告警条件
    4. 更新缓存数据
    """
    try:
        if not config_data.get('controller_ip'):
            return jsonify({"status": "error", "message": "请先配置控制器信息"})
        
        result = get_license_usage(
            config_data['controller_ip'],
            config_data['username'],
            config_data['password']
        )
        
        if result["status"] == "success":
            global license_data
            license_data = result["data"]
            
            # 检查告警条件
            print("手动刷新后检查告警条件...")
            check_license_alerts(license_data)
            
            return jsonify({"status": "success", "message": "刷新成功"})
        else:
            return jsonify({"status": "error", "message": result["message"]})
            
    except Exception as e:
        return jsonify({"status": "error", "message": f"刷新失败: {e}"})


@app.route('/api/status', methods=['GET'])
def get_status():
    """获取系统状态API"""
    return jsonify({
        "polling_active": polling_active,
        "last_update": datetime.datetime.now().isoformat(),
        "config_loaded": bool(config_data.get('controller_ip'))
    })


@app.route('/api/save-alert-settings', methods=['POST'])
def save_alert_settings():
    """保存告警设置API"""
    try:
        data = request.json
        hostname = data.get('hostname')
        threshold = data.get('threshold')
        email_enabled = data.get('email_enabled', False)
        syslog_enabled = data.get('syslog_enabled', False)
        
        if not hostname:
            return jsonify({"status": "error", "message": "缺少主机名"})
        
        # 初始化告警设置存储
        if 'alert_settings' not in config_data:
            config_data['alert_settings'] = {}
        
        # 保存告警设置
        config_data['alert_settings'][hostname] = {
            'threshold': int(threshold) if threshold else 0,
            'email_enabled': email_enabled,
            'syslog_enabled': syslog_enabled
        }
        
        # 保存到文件
        save_config()
        
        print(f"保存告警设置: {hostname} - 门限:{threshold}, 邮件:{email_enabled}, Syslog:{syslog_enabled}")
        
        return jsonify({"status": "success", "message": "告警设置保存成功"})
        
    except Exception as e:
        return jsonify({"status": "error", "message": f"保存告警设置失败: {e}"})


@app.route('/api/get-alert-settings', methods=['GET'])
def get_alert_settings():
    """获取告警设置API"""
    try:
        alert_settings = config_data.get('alert_settings', {})
        return jsonify({"status": "success", "data": alert_settings})
    except Exception as e:
        return jsonify({"status": "error", "message": f"获取告警设置失败: {e}"})


@app.route('/api/send-alert', methods=['POST'])
def send_alert():
    """发送告警通知API"""
    try:
        data = request.json
        hostname = data.get('hostname')
        ap_value = data.get('ap_value')
        threshold = data.get('threshold')
        alert_type = data.get('alert_type')
        
        if not all([hostname, ap_value, threshold, alert_type]):
            return jsonify({"status": "error", "message": "缺少必要参数"})
        
        # 生成告警消息
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        alert_message = f"Aruba License告警 - {timestamp}\n"
        alert_message += f"主机名: {hostname}\n"
        alert_message += f"AP值: {ap_value}\n"
        alert_message += f"告警门限: {threshold}\n"
        alert_message += f"控制器: {config_data.get('controller_ip', 'N/A')}\n"
        alert_message += f"告警类型: {alert_type}\n"
        
        if alert_type == 'email':
            # 发送邮件告警
            if config_data.get('smtp_enabled', False):
                # 确保通知管理器已配置
                if not notification_manager.smtp_config:
                    # 配置SMTP
                    notification_manager.configure_smtp(
                        config_data['smtp_server'],
                        config_data['smtp_port'],
                        config_data['smtp_username'],
                        config_data['smtp_password'],
                        config_data['smtp_from'],
                        [config_data['smtp_to']]
                    )
                
                subject = f"Aruba License告警 - {hostname}"
                success = notification_manager.send_email(subject, alert_message)
                if success:
                    return jsonify({"status": "success", "message": "邮件告警发送成功"})
                else:
                    return jsonify({"status": "error", "message": "邮件告警发送失败"})
            else:
                return jsonify({"status": "error", "message": "邮件通知未启用"})
                
        elif alert_type == 'syslog':
            # 发送Syslog告警
            if config_data.get('syslog_enabled', False):
                # 确保通知管理器已配置
                if not notification_manager.syslog_config:
                    # 配置Syslog
                    notification_manager.configure_syslog(
                        config_data['syslog_server'],
                        config_data['syslog_port']
                    )
                
                syslog_message = f"Aruba License Alert: {alert_message.replace(chr(10), ' ')}"
                success = notification_manager.send_syslog(syslog_message)
                if success:
                    return jsonify({"status": "success", "message": "Syslog告警发送成功"})
                else:
                    return jsonify({"status": "error", "message": "Syslog告警发送失败"})
            else:
                return jsonify({"status": "error", "message": "Syslog通知未启用"})
        else:
            return jsonify({"status": "error", "message": "不支持的告警类型"})
            
    except Exception as e:
        return jsonify({"status": "error", "message": f"发送告警失败: {e}"})


if __name__ == '__main__':
    # 加载配置
    load_config()
    
    # 如果配置了控制器信息，启动轮询（仅在应用启动时）
    if config_data.get('controller_ip') and not polling_active:
        polling_active = True
        polling_thread = threading.Thread(target=polling_worker, daemon=True)
        polling_thread.start()
        print("应用启动时轮询线程已启动")
    elif polling_active:
        print("轮询线程已在运行中，跳过启动")
    
    # 启动Web应用
    app.run(host='0.0.0.0', port=5005, debug=True)
