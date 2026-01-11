"""
BTflow 统一日志配置模块

Usage:
    from btflow.logging import logger
    
    logger.debug("调试信息")
    logger.info("一般信息")
    logger.warning("警告信息")
    logger.error("错误信息")

配置日志级别:
    import os
    os.environ["BTFLOW_LOG_LEVEL"] = "DEBUG"  # 在 import btflow 之前设置
"""
import os
import sys
from loguru import logger

# 移除默认 handler
logger.remove()

# 从环境变量读取日志级别，默认 INFO
log_level = os.environ.get("BTFLOW_LOG_LEVEL", "INFO").upper()

# 添加控制台 handler，带颜色和简洁格式
logger.add(
    sys.stderr,
    format="<level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    level=log_level,
    colorize=True,
)

__all__ = ["logger"]
