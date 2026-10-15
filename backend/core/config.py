# @Time    : 2026
# @Author  : 李涛
# @File    : config.py
# @Desc    : 功能实现
# Copyright (c) 2026 保留所有权利，开源遵循 MIT 开源协议
# 本代码可自由使用、修改、商用、二次分发，仅需保留本版权声明。

"""配置管理模块

此模块用于管理配置文件的读取和解析。
"""

import configparser


class ConfigManager:
    """配置管理器类
    
    用于读取和管理配置文件。
    """
    
    def __init__(self, config_file):
        """初始化配置管理器
        
        Args:
            config_file: 配置文件路径
        """
        self.config_file = config_file
        self.config = configparser.ConfigParser()
        self.load_config()
    
    def load_config(self):
        """加载配置文件"""
        try:
            self.config.read(self.config_file, encoding='utf-8')
        except Exception as e:
            print(f"加载配置文件失败: {e}")
    
    def get(self, section, option, default=None):
        """获取配置值
        
        Args:
            section: 配置节
            option: 配置项
            default: 默认值
            
        Returns:
            str: 配置值
        """
        try:
            return self.config.get(section, option)
        except Exception:
            return default
    
    def getint(self, section, option, default=0):
        """获取整数配置值
        
        Args:
            section: 配置节
            option: 配置项
            default: 默认值
            
        Returns:
            int: 配置值
        """
        try:
            return self.config.getint(section, option)
        except Exception:
            return default
    
    def getfloat(self, section, option, default=0.0):
        """获取浮点数配置值
        
        Args:
            section: 配置节
            option: 配置项
            default: 默认值
            
        Returns:
            float: 配置值
        """
        try:
            return self.config.getfloat(section, option)
        except Exception:
            return default
    
    def getboolean(self, section, option, default=False):
        """获取布尔值配置值
        
        Args:
            section: 配置节
            option: 配置项
            default: 默认值
            
        Returns:
            bool: 配置值
        """
        try:
            return self.config.getboolean(section, option)
        except Exception:
            return default
    
    def sections(self):
        """获取所有配置节
        
        Returns:
            list: 配置节列表
        """
        return self.config.sections()
    
    def options(self, section):
        """获取指定配置节的所有配置项
        
        Args:
            section: 配置节
            
        Returns:
            list: 配置项列表
        """
        try:
            return self.config.options(section)
        except Exception:
            return []