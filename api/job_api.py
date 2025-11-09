import logging
import traceback

from uuid import uuid4
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import APIRouter, HTTPException, Depends, Request, status, Query
from fastapi.responses import JSONResponse

from app.core import get_db_session
from app.services import JobService, JobNotFoundError
from app.schemas.pydantic.job import JobUploadRequest

job_router = APIRouter()
logger = logging.getLogger(__name__)


@job_router.post(
    "/upload",
    summary="stores the job posting in the database by parsing the JD into a structured format JSON",
)
async def upload_job(
    payload: JobUploadRequest,
    request: Request,
    db: AsyncSession = Depends(get_db_session),
):
    """
    Accepts a job description as a MarkDown text and stores it in the database.
    """
    request_id = getattr(request.state, "request_id", str(uuid4()))

    # --- START OF VERIFICATION LOGGING ---

    # 1. Log the payload as received by FastAPI (as a Pydantic object)
    logger.info("--- DATA VERIFICATION STEP 1: PAYLOAD AS Pydantic Model ---")
    logger.info(f"Received payload object: {payload}")
    logger.info(f"Type of received payload: {type(payload)}")
    logger.info("---------------------------------------------------------")

    # 2. Convert the Pydantic model to a standard Python dictionary
    job_data_dict = payload.model_dump()

    # 3. Log the resulting dictionary to see its final form before passing it on
    logger.info("--- DATA VERIFICATION STEP 2: PAYLOAD AS Python Dictionary ---")
    logger.info(f"Payload after model_dump(): {job_data_dict}")
    logger.info(f"Type of payload after model_dump(): {type(job_data_dict)}")
    logger.info("------------------------------------------------------------")

    # --- END OF VERIFICATION LOGGING ---

    allowed_content_types = [
        "application/json",
    ]

    content_type = request.headers.get("content-type")
    if not content_type:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Content-Type header is missing",
        )

    if content_type not in allowed_content_types:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid Content-Type. Only {', '.join(allowed_content_types)} is/are allowed.",
        )

    try:
        job_service = JobService(db)
        job_ids = await job_service.create_and_store_job(payload.model_dump())

    except AssertionError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        )

    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"{str(e)}",
        )

    return {
        "message": "data successfully processed",
        "job_id": job_ids,
        "request": {
            "request_id": request_id,
            "payload": payload,
        },
    }


@job_router.get(
    "",
    summary="Get job data from both job and processed_job models",
)
async def get_job(
    request: Request,
    job_id: str = Query(..., description="Job ID to fetch data for"),
    db: AsyncSession = Depends(get_db_session),
):
    """
    Retrieves job data from both job_model and processed_job model by job_id.

    Args:
        job_id: The ID of the job to retrieve

    Returns:
        Combined data from both job and processed_job models

    Raises:
        HTTPException: If the job is not found or if there's an error fetching data.
    """
    request_id = getattr(request.state, "request_id", str(uuid4()))
    headers = {"X-Request-ID": request_id}

    try:
        if not job_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="job_id is required",
            )

        job_service = JobService(db)
        job_data = await job_service.get_job_with_processed_data(
            job_id=job_id
        )
        
        if not job_data:
            raise JobNotFoundError(
                message=f"Job with id {job_id} not found"
            )

        return JSONResponse(
            content={
                "request_id": request_id,
                "data": job_data,
            },
            headers=headers,
        )
    
    except JobNotFoundError as e:
        logger.error(str(e))
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(e),
        )
    except Exception as e:
        
        # logger.error(f"Error fetching job: {str(e)} - traceback: {traceback.format_exc()}")
        # raise HTTPException(
        #     status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        #     detail="Error fetching job data",
        # )

        # This will log the full, detailed traceback to the console
        logger.error("--- AN UNHANDLED EXCEPTION REACHED THE API ENDPOINT ---")
        logger.error(f"Exception Type: {type(e)}")
        logger.error(f"Traceback:\n{traceback.format_exc()}")

        # Raise the HTTP exception so frontend gets notified
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="An internal error occurs. Check server logs for details.",
        )
