import json
import re
from typing import Any, List, Optional, Tuple

from py_trees.common import Status
from py_trees.behaviour import Behaviour

from btflow.core.logging import logger
from btflow.messages import Message
from btflow.messages.formatting import message_to_text


class ParserNode(Behaviour):
    """
    Parse structured information from the latest assistant message.
    """

    FINAL_ANSWER_PATTERN = re.compile(r"Final Answer:\s*(.+)", re.IGNORECASE | re.DOTALL)
    SCORE_PATTERN = re.compile(r"Score:\s*([0-9]+(?:\.[0-9]+)?)", re.IGNORECASE)
    ANSWER_PATTERN = re.compile(r"Answer:\s*(.+?)(?=\n\s*Score:|$)", re.DOTALL | re.IGNORECASE)
    REFLECTION_PATTERN = re.compile(r"Reflection:\s*(.+)", re.DOTALL | re.IGNORECASE)
    ACTION_PATTERN = re.compile(r"Action:\s*(.+?)\s*\n\s*Input:\s*(.+)", re.IGNORECASE | re.DOTALL)

    def __init__(
        self,
        name: str = "Parser",
        preset: str = "final_answer",
        custom_pattern: str = "",
    ):
        super().__init__(name)
        self.preset = preset
        self.custom_pattern = custom_pattern
        self.state_manager = None

    def update(self) -> Status:
        if self.state_manager is None:
            logger.error("❌ [{}] state_manager 未注入", self.name)
            return Status.FAILURE

        state = self.state_manager.get()
        messages: List[Message] = list(getattr(state, "messages", []) or [])
        if not messages:
            logger.warning("⚠️ [{}] No messages to parse", self.name)
            return Status.FAILURE

        content = self._latest_assistant_text(messages)
        if not content:
            logger.warning("⚠️ [{}] Empty assistant content", self.name)
            return Status.FAILURE

        updates: dict[str, Any] = {}

        if self.preset == "final_answer":
            final_answer = self._parse_final_answer(content)
            if final_answer:
                updates["final_answer"] = final_answer
        elif self.preset == "score":
            answer, score, reflection = self._parse_score(content)
            if answer is not None:
                updates["answer"] = answer
                updates["answer_history"] = [answer]
            if score is not None:
                updates["score"] = score
                updates["score_history"] = [score]
            if reflection is not None:
                updates["reflection"] = reflection
                updates["reflection_history"] = [reflection]
        elif self.preset == "action":
            actions = self._parse_actions(messages)
            updates["actions"] = actions
        elif self.preset == "custom":
            parsed = self._parse_custom(content)
            if parsed is not None:
                updates["parsed"] = parsed
        else:
            logger.warning("⚠️ [{}] Unknown preset: {}", self.name, self.preset)

        if updates:
            self.state_manager.update(updates)

        return Status.SUCCESS

    def _latest_assistant_text(self, messages: List[Message]) -> str:
        for msg in reversed(messages):
            if isinstance(msg, Message) and msg.role == "assistant":
                return message_to_text(msg)
            if not isinstance(msg, Message):
                return message_to_text(msg)
        return ""

    def _parse_final_answer(self, content: str) -> Optional[str]:
        match = self.FINAL_ANSWER_PATTERN.search(content)
        if match:
            return match.group(1).strip()
        return None

    def _parse_score(self, content: str) -> tuple[Optional[str], Optional[float], Optional[str]]:
        answer = None
        score = None
        reflection = None

        answer_match = self.ANSWER_PATTERN.search(content)
        if answer_match:
            answer = answer_match.group(1).strip()

        score_match = self.SCORE_PATTERN.search(content)
        if score_match:
            try:
                score = float(score_match.group(1))
            except ValueError:
                score = None

        reflection_match = self.REFLECTION_PATTERN.search(content)
        if reflection_match:
            reflection = reflection_match.group(1).strip()

        return answer, score, reflection

    def _parse_custom(self, content: str) -> Optional[str]:
        if not self.custom_pattern:
            return None
        try:
            pattern = re.compile(self.custom_pattern)
        except re.error as exc:
            logger.warning("⚠️ [{}] Invalid regex: {}", self.name, exc)
            return None
        match = pattern.search(content)
        if not match:
            return None
        if match.groups():
            return match.group(1)
        return match.group(0)

    def _parse_actions(self, messages: List[Message]) -> List[dict[str, Any]]:
        last_msg = None
        for msg in reversed(messages):
            if isinstance(msg, Message) and msg.role == "assistant":
                last_msg = msg
                break
            if not isinstance(msg, Message):
                last_msg = msg
                break

        if last_msg is None:
            return []

        # Priority 1: structured tool_calls
        if isinstance(last_msg, Message) and last_msg.tool_calls:
            actions = []
            for tc in last_msg.tool_calls:
                extracted = self._extract_tool_call_from_dict(tc)
                if extracted:
                    tool_name, args = extracted
                    actions.append({"tool": tool_name, "arguments": args})
            if actions:
                return actions

        content = message_to_text(last_msg)
        if not content:
            return []

        # Priority 2: ToolCall JSON marker
        extracted = self._extract_tool_call_from_marked(content)
        if extracted:
            tool_name, args = extracted
            return [{"tool": tool_name, "arguments": args}]

        # Priority 3: legacy Action/Input
        match = self.ACTION_PATTERN.search(content)
        if match:
            tool_name = match.group(1).strip().lower()
            tool_input = match.group(2).strip()
            return [{"tool": tool_name, "arguments": tool_input}]

        return []

    def _extract_tool_call_from_dict(self, data: Any) -> Optional[Tuple[str, Any]]:
        if not isinstance(data, dict):
            return None

        if "tool_calls" in data and isinstance(data["tool_calls"], list) and data["tool_calls"]:
            return self._extract_tool_call_from_dict(data["tool_calls"][0])

        if "function_call" in data and isinstance(data["function_call"], dict):
            return self._extract_tool_call_from_dict(data["function_call"])

        if "function" in data and isinstance(data["function"], dict):
            return self._extract_tool_call_from_dict(data["function"])

        tool_name = data.get("tool") or data.get("name") or data.get("tool_name")
        args_container = None
        for key in ("arguments", "args", "input"):
            if key in data:
                args_container = data[key]
                break

        if not tool_name:
            return None

        args = args_container
        if isinstance(args, str):
            args_str = args.strip()
            if args_str.startswith("{") or args_str.startswith("["):
                try:
                    args = json.loads(args_str)
                except json.JSONDecodeError:
                    pass

        return str(tool_name).lower(), args

    def _extract_tool_call_from_marked(self, content: str) -> Optional[Tuple[str, Any]]:
        marker = "ToolCall:"
        idx = content.find(marker)
        if idx == -1:
            return None

        payload = content[idx + len(marker):].strip()
        try:
            obj = json.loads(payload)
        except json.JSONDecodeError:
            return None

        return self._extract_tool_call_from_dict(obj)


class ConditionNode(Behaviour):
    """
    Evaluate a condition based on preset rules.
    """

    FINAL_ANSWER_PATTERN = re.compile(r"Final Answer:\s*(.+)", re.IGNORECASE | re.DOTALL)

    def __init__(
        self,
        name: str = "Condition",
        preset: str = "score_gte",
        threshold: float = 8.0,
        max_rounds: int = 10,
    ):
        super().__init__(name)
        self.preset = preset
        self.threshold = threshold
        self.max_rounds = max_rounds
        self.state_manager = None

    def update(self) -> Status:
        if self.state_manager is None:
            logger.error("❌ [{}] state_manager 未注入", self.name)
            return Status.FAILURE

        state = self.state_manager.get()
        passed = False
        updates: dict[str, Any] = {}

        if self.preset == "score_gte":
            score = getattr(state, "score", 0.0)
            passed = score >= self.threshold
            updates["is_complete"] = passed
        elif self.preset == "has_final_answer":
            final_answer = getattr(state, "final_answer", None)
            if not final_answer:
                messages: List[Message] = list(getattr(state, "messages", []) or [])
                content = self._latest_assistant_text(messages)
                match = self.FINAL_ANSWER_PATTERN.search(content) if content else None
                if match:
                    final_answer = match.group(1).strip()
                    updates["final_answer"] = final_answer
            passed = bool(final_answer)
        elif self.preset == "max_rounds":
            rounds = getattr(state, "rounds", 0)
            passed = rounds >= self.max_rounds
            updates["is_complete"] = passed
        else:
            logger.warning("⚠️ [{}] Unknown preset: {}", self.name, self.preset)
            return Status.FAILURE

        updates["passed"] = passed
        if updates:
            self.state_manager.update(updates)

        return Status.SUCCESS if passed else Status.FAILURE

    def _latest_assistant_text(self, messages: List[Message]) -> str:
        for msg in reversed(messages):
            if isinstance(msg, Message) and msg.role == "assistant":
                return message_to_text(msg)
            if not isinstance(msg, Message):
                return message_to_text(msg)
        return ""


__all__ = ["ParserNode", "ConditionNode"]
