import threading
from typing import Any, Dict, Type, TypeVar, Optional, get_origin, get_args, Annotated, Callable, get_type_hints, List
from pydantic import BaseModel, ValidationError
from btflow.core.logging import logger

T = TypeVar("T", bound=BaseModel)


class ActionField:
    """
    动作字段标记。
    用于标记需要每帧重置的字段（如 RL 场景中的动作输出）。
    
    Usage:
        class AgentState(BaseModel):
            speed: Annotated[float, ActionField()] = 0.0
            fire: Annotated[bool, ActionField()] = False
            messages: List[str] = []  # 非动作，不会被 reset_actions 重置
    """
    pass

class StateManager:
    """
    状态管理器 (Event-Driven)
    支持：类型校验、Reducer、以及数据变更通知
    
    重构说明：
        移除了 py_trees.Blackboard 依赖，直接使用 Pydantic Model 存储状态。
        - 避免多 Agent 场景下的 namespace 冲突
        - 减少中间层 overhead
        - 更简洁的架构
    """
    def __init__(self, schema: Type[T], namespace: str = "state"):
        self.schema = schema
        self.namespace = namespace  # 保留 namespace 用于日志/调试
        self.reducers: Dict[str, Callable[[Any, Any], Any]] = {}
        # ActionField 标记的字段: (default_value, default_factory)
        # 如果有 factory 则优先使用 factory，避免可变默认值陷阱
        self._action_fields: Dict[str, tuple] = {}
        
        # 监听器列表
        self._listeners: List[Callable[[], None]] = []
        
        self._lock = threading.Lock()
        
        # 直接存储 Pydantic Model 实例
        self._data: Optional[T] = None
        
        self._parse_schema()

    def subscribe(self, callback: Callable[[], None]):
        """注册状态变更回调"""
        self._listeners.append(callback)

    def unsubscribe(self, callback: Callable[[], None]):
        """取消订阅状态变更回调（防止内存泄漏）"""
        try:
            self._listeners.remove(callback)
        except ValueError:
            pass  # 回调不存在，忽略

    def _notify_listeners(self):
        """通知所有监听者"""
        for callback in self._listeners:
            try:
                callback()
            except Exception as e:
                logger.warning("⚠️ [StateManager] Listener callback failed: {}", e)

    def _parse_schema(self):
        """解析 Schema，提取 Reducer 和 ActionField 标记"""
        logger.debug("🔍 [StateManager] 解析 Schema: {}", self.schema.__name__)
        
        try:
            type_hints = get_type_hints(self.schema, include_extras=True)
        except Exception:
            type_hints = {}

        for name, field in self.schema.model_fields.items():
            annotation = type_hints.get(name, field.annotation)
            
            if get_origin(annotation) is Annotated:
                args = get_args(annotation)
                for arg in args[1:]:
                    # 检查是否为 ActionField 标记
                    if isinstance(arg, ActionField):
                        logger.debug("   🎯 [Action] 标记字段: '{}'", name)
                        # 存储 (default_value, default_factory) 元组
                        self._action_fields[name] = (field.default, field.default_factory)
                    # 检查是否为 Reducer 函数
                    elif callable(arg):
                        logger.debug("   ⚙️ [Reducer] 绑定字段: '{}' -> {}", name, arg.__name__)
                        self.reducers[name] = arg

    def initialize(self, initial_state: Optional[Dict[str, Any]] = None):
        """初始化并校验"""
        data = initial_state or {}
        try:
            self._data = self.schema(**data)
        except ValidationError as e:
            raise ValueError(f"❌ [StateManager] Init Error: {e}")
        
        # 初始化通常不触发通知

    def get(self) -> T:
        """获取当前状态（返回副本避免外部修改）"""
        with self._lock:
            if self._data is None:
                return self.schema()
            # 返回深拷贝，避免外部直接修改内部状态
            return self.schema(**self._data.model_dump())

    def update(self, updates: Dict[str, Any]):
        """
        更新状态 (线程安全 + Reducer + 强校验 + 事件通知)
        """
        with self._lock:
            if self._data is None:
                self._data = self.schema()
            
            current_data = self._data.model_dump()
            pending_writes = {}
            
            for name, update_val in updates.items():
                # 移除了字段过滤，允许 extra="allow" 模式下的动态字段更新
                # if name not in self.schema.model_fields:
                #     continue 

                if name in self.reducers:
                    reducer = self.reducers[name]
                    old_val = current_data.get(name)
                    try:
                        final_val = reducer(old_val, update_val)
                    except Exception as e:
                        raise RuntimeError(f"❌ [StateManager] Reducer '{name}' failed: {e}")
                else:
                    final_val = update_val
                
                pending_writes[name] = final_val

            merged_data = current_data.copy()
            merged_data.update(pending_writes)
            
            try:
                self._data = self.schema(**merged_data)
            except ValidationError as e:
                raise ValueError(f"❌ [StateManager] Update Validation Failed: {e}")

        # 数据落库后，通知 Runner
        self._notify_listeners()

    def reset_actions(self):
        """
        重置所有 ActionField 标记的字段为默认值。
        应在每帧开始时调用（step 模式）。
        
        Note:
            对于可变默认值（如 List），会调用 default_factory 生成新实例，
            避免多帧之间共享同一对象。
        """
        with self._lock:
            if self._data is None:
                return
            
            current_data = self._data.model_dump()
            
            for name, (default_value, default_factory) in self._action_fields.items():
                # 优先使用 factory 生成新实例
                if default_factory is not None:
                    current_data[name] = default_factory()
                else:
                    current_data[name] = default_value
            
            self._data = self.schema(**current_data)

    def get_actions(self) -> Dict[str, Any]:
        """
        获取所有 ActionField 标记字段的当前值。
        返回动作快照。
        """
        actions = {}
        with self._lock:
            if self._data is None:
                return actions
            
            data_dict = self._data.model_dump()
            for name in self._action_fields.keys():
                if name in data_dict:
                    actions[name] = data_dict[name]
        return actions