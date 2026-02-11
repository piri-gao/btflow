"""
RL Step 模式演示
展示如何使用 BTAgent.step() 进行强化学习训练

模拟一个简单的避障场景：
- 观测: {"obstacle": bool, "distance": float}
- 动作: speed, turn
"""
import sys
import os
import asyncio
from typing import Annotated, List
from pydantic import BaseModel, Field

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# 统一 import
from btflow import BTAgent, StateManager, ActionField, Behaviour, Status


# === 1. 定义 State Schema ===
class RLAgentState(BaseModel):
    # 观测数据（每帧更新）
    obstacle_detected: bool = False
    obstacle_distance: float = 100.0
    
    # 动作输出（ActionField 每帧自动重置）
    speed: Annotated[float, ActionField()] = 0.0
    turn: Annotated[float, ActionField()] = 0.0


# === 2. 定义同步行为节点（肌肉节点） ===
class ObstacleAvoidanceNode(Behaviour):
    """
    简单的避障逻辑（同步节点，立即返回）
    """
    def __init__(self, name: str):
        super().__init__(name)
        self.state_manager: StateManager = None
    
    def update(self) -> Status:
        state = self.state_manager.get()
        
        # 根据观测决策动作
        if state.obstacle_detected:
            if state.obstacle_distance < 10:
                # 紧急转向
                self.state_manager.update({"speed": 0.2, "turn": 0.8})
            else:
                # 减速转向
                self.state_manager.update({"speed": 0.5, "turn": 0.3})
        else:
            # 无障碍，全速前进
            self.state_manager.update({"speed": 1.0, "turn": 0.0})
        
        return Status.SUCCESS


# === 模拟环境 ===
class SimpleEnv:
    """简单的模拟环境"""
    def __init__(self):
        self.step_count = 0
        self.obstacle_pos = 20  # 障碍物位置
        self.agent_pos = 0
    
    def reset(self):
        self.step_count = 0
        self.agent_pos = 0
        return self._get_obs()
    
    def step(self, action: dict):
        # 执行动作
        speed = action.get("speed", 0)
        turn = action.get("turn", 0)
        
        # 简单模拟：前进 + 转向会避开障碍
        if turn > 0.5:
            self.agent_pos += speed  # 转向时障碍物相对距离不变
        else:
            self.agent_pos += speed
        
        self.step_count += 1
        
        # 计算奖励
        distance = self.obstacle_pos - self.agent_pos
        if distance < 5 and turn < 0.5:
            reward = -10  # 碰撞
            done = True
        elif self.agent_pos > 30:
            reward = 10  # 成功通过
            done = True
        else:
            reward = 0.1  # 存活奖励
            done = self.step_count >= 50
        
        return self._get_obs(), reward, done, {}
    
    def _get_obs(self):
        distance = max(0, self.obstacle_pos - self.agent_pos)
        return {
            "obstacle_detected": distance < 30,
            "obstacle_distance": distance
        }


async def main():
    print("=" * 50)
    print("🎮 RL Step 模式演示")
    print("=" * 50)
    
    # === 初始化 ===
    state_manager = StateManager(schema=RLAgentState)
    state_manager.initialize()
    
    # 构建行为树
    root = ObstacleAvoidanceNode("AvoidObstacle")
    agent = BTAgent(root, state_manager)
    
    # 创建环境
    env = SimpleEnv()
    
    # === 训练循环 ===
    num_episodes = 3
    
    for episode in range(num_episodes):
        print(f"\n--- Episode {episode + 1} ---")
        
        # Episode 开始：重置
        obs = env.reset()
        agent.reset(reset_data=True)  # 清空状态
        
        total_reward = 0
        done = False
        frame = 0
        
        while not done:
            # 使用 step() 模式：注入观测 → tick → 获取动作
            action = await agent.step(obs)
            
            # 打印关键帧
            if frame % 10 == 0 or obs["obstacle_distance"] < 15:
                print(f"  Frame {frame}: obs={obs}, action={action}")
            
            # 环境步进
            obs, reward, done, _ = env.step(action)
            total_reward += reward
            frame += 1
        
        print(f"  Episode {episode + 1} 结束: total_reward={total_reward:.2f}, frames={frame}")
    
    print("\n" + "=" * 50)
    print("✅ RL Step 模式演示完成！")
    print("=" * 50)


if __name__ == "__main__":
    asyncio.run(main())
