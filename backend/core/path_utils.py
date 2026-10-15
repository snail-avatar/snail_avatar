# -*- coding: utf-8 -*-
# @Time    : 2026
# @Author  : 李涛
# @File    : path_utils.py
# @Desc    : path_utils
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

import sys
import os


def is_frozen():
    """检测是否为打包环境"""
    return getattr(sys, 'frozen', False)


def get_resource_dir():
    """获取资源文件目录（兼容开发和打包环境）
    
    开发环境下返回 snail_avatar/ 根目录
    """
    if is_frozen():
        return os.path.join(sys._MEIPASS, 'snail_avatar')
    else:
        # 往上走三级：backend/core/path_utils.py → backend/ → snail_avatar/
        return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_writable_dir():
    """获取可写目录（配置、日志、数据库等）
    
    开发环境下返回 snail_avatar/ 根目录
    """
    if is_frozen():
        return os.path.dirname(sys.executable)
    else:
        # 往上走三级：backend/core/path_utils.py → backend/ → snail_avatar/
        return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def get_icon_path(icon_name):
    """获取图标路径"""
    resource_dir = get_resource_dir()
    return os.path.join(resource_dir, 'ui', 'resources', 'icons', icon_name)


def get_config_path(config_filename='config.ini'):
    """获取配置文件路径"""
    resource_dir = get_resource_dir()
    return os.path.join(resource_dir, 'data', config_filename)


def get_agent_config_path(agent_dir: str, config_filename: str):
    """获取Agent配置文件路径"""
    if is_frozen():
        resource_dir = get_resource_dir()
        agent_name = os.path.basename(agent_dir)
        return os.path.join(resource_dir, 'agents', agent_name, 'config', config_filename)
    else:
        return os.path.join(agent_dir, 'config', config_filename)


def get_agent_resource_path(agent_dir: str, *relative_path_parts):
    """获取Agent资源文件路径（兼容开发和打包环境）
    
    Args:
        agent_dir: Agent目录（通常为 os.path.dirname(__file__)）
        relative_path_parts: 相对于Agent目录的路径部分
        
    Returns:
        str: 完整路径
    """
    if is_frozen():
        resource_dir = get_resource_dir()
        agent_name = os.path.basename(agent_dir)
        return os.path.join(resource_dir, 'agents', agent_name, *relative_path_parts)
    else:
        return os.path.join(agent_dir, *relative_path_parts)