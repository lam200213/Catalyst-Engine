# backend-services/scheduler-service/app.py
# Celery init, Mongo connection class, and orchestration logic were moved to celery_app.py, db.py, and tasks.py.

import os
import logging

from flask import Flask, jsonify, request

# Import the Celery task (async entrypoint) instead of running the pipeline synchronously.
try:
    from tasks import run_screening_pipeline_task
except ImportError:
    # Fallback for environments where the module may be named differently.
    from task import run_screening_pipeline_task  # type: ignore

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)

logger = logging.getLogger(__name__)

app = Flask(__name__)

PORT = int(os.getenv("PORT", 3004))


@app.route("/health", methods=["GET"])
def health():
    return jsonify({"ok": True}), 200


@app.route("/jobs/screening/start", methods=["POST"])
def start_screening_job_endpoint():
    # Gone: result, status_code = run_screening_pipeline()
    # Gone: return jsonify(result), status_code

    # Enqueue the job via Celery and return immediately.
    # Request body is optional per spec; accepted here for forward compatibility.
    _ = request.get_json(silent=True) or {}

    try:
        async_result = run_screening_pipeline_task.delay()
        job_id = async_result.id
        return (
            jsonify(
                {
                    "message": "Batch screening job successfully queued.",
                    "job_id": job_id,
                }
            ),
            202,
        )
    except Exception as e:
        logger.exception("Failed to enqueue screening pipeline Celery task.")
        return (
            jsonify(
                {
                    "error": "Failed to queue screening job",
                    "details": str(e),
                }
            ),
            503,
        )


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT, threaded=True)
