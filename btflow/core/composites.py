"""
BTflow Composites: 结构控制节点

提供 btflow 专用的组合节点/装饰器节点，适配 event-driven 模式。
"""
from typing import Optional, TYPE_CHECKING
from py_trees.decorators import Decorator
from py_trees.common import Status
from btflow.core.logging import logger

if TYPE_CHECKING:
    from btflow.core.state import StateManager


class LoopUntilSuccess(Decorator):
    """
    循环执行子节点直到成功。
    
    适配 btflow 的 event-driven 模式：
    - 子节点 SUCCESS → 返回 SUCCESS（循环结束）
    - 子节点 FAILURE → 触发 tick_signal，返回 RUNNING（继续循环）
    - 子节点 RUNNING → 返回 RUNNING（等待）
    - 超过 max_iterations → 返回 FAILURE（熔断保护）
    
    与 py_trees.Retry 的区别：
    - Retry 在子节点失败时返回 FAILURE，导致 btflow Runner 停止
    - LoopUntilSuccess 在子节点失败时返回 RUNNING，保持 event-driven 循环
    
    Example:
        from btflow.core.composites import LoopUntilSuccess
        from py_trees.composites import Sequence
        
        root = LoopUntilSuccess(
            name="ReActLoop",
            max_iterations=10,
            child=Sequence("Body", memory=False, children=[
                llm_node,
                tool_executor,
                check_node  # 返回 SUCCESS 表示完成，FAILURE 表示继续
            ])
        )
    """
    
    def __init__(
        self, 
        name: str, 
        child, 
        max_iterations: int = 10
    ):
        """
        Args:
            name: 节点名称
            child: 子节点（通常是 Sequence）
            max_iterations: 最大迭代次数（熔断保护）
        """
        super().__init__(name=name, child=child)
        self.max_iterations = max_iterations
        self.iteration_count = 0
        self.state_manager: Optional['StateManager'] = None
    
    def initialise(self) -> None:
        """重置迭代计数"""
        self.iteration_count = 0
    
    def update(self) -> Status:
        """
        检查子节点状态，决定是否继续循环。
        """
        child_status = self.decorated.status
        
        if child_status == Status.SUCCESS:
            # 子节点成功，循环结束
            logger.debug("✅ [{}] 循环成功结束 (共 {} 轮)", self.name, self.iteration_count)
            return Status.SUCCESS
        
        elif child_status == Status.RUNNING:
            # 子节点运行中，继续等待
            return Status.RUNNING
        
        elif child_status == Status.FAILURE:
            # 子节点失败，准备下一轮
            self.iteration_count += 1
            
            # 熔断检查
            if self.iteration_count >= self.max_iterations:
                logger.warning("⚠️ [{}] 达到最大迭代次数 ({}), 强制停止", 
                             self.name, self.max_iterations)
                return Status.FAILURE
            
            logger.debug("🔄 [{}] 第 {} 轮失败，继续下一轮 (max={})", 
                        self.name, self.iteration_count, self.max_iterations)
            
            # 重置子节点状态，准备下一轮
            self.decorated.stop(Status.INVALID)
            
            # 触发 tick_signal，确保 event-driven 模式下能继续执行
            if self.state_manager is not None:
                self.state_manager.update({})
            
            return Status.RUNNING
        
        # INVALID 或其他状态
        return Status.INVALID
    
    def terminate(self, new_status: Status) -> None:
        """终止时重置迭代计数"""
        self.iteration_count = 0
        super().terminate(new_status)
