import uvicorn
from .server import app
from btflow.core.logging import logger

def start():
    """Entry point for CLI (btflow-studio)"""
    logger.info("🚀 Starting BTflow Studio...")
    # Open browser automatically? Maybe later.
    import webbrowser
    webbrowser.open("http://localhost:8000")
    
    # Run server
    uvicorn.run("btflow_studio.backend.app.server:app", host="0.0.0.0", port=8000, reload=False) # Reload false for prod

if __name__ == "__main__":
    # Dev mode
    uvicorn.run("backend.app.server:app", host="0.0.0.0", port=8000, reload=True)
