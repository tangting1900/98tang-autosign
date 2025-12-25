"""
主应用程序模块

整合所有功能模块，提供统一的签到服务
"""

import logging
import os
from typing import Optional
from datetime import datetime

from .config import ConfigManager
from .logger import LoggerManager
from ..browser.driver import BrowserDriverManager
from ..automation.signin import SignInManager
from ..automation.humanlike import HumanlikeBehavior
from ..utils.retry import RetryManager
from ..utils.timing import TimingManager
from ..notifications.telegram import (
    TelegramNotifier,
    TaskResult,
    ExecutionSummary,
    NotificationData,
)
from ..notifications.pushplus import PushPlusNotifier, ExecutionSummary as PushPlusExecutionSummary
from ..utils.timeout_protection import TimeoutProtectionContext
from ..utils.encoding import EncodingHelper
from ..utils.screenshot_helper import ScreenshotHelper


class AutoSignApp:
    """自动签到应用程序"""

    def __init__(self, config_file: str = "config.env", debug_mode: bool = False):
        """
        初始化应用程序

        Args:
            config_file: 配置文件路径
            debug_mode: 是否启用调试模式
        """
        self.debug_mode = debug_mode

        # 初始化配置管理器
        self.config_manager = ConfigManager(config_file)

        # 初始化日志管理器
        logging_config = self.config_manager.get_logging_config()
        # 设置编码环境，确保CI环境兼容性
        EncodingHelper.setup_encoding_environment()

        self.logger_manager = LoggerManager()
        self.logger = self.logger_manager.setup_logger(
            name=__name__,
            log_level=logging_config["log_level"],
            log_dir=logging_config["log_dir"],
            max_log_files=logging_config["max_log_files"],
            debug_mode=debug_mode,
        )

        # 初始化其他组件
        self.browser_manager = BrowserDriverManager(self.logger)
        security_config = self.config_manager.get_security_config()
        self.retry_manager = RetryManager(max_retries=security_config["max_retries"])

        # 业务逻辑管理器
        self.signin_manager: Optional[SignInManager] = None
        self.humanlike_manager: Optional[HumanlikeBehavior] = None

        # Telegram通知器
        self.telegram_notifier: Optional[TelegramNotifier] = None
        self._init_telegram_notifier()

         # PushPlus通知器
        self.pushplus_notifier: Optional[PushPlusNotifier] = None
        self._init_pushplus_notifier()
        
        # 执行摘要数据
        self.execution_start_time: Optional[str] = None
        self.task_results: list = []

        # 应用全局延迟倍数
        timing_config = self.config_manager.get_timing_config()
        TimingManager.set_global_multiplier(timing_config["timing_multiplier"])
        TimingManager.set_comment_interval(timing_config["comment_interval"])

        if self.debug_mode:
            self.logger.info("调试模式已启用，将输出详细信息")

        # 使用安全配置显示，避免敏感信息泄露
        safe_config = self.config_manager.get_safe_config()
        self.logger.info(f"配置加载完成，用户名: {self.config_manager.get('username')}")
        self.logger.debug(f"安全配置: {safe_config}")

    def test_telegram_connection(self) -> bool:
        """
        测试Telegram连接

        Returns:
            是否连接成功
        """
        if not self.telegram_notifier:
            self.logger.error("Telegram通知器未初始化")
            return False

        try:
            return self.telegram_notifier.test_connection()
        except Exception as e:
            self.logger.error(f"Telegram连接测试失败: {e}")
            return False

    def _init_telegram_notifier(self) -> None:
        """初始化Telegram通知器"""
        try:
            # 检查是否启用Telegram通知
            if not self.config_manager.get("ENABLE_TELEGRAM_NOTIFICATION", False):
                self.logger.debug("Telegram通知未启用")
                return

            # 获取配置
            bot_token = self.config_manager.get("TELEGRAM_BOT_TOKEN", "").strip()
            chat_id = self.config_manager.get("TELEGRAM_CHAT_ID", "").strip()
            proxy_url = self.config_manager.get("TELEGRAM_PROXY_URL", "").strip()

            if not bot_token or not chat_id:
                self.logger.warning("Telegram通知已启用但配置不完整，跳过初始化")
                return

            # 创建通知器
            self.telegram_notifier = TelegramNotifier(
                bot_token=bot_token,
                chat_id=chat_id,
                proxy_url=proxy_url,
                logger=self.logger,
            )

            self.logger.info("Telegram通知器初始化成功")

        except Exception as e:
            self.logger.error(f"Telegram通知器初始化失败: {e}")
            self.telegram_notifier = None


        def _init_pushplus_notifier(self) -> None:
        """初始化PushPlus通知器"""
        try:
            # 检查是否启用PushPlus通知（建议在config中添加此配置项，如果没有可临时硬编码或使用现有变量）
            if not self.config_manager.get("ENABLE_PUSHPLUS_NOTIFICATION", False):
                self.logger.debug("PushPlus通知未启用")
                return

            # 获取配置（假设你在config.env中添加了 PUSHPLUS_TOKEN）
            token = self.config_manager.get("PUSHPLUS_TOKEN", "").strip()

            if not token:
                self.logger.warning("PushPlus通知已启用但Token缺失，跳过初始化")
                return

            # 创建通知器
            self.pushplus_notifier = PushPlusNotifier(
                token=token,
                logger=self.logger,
            )

            self.logger.info("PushPlus通知器初始化成功")

        except Exception as e:
            self.logger.error(f"PushPlus通知器初始化失败: {e}")
            self.pushplus_notifier = None

    
    def _record_task_result(
        self, task_type: str, success: bool, message: str, details: str = None
    ) -> None:
        """记录任务执行结果"""
        task_result = TaskResult(
            task_type=task_type, success=success, message=message, details=details
        )
        self.task_results.append(task_result)

        # 不再发送单个任务通知，只在最后发送摘要

    def _capture_debug_files(self) -> tuple[Optional[str], Optional[str]]:
        """
        捕获调试文件（截图和HTML源代码）

        Returns:
            (screenshot_path, html_path): 截图文件路径和HTML文件路径的元组
        """
        screenshot_path = None
        html_path = None

        try:
            if self.browser_manager and self.browser_manager.driver:
                # 创建调试文件目录
                debug_dir = os.path.join("logs", "debug")
                os.makedirs(debug_dir, exist_ok=True)

                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")

                # 捕获截图
                try:
                    screenshot_path = os.path.join(
                        debug_dir, f"error_screenshot_{timestamp}.png"
                    )
                    self.browser_manager.driver.save_screenshot(screenshot_path)
                    self.logger.debug(f"错误截图已保存: {screenshot_path}")
                except Exception as e:
                    self.logger.warning(f"捕获错误截图失败: {e}")
                    screenshot_path = None

                # 捕获HTML源代码
                try:
                    html_path = os.path.join(
                        debug_dir, f"error_source_{timestamp}.html"
                    )
                    page_source = self.browser_manager.driver.page_source

                    # 使用编码助手安全地保存HTML源代码
                    if EncodingHelper.safe_write_text(html_path, page_source):
                        self.logger.debug(f"错误HTML源代码已保存: {html_path}")
                    else:
                        self.logger.warning("错误HTML源代码保存失败")
                        html_path = None
                except Exception as e:
                    self.logger.warning(f"捕获错误HTML源代码失败: {e}")
                    html_path = None

        except Exception as e:
            self.logger.warning(f"捕获调试文件失败: {e}")

        return screenshot_path, html_path

    def _send_error_with_log(self, error_message: str, error_title: str) -> None:
        """发送统一的错误通知（包含所有相关文件和信息）"""
        if not self.telegram_notifier:
            return

        try:
            # 准备所有文件路径
            log_file_path = None
            screenshot_path = None
            html_path = None
            include_live_screenshot = False
            live_screenshot_context = None

            # 捕获调试文件
            if self.config_manager.get("TELEGRAM_SEND_LOG_FILE", False):
                screenshot_path, html_path = self._capture_debug_files()

                # 获取日志文件
                current_log_file = self.logger_manager.get_current_log_file()
                if current_log_file and os.path.exists(current_log_file):
                    log_file_path = current_log_file

            # 检查是否需要实时截图（避免重复发送截图）
            if (
                self.config_manager.get("TELEGRAM_SEND_SCREENSHOT", False)
                and not screenshot_path  # 只有在没有静态截图时才发送实时截图
                and hasattr(self, "browser_manager")
                and self.browser_manager
                and hasattr(self.browser_manager, "driver")
                and self.browser_manager.driver
            ):
                include_live_screenshot = True
                live_screenshot_context = f"执行过程中发生错误: {error_title}"

            # 创建统一的错误通知数据包
            notification_data = self.telegram_notifier.create_error_notification(
                error_message=error_message,
                error_type=error_title,
                log_file_path=log_file_path,
                screenshot_path=screenshot_path,
                html_path=html_path,
                include_live_screenshot=include_live_screenshot,
                live_screenshot_context=live_screenshot_context,
            )

            # 发送统一通知
            success = self.telegram_notifier.send_batch_notification(notification_data)

            if success:
                self.logger.debug("统一错误通知已发送到Telegram")
            else:
                self.logger.warning("统一错误通知发送失败")

            # 发送实时截图（如果启用）
            if include_live_screenshot:
                try:
                    screenshot_helper = ScreenshotHelper(
                        telegram_notifier=self.telegram_notifier
                    )
                    screenshot_helper.capture_and_send_screenshot(
                        driver=self.browser_manager.driver,
                        scenario="execution_error",
                        description=live_screenshot_context,
                    )
                    self.logger.debug("实时错误截图已发送到Telegram")
                except Exception as live_screenshot_error:
                    self.logger.warning(
                        f"发送实时错误截图失败: {live_screenshot_error}"
                    )

        except Exception as notify_error:
            self.logger.warning(f"发送错误通知时出错: {notify_error}")

         # 添加 PushPlus 错误通知（简单文本）
        if self.pushplus_notifier:
            try:
                title = "98tang-autosign 错误报告"
                content = f"""
                执行过程中发生错误: {error_title}
                
                错误详情:
                {error_message}
                
                时间: {datetime.now().strftime("%Y-%m-%d %H:%M:%S")}
                用户名: {self.config_manager.get('username', '未知')}
                """.strip()
                success = self.pushplus_notifier.send_message(title, content)
                if success:
                    self.logger.debug("PushPlus错误通知已发送")
                else:
                    self.logger.warning("PushPlus错误通知发送失败")
            except Exception as e:
                self.logger.warning(f"发送PushPlus错误通知时出错: {e}")

    def _send_execution_summary(self, overall_success: bool) -> None:
        """发送统一的执行摘要通知（包含所有相关文件和信息）"""
        if not self.telegram_notifier or not self.execution_start_time:
            return

        try:
            end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 计算执行时长
            start_dt = datetime.strptime(self.execution_start_time, "%Y-%m-%d %H:%M:%S")
            end_dt = datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
            duration = end_dt - start_dt

            # 格式化时长
            total_seconds = int(duration.total_seconds())
            minutes = total_seconds // 60
            seconds = total_seconds % 60
            duration_str = f"{minutes}分{seconds}秒" if minutes > 0 else f"{seconds}秒"

            # 创建执行摘要
            summary = ExecutionSummary(
                username=self.config_manager.get("username", "未知用户"),
                start_time=self.execution_start_time,
                end_time=end_time,
                total_duration=duration_str,
                tasks=self.task_results,
                overall_success=overall_success,
            )

            # 准备附件信息
            log_file_path = None
            include_live_screenshot = False
            live_screenshot_context = None

            # 只在执行成功时发送日志文件（避免与错误通知重复推送）
            if overall_success and self.config_manager.get(
                "TELEGRAM_SEND_LOG_FILE", False
            ):
                current_log_file = self.logger_manager.get_current_log_file()
                if current_log_file and os.path.exists(current_log_file):
                    log_file_path = current_log_file

            # 检查是否需要成功截图
            if overall_success and self.config_manager.get(
                "TELEGRAM_SEND_SCREENSHOT", False
            ):
                include_live_screenshot = True
                live_screenshot_context = "签到任务执行成功"

            # 创建统一的成功通知数据包
            notification_data = self.telegram_notifier.create_success_notification(
                summary=summary,
                log_file_path=log_file_path,
                include_live_screenshot=include_live_screenshot,
                live_screenshot_context=live_screenshot_context,
            )

            # 发送统一通知
            success = self.telegram_notifier.send_batch_notification(notification_data)

            if success:
                self.logger.debug("统一执行摘要已发送到Telegram")
            else:
                self.logger.warning("统一执行摘要发送失败")

            # 发送实时截图（如果启用且成功）
            if include_live_screenshot:
                try:
                    screenshot_helper = ScreenshotHelper(
                        telegram_notifier=self.telegram_notifier
                    )
                    screenshot_helper.capture_and_send_screenshot(
                        driver=self.browser_manager.driver,
                        scenario="execution_success",
                        description=live_screenshot_context,
                    )
                    self.logger.debug("执行成功截图已发送到Telegram")
                except Exception as screenshot_error:
                    self.logger.warning(f"发送执行成功截图失败: {screenshot_error}")

        except Exception as e:
            self.logger.warning(f"发送Telegram执行摘要失败: {e}")

      # 添加 PushPlus 执行摘要通知
        if self.pushplus_notifier and self.execution_start_time:
            try:
                end_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

                # 计算执行时长（复用已有逻辑）
                start_dt = datetime.strptime(self.execution_start_time, "%Y-%m-%d %H:%M:%S")
                end_dt = datetime.strptime(end_time, "%Y-%m-%d %H:%M:%S")
                duration = end_dt - start_dt
                total_seconds = int(duration.total_seconds())
                minutes = total_seconds // 60
                seconds = total_seconds % 60
                duration_str = f"{minutes}分{seconds}秒" if minutes > 0 else f"{seconds}秒"

                # 创建 PushPlus 专用的 ExecutionSummary
                summary = PushPlusExecutionSummary(
                    username=self.config_manager.get("username", "未知用户"),
                    start_time=self.execution_start_time,
                    end_time=end_time,
                    total_duration=duration_str,
                    tasks=self.task_results,
                    overall_success=overall_success,
                )

                success = self.pushplus_notifier.send_summary(summary)
                if success:
                    self.logger.debug("PushPlus执行摘要已发送")
                else:
                    self.logger.warning("PushPlus执行摘要发送失败")
            except Exception as e:
                self.logger.warning(f"发送PushPlus执行摘要失败: {e}")

    
    def _initialize_managers(self) -> bool:
        """
        初始化业务管理器

        Returns:
            是否初始化成功
        """
        try:
            driver = self.browser_manager.get_driver()
            if not driver:
                self.logger.error("浏览器驱动未初始化")
                return False

            # 初始化签到管理器
            auth_config = self.config_manager.get_auth_config()
            auth_config.update(self.config_manager.get_browser_config())
            self.signin_manager = SignInManager(driver, auth_config, self.logger)

            # 初始化拟人化行为管理器
            humanlike_config = self.config_manager.get_humanlike_config()
            humanlike_config.update(self.config_manager.get_browser_config())
            self.humanlike_manager = HumanlikeBehavior(
                driver, humanlike_config, self.logger
            )

            return True

        except Exception as e:
            self.logger.error(f"初始化业务管理器失败: {e}")
            return False

    def _create_browser(self) -> bool:
        """
        创建浏览器驱动

        Returns:
            是否创建成功
        """
        browser_config = self.config_manager.get_browser_config()
        return self.browser_manager.create_driver(browser_config)

    def _login_with_retry(self) -> bool:
        """
        带重试的登录

        Returns:
            是否登录成功
        """
        operation = "login"

        while self.retry_manager.can_retry(operation):
            try:
                if self.signin_manager.login():
                    self.retry_manager.reset(operation)
                    return True
                else:
                    retry_count = self.retry_manager.get_retry_count(operation)
                    remaining = self.retry_manager.get_remaining_retries(operation)
                    self.logger.warning(
                        f"登录失败，第 {retry_count} 次尝试，还剩 {remaining} 次重试机会"
                    )

            except Exception as e:
                retry_count = self.retry_manager.get_retry_count(operation)
                remaining = self.retry_manager.get_remaining_retries(operation)

                # 检查是否是账号锁定错误
                if "账号锁定" in str(e) or "密码错误次数过多" in str(e):
                    self.logger.error(f"账号被锁定，停止重试: {e}")
                    return False  # 账号锁定时不继续重试

                self.logger.error(
                    f"登录过程出错: {e}，第 {retry_count} 次尝试，还剩 {remaining} 次重试机会"
                )

        error_msg = "登录重试次数已达上限"
        self.logger.error(error_msg)

        # 不在这里发送错误通知，由调用方统一处理
        # 避免重复通知，统一在 run() 方法中发送最终报告

        return False

    def _perform_humanlike_activities(self) -> None:
        """执行拟人化活动"""
        # 检查两个拟人化功能是否都禁用
        enable_reply = self.config_manager.get("enable_reply", True)
        enable_browsing = self.config_manager.get("enable_random_browsing", True)

        if not enable_reply and not enable_browsing:
            self.logger.info("拟人化活动已禁用")
            self._record_task_result("browse", True, "拟人化活动已禁用，跳过执行")
            return

        try:
            self.logger.info("开始执行拟人化活动")

            # 执行拟人化活动并获取详细结果
            activity_results = (
                self.humanlike_manager.perform_humanlike_activities_with_results()
            )

            # 记录浏览活动结果
            if enable_browsing:
                browse_success = activity_results.get("browse_success", True)
                browse_message = activity_results.get(
                    "browse_message", "拟真浏览执行成功"
                )
                self._record_task_result("browse", browse_success, browse_message)

            # 记录回帖活动结果
            if enable_reply:
                reply_success = activity_results.get("reply_success", False)
                reply_message = activity_results.get(
                    "reply_message", "回帖活动执行失败"
                )
                reply_details = activity_results.get("reply_details")
                self._record_task_result(
                    "reply", reply_success, reply_message, reply_details
                )

            self.logger.info("拟人化活动执行完成")

        except Exception as e:
            self.logger.warning(f"拟人化活动执行失败: {e}")
            self._record_task_result("browse", False, "拟人化活动执行失败", str(e))

    def _perform_signin(self) -> bool:
        """
        执行签到

        Returns:
            是否签到成功
        """
        if not self.config_manager.get("enable_checkin", True):
            self.logger.info("签到功能已禁用")
            self._record_task_result("signin", True, "签到功能已禁用，跳过执行")
            return True

        try:
            self.logger.info("开始执行签到")

            if self.signin_manager.sign_in():
                self.logger.info("签到完成")
                self._record_task_result("signin", True, "签到执行成功")
                return True
            else:
                error_msg = "签到失败"
                self.logger.error(error_msg)
                self._record_task_result("signin", False, "签到执行失败")

                # 注意：这里不发送错误通知，由run()方法统一处理

                return False

        except Exception as e:
            error_msg = f"签到过程出错: {e}"
            self.logger.error(error_msg)
            self._record_task_result("signin", False, "签到过程出错", str(e))

            # 注意：这里不发送错误通知，由run()方法统一处理

            return False

    def run(self) -> bool:
        """
        运行主流程

        Returns:
            是否执行成功
        """
        # 获取安全配置
        security_config = self.config_manager.get_security_config()
        timeout_seconds = security_config["timeout_seconds"]
        timeout_minutes = security_config["timeout_minutes"]

        self.logger.info(f"启动超时保护，超时时间: {timeout_minutes} 分钟")

        # 使用超时保护上下文管理器
        with TimeoutProtectionContext(self, timeout_seconds) as timeout_manager:
            # 记录开始时间
            self.execution_start_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

            # 执行结果标志
            execution_success = False
            last_error_message = "程序执行过程中出现未知错误"

            try:
                self.logger.info("开始98tang-autosign程序")

                if self.debug_mode:
                    self._log_debug_info()

                # 步骤1: 创建浏览器
                self.logger.debug("步骤1: 创建浏览器驱动")
                if not self._create_browser():
                    last_error_message = "浏览器驱动创建失败"
                    self.logger.error(last_error_message)
                    return False
                self.logger.debug("浏览器驱动创建成功")

                # 步骤2: 初始化业务管理器
                self.logger.debug("步骤2: 初始化业务管理器")
                if not self._initialize_managers():
                    last_error_message = "业务管理器初始化失败"
                    self.logger.error(last_error_message)
                    return False
                self.logger.debug("业务管理器初始化成功")

                # 步骤3: 登录
                self.logger.debug("步骤3: 执行登录流程")
                if not self._login_with_retry():
                    last_error_message = "登录失败"
                    self.logger.error(last_error_message)
                    return False
                self.logger.debug("登录流程完成")

                # 步骤4: 执行拟人化活动
                self.logger.debug("步骤4: 执行拟人化活动")
                self._perform_humanlike_activities()

                # 步骤5: 签到
                self.logger.debug("步骤5: 执行签到流程")
                if not self._perform_signin():
                    # 从任务结果中获取更详细的错误信息
                    signin_result = next(
                        (r for r in self.task_results if r.task_type == "signin"), None
                    )
                    if signin_result and not signin_result.success:
                        last_error_message = (
                            signin_result.details or signin_result.message or "签到失败"
                        )
                    else:
                        last_error_message = "签到失败"
                    self.logger.error(last_error_message)
                    return False

                self.logger.info("程序执行完成")
                execution_success = True
                return True

            except Exception as e:
                last_error_message = f"程序运行异常: {str(e)}"
                self.logger.error(last_error_message)
                if self.debug_mode:
                    import traceback

                    self.logger.debug(f"详细错误信息: {traceback.format_exc()}")
                return False

            finally:
                # 统一发送执行报告（无论成功或失败）
                if execution_success:
                    # 发送成功摘要
                    self._send_execution_summary(True)
                else:
                    # 发送失败摘要和错误通知
                    self._send_execution_summary(False)
                    self._send_error_with_log(last_error_message, "程序执行失败")

                # 清理资源
                self._cleanup()

    def _log_debug_info(self) -> None:
        """输出调试信息"""
        self.logger.debug("运行配置信息:")
        self.logger.debug(f"  - 基础URL: {self.config_manager.get('base_url')}")
        self.logger.debug(f"  - 用户名: {self.config_manager.get('username')}")
        self.logger.debug(f"  - 无头模式: {self.config_manager.get('headless')}")
        self.logger.debug(
            f"  - 签到功能: {'启用' if self.config_manager.get('enable_checkin') else '禁用'}"
        )
        self.logger.debug(
            f"  - 拟人化活动: {'启用' if self.config_manager.get('enable_humanlike') else '禁用'}"
        )
        self.logger.debug(f"  - 最大重试次数: {self.retry_manager.max_retries}")

    def _cleanup(self) -> None:
        """清理资源"""
        self.logger.debug("开始清理资源")

        if self.browser_manager:
            self.browser_manager.quit_driver()

        self.logger.debug("资源清理完成")
