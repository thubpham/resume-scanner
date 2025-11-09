import uuid
import json
import logging

from typing import List, Dict, Any, Optional
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.resume_db import Resume, ProcessedResume
from database.job_db import Job, ProcessedJob
from agent_manager import AgentManager
from prompt.prompt_manager import PromptFactory
from schema.json.json_manager import JSONSchemaFactory
from schema.pydantic.structured_resume_pydantic import StructuredResumeModel
from schema.pydantic.structured_job_pydantic import StructuredJobModel
from exception import ResumeNotFoundError, ResumeValidationError, JobNotFoundError

logger = logging.getLogger(__name__)


class JobService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.json_agent_manager = AgentManager()

    async def create_and_store_job(self, job_data: dict) -> List[str]:
        """
        Stores job data in the database and returns a list of job IDs.
        """
        resume_id = str(job_data.get("resume_id"))

        if not await self._is_resume_available(resume_id):
            raise AssertionError(
                f"resume corresponding to resume_id: {resume_id} not found"
            )

        job_ids = []
        for job_description in job_data.get("job_descriptions", []):
            job_id = str(uuid.uuid4())
            job = Job(
                job_id=job_id,
                resume_id=str(resume_id),
                content=job_description,
            )
            self.db.add(job)

            await self._extract_and_store_structured_job(
                job_id=job_id, job_description_text=job_description
            )
            logger.info(f"Job ID: {job_id}")
            job_ids.append(job_id)

        await self.db.commit()
        return job_ids

    async def _is_resume_available(self, resume_id: str) -> bool:
        """
        Checks if a resume exists in the database.
        """
        query = select(Resume).where(Resume.resume_id == resume_id)
        result = await self.db.scalar(query)
        return result is not None
 
    async def _extract_and_store_structured_job(
        self, job_id, job_description_text: str
    ):
        """
        extract and store structured job data in the database
        """
        structured_job = await self._extract_structured_json(job_description_text)
        if not structured_job:
            logger.info("Structured job extraction failed.")
            return None

        processed_job = ProcessedJob(
            job_id=job_id,
            job_title=structured_job.get("job_title"),
            company_profile=json.dumps(structured_job.get("company_profile"))
            if structured_job.get("company_profile")
            else None,
            location=json.dumps(structured_job.get("location"))
            if structured_job.get("location")
            else None,
            date_posted=structured_job.get("date_posted"),
            employment_type=structured_job.get("employment_type"),
            job_summary=structured_job.get("job_summary"),
            key_responsibilities=json.dumps(
                {"key_responsibilities": structured_job.get("key_responsibilities", [])}
            )
            if structured_job.get("key_responsibilities")
            else None,
            qualifications=json.dumps(structured_job.get("qualifications", []))
            if structured_job.get("qualifications")
            else None,
            compensation_and_benfits=json.dumps(
                structured_job.get("compensation_and_benfits", [])
            )
            if structured_job.get("compensation_and_benfits")
            else None,
            application_info=json.dumps(structured_job.get("application_info", []))
            if structured_job.get("application_info")
            else None,
            extracted_keywords=json.dumps(
                {"extracted_keywords": structured_job.get("extracted_keywords", [])}
            )
            if structured_job.get("extracted_keywords")
            else None,
        )

        self.db.add(processed_job)
        await self.db.flush()
        await self.db.commit()

        return job_id

    # DEBUG: Most likely bug starts here
    async def _extract_structured_json(self, job_description_text: str) -> Dict[str, Any] | None:
        """
        Uses the AgentManager+JSONWrapper to ask the LLM to
        return the data in exact JSON schema we need.
        """
        prompt_template = prompt_factory.get("structured_job")
        prompt = prompt_template.format(
            json.dumps(json_schema_factory.get("structured_job"), indent=2),
            job_description_text,
        )
        logger.info(f"Structured Job Prompt: {prompt}")
        raw_output = await self.json_agent_manager.run(prompt=prompt)

        # Debug: Log the raw output received from the agent
        logger.info(f"Raw output from JSON agent: {raw_output}")

        # Normalize location field to allowed enum values
        allowed_locations = {
            "Fully Remote": "Fully Remote",
            "Remote": "Remote",
            "Hybrid": "Hybrid",
            "On-site": "On-site",
            "Not Specified": "Not Specified",
            "Multiple Locations": "Multiple Locations"
        }
        if isinstance(raw_output, dict) and "location" in raw_output:

            # Retrieve "location" from raw_output
            loc = raw_output["location"]
            
             # --- START: ENHANCED NORMALIZATION LOGIC ---
            try: 
                # Happy path: loc is a string
                if loc not in allowed_locations:
                    # Set the dictionary to a string value 
                    raw_output["location"] = "Not Specified"
            except TypeError:
                logger.warning(
                    f"Caught a TypeError for the 'location' field."
                    f"The LLM likely returned a dictionary instead of a string."
                    f"Value received: {loc}. Defaulting to 'Not Specified'."
                    )
            # --- END: ENHANCED NORMALIZATION LOGIC --- 

            # --- START: VERIFICATION LOGGING ---
            # Add this blog to verify the loc instance before normalization
            logger.info("--- VERIFYING 'loc' VARIABLE ---") 
            logger.info(f"Value of loc: {loc}")
            logger.info(f"Type of loc: {type(loc)}")
            logger.info("--------------------------------")
            # --- END: VERIFICATION LOGGING ---
            
            if isinstance(loc, str) and "|" in loc:
                loc_options = [l.strip() for l in loc.split("|")]
                for option in loc_options:
                    if option in allowed_locations:
                        raw_output["location"] = allowed_locations[option]
                        break
                    else:
                        raw_output["location"] = "Not Specified"
            elif loc not in allowed_locations:
                raw_output["location"] = "Not Specified"

        try:
            structured_job: StructuredJobModel = StructuredJobModel.model_validate(
                raw_output
            )
        except ValidationError as e:
            # logger.info(f"Validation error: {e}")
            # error_details = []
            # for error in e.errors():
            #     field = " -> ".join(str(loc) for loc in error["loc"])
            #     error_details.append(f"{field}: {error['msg']}")
            
            # logger.info(f"Validation error details: {'; '.join(error_details)}")
            # return None

            logger.error(f"--- Pydantic Validation Failure ---")
            logger.error(f"LLM Output that failed validation: {raw_output}")
            logger.error(f"Pydantic Validation Error: {e}")
            raise e

        return structured_job.model_dump(mode="json")

    async def get_job_with_processed_data(self, job_id: str) -> Optional[Dict]:
        """
        Fetches both job and processed job data from the database and combines them.

        Args:
            job_id: The ID of the job to retrieve

        Returns:
            Combined data from both job and processed_job models

        Raises:
            JobNotFoundError: If the job is not found
        """
        job_query = select(Job).where(Job.job_id == job_id)
        job_result = await self.db.execute(job_query)
        job = job_result.scalars().first()

        if not job:
            raise JobNotFoundError(job_id=job_id)

        processed_query = select(ProcessedJob).where(ProcessedJob.job_id == job_id)
        processed_result = await self.db.execute(processed_query)
        processed_job = processed_result.scalars().first()

        combined_data = {
            "job_id": job.job_id,
            "raw_job": {
                "id": job.id,
                "resume_id": job.resume_id,
                "content": job.content,
                "created_at": job.created_at.isoformat() if job.created_at else None,
            },
            "processed_job": None
        }

        if processed_job:
            combined_data["processed_job"] = {
                "job_title": processed_job.job_title,
                "company_profile": json.loads(processed_job.company_profile) if processed_job.company_profile else None,
                "location": json.loads(processed_job.location) if processed_job.location else None,
                "date_posted": processed_job.date_posted,
                "employment_type": processed_job.employment_type,
                "job_summary": processed_job.job_summary,
                "key_responsibilities": json.loads(processed_job.key_responsibilities).get("key_responsibilities", []) if processed_job.key_responsibilities else None,
                "qualifications": json.loads(processed_job.qualifications).get("qualifications", []) if processed_job.qualifications else None,
                "compensation_and_benfits": json.loads(processed_job.compensation_and_benfits).get("compensation_and_benfits", []) if processed_job.compensation_and_benfits else None,
                "application_info": json.loads(processed_job.application_info).get("application_info", []) if processed_job.application_info else None,
                "extracted_keywords": json.loads(processed_job.extracted_keywords).get("extracted_keywords", []) if processed_job.extracted_keywords else None,
                "processed_at": processed_job.processed_at.isoformat() if processed_job.processed_at else None,
            }

        return combined_data