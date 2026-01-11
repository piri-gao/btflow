from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from fastapi.middleware.cors import CORSMiddleware
import os
from typing import List, Dict, Optional, Any
import uuid
import asyncio
from pydantic import BaseModel
import btflow

from .workflow_schema import WorkflowDefinition
from .node_registry import node_registry, NodeMetadata
from .converter import WorkflowConverter
from .websocket import manager
from fastapi import WebSocket, WebSocketDisconnect
from btflow.core.agent import BTAgent
from btflow.core.runtime import ReactiveRunner
from btflow.core.logging import logger

class StudioVisitor(btflow.VisitorBase):
    """Captures node status after each tick and schedules a broadcast."""
    def __init__(self, workflow_id: str):
        super().__init__()
        self.workflow_id = workflow_id
        self.status_map = {}
        self.full = True # Visit all nodes

    def initialise(self):
        """Reset status map at the start of each tick."""
        self.status_map = {}

    def run(self, behaviour: btflow.Behaviour):
        """Collect status for each visited behaviour."""
        self.status_map[behaviour.name] = behaviour.status.name

    def finalise(self):
        """Broadcast collected statuses after tick completes."""
        logger.debug("📡 [Visitor] Broadcasting node_update: {}", self.status_map)
        # Broadcast via asyncio (fire and forget)
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

@app.get("/api/nodes", response_model=List[NodeMetadata])
async def get_nodes():
    """List all available node types."""
    return node_registry.get_all()

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

    # Set up log broadcast callback
    from btflow.nodes.common.debug import Log
    def broadcast_log(msg_type: str, message: str):
        asyncio.create_task(manager.broadcast(workflow_id, {
            "type": msg_type,
            "message": message
        }))
    Log._broadcast_callback = broadcast_log

    try:
        await manager.broadcast(workflow_id, {"type": "status", "status": "running"})
        await agent.run()
        await manager.broadcast(workflow_id, {"type": "status", "status": "completed"})
        
    except asyncio.CancelledError:
        logger.info("⏹️ [API] Workflow {} cancelled", workflow_id)
        await manager.broadcast(workflow_id, {"type": "status", "status": "stopped"})
        raise  # Re-raise to properly cancel the task
    except Exception as e:
        logger.error("🔥 [API] Workflow {} failed: {}", workflow_id, e)
        import traceback
        traceback.print_exc()
        await manager.broadcast(workflow_id, {"type": "error", "message": str(e)})
    finally:
        logger.info("💤 [API] Workflow {} finished", workflow_id)
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
async def run_workflow(workflow_id: str, background_tasks: BackgroundTasks):
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
        
        # 2. Setup Runner & Agent
        runner = ReactiveRunner(root, state_manager)
        agent = BTAgent(runner)
        
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

@app.post("/api/chat/generate-workflow")
async def generate_workflow_from_chat(request: ChatRequest):
    """
    Generate or modify workflow using LLM based on user message.
    Supports multi-turn conversations.
    """
    try:
        llm = get_workflow_llm()
        result = llm.generate_workflow(
            user_message=request.message,
            conversation_history=request.conversation_history,
            current_workflow=request.current_workflow,
            available_nodes=request.available_nodes
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
