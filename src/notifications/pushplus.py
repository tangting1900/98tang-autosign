"""
PushPlus 通知模块（微信推送）
"""

import json
import logging
import requests
from datetime import datetime
from typing import List, Optional
from dataclasses import dataclass

@dataclass
class TaskResult:
    task_type: str
    success: bool
    message: str
    details: Optional[str] = None
    timestamp: Optional[str] = None

    def __post_init__(self):
        if self.timestamp is None:
            self.timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

@dataclass
class ExecutionSummary:
    username: str
    start_time: str
    end_time: str
    total_duration: str
    tasks: List[TaskResult]
    overall_success: bool

    def to_message(self) -> str:
        status_emoji = "✅" if self.overall_success else "❌"
        status_text = "成功" if self.overall_success else "失败"

        success_count = sum(1 for task in self.tasks if task.success)
        total_count = len(self.tasks)

        message = f"""# 98tang-autosign 执行报告

**账号:** `{self.username}`  
**日期:** `{self.start_time.split()[0]}`  
**开始时间:** `{self.start_time.split()[1]}`  
**结束时间:** `{self.end_time.split()[1]}`  
**总耗时:** `{self.total_duration}`  
**执行状态:** {status_emoji} **{status_text}**  
**任务统计:** `{success_count}/{total_count}` 成功

## 任务详情:
"""

        for task in self.tasks:
            task_emoji = "✅" if task.success else "❌"
            task_name = {
                "signin": "签到",
                "reply": "回帖",
                "browse": "拟真浏览",
            }.get(task.task_type, task.task_type)

            message += f"{task_emoji} **{task_name}:** `{task.message}`\n"
            if task.details:
                message += f"  *{task.details}*\n"

        return message.strip()

class PushPlusNotifier:
    def __init__(
        self,
        token: str,
        logger: Optional[logging.Logger] = None,
    ):
        self.token = token.strip() if token else ""
        self.url = "http://www.pushplus.plus/send"
        self.logger = logger or logging.getLogger(__name__)

        if not self.token:
            raise ValueError("PushPlus Token 不能为空")

        self.logger.debug("PushPlus通知器初始化完成")

    def send_message(self, title: str, content: str, template: str = "markdown") -> bool:
        try:
            data = {
                "token": self.token,
                "title": title,
                "content": content,
                "template": template,
                "channel": "wechat",
            }

            headers = {'Content-Type': 'application/json'}

            response = requests.post(self.url, json=data, headers=headers, timeout=30)
            if response.status_code == 200:
                result = response.json()
                if result.get("code") == 200:
                    self.logger.debug("PushPlus消息发送成功")
                    return True
                else:
                    self.logger.error(f"PushPlus API错误: {result.get('msg')}")
                    return False
            else:
                self.logger.error(f"PushPlus HTTP错误: {response.status_code}")
                return False

        except Exception as e:
            self.logger.error(f"PushPlus发送异常: {e}")
            return False

    def send_summary(self, summary: ExecutionSummary) -> bool:
        title = "98tang-autosign 执行报告"
        content = summary.to_message()
        return self.send_message(title, content)

    def send_error(self, error_message: str, error_type: str = "程序错误") -> bool:
        title = "98tang-autosign 错误报告"
        content = f"""
# 98tang-autosign 错误报告

**错误类型:** `{error_type}`  
**时间:** `{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}`

## 错误详情:	
"""
        return self.send_message(title, content.strip())

    def test_connection(self) -> bool:
        title = "98tang-autosign 连接测试"
        content = f"""
# 连接测试成功

PushPlus 配置正常  
时间: `{datetime.now().strftime("%Y-%m-%d %H:%M:%S")}`
"""
        return self.send_message(title, content.strip())
