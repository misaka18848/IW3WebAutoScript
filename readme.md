# IW3WebAutoScript
## 简介
配合IW3 Web GUI使用的自动化脚本。自动检测文件夹列表内新视频并将其上传至IW3 Web GUI中开始处理,处理完成后自动下载回原文件夹下的VR文件夹里,可以用于配合RSS订阅自动追番自动转换。如果你觉得这个项目帮到了你，欢迎在右上角点个star。
## 如何使用
1.参考[此处](https://github.com/misaka18848/IW3-Web-GUI)部署IW3 Web GUI  
2.安装Python  
3.在项目文件夹里打开`auto_config.json`修改  
`website_url` 的地址为你的IW3 Web GUI的地址  
`check_interval_minutes` 为隔多久检测一次文件夹内有无新文件的时间  
`download_check_interval_minutes` 为隔多久检测一次网站是否转换完视频的时间  
`folders_to_monitor`中 `path` 为你要检测的文件夹，`additional_args` 为转换附加参数（`""`为默认参数）  
检测的文件夹列表可自由增减，如  
```json
    "folders_to_monitor": [
        {
            "path": "C:/Video",
            "additional_args": "--low-vram --disable-amp --depth-model Any_V2_S"
        },
        {
            "path": "C:/Video2",
            "additional_args": "--low-vram --disable-amp --depth-model Any_V2_S"
        }
    ],
```
或者
```json
    "folders_to_monitor": [
        {
            "path": "C:/Video",
            "additional_args": "--low-vram --disable-amp --depth-model Any_V2_S"
        },
        {
            "path": "C:/Video2",
            "additional_args": "--depth-model Any_V2_L"
        },
        {
            "path": "C:/Video3",
            "additional_args": ""
        }
    ],
```
都是可以的  
4.在项目文件夹里打开命令提示符，输入以下内容安装项目依赖
```cmd
pip install -r requirements.txt
```
5.由于ffmpeg的许可证限制，本项目无法在仓库内置ffmpeg的可执行文件，故需要你自行从[此处](https://www.gyan.dev/ffmpeg/builds/ffmpeg-git-full.7z)下载ffmpeg,解压后把bin文件夹和bin文件夹里面的文件放入项目文件夹里  
这时你的文件目录结构应该像这样  
```
- AutoIW3Web/
    - bin/
        - ffmpeg.exe
        - ffplay.exe
        - ffprobe.exe
    - 本项目文件（比如auto_upload_download.py auto_config.json等）
``` 
6.在项目文件夹里打开命令提示符，输入以下内容启动该脚本
```cmd
python auto_upload_download.py
```