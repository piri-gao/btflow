import uvicorn
from .server import app
from btflow.logging import logger

if __name__ == "__main__":
    logger.info("🚀 Starting BTflow Studio Backend...")
    # Assuming run from btflow-studio/
    uvicorn.run("backend.app.server:app", host="0.0.0.0", port=8000, reload=True)
