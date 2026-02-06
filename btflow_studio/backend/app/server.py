from fastapi import FastAPI, HTTPException, BackgroundTasks, UploadFile, File, Form
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import os
from dotenv import load_dotenv, dotenv_values
from pathlib import Path

env_path = Path(__file__).resolve().parents[3] / ".env"
env_vals = dotenv_values(env_path)

LLM_KEYS = [
    "API_KEY",
    "OPENAI_API_KEY",
    "OPENAI_BASE_URL",
    "OPENAI_API_BASE",
    "GOOGLE_API_KEY",
    "GEMINI_API_KEY",
    "BASE_URL",
]

for key in LLM_KEYS:
    if key in env_vals and env_vals[key] is not None:
        os.environ[key] = env_vals[key]
    else:
        os.environ.pop(key, None)

load_dotenv(env_path, override=True)

from typing import List, Dict, Optional, Any
import tempfile
import uuid
import asyncio
from pydantic import BaseModel
import btflow

from .workflow_schema import WorkflowDefinition
from .node_registry import node_registry, NodeMetadata
from .tool_registry import get_builtin_tools, ToolMetadata
from .converter import WorkflowConverter
from .websocket import manager
from fastapi import WebSocket, WebSocketDisconnect
from btflow.core.agent import BTAgent
from btflow.core.runtime import ReactiveRunner
from btflow.core.logging import logger
from btflow.core.trace import subscribe as trace_subscribe, unsubscribe as trace_unsubscribe
from btflow.core.trace import set_context as trace_set_context, reset_context as trace_reset_context
from btflow.memory import Memory
from btflow.memory.store import SQLiteStore

# 配置持久化日志用于调试
logger.add("studio_backend.log", rotation="10 MB", level="DEBUG")

class StudioVisitor(btflow.VisitorBase):
    """Captures node status after each tick and schedules a broadcast."""
    def __init__(self, workflow_id: str):
        super().__init__()
        self.workflow_id = workflow_id
        self.status_map = {}
        self.full = True # Visit all nodes
        self._last_broadcast_time = 0

    def initialise(self):
        """Reset status map at the start of each tick."""
        self.status_map = {}

    def run(self, behaviour: btflow.Behaviour):
        """Collect status for each visited behaviour."""
        node_id = getattr(behaviour, "_studio_id", behaviour.name)
        self.status_map[node_id] = behaviour.status.name

    def finalise(self):
        """Broadcast collected statuses after tick completes (with rate limiting)."""
        import time
        now = time.time()
        if now - self._last_broadcast_time < 0.1: # 限制在 10Hz
            return
            
        self._last_broadcast_time = now
        logger.debug("📡 [Visitor] Broadcasting node_update: {}", self.status_map)
        asyncio.create_task(manager.broadcast(self.workflow_id, {
            "type": "node_update",
            "data": self.status_map
        }))



app = FastAPI(title="BTflow Studio API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# In-memory storage for now (Replace with DB/File later)
workflows_db: Dict[str, WorkflowDefinition] = {}
running_agents: Dict[str, BTAgent] = {}
running_tasks: Dict[str, asyncio.Task] = {}  # Track running async tasks for cancellation

class WorkflowCreateRequest(BaseModel):
    name: str = "New Workflow"
    description: Optional[str] = None


class WorkflowRunRequest(BaseModel):
    initial_state: Optional[Dict[str, Any]] = None


class StudioSettings(BaseModel):
    language: str = "zh"
    memory_enabled: bool = True
    api_key: str = ""
    base_url: str = ""
    model: str = ""


def _parse_bool(value: Optional[str], default: bool = True) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _memory_enabled() -> bool:
    return _parse_bool(os.getenv("BTFLOW_MEMORY_ENABLED", "true"))


def _default_memory_path(workflow_id: str, memory_id: str) -> Path:
    safe_workflow = workflow_id or "workflow"
    safe_memory = memory_id or "default"
    base_dir = Path(__file__).resolve().parent / "data" / "memory"
    base_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{safe_workflow}_{safe_memory}.sqlite"
    return base_dir / filename


def _read_env_settings() -> StudioSettings:
    values = dotenv_values(env_path)
    return StudioSettings(
        language=values.get("BTFLOW_LANG", "zh"),
        memory_enabled=_parse_bool(values.get("BTFLOW_MEMORY_ENABLED", "true")),
        api_key=values.get("API_KEY", ""),
        base_url=values.get("BASE_URL", ""),
        model=values.get("MODEL", ""),
    )


def _write_env_settings(settings: StudioSettings) -> None:
    env_path.parent.mkdir(parents=True, exist_ok=True)
    lines = []
    if env_path.exists():
        lines = env_path.read_text(encoding="utf-8").splitlines()

    updates = {
        "BTFLOW_LANG": settings.language,
        "BTFLOW_MEMORY_ENABLED": "1" if settings.memory_enabled else "0",
        "API_KEY": settings.api_key or "",
        "BASE_URL": settings.base_url or "",
        "MODEL": settings.model or "",
    }

    updated = set()
    new_lines = []
    for line in lines:
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in line:
            new_lines.append(line)
            continue
        key, _, _ = line.partition("=")
        key = key.strip()
        if key in updates:
            value = updates[key]
            if value == "":
                updated.add(key)
                continue
            new_lines.append(f"{key}={value}")
            updated.add(key)
        else:
            new_lines.append(line)

    for key, value in updates.items():
        if key in updated:
            continue
        if value == "":
            continue
        new_lines.append(f"{key}={value}")

    env_path.write_text("\n".join(new_lines) + "\n", encoding="utf-8")

    for key, value in updates.items():
        if value == "":
            os.environ.pop(key, None)
        else:
            os.environ[key] = value

@app.get("/api/nodes", response_model=List[NodeMetadata])
async def get_nodes():
    """List all available node types."""
    return node_registry.get_all()

@app.get("/api/tools", response_model=List[ToolMetadata])
async def get_tools():
    """List all available tools (builtin for now)."""
    return get_builtin_tools()

@app.get("/api/settings", response_model=StudioSettings)
async def get_settings():
    return _read_env_settings()

@app.post("/api/settings", response_model=StudioSettings)
async def update_settings(payload: StudioSettings):
    _write_env_settings(payload)
    return _read_env_settings()

@app.post("/api/memory/ingest")
async def ingest_memory(
    workflow_id: str = Form(...),
    memory_id: str = Form("default"),
    chunk_size: int = Form(500),
    overlap: int = Form(50),
    files: List[UploadFile] = File(...),
):
    if not _memory_enabled():
        raise HTTPException(status_code=400, detail="Memory is disabled")
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    db_path = _default_memory_path(workflow_id, memory_id)
    store = SQLiteStore(str(db_path))
    memory = Memory(store=store)

    results = []
    for upload in files:
        suffix = Path(upload.filename).suffix
        tmp_path = None
        try:
            with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
                tmp.write(await upload.read())
                tmp_path = tmp.name
            ids = memory.ingest_file(
                tmp_path,
                chunk_size=chunk_size,
                overlap=overlap,
                metadata={"source": upload.filename},
            )
            results.append({
                "file": upload.filename,
                "chunks": len(ids),
                "ok": True,
            })
        except Exception as e:
            results.append({
                "file": upload.filename,
                "chunks": 0,
                "ok": False,
                "error": str(e),
            })
        finally:
            try:
                if tmp_path:
                    os.remove(tmp_path)
            except Exception:
                pass

    memory.save()
    return {
        "ok": True,
        "db_path": str(db_path),
        "records": len(memory),
        "results": results,
    }

@app.get("/api/workflows", response_model=List[WorkflowDefinition])
async def list_workflows():
    return list(workflows_db.values())

@app.post("/api/workflows", response_model=WorkflowDefinition)
async def create_workflow(req: WorkflowCreateRequest):
    workflow_id = str(uuid.uuid4())
    wf = WorkflowDefinition(
        id=workflow_id,
        name=req.name,
        description=req.description
    )
    workflows_db[workflow_id] = wf
    return wf

@app.get("/api/workflows/{workflow_id}", response_model=WorkflowDefinition)
async def get_workflow(workflow_id: str):
    if workflow_id not in workflows_db:
        raise HTTPException(status_code=404, detail="Workflow not found")
    return workflows_db[workflow_id]

@app.put("/api/workflows/{workflow_id}", response_model=WorkflowDefinition)
async def update_workflow(workflow_id: str, workflow: WorkflowDefinition):
    if workflow_id not in workflows_db:
        raise HTTPException(status_code=404, detail="Workflow not found")
    # Ensure ID match
    workflow.id = workflow_id
    workflows_db[workflow_id] = workflow
    return workflow

@app.delete("/api/workflows/{workflow_id}")
async def delete_workflow(workflow_id: str):
    if workflow_id in workflows_db:
        del workflows_db[workflow_id]
    return {"status": "success"}

async def _run_agent_task(workflow_id: str, agent: BTAgent):
    """Background task to run the agent with WebSocket broadcasting."""
    logger.info("🚀 [API] Starting workflow {}", workflow_id)
    
    # Define a callback to broadcast state
    async def on_tick_update():
        state_data = agent.state_manager.get().model_dump(mode='json')
        # We can also get the tree status if available directly
        # But agent logic runs inside runner.run().
        # Ideally, we should inject a callback into Runner.
        # BTflow's Runner relies on state changes.
        
        await manager.broadcast(workflow_id, {
            "type": "state_update",
            "data": state_data
        })
    
    # Currently Runner doesn't support async callbacks easily without modification.
    # But wait, StateManager has .subscribe().
    # Note: StateManager.subscribe callbacks are synchronous for now (see state.py).
    # We might need a bridge.
    
    # Hook up Visitor
    visitor = StudioVisitor(workflow_id)
    agent.runner.tree.visitors.append(visitor)

    # Trace subscription
    def on_trace(event: str, data: dict):
        if data.get("workflow_id") != workflow_id:
            return
        asyncio.create_task(manager.broadcast(workflow_id, {
            "type": "trace",
            "event": event,
            "data": data
        }))

    trace_token = trace_set_context(workflow_id=workflow_id)
    trace_subscribe(on_trace)

    # Set up log broadcast callback
    def broadcast_log(msg_type: str, message: str):
        asyncio.create_task(manager.broadcast(workflow_id, {
            "type": msg_type,
            "message": message
        }))
    
    # 注入全局 Log 节点广播
    from btflow.nodes import Log
    Log._broadcast_callback = broadcast_log

    # 注入 loguru sink 以捕获内部日志
    def studio_log_sink(message):
        record = message.record
        msg_type = "log" if record["level"].name != "ERROR" else "error"
        asyncio.create_task(manager.broadcast(workflow_id, {
            "type": msg_type,
            "message": f"[{record['name']}] {record['message']}"
        }))
    
    sink_id = logger.add(studio_log_sink, level="INFO", format="{message}")

    try:
        await manager.broadcast(workflow_id, {"type": "status", "status": "running"})
        await agent.run()
        try:
            final_state = agent.state_manager.get().model_dump(mode='json')
            await manager.broadcast(workflow_id, {"type": "state_update", "data": final_state})
        except Exception as state_error:
            logger.warning("⚠️ [API] Workflow {} state snapshot failed: {}", workflow_id, state_error)
        await manager.broadcast(workflow_id, {"type": "status", "status": "completed"})
        
    except asyncio.CancelledError:
        logger.info("⏹️ [API] Workflow {} cancelled", workflow_id)
        try:
            final_state = agent.state_manager.get().model_dump(mode='json')
            asyncio.create_task(manager.broadcast(workflow_id, {"type": "state_update", "data": final_state}))
        except Exception:
            pass
        # 使用 create_task 而不是 await，确保不会阻塞取消流程
        asyncio.create_task(manager.broadcast(workflow_id, {"type": "status", "status": "stopped"}))
        raise  # Re-raise to properly cancel the task
    except Exception as e:
        logger.error("🔥 [API] Workflow {} failed: {}", workflow_id, e)
        import traceback
        traceback.print_exc()
        try:
            final_state = agent.state_manager.get().model_dump(mode='json')
            await manager.broadcast(workflow_id, {"type": "state_update", "data": final_state})
        except Exception:
            pass
        await manager.broadcast(workflow_id, {"type": "error", "message": str(e)})
    finally:
        logger.info("💤 [API] Workflow {} finished", workflow_id)
        logger.remove(sink_id) # 重要：移除沉降器防止内存泄漏
        trace_unsubscribe(on_trace)
        trace_reset_context(trace_token)
        if workflow_id in running_agents:
            del running_agents[workflow_id]
        if workflow_id in running_tasks:
            del running_tasks[workflow_id]

@app.websocket("/ws/{workflow_id}")
async def websocket_endpoint(websocket: WebSocket, workflow_id: str):
    await manager.connect(workflow_id, websocket)
    try:
        while True:
            # Keep alive, maybe receive commands (e.g. step, pause)
            data = await websocket.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(workflow_id, websocket)


@app.post("/api/workflows/{workflow_id}/run")
async def run_workflow(workflow_id: str, background_tasks: BackgroundTasks, req: Optional[WorkflowRunRequest] = None):
    if workflow_id not in workflows_db:
        raise HTTPException(status_code=404, detail="Workflow not found")
    
    if workflow_id in running_agents:
        raise HTTPException(status_code=400, detail="Workflow is already running")

    wf_def = workflows_db[workflow_id]
    
    try:
        # 1. Compile to Tree
        converter = WorkflowConverter(wf_def)
        root = converter.compile()
        state_manager = converter.state_manager
        if req and req.initial_state:
            state_manager.update(req.initial_state)
        
        # 2. Setup Agent
        # BTAgent implicitly creates a ReactiveRunner which sets up the tree (injects state_manager, calls setup())
        agent = BTAgent(root, state_manager)
        
        # Debug: 打印树结构
        import py_trees
        logger.info("🌳 [Server] Tree Structure:\n{}", py_trees.display.ascii_tree(root))
        
        # 3. Store reference
        running_agents[workflow_id] = agent
        
        # 4.  Start in background and store task for cancellation
        task = asyncio.create_task(_run_agent_task(workflow_id, agent))
        running_tasks[workflow_id] = task
        background_tasks.add_task(lambda: None)  # Dummy to keep FastAPI happy
        
        return {"status": "started", "workflow_id": workflow_id}
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/workflows/{workflow_id}/stop")
async def stop_workflow(workflow_id: str):
    if workflow_id in running_tasks:
        task = running_tasks[workflow_id]
        task.cancel()  # Cancel the async task
        # Don't broadcast here - let the CancelledError handler do it
        try:
            await task  # Wait for cancellation to complete
        except asyncio.CancelledError:
            pass  # Expected
        return {"status": "stopped"}
    return {"status": "not_running"}

# === Chat Assistant API ===
from .llm import get_workflow_llm

class ChatRequest(BaseModel):
    message: str
    conversation_history: Optional[List[Dict[str, str]]] = None
    current_workflow: Optional[Dict[str, Any]] = None
    available_nodes: Optional[List[Dict[str, Any]]] = None
    available_tools: Optional[List[Dict[str, Any]]] = None

@app.post("/api/chat/generate-workflow")
async def generate_workflow_from_chat(request: ChatRequest):
    """
    Generate or modify workflow using LLM based on user message.
    Supports multi-turn conversations.
    """
    try:
        llm = get_workflow_llm()
        result = await llm.generate_workflow(
            user_message=request.message,
            conversation_history=request.conversation_history,
            current_workflow=request.current_workflow,
            available_nodes=request.available_nodes,
            available_tools=request.available_tools,
        )
        
        return result
        
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

# === Static Files & SPA Support ===
static_dir = os.path.join(os.path.dirname(__file__), "static")

# Only mount if directory exists (PROD mode)
if os.path.exists(static_dir):
    # Mount assets (JS/CSS)
    assets_dir = os.path.join(static_dir, "assets")
    if os.path.exists(assets_dir):
        app.mount("/assets", StaticFiles(directory=assets_dir), name="assets")

    # Catch-all route for SPA (React Router)
    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        if full_path.startswith("api/") or full_path.startswith("ws/"):
            raise HTTPException(status_code=404, detail="Not Found")

        file_path = os.path.join(static_dir, full_path)
        if os.path.isfile(file_path):
            return FileResponse(file_path)

        return FileResponse(os.path.join(static_dir, "index.html"))
