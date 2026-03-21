import os, json, uuid, asyncio, logging
from datetime import datetime
from fastapi import APIRouter, Request, HTTPException, BackgroundTasks, UploadFile, File, Response, Form
from fastapi.responses import StreamingResponse
from schemas import *
from config import settings
from db import db
from services import get_student_profile

logger = logging.getLogger(__name__)
router = APIRouter()

@router.post("/debug/analyze")
async def analyze_code_error(body: DebugRequest):
    """AI-powered code debugger — explains error and suggests fix."""
    result = await debug_code(body.code, body.stderr, body.language)
    return result


