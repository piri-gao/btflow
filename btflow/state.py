import threading
from typing import Any, Dict, Type, TypeVar, Optional, get_origin, get_args, Annotated, Callable, get_type_hints, List
import py_trees
from py_trees.blackboard import Client as BlackboardClient
from pydantic import BaseModel, ValidationError

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
    """
    def __init__(self, schema: Type[T], namespace: str = "state"):
        self.schema = schema
        self.namespace = namespace
        self.blackboard = BlackboardClient(name=f"State:{namespace}")
        self.reducers: Dict[str, Callable[[Any, Any], Any]] = {}
        # ActionField 标记的字段: (default_value, default_factory)
        # 如果有 factory 则优先使用 factory，避免可变默认值陷阱
        self._action_fields: Dict[str, tuple] = {}
        
        # 监听器列表
        self._listeners: List[Callable[[], None]] = []
        
        self._lock = threading.Lock()
        
        self._register_schema()

    def subscribe(self, callback: Callable[[], None]):
        """注册状态变更回调"""
        self._listeners.append(callback)

    def _notify_listeners(self):
        """通知所有监听者"""
        for callback in self._listeners:
            try:
                callback()
            except Exception as e:
                print(f"⚠️ [StateManager] Listener callback failed: {e}")

    def _register_schema(self):
        """解析 Schema，注册 Key 到 Blackboard，并提取 Reducer"""
        print(f"🔍 [StateManager] 解析 Schema: {self.schema.__name__}")
        
        try:
            type_hints = get_type_hints(self.schema, include_extras=True)
        except Exception:
            type_hints = {}

        for name, field in self.schema.model_fields.items():
            key = self._get_key(name)
            self.blackboard.register_key(key=key, access=py_trees.common.Access.WRITE)
            self.blackboard.register_key(key=key, access=py_trees.common.Access.READ)
            
            annotation = type_hints.get(name, field.annotation)
            
            if get_origin(annotation) is Annotated:
                args = get_args(annotation)
                for arg in args[1:]:
                    # 检查是否为 ActionField 标记
                    if isinstance(arg, ActionField):
                        print(f"   🎯 [Action] 标记字段: '{name}'")
                        # 存储 (default_value, default_factory) 元组
                        self._action_fields[name] = (field.default, field.default_factory)
                    # 检查是否为 Reducer 函数
                    elif callable(arg):
                        print(f"   ⚙️ [Reducer] 绑定字段: '{name}' -> {arg.__name__}")
                        self.reducers[name] = arg

    def _get_key(self, field_name: str) -> str:
        return f"{self.namespace}/{field_name}"

    def initialize(self, initial_state: Optional[Dict[str, Any]] = None):
        """初始化并校验"""
        data = initial_state or {}
        try:
            model = self.schema(**data)
        except ValidationError as e:
            raise ValueError(f"❌ [StateManager] Init Error: {e}")
        
        with self._lock:
            for name, value in model.model_dump().items():
                key = self._get_key(name)
                self.blackboard.set(key, value)
        
        # 初始化通常不触发通知，或者根据需求触发

    def get(self) -> T:
        """获取快照"""
        data = {}
        with self._lock:
            for name in self.schema.model_fields.keys():
                key = self._get_key(name)
                if self.blackboard.exists(key):
                    val = self.blackboard.get(key)
                    if val is not None:
                        data[name] = val
            return self.schema(**data)

    def update(self, updates: Dict[str, Any]):
        """
        更新状态 (线程安全 + Reducer + 强校验 + 事件通知)
        """
        with self._lock:
            current_data = {}
            for name in self.schema.model_fields.keys():
                key = self._get_key(name)
                if self.blackboard.exists(key):
                    val = self.blackboard.get(key)
                    if val is not None:
                        current_data[name] = val
            
            current_model = self.schema(**current_data)
            pending_writes = {}
            
            for name, update_val in updates.items():
                if name not in self.schema.model_fields:
                    continue 

                if name in self.reducers:
                    reducer = self.reducers[name]
                    old_val = getattr(current_model, name)
                    try:
                        final_val = reducer(old_val, update_val)
                    except Exception as e:
                        raise RuntimeError(f"❌ [StateManager] Reducer '{name}' failed: {e}")
                else:
                    final_val = update_val
                
                pending_writes[name] = final_val

            merged_data = current_model.model_dump()
            merged_data.update(pending_writes)
            
            try:
                self.schema(**merged_data)
            except ValidationError as e:
                raise ValueError(f"❌ [StateManager] Update Validation Failed: {e}")

            for name, val in pending_writes.items():
                key = self._get_key(name)
                self.blackboard.set(key, val)

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
            for name, (default_value, default_factory) in self._action_fields.items():
                key = self._get_key(name)
                # 优先使用 factory 生成新实例
                if default_factory is not None:
                    self.blackboard.set(key, default_factory())
                else:
                    self.blackboard.set(key, default_value)

    def get_actions(self) -> Dict[str, Any]:
        """
        获取所有 ActionField 标记字段的当前值。
        返回动作快照。
        """
        actions = {}
        with self._lock:
            for name in self._action_fields.keys():
                key = self._get_key(name)
                if self.blackboard.exists(key):
                    actions[name] = self.blackboard.get(key)
        return actions