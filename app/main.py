import uuid, time, json, logging, sys
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from app.db import init_db
from app.ingestion import router as ingest_router
from app.metrics import router as metrics_router
from app.anomalies import router as anomaly_router
from app.health import router as health_router

class JSONFormatter(logging.Formatter):
    def format(self, record):
        try:
            msg = json.loads(record.getMessage())
        except:
            msg = {'message': record.getMessage()}
        msg.update({'level': record.levelname, 'logger': record.name,
                    'time': datetime.now(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')})
        return json.dumps(msg)

handler = logging.StreamHandler(sys.stdout)
handler.setFormatter(JSONFormatter())
logging.basicConfig(level=logging.INFO, handlers=[handler])
log = logging.getLogger('main')

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    log.info(json.dumps({'message': 'Store Intelligence API started', 'status': 'ready'}))
    yield

app = FastAPI(title='Store Intelligence API', version='1.0.0', lifespan=lifespan)

app.add_middleware(CORSMiddleware,
                   allow_origins=['*'],
                   allow_methods=['*'],
                   allow_headers=['*'])

@app.middleware('http')
async def request_logging(request: Request, call_next):
    trace_id = request.headers.get('X-Trace-Id', str(uuid.uuid4()))
    start = time.time()
    try:
        response = await call_next(request)
        ms = round((time.time() - start) * 1000, 2)
        log.info(json.dumps({
            'trace_id': trace_id,
            'method': request.method,
            'endpoint': str(request.url.path),
            'store_id': request.path_params.get('store_id', ''),
            'latency_ms': ms,
            'status_code': response.status_code,
        }))
        response.headers['X-Trace-Id'] = trace_id
        return response
    except Exception as e:
        ms = round((time.time() - start) * 1000, 2)
        log.error(json.dumps({'trace_id': trace_id, 'error': str(e), 'latency_ms': ms}))
        return JSONResponse(status_code=503,
                            content={'error': 'Service unavailable', 'trace_id': trace_id})

app.include_router(ingest_router)
app.include_router(metrics_router)
app.include_router(anomaly_router)
app.include_router(health_router)

@app.get('/')
async def root():
    return {'service': 'Store Intelligence API', 'version': '1.0.0', 'docs': '/docs'}
