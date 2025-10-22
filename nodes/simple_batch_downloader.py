import os
import requests
import json
import sys
from pathlib import Path
import time
from comfy_execution.graph import ExecutionBlocker
import threading
import folder_paths
from tqdm import tqdm

class AnyType(str):
    def __ne__(self, __value: object) -> bool:
        return False

ANY = AnyType("*")

class AlwaysEqualProxy(str):
    def __eq__(self, _):
        return True

    def __ne__(self, _):
        return False
any_type = AlwaysEqualProxy("*")

def download_file_with_temp(url, file_path, overwrite=False):
    """下载单个文件到指定路径，使用临时文件（共享函数）"""
    try:
        if os.path.exists(file_path):
            if not overwrite:
                print(f"文件已存在，跳过下载: {file_path}")
                return True, f"文件已存在，跳过下载: {file_path}"
            else:
                print(f"文件已存在，将在下载完成后覆盖: {file_path}")

        partial_file_path = file_path + ".partial"

        os.makedirs(os.path.dirname(file_path), exist_ok=True)

        print(f"开始下载: {url} 到 {file_path}")
        start_time = time.time()

        with requests.get(url, stream=True, allow_redirects=True) as response:
            response.raise_for_status()

            total_size = int(response.headers.get('content-length', 0))
            downloaded_size = 0

            filename = os.path.basename(file_path)
            with tqdm(total=total_size, unit='B', unit_scale=True, unit_divisor=1024,
                      desc=f"下载 {filename}", ascii=True) as pbar:

                with open(partial_file_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                            chunk_size = len(chunk)
                            downloaded_size += chunk_size
                            
                            pbar.update(chunk_size)

                            elapsed_time = time.time() - start_time
                            if elapsed_time > 0:
                                speed = downloaded_size / elapsed_time / 1024 / 1024  # MB/s
                                pbar.set_postfix(speed=f"{speed:.2f} MB/s")

        if os.path.exists(partial_file_path):
            if os.path.exists(file_path):
                os.remove(file_path)
                print(f"已删除原有文件: {file_path}")

            os.rename(partial_file_path, file_path)
            print(f"下载完成: {file_path}")
            return True, f"下载完成: {file_path}"

    except Exception as e:
        if os.path.exists(partial_file_path):
            try:
                os.remove(partial_file_path)
            except:
                pass
        error_msg = f"下载失败: {url}. 错误: {str(e)}"
        print(error_msg)
        return False, error_msg

class SimpleBatchDownloader:
    """批量下载模型节点，可以同时下载多个URL"""
    NAME = "SimpleBatchDownloader"
    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "url1": ("STRING", {"default": "", "multiline": False}),
                "url2": ("STRING", {"default": "", "multiline": False}),
                "url3": ("STRING", {"default": "", "multiline": False}),
                "url4": ("STRING", {"default": "", "multiline": False}),
                "url5": ("STRING", {"default": "", "multiline": False}),
                "model_folder": ("STRING", {"default": "checkpoints", "multiline": False}),
                "run_download": ("BOOLEAN", {"default": True}),
                "overwrite_existing": ("BOOLEAN", {"default": False}),  # 新增选项，默认为False
            },
            "optional": {
                "anything": (any_type, {})
            },
        }

    RETURN_TYPES = (any_type,"STRING")
    RETURN_NAMES = ("output", "system_message")
    FUNCTION = "download_files"
    CATEGORY = "utils/download"

    def __init__(self):
        self.download_lock = threading.Lock()

    def download_files(self, url1, url2, url3, url4, url5, model_folder, run_download=True, overwrite_existing=False, anything=None):
        """下载所有非空URL的文件"""
        if not run_download:
            return ("下载已取消",)

        urls = [url for url in [url1, url2, url3, url4, url5] if url.strip()]

        if not urls:
            return ("没有提供有效的URL",)

        results = []
        with self.download_lock:
            for url in urls:
                try:
                    file_name = url.split('/')[-1].split('?')[0]
                    model_dir = folder_paths.get_folder_paths(model_folder)[0] if model_folder in folder_paths.folder_names_and_paths else os.path.join(folder_paths.models_dir, model_folder)

                    os.makedirs(model_dir, exist_ok=True)

                    file_path = os.path.join(model_dir, file_name)
                
                    success, message = download_file_with_temp(url, file_path, overwrite_existing)
                    results.append(message)
                    
                except Exception as e:
                    results.append(f"处理URL {url} 时出错: {str(e)}")

        final_message = "\n".join(results)
        
        return (anything, final_message)

class SimpleModelDownloader:
    """单URL下载节点，下载模型并返回模型名称"""

    NAME = "SimpleModelDownloader"

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "model_url": ("STRING", {"default": "", "multiline": False}),
                "model_folder": ("STRING", {"default": "checkpoints", "multiline": False}),
                "run_download": ("BOOLEAN", {"default": True}),
                "overwrite_existing": ("BOOLEAN", {"default": False}),  # 新增选项，默认为False
            },
            "optional": {
                "anything": (any_type, {})
            },
        }

    RETURN_TYPES = (ANY, "STRING")
    RETURN_NAMES = ("model_name", "download_message")
    FUNCTION = "download_model"
    CATEGORY = "utils/download"

    def __init__(self):

        self.download_lock = threading.Lock()

    def download_model(self, model_url, model_folder, run_download=True, overwrite_existing=False, anything=None):
        """下载模型并返回带后缀的模型名称"""
        if not run_download:
            return ("", "下载已取消")
        
        if not model_url.strip():
            return ("", "没有提供有效的URL")
        
        try:
            model_name_with_ext = model_url.split('/')[-1].split('?')[0]

            model_dir = folder_paths.get_folder_paths(model_folder)[0] if model_folder in folder_paths.folder_names_and_paths else os.path.join(folder_paths.models_dir, model_folder)

            os.makedirs(model_dir, exist_ok=True)

            file_path = os.path.join(model_dir, model_name_with_ext)
            
            with self.download_lock:
                success, message = download_file_with_temp(model_url, file_path, overwrite_existing)
                
                if success:
                    return (model_name_with_ext, message)
                else:
                    return ("", message)
                    
        except Exception as e:
            error_msg = f"处理URL时出错: {str(e)}"
            return ("", error_msg)