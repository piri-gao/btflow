import os
import asyncio
from typing import List, Dict, Any
from py_trees.common import Status
from btflow.core import AsyncBehaviour
from btflow.state import StateManager
from dotenv import load_dotenv
from btflow.logging import logger

# 引入 Google GenAI SDK
from google import genai
from google.genai import types

load_dotenv()

class GeminiNode(AsyncBehaviour):
    """
    Gemini 节点 (基于 google-genai SDK 原生异步支持)
    """
    def __init__(self, 
                 name: str, 
                 state_manager: StateManager,
                 model: str = "gemini-2.5-flash", 
                 system_prompt: str = "You are a helpful AI assistant."):
        super().__init__(name)
        self.state = state_manager
        self.model = model
        self.system_prompt = system_prompt
        
        api_key = os.getenv("GOOGLE_API_KEY")
        if not api_key:
            logger.warning("⚠️ [GeminiNode] Warning: GOOGLE_API_KEY not found in env!")

        # 初始化客户端 (同步/异步共用同一个 client 实例)
        self.client = genai.Client(api_key=api_key)

    async def update_async(self) -> Status:
        try:
            # 1. 准备上下文
            current_state = self.state.get()
            
            # 将历史消息转换为 Gemini 接受的 contents 格式 (字符串或列表)
            prompt_content = self._build_prompt(current_state.messages)
            
            logger.debug("   ✨ [{}] 正在询问 Gemini ({})...", self.name, self.model)

            # 2. 调用 API (原生异步)
            # 关键点：使用 .aio 访问异步方法
            response = await asyncio.wait_for(
                            self.client.aio.models.generate_content(
                                model=self.model,
                                contents=prompt_content,
                                config=types.GenerateContentConfig(
                                    system_instruction=self.system_prompt,
                                    temperature=0.7
                                )
                            ),
                            timeout=30.0 # 30秒超时
                        )
            
            content = response.text
            # print(f"   📥 [Gemini] 回复: {content[:50]}...")

            # 3. 写入状态 (触发 Runner 唤醒)
            self.state.update({
                "messages": [f"Gemini: {content}"], 
                "step_count": 1
            })
            
            return Status.SUCCESS
        except asyncio.TimeoutError:
            logger.warning("   ⏰ [{}] 请求超时", self.name)
            return Status.FAILURE
        except Exception as e:
            logger.error("   🔥 [{}] Gemini 调用失败: {}", self.name, e)
            self.feedback_message = str(e)
            return Status.FAILURE

    def _build_prompt(self, messages: List[Any]) -> str:
        """
        简单地将历史消息拼接为 prompt。
        更高级的做法是构建 ChatSession (client.chats.create)，
        但这需要维护一个 session 对象，对于单次无状态节点，拼接字符串最简单。
        """
        full_text = ""
        for msg in messages:
            # 简单处理：将列表中的每一项转为字符串并换行
            full_text += str(msg) + "\n"
        return full_text