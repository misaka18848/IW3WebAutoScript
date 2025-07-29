import os
import time
import requests
import json
import shutil
from datetime import datetime
from pathlib import Path
import schedule
import logging
from urllib.parse import urlparse
import re

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('auto_upload_download.log'),
        logging.StreamHandler()
    ]
)
logger = logging.getLogger(__name__)

class AutoUploadDownload:
    def __init__(self, config_file='auto_config.json'):
        self.config_file = config_file
        self.config = {
            'website_url': 'http://localhost:5000',  # 您的网站地址
            'check_interval_minutes': 30,  # 检查间隔（分钟）
            'download_check_interval_minutes': 30,  # 下载检查间隔（分钟）
            'folders_to_monitor': [
                {
                    'path': 'D:/videos',  # 监控的文件夹路径
                    'additional_args': ''  # 预设参数
                }
            ],
            'history_file': 'upload_history.json',  # 历史记录文件
            'max_retries': 5,  # 最大重试次数
            'retry_delay': 10  # 重试延迟（秒）
        }
        
        # 加载配置
        self.load_config()
        
        # 加载历史记录
        self.history = self.load_history()
        
        # 确保历史文件夹存在
        history_dir = os.path.dirname(self.config['history_file'])
        if history_dir:
            os.makedirs(history_dir, exist_ok=True)
    
    def load_config(self):
        """加载配置文件"""
        try:
            if os.path.exists(self.config_file):
                with open(self.config_file, 'r', encoding='utf-8') as f:
                    loaded_config = json.load(f)
                    # 合并配置，保留默认值
                    for key, value in loaded_config.items():
                        self.config[key] = value
                logger.info(f"已加载配置文件: {self.config_file}")
            else:
                # 创建默认配置文件
                self.save_config()
                logger.info(f"创建默认配置文件: {self.config_file}")
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")
    
    def save_config(self):
        """保存配置文件"""
        try:
            with open(self.config_file, 'w', encoding='utf-8') as f:
                json.dump(self.config, f, indent=4, ensure_ascii=False)
            logger.info(f"配置已保存到: {self.config_file}")
        except Exception as e:
            logger.error(f"保存配置文件失败: {e}")
    
    def load_history(self):
        """加载历史记录"""
        try:
            if os.path.exists(self.config['history_file']):
                with open(self.config['history_file'], 'r', encoding='utf-8') as f:
                    history = json.load(f)
                    # 确保所有必要的键都存在
                    if 'uploaded_files' not in history:
                        history['uploaded_files'] = {}
                    if 'downloaded_files' not in history:
                        history['downloaded_files'] = {}
                    return history
            else:
                # 创建默认历史记录
                history = {
                    'uploaded_files': {},  # {full_path: {'uploaded_at': timestamp, 'url': url, 'additional_args': args}}
                    'downloaded_files': {}  # {full_path: {'downloaded_at': timestamp, 'target_folder': folder}}
                }
                self.save_history(history)
                return history
        except Exception as e:
            logger.error(f"加载历史记录失败: {e}")
            return {
                'uploaded_files': {},
                'downloaded_files': {}
            }
    
    def save_history(self, history=None):
        """保存历史记录"""
        try:
            if history is None:
                history = self.history
            with open(self.config['history_file'], 'w', encoding='utf-8') as f:
                json.dump(history, f, indent=4, ensure_ascii=False)
            logger.info(f"历史记录已保存到: {self.config['history_file']}")
        except Exception as e:
            logger.error(f"保存历史记录失败: {e}")
    
    def get_file_hash(self, file_path):
        """生成文件的唯一标识（基于文件路径和大小）"""
        try:
            stat = os.stat(file_path)
            file_info = f"{file_path}|{stat.st_size}|{stat.st_mtime}"
            import hashlib
            return hashlib.md5(file_info.encode('utf-8')).hexdigest()
        except Exception as e:
            logger.error(f"生成文件哈希失败 {file_path}: {e}")
            return None
    
    def is_file_processed(self, file_path):
        """检查文件是否已经处理过"""
        file_hash = self.get_file_hash(file_path)
        if not file_hash:
            return False
            
        # 检查是否已经上传过
        for uploaded_info in self.history['uploaded_files'].values():
            if uploaded_info.get('file_hash') == file_hash:
                return True
        return False
    
    def find_new_videos(self):
        """查找新的视频文件"""
        new_videos = []
        
        for folder_info in self.config['folders_to_monitor']:
            folder_path = folder_info['path']
            if not os.path.exists(folder_path):
                logger.warning(f"监控文件夹不存在: {folder_path}")
                continue
                
            try:
                # 支持的视频格式
                video_extensions = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm'}
                
                for root, dirs, files in os.walk(folder_path):
                    for file in files:
                        file_path = os.path.join(root, file)
                        file_ext = os.path.splitext(file.lower())[1]
                        
                        if file_ext in video_extensions:
                            # 检查文件是否已经处理过
                            if not self.is_file_processed(file_path):
                                new_videos.append({
                                    'path': file_path,
                                    'folder_info': folder_info,
                                    'target_folder': os.path.dirname(file_path)  # 目标文件夹是原文件夹
                                })
                            else:
                                logger.debug(f"跳过已处理的文件: {file_path}")
                                
            except Exception as e:
                logger.error(f"扫描文件夹失败 {folder_path}: {e}")
        
        return new_videos
    
    def upload_video(self, video_path, additional_args, target_folder):
        """上传视频到网站"""
        session = requests.Session()
        
        # 确保目标VR文件夹存在
        vr_folder = os.path.join(target_folder, 'VR')
        os.makedirs(vr_folder, exist_ok=True)
        
        # 准备上传
        files = {'file': open(video_path, 'rb')}
        data = {'additional_args': additional_args}
        
        # 获取文件名（保留原始文件名）
        filename = os.path.basename(video_path)
        
        for attempt in range(self.config['max_retries']):
            try:
                logger.info(f"尝试上传文件 (第{attempt+1}次): {filename}")
                
                response = session.post(
                    f"{self.config['website_url']}/",
                    files=files,
                    data=data,
                    timeout=30
                )
                
                if response.status_code == 200:
                    # 检查是否上传成功（可以通过检查响应内容判断）
                    if '上传并转换' in response.text or 'file' in response.text.lower():
                        logger.info(f"上传成功: {filename}")
                        
                        # 记录到历史
                        file_hash = self.get_file_hash(video_path)
                        self.history['uploaded_files'][video_path] = {
                            'uploaded_at': datetime.now().isoformat(),
                            'url': self.config['website_url'],
                            'additional_args': additional_args,
                            'target_folder': target_folder,
                            'file_hash': file_hash,
                            'status': 'uploaded'
                        }
                        self.save_history()
                        
                        files['file'].close()
                        return True
                    else:
                        logger.warning(f"上传响应异常: {response.status_code}")
                        
            except Exception as e:
                logger.error(f"上传失败 (第{attempt+1}次): {filename}, 错误: {e}")
                if attempt < self.config['max_retries'] - 1:
                    logger.info(f"等待 {self.config['retry_delay']} 秒后重试...")
                    time.sleep(self.config['retry_delay'])
            
            # 重新打开文件（如果需要重试）
            if attempt < self.config['max_retries'] - 1:
                try:
                    files['file'].close()
                    files['file'] = open(video_path, 'rb')
                except:
                    pass
        
        logger.error(f"上传失败达到最大重试次数: {filename}")
        files['file'].close()
        return False
    
    def check_conversion_status(self):
        """检查转换状态并下载完成的文件"""
        session = requests.Session()
        
        try:
            # 获取网站状态
            status_response = session.get(f"{self.config['website_url']}/", timeout=10)
            if status_response.status_code != 200:
                logger.warning(f"无法获取网站状态: {status_response.status_code}")
                return
            
            # 解析HTML获取已转换的文件列表
            # 这里需要根据您的网站HTML结构调整
            converted_files = []
            
            # 简单的HTML解析（可以根据需要改进）
            import re
            # 查找转换完成的文件链接
            pattern = r'<a href="[^"]*/download/([^"]+)"[^>]*>下载</a>'
            matches = re.findall(pattern, status_response.text)
            
            for filename in matches:
                # URL解码
                import urllib.parse
                decoded_filename = urllib.parse.unquote(filename)
                
                # 在历史记录中查找对应的上传文件
                for uploaded_path, info in self.history['uploaded_files'].items():
                    if (info['status'] == 'uploaded' and 
                        os.path.basename(uploaded_path) == decoded_filename):
                        
                        # 下载文件
                        if self.download_converted_file(decoded_filename, info['target_folder']):
                            # 更新历史记录
                            info['status'] = 'downloaded'
                            info['downloaded_at'] = datetime.now().isoformat()
                            
                            self.history['downloaded_files'][uploaded_path] = {
                                'downloaded_at': datetime.now().isoformat(),
                                'target_folder': info['target_folder'],
                                'original_filename': decoded_filename
                            }
                            
                            logger.info(f"文件已下载并记录: {decoded_filename}")
            
            self.save_history()
            
        except Exception as e:
            logger.error(f"检查转换状态失败: {e}")
    
    def download_converted_file(self, filename, target_folder):
        """下载转换完成的文件"""
        session = requests.Session()
        
        try:
            # 构建下载URL
            download_url = f"{self.config['website_url']}/download/{filename}"
            
            # 确保VR文件夹存在
            vr_folder = os.path.join(target_folder, 'VR')
            os.makedirs(vr_folder, exist_ok=True)
            
            # 下载文件
            response = session.get(download_url, stream=True, timeout=30)
            if response.status_code == 200:
                # 构建目标文件路径
                target_path = os.path.join(vr_folder, filename)
                
                # 保存文件
                with open(target_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        f.write(chunk)
                
                logger.info(f"下载成功: {target_path}")
                return True
            else:
                logger.error(f"下载失败: {filename}, 状态码: {response.status_code}")
                return False
                
        except Exception as e:
            logger.error(f"下载文件失败 {filename}: {e}")
            return False
    
    def run_once(self):
        """执行一次完整流程"""
        logger.info("开始执行自动化任务...")
        
        # 1. 查找新视频并上传
        new_videos = self.find_new_videos()
        logger.info(f"找到 {len(new_videos)} 个新视频")
        
        for video in new_videos:
            try:
                success = self.upload_video(
                    video['path'], 
                    video['folder_info']['additional_args'],
                    video['target_folder']
                )
                if success:
                    logger.info(f"成功上传: {video['path']}")
                else:
                    logger.error(f"上传失败: {video['path']}")
            except Exception as e:
                logger.error(f"处理视频失败 {video['path']}: {e}")
        
        # 2. 检查并下载已转换的文件
        self.check_conversion_status()
        
        logger.info("自动化任务执行完成")
    
    def start_scheduler(self):
        """启动定时任务"""
        logger.info(f"启动自动化脚本，监控配置: {self.config_file}")
        
        # 每30分钟检查新视频
        schedule.every(self.config['check_interval_minutes']).minutes.do(self.run_once)
        
        # 也可以设置具体时间点
        # schedule.every().hour.at(":00").do(self.run_once)
        # schedule.every().hour.at(":30").do(self.run_once)
        
        logger.info(f"已设置定时任务: 每 {self.config['check_interval_minutes']} 分钟检查一次")
        
        # 立即执行一次
        self.run_once()
        
        # 开始循环
        while True:
            schedule.run_pending()
            time.sleep(60)  # 每分钟检查一次

def create_sample_config():
    """创建示例配置文件"""
    config = {
        'website_url': 'http://localhost:5000',
        'check_interval_minutes': 30,
        'download_check_interval_minutes': 30,
        'folders_to_monitor': [
            {
                'path': 'D:/videos',
                'additional_args': ''
            },
            {
                'path': 'E:/movies',
                'additional_args': ''
            }
        ],
        'history_file': 'upload_history.json',
        'max_retries': 5,
        'retry_delay': 10
    }
    
    with open('auto_config.json', 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=4, ensure_ascii=False)
    
    print("已创建示例配置文件 auto_config.json")
    print("请根据您的实际情况修改配置文件")

if __name__ == "__main__":
    # 如果没有配置文件，创建示例配置
    if not os.path.exists('auto_config.json'):
        create_sample_config()
    
    # 创建自动化实例并启动
    auto = AutoUploadDownload()
    auto.start_scheduler()