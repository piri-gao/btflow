"""
脑肌结合 Demo（真实 LLM 版本）
展示如何在 step() 模式下同时运行异步大脑节点和同步肌肉节点

场景模拟：机器人导航
- 大脑（LLM）：异步决策目标点（低频）
- 肌肉（控制器）：同步执行移动（高频，每帧）
- 环境：2D 网格世界，有障碍物

使用前请确保设置环境变量（任选其一）：
    export GOOGLE_API_KEY="your-api-key"
    export OPENAI_API_KEY="your-api-key"
    export API_KEY="your-api-key"
    export BASE_URL="https://your-openai-compatible-endpoint"
"""
import sys
import os
import asyncio
import json
from typing import Annotated
from pydantic import BaseModel
from dotenv import load_dotenv

sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

# 统一 import
from btflow import BTAgent, StateManager, ActionField, AsyncBehaviour, Parallel, ParallelPolicy, Status, Behaviour
from btflow.llm import LLMProvider

load_dotenv()


# === 1. 定义 State Schema ===
class BrainMuscleState(BaseModel):
    # 观测数据（每帧更新）
    position: tuple = (0, 0)
    obstacles: list = []  # 障碍物位置列表
    goal: tuple = (19, 19)  # 最终目标
    frame: int = 0
    
    # 大脑决策（持久化，低频更新）
    waypoint: tuple = (5, 5)  # 中间路径点
    reasoning: str = ""  # LLM 的推理过程
    plan_count: int = 0
    
    # 肌肉动作（ActionField，每帧重置）
    move_x: Annotated[int, ActionField()] = 0
    move_y: Annotated[int, ActionField()] = 0


# === 2. 大脑节点：LLM 路径规划 ===
class LLMBrainNode(AsyncBehaviour):
    """
    真实 LLM 决策：根据当前位置和障碍物规划下一个路径点
    """
    def __init__(
        self,
        name: str,
        state_manager: StateManager,
        provider: LLMProvider,
        model: str = "gemini-2.0-flash",
    ):
        super().__init__(name)
        self.state_manager = state_manager
        self.model = model
        self.provider = provider
    
    async def update_async(self) -> Status:
        state = self.state_manager.get()

        if state.plan_count > 0 and state.frame % 5 != 0:
            return Status.SUCCESS
        
        print(f"\n🧠 [Brain] LLM 正在规划路径...")
        print(f"   当前位置: {state.position}")
        print(f"   最终目标: {state.goal}")
        
        prompt = f"""你是一个机器人导航规划器。

当前状态（20x20 网格，坐标范围 0-19）：
- 机器人位置: {state.position}
- 最终目标: {state.goal}
- 障碍物位置: {state.obstacles}

请规划下一个路径点（waypoint），要求：
1. waypoint 必须是整数坐标 [x, y]
2. waypoint 必须在 0-19 范围内
3. waypoint 不能落在障碍物上
4. 尽量朝向最终目标，并绕开障碍物

请以 JSON 格式返回：
{{"waypoint": [x, y], "reasoning": "简短说明"}}
"""
        
        try:
            response = await self.provider.generate_text(
                prompt=prompt,
                model=self.model,
                system_instruction="你是一个精确的路径规划器。只返回 JSON，不要其他内容。",
                temperature=0.3,
                timeout=30.0,
            )
            
            # 解析 JSON
            text = response.content.strip()
            # 移除可能的 markdown 代码块标记
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
            if text.endswith("```"):
                text = text.rsplit("\n", 1)[0]
            text = text.strip()
            
            result = json.loads(text)
            waypoint_raw = result.get("waypoint", [])
            if not isinstance(waypoint_raw, (list, tuple)) or len(waypoint_raw) != 2:
                raise ValueError("Invalid waypoint format")
            x = int(round(float(waypoint_raw[0])))
            y = int(round(float(waypoint_raw[1])))
            x = max(0, min(19, x))
            y = max(0, min(19, y))
            if (x, y) in state.obstacles:
                x, y = state.waypoint
            waypoint = (x, y)
            reasoning = result.get("reasoning", "")
            
            self.state_manager.update({
                "waypoint": waypoint,
                "reasoning": reasoning,
                "plan_count": state.plan_count + 1
            })
            
            print(f"   📍 新路径点: {waypoint}")
            print(f"   💭 推理: {reasoning}")
            
            return Status.SUCCESS
            
        except Exception as e:
            print(f"🔥 [Brain] 错误: {e}")
            return Status.FAILURE


# === 4. 肌肉节点：同步控制 ===
class MuscleNode(Behaviour):
    """
    实时控制：根据当前位置和路径点选择下一步移动
    每帧执行，读取大脑的 waypoint
    """
    def __init__(self, name: str):
        super().__init__(name)
        # 依赖注入：由 Runner 在运行时赋值
        self.state_manager: StateManager = None
    
    def update(self) -> Status:
        state = self.state_manager.get()
        
        dx = state.waypoint[0] - state.position[0]
        dy = state.waypoint[1] - state.position[1]

        if dx == 0 and dy == 0:
            step_x, step_y = 0, 0
        elif abs(dx) >= abs(dy):
            step_x = 1 if dx > 0 else -1
            step_y = 0
        else:
            step_x = 0
            step_y = 1 if dy > 0 else -1
        
        self.state_manager.update({
            "move_x": step_x,
            "move_y": step_y
        })
        
        return Status.SUCCESS


# === 5. 简单环境模拟 ===
class GridWorldEnv:
    def __init__(self):
        self.width = 20
        self.height = 20
        self.position = [0, 0]
        self.goal = (19, 19)
        self.obstacles = {
            (8, 8),
            (12, 5),
            (6, 15),
        }
        self.frame = 0
    
    def reset(self):
        self.position = [0, 0]
        self.frame = 0
        return self._get_obs()
    
    def step(self, action: dict):
        move_x = int(action.get("move_x", 0))
        move_y = int(action.get("move_y", 0))

        if abs(move_x) + abs(move_y) > 1:
            move_y = 0

        next_x = self.position[0] + move_x
        next_y = self.position[1] + move_y
        if (
            0 <= next_x < self.width
            and 0 <= next_y < self.height
            and (next_x, next_y) not in self.obstacles
        ):
            self.position[0] = next_x
            self.position[1] = next_y

        self.frame += 1
        
        # 检查是否到达目标
        done = tuple(self.position) == self.goal
        
        return self._get_obs(), done
    
    def _get_obs(self):
        return {
            "position": tuple(self.position),
            "obstacles": sorted(self.obstacles),
            "goal": self.goal,
            "frame": self.frame
        }


async def main():
    print("=" * 60)
    print("🧠💪 脑肌结合 Demo（真实 LLM 版本）")
    print("展示 LLM 大脑 + 同步肌肉 在 step() 模式下协同工作")
    print("=" * 60)
    
    # === 初始化 ===
    state_manager = StateManager(schema=BrainMuscleState)
    state_manager.initialize()
    
    base_url = os.getenv("BASE_URL")
    try:
        provider = LLMProvider.default(preference=["gemini", "openai"], base_url=base_url)
    except RuntimeError as e:
        print(str(e))
        return

    # 构建行为树
    brain_node = LLMBrainNode("LLM_Brain", state_manager, provider=provider)
    muscle_node = MuscleNode("Muscle")
    
    root = Parallel(
        name="BrainMuscle",
        policy=ParallelPolicy.SuccessOnAll(synchronise=False),
        children=[brain_node, muscle_node]
    )
    
    # 创建 Agent (无需手动创建 Runner)
    agent = BTAgent(root, state_manager)
    
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
        if frame % 5 == 0:
            state = state_manager.get()
            brain_status = brain_node.status.name
            print(f"  Frame {frame:3d}: pos=({obs['position'][0]:2d}, {obs['position'][1]:2d}) "
                  f"→ waypoint=({state.waypoint[0]:2d}, {state.waypoint[1]:2d}) "
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
