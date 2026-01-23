import asyncio
from typing import Optional, TYPE_CHECKING
import py_trees
from py_trees.common import Status
from py_trees.decorators import Decorator
from py_trees.behaviour import Behaviour
from dotenv import load_dotenv
from btflow.core.logging import logger

load_dotenv()

if TYPE_CHECKING:
    from btflow.core.state import StateManager


class _Placeholder(Behaviour):
    """
    占位符节点，用于延迟绑定场景。
    在 Studio 中，用户可能先创建装饰器节点，稍后再连接子节点。
    此占位符允许装饰器在无真实子节点时也能被实例化。
    """
    def __init__(self):
        super().__init__(name="__placeholder__")
    
    def update(self) -> Status:
        # 占位符被执行说明配置不完整
        logger.warning("⚠️ [Placeholder] 装饰器子节点未配置!")
        return Status.FAILURE


class LoopUntilSuccess(Decorator):
    """
    循环执行子节点直到成功。
    
    适配 btflow 的 event-driven 模式：
    - 子节点 SUCCESS → 返回 SUCCESS（循环结束）
    - 子节点 FAILURE → 请求重试（通过 call_soon），返回 RUNNING
    - 超过 max_iterations → 返回 FAILURE（熔断保护）
    
    注意：具体的重试间隔由 Runner 的 max_fps 控制，节点本身不关心时间。
    """
    
    def __init__(
        self, 
        name: str, 
        child: Optional[Behaviour] = None, 
        max_iterations: int = 10
    ):
        # 如果没有提供子节点，使用占位符初始化
        actual_child = child if child is not None else _Placeholder()
        super().__init__(name=name, child=actual_child)
        
        self.max_iterations = max_iterations
        self.iteration_count = 0
        self.state_manager: Optional['StateManager'] = None
    
    def bind_child(self, child: Behaviour) -> Behaviour:
        """
        延迟绑定子节点（替换占位符）。
        供 Studio 在运行前调用。
        """
        # 断开旧子节点
        if self.decorated:
            self.decorated.parent = None
        
        # 绑定新子节点
        child.parent = self
        self.decorated = child
        
        # 同步 children 列表（Decorator 内部维护）
        self.children = [child]
        
        logger.debug("🔗 [{}] 绑定子节点: {}", self.name, child.name)
        return child

    def decorate(self, child: Behaviour):
        """兼容装饰器接口"""
        self.bind_child(child)
    
    def initialise(self) -> None:
        """重置迭代计数"""
        self.iteration_count = 0
    
    def update(self) -> Status:
        """
        检查子节点状态。
        """
        if not self.decorated:
            return Status.FAILURE

        child_status = self.decorated.status
        
        if child_status == Status.SUCCESS:
            logger.debug("✅ [{}] 循环成功结束 (共 {} 轮)", self.name, self.iteration_count)
            return Status.SUCCESS
        
        elif child_status == Status.RUNNING:
            return Status.RUNNING
        
        elif child_status == Status.FAILURE:
            self.iteration_count += 1
            if self.iteration_count >= self.max_iterations:
                logger.warning("⚠️ [{}] 达到最大迭代次数 ({}), 强制停止", 
                             self.name, self.max_iterations)
                return Status.FAILURE
            
            logger.debug("🔄 [{}] 第 {} 轮失败，继续下一轮 (max={})", 
                        self.name, self.iteration_count, self.max_iterations)
            
            # 重置子节点状态，准备下一轮
            self.decorated.stop(Status.INVALID)
            
            # 使用 call_soon 请求重试（不关心具体等多久，由 Runner 控制）
            if self.state_manager is not None:
                try:
                    loop = asyncio.get_running_loop()
                    loop.call_soon(self.state_manager.update, {})
                except RuntimeError:
                    # Fallback：如果没有运行中的 event loop，则同步调用
                    self.state_manager.update({})
            
            return Status.RUNNING
        
        return Status.INVALID
    
    def terminate(self, new_status: Status) -> None:
        """清理记录"""
        self.iteration_count = 0
        if self.decorated:
             self.decorated.stop(new_status)
