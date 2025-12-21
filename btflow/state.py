import threading
from typing import Any, Dict, Type, TypeVar, Optional, get_origin, get_args, Annotated, Callable, get_type_hints
import py_trees
from py_trees.blackboard import Client as BlackboardClient
from pydantic import BaseModel, ValidationError

T = TypeVar("T", bound=BaseModel)

class StateManager:
    """
    状态管理器
    """
    def __init__(self, schema: Type[T], namespace: str = "state"):
        self.schema = schema
        self.namespace = namespace
        self.blackboard = BlackboardClient(name=f"State:{namespace}")
        self.reducers: Dict[str, Callable[[Any, Any], Any]] = {}
        
        self._lock = threading.Lock()
        
        self._register_schema()

    def _register_schema(self):
        """解析 Schema，注册 Key 到 Blackboard，并提取 Reducer"""
        print(f"🔍 [StateManager] 解析 Schema: {self.schema.__name__}")
        
        try:
            type_hints = get_type_hints(self.schema, include_extras=True)
        except Exception:
            # 某些复杂情况可能失败，回退到 model_fields
            type_hints = {}

        for name, field in self.schema.model_fields.items():
            key = self._get_key(name)
            self.blackboard.register_key(key=key, access=py_trees.common.Access.WRITE)
            self.blackboard.register_key(key=key, access=py_trees.common.Access.READ)
            
            # 优先使用 get_type_hints 里的原始定义，否则用 field.annotation
            annotation = type_hints.get(name, field.annotation)
            
            # 检查 Annotated
            if get_origin(annotation) is Annotated:
                args = get_args(annotation)
                for arg in args[1:]:
                    if callable(arg):
                        print(f"   ⚙️ [Reducer] 绑定字段: '{name}' -> {arg.__name__}")
                        self.reducers[name] = arg
                        break

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
        更新状态 (线程安全 + Reducer + 强校验)
        """
        with self._lock:
            current_data = {}
            for name in self.schema.model_fields.keys():
                key = self._get_key(name)
                if self.blackboard.exists(key):
                    val = self.blackboard.get(key)
                    if val is not None:
                        current_data[name] = val
            
            # 构造基准模型
            current_model = self.schema(**current_data)
            pending_writes = {}
            
            for name, update_val in updates.items():
                if name not in self.schema.model_fields:
                    continue 

                # 应用 Reducer
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

            # 整体验证
            merged_data = current_model.model_dump()
            merged_data.update(pending_writes)
            
            try:
                self.schema(**merged_data)
            except ValidationError as e:
                raise ValueError(f"❌ [StateManager] Update Validation Failed: {e}")

            # 写入
            for name, val in pending_writes.items():
                key = self._get_key(name)
                self.blackboard.set(key, val)