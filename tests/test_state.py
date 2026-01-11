import unittest
import operator
from typing import Annotated, List
from pydantic import BaseModel, Field
from btflow.core.state import StateManager

# 1. 定义测试用的 Schema
class TestState(BaseModel):
    # 普通字段 (覆盖模式)
    count: int = 0
    # Reducer 字段 (追加模式)
    history: Annotated[List[str], operator.add] = Field(default_factory=list)

class TestStateManager(unittest.TestCase):
    
    def setUp(self):
        """每个测试前运行"""
        self.state = StateManager(schema=TestState)
        self.state.initialize({"count": 10, "history": ["Init"]})

    def test_basic_get(self):
        """测试读取"""
        data = self.state.get()
        self.assertEqual(data.count, 10)
        self.assertEqual(data.history, ["Init"])

    def test_normal_update(self):
        """测试普通字段覆盖"""
        self.state.update({"count": 20})
        self.assertEqual(self.state.get().count, 20)

    def test_reducer_update(self):
        """测试 Reducer 是否生效 (最重要!)"""
        # 第一次追加
        self.state.update({"history": ["Msg1"]})
        current = self.state.get().history
        # 应该是 Init + Msg1
        self.assertEqual(len(current), 2)
        self.assertEqual(current, ["Init", "Msg1"])
        
        # 第二次追加
        self.state.update({"history": ["Msg2"]})
        self.assertEqual(len(self.state.get().history), 3)

    def test_validation_error(self):
        """测试类型错误是否会被 Pydantic 拦截"""
        with self.assertRaises(ValueError):
            self.state.update({"count": "NotANumber"})

if __name__ == '__main__':
    unittest.main()