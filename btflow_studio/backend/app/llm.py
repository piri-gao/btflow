"""
LLM integration for workflow generation using Gemini API.
Supports multi-turn conversations and workflow modifications.
"""
import os
import json
from typing import List, Dict, Any, Optional
import google.generativeai as genai
from dotenv import load_dotenv
from btflow.core.logging import logger

# Load environment variables
load_dotenv()

# Configure Gemini
genai.configure(api_key=os.getenv("GEMINI_API_KEY"))

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

4. **Wait** (Action)
   - Waits for specified duration (non-blocking)
   - Config: `duration` (float) - seconds to wait

5. **Log** (Debug)
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
  ]
}
```

**Layout Guidelines:**
- Root node at x=400, y=50
- Children spread horizontally (x: 200, 400, 600...)
- Each level increases y by 150
- Left-to-right = execution order for Sequence

**Instructions:**
1. When user describes a new workflow, generate complete JSON
2. When user requests modifications ("add", "change", "remove"), update the existing workflow
3. Always respond with:
   - Brief explanation of what you created/changed
   - Complete workflow JSON (even for modifications)
4. Use descriptive labels (not generic names)
5. Set reasonable default configs

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
    
    def __init__(self, model_name: str = "models/gemini-2.5-flash"):
        try:
            self.model = genai.GenerativeModel(
                model_name=model_name,
                generation_config={
                    "temperature": 0.3,
                    "top_p": 0.95,
                    "top_k": 40,
                }
            )
        except Exception as e:
            logger.warning("⚠️ Failed to initialize model {}: {}", model_name, e)
            logger.info("Trying fallback model...")
            # Fallback to a known working model
            self.model = genai.GenerativeModel(
                model_name="gemini-1.5-flash",
                generation_config={
                    "temperature": 0.3,
                    "top_p": 0.95,
                    "top_k": 40,
                }
            )
        
    def generate_workflow(
        self, 
        user_message: str,
        conversation_history: Optional[List[Dict[str, str]]] = None,
        current_workflow: Optional[Dict[str, Any]] = None,
        available_nodes: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        """
        Generate or modify a workflow based on user message.
        
        Args:
            user_message: User's request
            conversation_history: Previous messages
            current_workflow: Existing workflow JSON (for modifications)
            available_nodes: List of available node types from /api/nodes
            
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
        
        # Build conversation context
        messages = []
        
        # Add system prompt
        messages.append({"role": "user", "parts": [system_prompt]})
        messages.append({"role": "model", "parts": ["Understood. I'll help you create workflows using only the available node types."]})
        
        # Add conversation history
        if conversation_history:
            for msg in conversation_history:
                messages.append({
                    "role": msg["role"],
                    "parts": [msg["content"]]
                })
        
        # Add current workflow context if modifying
        if current_workflow:
            context = f"\n\n**Current Workflow:**\n```json\n{json.dumps(current_workflow, indent=2)}\n```\n\n**User Request:** {user_message}"
            messages.append({"role": "user", "parts": [context]})
        else:
            messages.append({"role": "user", "parts": [user_message]})
        
        # Generate response
        try:
            chat = self.model.start_chat(history=messages[:-1])
            response = chat.send_message(messages[-1]["parts"][0])
            reply_text = response.text
            
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
                if schema.get('properties'):
                    node_doc += "\n   - Config:"
                    for key, prop in schema['properties'].items():
                        prop_type = prop.get('type', 'any')
                        node_doc += f"\n     * `{key}` ({prop_type})"
                        if prop.get('description'):
                            node_doc += f" - {prop['description']}"
            
            docs.append(node_doc)
        
        return "\n\n".join(docs)
    
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
_workflow_llm = None

def get_workflow_llm() -> WorkflowLLM:
    """Get or create the WorkflowLLM singleton."""
    global _workflow_llm
    if _workflow_llm is None:
        _workflow_llm = WorkflowLLM()
    return _workflow_llm
