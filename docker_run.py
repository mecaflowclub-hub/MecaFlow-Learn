import sys
import logging
import uvicorn

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger("docker_runner")

if __name__ == "__main__":
    port = 8000  # Fixed inside container
    logger.info(f"Starting server on port {port}")

    try:
        uvicorn.run(
            "main:app",
            host="0.0.0.0",
            port=port,
            workers=1,
            timeout_keep_alive=75,
            log_level="info"
        )
    except Exception as e:
        logger.error(f"Failed to start server: {e}")
        sys.exit(1)
