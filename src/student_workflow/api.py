"""Serve the demo workflow and sourced school search while live workflow work is pending."""

import logging

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from .config import cors_origins, mock_path, use_mock
from .contract import Workflow
from .rules import load_rules
from .schools import School, search_schools

logger = logging.getLogger(__name__)

app = FastAPI(title='CRC Student Workflow API')

# Streamlit calls the API from its server, so CORS does not affect it today.
# It only matters if a browser calls the API directly. Use specific origins, never '*'.
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_methods=['GET', 'POST'],
    allow_headers=['*'],
)


@app.get('/health')
def health():
    return {'status': 'ok'}


@app.get('/schools', response_model=list[School])
def get_schools(
    q: str = Query(default='', max_length=100),
    limit: int = Query(default=20, ge=1, le=100),
):
    try:
        return search_schools(q, limit, load_rules())
    except (OSError, ValueError) as error:
        # The student sees a short 503; the server log keeps the real reason for us to fix.
        logger.exception('school search failed')
        raise HTTPException(
            status_code=503, detail='School search is temporarily unavailable'
        ) from error


@app.get('/workflow', response_model=Workflow)
def get_workflow():
    if not use_mock():
        # Day 3: replace with the live engine
        raise HTTPException(status_code=501, detail='Live engine not implemented yet')
    path = mock_path()
    if not path.exists():
        raise HTTPException(status_code=404, detail='Mock file not found')
    return Workflow.model_validate_json(path.read_text(encoding='utf-8'))
