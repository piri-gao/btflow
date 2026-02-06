"""
LLM integration for workflow generation using BTFlow LLMProvider.
Supports multi-turn conversations and workflow modifications.
"""
import os
import json
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv
from btflow.core.logging import logger
from btflow.llm import LLMProvider

load_dotenv()

# System prompt for workflow generation
SYSTEM_PROMPT = """You are a workflow generation assistant for BTflow Studio, a behavior tree orchestration tool.

Your role is to help users create and modify workflows through natural conversation.

**Available Node Types:**

1. **Sequence** (Control Flow)
   - Executes children sequentially from left to right
   - Succeeds only if all children succeed
   - Config: `memory` (bool, default: true) - whether to remember progress

2. **Selector** (Control Flow)
   - Tries children until one succeeds
   - Config: `memory` (bool, default: true)

3. **Parallel** (Control Flow)
   - Executes all children simultaneously
   - Config: `policy` (string) - "SuccessOnAll" or "SuccessOnOne"

4. **Wait** (Utilities)
   - Waits for specified duration (non-blocking)
   - Config: `duration` (float) - seconds to wait

5. **Log** (Utilities)
   - Prints a message to execution logs
   - Config: `message` (string) - the message to print

**Workflow JSON Format:**
```json
{
  "nodes": [
    {
      "id": "unique_id",
      "type": "NodeType",
      "label": "Display Name",
      "position": {"x": 100, "y": 50},
      "config": {...}
    }
  ],
  "edges": [
    {
      "id": "edge_id",
      "source": "parent_node_id",
      "target": "child_node_id"
    }
  ],
  "state": { // optional state definition
    "fields": [{"name": "task", "type": "str", "default": "hello"}]
  }
}
```

**Advanced Patterns Guidelines:**

1. **ReAct Pattern (Agentic Reasoning)**:
   - Root: `LoopUntilSuccess` (max_iterations: 10)
   - Child of Root: `Sequence` (memory: true)
   - Children of Sequence (in order): 
     * `AgentLLMNode`
     * `ToolExecutor` (configure tools via `config.tools`)
     * `ConditionNode` (preset: has_final_answer)

2. **Reflexion Pattern**:
   - Root: `LoopUntilSuccess`
   - Child of Root: `Sequence` (memory: true)
   - Children of Sequence:
     * `AgentLLMNode`
     * `ParserNode` (preset: score)
     * `ConditionNode` (preset: score_gte)

3. **Tool Usage**:
   - For agent-style tool use: configure `ToolExecutor.config.tools` with tool ids from the available tools list.
   - For deterministic tool execution: add a `ToolNode` and set `config.tool_id` to the tool id.
   - Do NOT invent tool node types like `CalculatorTool`; always use ToolExecutor or ToolNode.

**Layout Guidelines:**
- Root node at x=400, y=50
- Children spread horizontally (x: 200, 400, 600...)
- Each level increases y by 150
- Left-to-right = execution order for Sequence

**Instructions:**
1. When user describes a new workflow, generate complete JSON
3. When user requests modifications, update the existing workflow
4. Use descriptive labels
5. Set reasonable default configs
6. Always include both explanation and valid JSON in your response.
**Example:**
User: "Create a workflow that waits 3 seconds then prints Hello"
Response:
I've created a simple workflow with a Sequence containing Wait and Log nodes.

```json
{
  "nodes": [
    {
      "id": "seq_1",
      "type": "Sequence",
      "label": "Main Sequence",
      "position": {"x": 400, "y": 50},
      "config": {"memory": true}
    },
    {
      "id": "wait_1",
      "type": "Wait",
      "label": "Wait 3s",
      "position": {"x": 300, "y": 200},
      "config": {"duration": 3}
    },
    {
      "id": "log_1",
      "type": "Log",
      "label": "Print Hello",
      "position": {"x": 500, "y": 200},
      "config": {"message": "Hello"}
    }
  ],
  "edges": [
    {"id": "e1", "source": "seq_1", "target": "wait_1"},
    {"id": "e2", "source": "seq_1", "target": "log_1"}
  ]
}
```

Always include both explanation and valid JSON in your response."""


class WorkflowLLM:
    """Handles LLM interactions for workflow generation."""

    def __init__(self, model_name: Optional[str] = None):
        self.model_name = model_name or os.getenv("MODEL", "gemini-2.5-flash")
        
    async def generate_workflow(
        self, 
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        current_workflow: Optional[Dict[str, Any]] = None,
        available_nodes: Optional[List[Dict[str, Any]]] = None,
        available_tools: Optional[List[Dict[str, Any]]] = None,
    ) -> Dict[str, Any]:
        """
        Generate or modify a workflow based on user message.
        
        Args:
            user_message: User's request
            conversation_history: Previous messages
            current_workflow: Existing workflow JSON (for modifications)
            available_nodes: List of available node types from /api/nodes
            available_tools: List of available tools from /api/tools
            
        Returns:
            {
                "reply": "Assistant's explanation",
                "workflow": {...} or None
            }
        """
        # Build dynamic system prompt with actual available nodes
        system_prompt = SYSTEM_PROMPT
        if available_nodes:
            nodes_doc = self._build_nodes_documentation(available_nodes)
            system_prompt = system_prompt.replace(
                "**Available Node Types:**\n\n1. **Sequence**",
                f"**Available Node Types:**\n\n{nodes_doc}\n\n**Note:** Use ONLY these node types. Do not invent new ones.\n\n1. **Sequence (for reference)**"
            )

        if available_tools:
            tools_doc = self._build_tools_documentation(available_tools)
            system_prompt = system_prompt + f"\n\n**Available Tools:**\n\n{tools_doc}\n\n**Note:** Use tool ids from this list when setting ToolExecutor.config.tools or ToolNode.config.tool_id."
        
        prompt = self._build_prompt(
            system_prompt=system_prompt,
            user_message=user_message,
            conversation_history=conversation_history,
            current_workflow=current_workflow,
        )

        try:
            provider = LLMProvider.default(
                preference=["openai", "gemini", "anthropic"],
                base_url=os.getenv("BASE_URL"),
            )
            model = os.getenv("MODEL", self.model_name)
            response = await provider.generate_text(
                prompt=prompt,
                model=model,
                temperature=0.3,
                top_p=0.95,
                top_k=40,
                timeout=60.0,
            )

            reply_text = getattr(response, "content", None) or str(response)
            
            # Extract workflow JSON
            workflow = self._extract_workflow_json(reply_text)
            
            return {
                "reply": reply_text,
                "workflow": workflow
            }
            
        except Exception as e:
            return {
                "reply": f"❌ Error generating workflow: {str(e)}",
                "workflow": None
            }
    
    def _build_nodes_documentation(self, available_nodes: List[Dict[str, Any]]) -> str:
        """Build documentation string from available nodes."""
        docs = []
        for idx, node in enumerate(available_nodes, 1):
            node_doc = f"{idx}. **{node['id']}** ({node.get('category', 'Unknown')})"
            if node.get('description'):
                node_doc += f"\n   - {node['description']}"
            
            # Add config schema if available
            if node.get('config_schema'):
                schema = node['config_schema']
                if isinstance(schema, dict):
                    node_doc += "\n   - Config:"
                    for key, prop in schema.items():
                        if isinstance(prop, dict):
                            prop_type = prop.get('type', 'any')
                            default = prop.get('default', None)
                            options = prop.get('options')
                            line = f"\n     * `{key}` ({prop_type})"
                            if default not in (None, ""):
                                line += f", default={default}"
                            if options:
                                line += f", options={options}"
                            node_doc += line
                        else:
                            node_doc += f"\n     * `{key}`"
            
            docs.append(node_doc)
        
        return "\n\n".join(docs)

    def _build_tools_documentation(self, available_tools: List[Dict[str, Any]]) -> str:
        docs = []
        for idx, tool in enumerate(available_tools, 1):
            if tool.get('available') is False:
                continue
            label = tool.get('label') or tool.get('id') or tool.get('name')
            tool_id = tool.get('id') or tool.get('name')
            desc = tool.get('description', '')
            docs.append(f"{idx}. **{label}** (id: `{tool_id}`)\n   - {desc}")
        return "\n\n".join(docs)

    def _build_prompt(
        self,
        system_prompt: str,
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        current_workflow: Optional[Dict[str, Any]] = None,
    ) -> str:
        parts = [system_prompt.strip()]

        if conversation_history:
            parts.append("Conversation:")
            for msg in conversation_history:
                role = msg.get("role", "user")
                content = msg.get("content", "")
                if role == "model":
                    role = "assistant"
                parts.append(f"{role.title()}: {content}")

        if current_workflow:
            parts.append("Current Workflow (JSON):")
            parts.append(json.dumps(current_workflow, indent=2))

        parts.append(f"User: {user_message}")
        return "\n\n".join(parts)
    
    def _extract_workflow_json(self, text: str) -> Optional[Dict[str, Any]]:
        """Extract workflow JSON from LLM response."""
        # Try to find JSON block
        import re
        
        # Look for ```json ... ``` blocks
        json_match = re.search(r'```json\s*(.*?)\s*```', text, re.DOTALL)
        if json_match:
            try:
                return json.loads(json_match.group(1))
            except json.JSONDecodeError:
                pass
        
        # Try to find any {...} block that looks like workflow
        json_match = re.search(r'\{[\s\S]*"nodes"[\s\S]*"edges"[\s\S]*\}', text)
        if json_match:
            try:
                return json.loads(json_match.group(0))
            except json.JSONDecodeError:
                pass
        
        return None


# Singleton instance
def get_workflow_llm() -> WorkflowLLM:
    """Create a fresh WorkflowLLM (config is read from env each call)."""
    return WorkflowLLM()
