"""
配置管理模块

负责加载和管理应用程序配置
"""

import os
import sys
from typing import Dict, Any, List
from dotenv import load_dotenv


class ConfigManager:
    """配置管理器"""

    def __init__(self, config_file: str = "config.env"):
        """
        初始化配置管理器

        Args:
            config_file: 配置文件路径
        """
        self.config_file = config_file
        self._config: Dict[str, Any] = {}
        self.load_config()

    def load_config(self) -> None:
        """加载配置文件"""
        # 优先加载本地配置文件，如果不存在则使用环境变量
        if os.path.exists(self.config_file):
            load_dotenv(self.config_file)

        # Github Action 和其他CI环境会直接设置环境变量
        # 无需config.env文件

        # 基本配置
        self._config.update(
            {
                "username": os.getenv("SITE_USERNAME", "").strip(),
                "password": os.getenv("SITE_PASSWORD", "").strip(),
                "base_url": os.getenv("BASE_URL", "https://www.sehuatang.org"),
                "headless": os.getenv("HEADLESS", "true").lower() == "true",
                "log_level": os.getenv("LOG_LEVEL", "DEBUG").upper(),
            }
        )

        # 日志配置
        self._config.update(
            {
                "log_dir": os.getenv("LOG_DIR", "logs"),
                "max_log_files": int(os.getenv("MAX_LOG_FILES", "7")),
            }
        )

        # 安全提问配置
        self._config.update(
            {
                "enable_security_question": os.getenv(
                    "ENABLE_SECURITY_QUESTION", "false"
                ).lower()
                == "true",
                "security_answer": os.getenv("SECURITY_ANSWER", "").strip(),
                "security_question": os.getenv("SECURITY_QUESTION", "").strip(),
            }
        )

        # 登录安全配置 - 默认启用
        self._config.update(
            {
                "detect_account_lockout": True,
                "lockout_wait_minutes": 15,
            }
        )

        # 拟人化行为配置
        self._config.update(
            {
                "enable_reply": os.getenv("ENABLE_REPLY", "true").lower() == "true",
                "reply_count": int(os.getenv("REPLY_COUNT", "2")),
                "enable_random_browsing": os.getenv(
                    "ENABLE_RANDOM_BROWSING", "true"
                ).lower()
                == "true",
                "browse_page_count": int(os.getenv("BROWSE_PAGE_COUNT", "3")),
                "wait_after_login": int(os.getenv("WAIT_AFTER_LOGIN", "5")),
            }
        )

        # 评论配置
        comment_interval = int(os.getenv("COMMENT_INTERVAL", "15"))
        self._config["comment_interval"] = max(15, comment_interval)  # 强制不低于15秒

        reply_messages_str = os.getenv("REPLY_MESSAGES", "")
        if reply_messages_str:
            self._config["reply_messages"] = [
                msg.strip() for msg in reply_messages_str.split(";") if msg.strip()
            ]
        else:
            self._config["reply_messages"] = [
                "感谢分享资源，收藏了",
                "好资源收藏了，谢谢楼主",
                "感谢楼主的精彩分享",
                "谢谢分享，非常实用",
                "好内容，支持一下楼主",
            ]

        # 功能开关
        self._config.update(
            {
                "enable_checkin": os.getenv("ENABLE_CHECKIN", "true").lower() == "true",
                "timing_multiplier": float(os.getenv("TIMING_MULTIPLIER", "1.0")),
                "enable_smart_timing": os.getenv("ENABLE_SMART_TIMING", "true").lower()
                == "true",
            }
        )

        # PushPlus 微信通知配置
        self._config.update(
            {
                "ENABLE_PUSHPLUS_NOTIFICATION": os.getenv(
                    "ENABLE_PUSHPLUS_NOTIFICATION", "false"
                ).lower()
                == "true",
                "TELEGRAM_BOT_TOKEN": os.getenv("PUSHPLUS_TOKEN", "").strip(),
            }
        )
        
        # Telegram 通知配置
        self._config.update(
            {
                "ENABLE_TELEGRAM_NOTIFICATION": os.getenv(
                    "ENABLE_TELEGRAM_NOTIFICATION", "false"
                ).lower()
                == "true",
                "TELEGRAM_BOT_TOKEN": os.getenv("TELEGRAM_BOT_TOKEN", "").strip(),
                "TELEGRAM_CHAT_ID": os.getenv("TELEGRAM_CHAT_ID", "").strip(),
                "TELEGRAM_PROXY_URL": os.getenv("TELEGRAM_PROXY_URL", "").strip(),
                "TELEGRAM_SEND_LOG_FILE": os.getenv(
                    "TELEGRAM_SEND_LOG_FILE", "false"
                ).lower()
                == "true",
                "TELEGRAM_SEND_SCREENSHOT": os.getenv(
                    "TELEGRAM_SEND_SCREENSHOT", "false"
                ).lower()
                == "true",
            }
        )

        # 拟人化活动总开关
        self._config["enable_humanlike"] = (
            self._config["enable_reply"] or self._config["enable_random_browsing"]
        )

        # 安全保护配置
        timeout_minutes = int(os.getenv("TIMEOUT_MINUTES", "5"))
        max_retries = int(os.getenv("MAX_RETRIES", "3"))
        self._config.update(
            {
                "timeout_minutes": max(1, timeout_minutes),  # 最少1分钟
                "timeout_seconds": max(60, timeout_minutes * 60),  # 转换为秒
                "max_retries": max(1, max_retries),  # 最少1次重试
            }
        )

        # 验证必要配置
        self._validate_config()

    def _validate_config(self) -> None:
        """验证配置的有效性"""
        if not self._config["username"] or not self._config["password"]:
            print("配置错误：请设置SITE_USERNAME和SITE_PASSWORD环境变量")
            print("本地运行：请在config.env文件中设置")
            print("Github Action：请在仓库Secrets中设置")
            sys.exit(1)

        # 验证安全提问配置
        if self._config["enable_security_question"]:
            if not self._config["security_answer"]:
                print("配置错误：启用安全提问功能需要设置SECURITY_ANSWER")
                sys.exit(1)

        # 验证Telegram通知配置
        if self._config["ENABLE_TELEGRAM_NOTIFICATION"]:
            if (
                not self._config["TELEGRAM_BOT_TOKEN"]
                or not self._config["TELEGRAM_CHAT_ID"]
            ):
                print(
                    "配置错误：启用Telegram通知需要设置TELEGRAM_BOT_TOKEN和TELEGRAM_CHAT_ID"
                )
                sys.exit(1)

    def get(self, key: str, default: Any = None) -> Any:
        """
        获取配置值

        Args:
            key: 配置键名
            default: 默认值

        Returns:
            配置值
        """
        return self._config.get(key, default)

    def get_all(self) -> Dict[str, Any]:
        """获取所有配置"""
        return self._config.copy()

    def get_safe_config(self) -> Dict[str, Any]:
        """
        获取安全的配置副本（敏感信息已掩码）
        用于日志记录等场景

        Returns:
            掩码后的配置字典
        """
        safe_config = self._config.copy()

        # 敏感字段列表
        sensitive_fields = [
            "password",
            "security_answer",
            "TELEGRAM_BOT_TOKEN",
            "TELEGRAM_CHAT_ID",
            "TELEGRAM_PROXY_URL",
        ]

        # 对敏感字段进行掩码处理
        for field in sensitive_fields:
            if field in safe_config and safe_config[field]:
                value = str(safe_config[field])
                if len(value) <= 4:
                    safe_config[field] = "***"
                else:
                    # 显示前2位和后2位，中间用*代替
                    safe_config[field] = value[:2] + "*" * (len(value) - 4) + value[-2:]

        return safe_config

    def mask_sensitive_value(self, value: str) -> str:
        """
        对敏感值进行掩码处理

        Args:
            value: 原始值

        Returns:
            掩码后的值
        """
        if not value:
            return ""

        if len(value) <= 4:
            return "***"
        else:
            return value[:2] + "*" * (len(value) - 4) + value[-2:]

    def set(self, key: str, value: Any) -> None:
        """
        设置配置值

        Args:
            key: 配置键名
            value: 配置值
        """
        self._config[key] = value

    def get_browser_config(self) -> Dict[str, Any]:
        """获取浏览器相关配置"""
        return {
            "headless": self._config["headless"],
            "base_url": self._config["base_url"],
        }

    def get_auth_config(self) -> Dict[str, Any]:
        """获取认证相关配置"""
        return {
            "username": self._config["username"],
            "password": self._config["password"],
            "enable_security_question": self._config["enable_security_question"],
            "security_answer": self._config["security_answer"],
            "security_question": self._config["security_question"],
        }

    def get_humanlike_config(self) -> Dict[str, Any]:
        """获取拟人化行为配置"""
        return {
            "enable_humanlike": self._config["enable_humanlike"],
            "enable_reply": self._config["enable_reply"],
            "reply_count": self._config["reply_count"],
            "enable_random_browsing": self._config["enable_random_browsing"],
            "browse_page_count": self._config["browse_page_count"],
            "reply_messages": self._config["reply_messages"],
            "comment_interval": self._config["comment_interval"],
            "wait_after_login": self._config["wait_after_login"],
        }

    def get_timing_config(self) -> Dict[str, Any]:
        """获取时间相关配置"""
        return {
            "timing_multiplier": self._config["timing_multiplier"],
            "enable_smart_timing": self._config["enable_smart_timing"],
            "comment_interval": self._config["comment_interval"],
        }

    def get_logging_config(self) -> Dict[str, Any]:
        """获取日志配置"""
        return {
            "log_level": self._config["log_level"],
            "log_dir": self._config["log_dir"],
            "max_log_files": self._config["max_log_files"],
        }

    def get_telegram_config(self) -> Dict[str, Any]:
        """获取 Telegram 通知配置"""
        return {
            "ENABLE_TELEGRAM_NOTIFICATION": self._config[
                "ENABLE_TELEGRAM_NOTIFICATION"
            ],
            "TELEGRAM_BOT_TOKEN": self._config["TELEGRAM_BOT_TOKEN"],
            "TELEGRAM_CHAT_ID": self._config["TELEGRAM_CHAT_ID"],
            "TELEGRAM_PROXY_URL": self._config["TELEGRAM_PROXY_URL"],
            "TELEGRAM_SEND_LOG_FILE": self._config["TELEGRAM_SEND_LOG_FILE"],
            "TELEGRAM_SEND_SCREENSHOT": self._config["TELEGRAM_SEND_SCREENSHOT"],
        }

    def get_security_config(self) -> Dict[str, Any]:
        """获取安全保护配置"""
        return {
            "timeout_minutes": self._config["timeout_minutes"],
            "timeout_seconds": self._config["timeout_seconds"],
            "max_retries": self._config["max_retries"],
        }
