"""
脑肌结合 Demo（真实 LLM 版本）
展示如何在 step() 模式下同时运行异步大脑节点和同步肌肉节点

场景模拟：机器人导航
- 大脑（Gemini LLM）：异步决策目标点（低频）
- 肌肉（控制器）：同步执行运动（高频，每帧）
- 环境：2D 网格世界，有障碍物

使用前请确保设置环境变量：
    export GOOGLE_API_KEY="your-api-key"
"""
import sys
import os
import asyncio
import json
from typing import Annotated
from pydantic import BaseModel
import py_trees
from py_trees.composites import Parallel
from py_trees.common import ParallelPolicy
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from btflow.core import AsyncBehaviour
from btflow.state import StateManager, ActionField
from btflow.runtime import ReactiveRunner
from btflow.agent import BTAgent

from google import genai
from google.genai import types

load_dotenv()


# === 1. 定义 State Schema ===
class BrainMuscleState(BaseModel):
    # 观测数据（每帧更新）
    position: tuple = (0.0, 0.0)
    obstacles: list = []  # 障碍物位置列表
    goal: tuple = (20.0, 20.0)  # 最终目标
    frame: int = 0
    
    # 大脑决策（持久化，低频更新）
    waypoint: tuple = (5.0, 5.0)  # 中间路径点
    reasoning: str = ""  # LLM 的推理过程
    plan_count: int = 0
    
    # 肌肉动作（ActionField，每帧重置）
    velocity_x: Annotated[float, ActionField()] = 0.0
    velocity_y: Annotated[float, ActionField()] = 0.0


# === 2. Gemini 客户端 ===
def get_gemini_client():
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        raise ValueError("❌ GOOGLE_API_KEY not found! Please set it in .env or environment.")
    return genai.Client(api_key=api_key)


# === 3. 大脑节点：LLM 路径规划 ===
class LLMBrainNode(AsyncBehaviour):
    """
    真实 LLM 决策：根据当前位置和障碍物规划下一个路径点
    """
    def __init__(self, name: str, state_manager: StateManager, model: str = "gemini-2.0-flash"):
        super().__init__(name)
        self.state_manager = state_manager
        self.model = model
        self.client = get_gemini_client()
    
    async def update_async(self) -> py_trees.common.Status:
        state = self.state_manager.get()
        
        print(f"\n🧠 [Brain] LLM 正在规划路径...")
        print(f"   当前位置: {state.position}")
        print(f"   最终目标: {state.goal}")
        
        prompt = f"""你是一个机器人导航规划器。

当前状态：
- 机器人位置: {state.position}
- 最终目标: {state.goal}
- 障碍物位置: {state.obstacles}

请规划下一个路径点（waypoint），要求：
1. 朝着最终目标方向前进
2. 避开障碍物（保持至少 3 个单位距离）
3. 每次移动距离不超过 8 个单位

请以 JSON 格式返回：
{{"waypoint": [x, y], "reasoning": "简短说明"}}
"""
        
        try:
            response = await asyncio.wait_for(
                self.client.aio.models.generate_content(
                    model=self.model,
                    contents=prompt,
                    config=types.GenerateContentConfig(
                        system_instruction="你是一个精确的路径规划器。只返回 JSON，不要其他内容。",
                        temperature=0.3
                    )
                ),
                timeout=30.0
            )
            
            # 解析 JSON
            text = response.text.strip()
            # 移除可能的 markdown 代码块标记
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
            if text.endswith("```"):
                text = text.rsplit("\n", 1)[0]
            text = text.strip()
            
            result = json.loads(text)
            waypoint = tuple(result["waypoint"])
            reasoning = result.get("reasoning", "")
            
            self.state_manager.update({
                "waypoint": waypoint,
                "reasoning": reasoning,
                "plan_count": state.plan_count + 1
            })
            
            print(f"   📍 新路径点: {waypoint}")
            print(f"   💭 推理: {reasoning}")
            
            return py_trees.common.Status.SUCCESS
            
        except asyncio.TimeoutError:
            print(f"🔥 [Brain] LLM 超时!")
            return py_trees.common.Status.FAILURE
        except Exception as e:
            print(f"🔥 [Brain] 错误: {e}")
            return py_trees.common.Status.FAILURE


# === 4. 肌肉节点：同步控制 ===
class MuscleNode(py_trees.behaviour.Behaviour):
    """
    实时控制：根据当前位置和路径点计算速度
    每帧执行，读取大脑的 waypoint
    """
    def __init__(self, name: str, state_manager: StateManager):
        super().__init__(name)
        self.state_manager = state_manager
    
    def update(self) -> py_trees.common.Status:
        state = self.state_manager.get()
        
        # 计算到路径点的方向
        dx = state.waypoint[0] - state.position[0]
        dy = state.waypoint[1] - state.position[1]
        
        distance = (dx**2 + dy**2) ** 0.5
        
        if distance > 0.5:
            # 归一化 + 速度控制
            speed = min(1.0, distance / 3.0)
            vx = (dx / distance) * speed
            vy = (dy / distance) * speed
        else:
            vx, vy = 0.0, 0.0
        
        self.state_manager.update({
            "velocity_x": vx,
            "velocity_y": vy
        })
        
        return py_trees.common.Status.SUCCESS


# === 5. 简单环境模拟 ===
class GridWorldEnv:
    def __init__(self):
        self.position = [0.0, 0.0]
        self.goal = (20.0, 20.0)
        self.obstacles = [
            (8.0, 8.0),
            (12.0, 5.0),
            (6.0, 15.0)
        ]
        self.frame = 0
    
    def reset(self):
        self.position = [0.0, 0.0]
        self.frame = 0
        return self._get_obs()
    
    def step(self, action: dict):
        vx = action.get("velocity_x", 0)
        vy = action.get("velocity_y", 0)
        
        dt = 0.1  # 10Hz
        self.position[0] += vx * dt
        self.position[1] += vy * dt
        self.frame += 1
        
        # 检查是否到达目标
        dx = self.goal[0] - self.position[0]
        dy = self.goal[1] - self.position[1]
        done = (dx**2 + dy**2) ** 0.5 < 2.0
        
        return self._get_obs(), done
    
    def _get_obs(self):
        return {
            "position": tuple(self.position),
            "obstacles": self.obstacles,
            "goal": self.goal,
            "frame": self.frame
        }


async def main():
    print("=" * 60)
    print("🧠💪 脑肌结合 Demo（真实 LLM 版本）")
    print("展示 Gemini LLM 大脑 + 同步肌肉 在 step() 模式下协同工作")
    print("=" * 60)
    
    # === 初始化 ===
    state_manager = StateManager(schema=BrainMuscleState)
    state_manager.initialize()
    
    # 构建行为树
    brain_node = LLMBrainNode("LLM_Brain", state_manager)
    muscle_node = MuscleNode("Muscle", state_manager)
    
    root = Parallel(
        name="BrainMuscle",
        policy=ParallelPolicy.SuccessOnAll(),
        children=[brain_node, muscle_node]
    )
    
    runner = ReactiveRunner(root, state_manager)
    agent = BTAgent(runner)
    
    # 创建环境
    env = GridWorldEnv()
    
    # === 运行循环 ===
    max_frames = 200
    obs = env.reset()
    
    print(f"\n🎬 开始运行 (最多 {max_frames} 帧)")
    print(f"   初始位置: {obs['position']}")
    print(f"   目标位置: {obs['goal']}")
    print(f"   障碍物: {obs['obstacles']}")
    print()
    
    done = False
    
    for frame in range(max_frames):
        if done:
            break
            
        # 关键：yield_to_async=True 让 LLM 任务有机会执行
        action = await agent.step(obs, yield_to_async=True)
        
        # 应用动作
        obs, done = env.step(action)
        
        # 打印关键帧
        if frame % 20 == 0:
            state = state_manager.get()
            brain_status = brain_node.status.name
            print(f"  Frame {frame:3d}: pos=({obs['position'][0]:5.1f}, {obs['position'][1]:5.1f}) "
                  f"→ waypoint=({state.waypoint[0]:5.1f}, {state.waypoint[1]:5.1f}) "
                  f"[Brain: {brain_status}, Plans: {state.plan_count}]")
        
        # 小延迟模拟帧率
        await asyncio.sleep(0.05)
    
    final_state = state_manager.get()
    print()
    print("=" * 60)
    if done:
        print(f"🎉 成功到达目标!")
    else:
        print(f"⏰ 达到最大帧数限制")
    print(f"   总帧数: {frame + 1}")
    print(f"   LLM 规划次数: {final_state.plan_count}")
    print(f"   最终位置: {obs['position']}")
    print(f"   最后推理: {final_state.reasoning}")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(main())
