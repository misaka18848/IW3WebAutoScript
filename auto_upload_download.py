import os
import time
import requests
import json
import shutil
from datetime import datetime
from pathlib import Path
import schedule
import logging
from urllib.parse import urljoin, quote
from urllib3.util.retry import Retry
import re
import sys
import io

# 强制 stdout 和 stderr 使用 UTF-8 编码
if sys.stdout:
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
if sys.stderr:
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 同时设置环境变量（可选）
os.environ['PYTHONIOENCODING'] = 'utf-8'
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
        """查找新的视频文件（仅限监控文件夹根目录，不递归）"""
        new_videos = []
        
        for folder_info in self.config['folders_to_monitor']:
            folder_path = folder_info['path']
            if not os.path.exists(folder_path):
                logger.warning(f"监控文件夹不存在: {folder_path}")
                continue
                
            try:
                # 支持的视频格式
                video_extensions = {'.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm'}
                
                # ---  关键修改：只遍历根目录，不递归 ---
                # 方法一：使用 os.scandir() (推荐，效率高)
                with os.scandir(folder_path) as entries:
                    for entry in entries:
                        # 只处理文件，忽略目录
                        if entry.is_file():
                            file_ext = os.path.splitext(entry.name.lower())[1]
                            if file_ext in video_extensions:
                                file_path = entry.path # entry.path 包含完整路径
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
        """使用分块上传方式上传大视频文件，适配当前后端 session_id 机制"""
        session = requests.Session()
        
        # 确保目标VR文件夹存在 (如果您的脚本逻辑还需要这个)
        vr_folder = os.path.join(target_folder, 'VR')
        os.makedirs(vr_folder, exist_ok=True)
        
        filename = os.path.basename(video_path)
        file_size = os.path.getsize(video_path)
        chunk_size = 10 * 1024 * 1024  # 10MB 每块（可配置）
        total_chunks = (file_size // chunk_size) + (1 if file_size % chunk_size else 0)
        
        logger.info(f"准备上传大文件: {filename}")
        logger.info(f"大小: {file_size / (1024*1024):.1f}MB | 分块数: {total_chunks} | 块大小: {chunk_size / 1024:.1f}KB")
        
        # === 分块上传逻辑开始 ===
        # 🟡 关键：初始化 session_id 为 None，首次上传时不会发送
        current_session_id = None 
        
        try:
            with open(video_path, 'rb') as f:
                for chunk_index in range(total_chunks):
                    # 计算当前块
                    f.seek(chunk_index * chunk_size)
                    chunk_data = f.read(chunk_size)
                    
                    # 准备分块数据
                    files = {
                        'chunk': ('chunk', chunk_data) # 文件块数据
                    }
                    data = {
                        'filename': filename,
                        'chunk_index': chunk_index,
                        'total_chunks': total_chunks,
                        'additional_args': additional_args
                        # 'session_id': current_session_id # 在下面的条件中添加
                    }
                    
                    # 🟡 关键：如果已有 session_id，则添加到 data 中
                    if current_session_id is not None:
                        data['session_id'] = current_session_id
                    
                    # 带重试的上传
                    for attempt in range(self.config['max_retries']):
                        try:
                            logger.debug(f"上传块 {chunk_index + 1}/{total_chunks} (尝试 {attempt + 1})")
                            
                            response = session.post(
                                f"{self.config['website_url']}/upload",  # 使用 /upload 接口
                                files=files,
                                data=data,
                                timeout=300  # 每块上传超时5分钟
                            )
                            
                            if response.status_code == 200:
                                try:
                                    result = response.json()
                                except requests.exceptions.JSONDecodeError as e:
                                    logger.error(f"解析服务器响应失败 (HTTP 200): {e}")
                                    logger.error(f"响应内容: {response.text}")
                                    # 如果解析失败，本次尝试视为失败，进行重试
                                    continue # 跳出本次 attempt 的成功处理，进入下一次重试或循环

                                # 🟡 关键：检查响应是否包含新的 session_id (首次上传或后续上传都会返回)
                                if 'session_id' in result:
                                    # 🟡 关键：更新当前的 session_id，用于下一次上传
                                    # 即使是第一次，也会从服务器获取到新的 session_id
                                    current_session_id = result['session_id']
                                    logger.debug(f"获取/更新 session_id: {current_session_id}")

                                # 🟡 关键：检查是否是最终的合并成功消息
                                if result.get('message') == '上传并合并完成，已加入转换队列':
                                    logger.info(f" 文件 '{filename}' 上传、合并成功，并已加入转换队列！")
                                    # 🟡 关键：记录到历史（状态为 uploaded）
                                    file_hash = self.get_file_hash(video_path)
                                    self.history['uploaded_files'][video_path] = {
                                        'uploaded_at': datetime.now().isoformat(),
                                        'url': self.config['website_url'],
                                        'additional_args': additional_args,
                                        'target_folder': target_folder,
                                        'file_hash': file_hash,
                                        'status': 'uploaded', # 等待 check_conversion_status 下载
                                        # 可选：存储 session_id 以便后续追踪
                                        'session_id': current_session_id 
                                    }
                                    self.save_history()
                                    return True # 上传和合并成功，直接返回

                                # 如果不是最终成功，但块上传成功 (例如 '块 X/Y 上传成功')
                                if 'message' in result and ('上传成功' in result['message'] or '上传完成' in result['message']):
                                    logger.info(f" 块 {chunk_index + 1}/{total_chunks} 上传成功: {result.get('message', 'OK')}")
                                    break # 成功，跳出重试循环，处理下一个块
                                else:
                                    # 服务器返回了 200 但消息不是预期的成功，视为失败
                                    logger.warning(f" 块 {chunk_index} 上传未成功 (HTTP 200 但消息异常): {result}")
                                    
                            else:
                                logger.warning(f" 块 {chunk_index} 上传失败 (HTTP {response.status_code}): {response.text}")
                                
                        except Exception as e:
                            logger.warning(f" 块 {chunk_index} 上传异常 (尝试 {attempt + 1}): {e}")
                        
                        # 重试前等待
                        if attempt < self.config['max_retries'] - 1:
                            time.sleep(self.config['retry_delay'])
                    else:
                        # 所有重试均失败
                        logger.error(f" 块 {chunk_index} 达到最大重试次数，上传中断")
                        return False  # 整体上传失败
                
                # === 注意：正常情况下，循环结束前应该因为最终成功消息而 return True ===
                # 如果代码执行到这里，意味着所有分块都上传了，但没有收到最终的合并成功消息
                # 这通常不应该发生，可能是网络问题导致最后的响应没收到
                logger.warning(f"所有 {total_chunks} 个分块上传完成，但未收到最终合并成功确认。可能需要手动检查或重试。")
                # 您可以选择在这里返回 False，或者尝试添加一个逻辑去轮询状态
                # 但根据现有后端逻辑，这应该很少见。
                return False
                
        except Exception as e:
            logger.error(f"分块上传过程中发生严重错误 {filename}: {e}")
            return False
    
    def check_conversion_status(self):
        """检查转换状态并下载完成的文件（适配新版网站 API - 返回字符串列表）"""
        session = requests.Session()
        
        try:
            api_url = f"{self.config['website_url']}/api/status"
            logger.debug(f"请求状态接口: {api_url}")
            
            response = session.get(api_url, timeout=10)
            if response.status_code != 200:
                logger.warning(f"获取状态失败: {response.status_code} - {response.text}")
                return
            
            try:
                data = response.json()
            except json.JSONDecodeError as e:
                logger.error(f"响应不是有效的JSON: {e}")
                return

            # 提取已转换文件列表
            # 关键：后端返回的是字符串列表，如 ["file1.mp4", "file2.mp4"]
            converted_files = data.get('converted_files', [])
            if not converted_files:
                logger.info("暂无已转换的文件。")
                return

            logger.info(f"发现 {len(converted_files)} 个已转换文件: {converted_files}")

            # 关键：直接遍历字符串列表中的文件名
            for filename in converted_files:
                # 确保文件名存在且不为空
                if not filename or not isinstance(filename, str):
                    continue

                # 在上传历史中查找匹配的原始文件
                matched = False
                for uploaded_path, info in self.history['uploaded_files'].items():
                    # 检查状态为 'uploaded' 且原始文件名匹配
                    if (info.get('status') == 'uploaded' and 
                        os.path.basename(uploaded_path) == filename):
                        
                        # 找到匹配，开始下载
                        if self.download_converted_file(session, filename, info['target_folder']):
                            # 更新上传历史中的状态
                            info['status'] = 'downloaded'
                            info['downloaded_at'] = datetime.now().isoformat()
                            
                            # 将信息添加到下载历史
                            self.history['downloaded_files'][uploaded_path] = {
                                'downloaded_at': datetime.now().isoformat(),
                                'target_folder': info['target_folder'],
                                'original_filename': filename
                            }
                            logger.info(f"文件已下载并记录: {filename}")
                        
                        matched = True
                        break # 找到匹配项后跳出循环

                if not matched:
                    logger.warning(f"未找到上传记录的已转换文件: {filename}")

            # 保存更新后的历史记录
            self.save_history()

        except requests.exceptions.RequestException as e:
            logger.error(f"请求网站状态时发生网络错误: {e}")
        except Exception as e:
            logger.error(f"检查转换状态时发生未知错误: {e}")
    
    def download_converted_file(self, session, filename, target_folder):
        """
        下载转换完成的文件，支持断点续传 (Resume)
        """
        try:
            encoded_filename = quote(filename, safe='')
            download_url = f"{self.config['website_url']}/download/{encoded_filename}"
            
            vr_folder = os.path.join(target_folder, 'VR')
            os.makedirs(vr_folder, exist_ok=True)
            target_path = os.path.join(vr_folder, filename)
            
            logger.info(f"开始下载: {filename} -> {target_path}")
            
            # --- 断点续传逻辑 ---
            resume_byte_pos = 0
            if os.path.exists(target_path):
                resume_byte_pos = os.path.getsize(target_path)
                if resume_byte_pos > 0:
                    logger.info(f"检测到部分下载的文件，大小: {resume_byte_pos} 字节，尝试续传...")
                else:
                    logger.info(f"检测到空文件，重新开始下载...")
                    resume_byte_pos = 0 # 0字节文件也当新文件处理

            # --- 重试配置 ---
            max_retries = self.config.get('max_download_retries', 3)
            retry_strategy = Retry(
                total=max_retries,
                backoff_factor=1, # 重试间隔会指数增长 (1, 2, 4, 8... 秒)
                status_forcelist=[429, 500, 502, 503, 504], # 对这些状态码重试
                allowed_methods=["HEAD", "GET"] # 允许重试的HTTP方法
            )
            # 为这个 session 配置重试 (可选，也可以在循环内手动重试)
            # adapter = HTTPAdapter(max_retries=retry_strategy)
            # session.mount("http://", adapter)
            # session.mount("https://", adapter)

            for attempt in range(max_retries + 1):
                try:
                    # --- 构建带 Range 头的请求 ---
                    headers = {}
                    if resume_byte_pos > 0:
                        # 请求从 resume_byte_pos 开始到文件末尾
                        headers['Range'] = f'bytes={resume_byte_pos}-'
                    
                    # 使用更长的读取超时
                    response = session.get(download_url, headers=headers, stream=True, timeout=(30, 7200),allow_redirects=True)

                    # --- 处理响应 ---
                    if response.status_code == 200:
                        # 服务器不支持 Range，返回了整个文件
                        # 如果 resume_byte_pos > 0，说明我们预期续传，但服务器没支持，需要重新开始
                        if resume_byte_pos > 0:
                            logger.warning("服务器不支持 Range 请求，将重新开始下载。")
                            # 删除部分文件，重新下载
                            os.remove(target_path)
                            resume_byte_pos = 0
                            # 注意：这里需要 continue 到循环开头，重新发起不带 Range 的请求
                            # 但为避免无限循环，我们简单处理：记录警告，然后覆盖写入（相当于重新开始）
                            # 更好的做法是 break 并让下一次 run_once 重新开始
                            logger.info("将覆盖现有文件重新下载。")
                        # 以写入模式 ('wb') 打开，覆盖或创建新文件
                        file_mode = 'wb'
                        expected_status = 200
                    elif response.status_code == 206:
                        # 服务器支持 Range，成功返回部分内容
                        if resume_byte_pos == 0:
                            logger.warning("收到 206 状态码但未请求 Range，行为异常。")
                            # 可能还是当完整文件处理？
                            file_mode = 'wb'
                        else:
                            # 正常续传情况
                            file_mode = 'ab' # 追加模式
                        expected_status = 206
                    else:
                        logger.error(f"下载失败 (HTTP {response.status_code}): {filename}")
                        if 400 <= response.status_code < 500:
                            return False # 客户端错误，重试无意义
                        if attempt < max_retries:
                            logger.warning(f"HTTP 错误，准备重试...")
                            time.sleep(self.config.get('retry_delay', 10))
                            continue
                        else:
                            return False

                    # --- 流式写入文件 ---
                    # 检查状态码是否符合预期
                    if response.status_code != expected_status:
                        logger.error(f"预期状态码 {expected_status}，实际为 {response.status_code}")
                        if attempt < max_retries:
                            time.sleep(self.config.get('retry_delay', 10))
                            continue
                        else:
                            return False

                    # 以正确模式打开文件
                    with open(target_path, file_mode) as f:
                        bytes_downloaded = 0
                        for chunk in response.iter_content(chunk_size=8192):
                            if chunk:
                                f.write(chunk)
                                bytes_downloaded += len(chunk)
                    
                    # --- 验证下载完整性 ---
                    # 理论上，对于 200，应该下载完整文件；对于 206，应该下载了请求的范围
                    # 这里简化处理：只要没有异常，就认为成功
                    logger.info(f"下载完成: {filename} (本次传输 {bytes_downloaded} 字节)")
                    return True # 下载成功

                except requests.exceptions.RequestException as e:
                    logger.warning(f"请求异常 (下载 {filename}) (尝试 {attempt + 1}/{max_retries + 1}): {e}")
                    if attempt < max_retries:
                        time.sleep(self.config.get('retry_delay', 10))
                    else:
                        logger.error(f"下载 {filename} 达到最大重试次数，失败。")
                        return False
                except OSError as e:
                    logger.error(f"文件系统错误 (下载 {filename}): {e}")
                    return False
                except Exception as e:
                    logger.error(f"下载文件失败 {filename}: {e}")
                    return False

            return False # 所有尝试都失败
                
        except Exception as e:
            logger.error(f"下载文件 {filename} 发生未知错误: {e}")
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