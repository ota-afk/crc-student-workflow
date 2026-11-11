from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from .config import cors_origins, mock_path, use_mock
from .contract import Workflow

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


@app.get('/workflow', response_model=Workflow)
def get_workflow():
    if not use_mock():
        # Day 3: replace with the live engine
        raise HTTPException(status_code=501, detail='Live engine not implemented yet')
    path = mock_path()
    if not path.exists():
        raise HTTPException(status_code=404, detail='Mock file not found')
    return Workflow.model_validate_json(path.read_text(encoding='utf-8'))
