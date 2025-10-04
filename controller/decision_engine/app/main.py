from fastapi import FastAPI
from pydantic import BaseModel
import math, time
from typing import List, Dict, Optional

app = FastAPI(title="Decision Engine", version="0.1.0")

class ScaleReq(BaseModel):
    function_id: str
    qps_hat: float = 10.0
    p95_cpu_ms: float = 5.0
    cpu_ms_per_pod: float = 50.0
    headroom: float = 0.2

class ScaleResp(BaseModel):
    replicas: int
    cooldown_sec: int = 30

class PlacementReq(BaseModel):
    function_id: str
    candidate_nodes: List[str]
    features: Dict[str, float]

class PlacementResp(BaseModel):
    node_scores: Dict[str, float]
    migrate_to: Optional[str] = None

class RouterCtx(BaseModel):
    function_id: str
    candidates: List[str]
    rtt_ms: Dict[str, float]
    queue_len: Dict[str, float]

@app.get("/healthz")
def healthz():
    return {"ok": True, "ts": time.time()}

@app.post("/decision/scale", response_model=ScaleResp)
def decision_scale(req: ScaleReq):
    demand = req.qps_hat * req.p95_cpu_ms
    denom = max(req.cpu_ms_per_pod * (1 - req.headroom), 1e-6)
    k = math.ceil(demand / denom)
    k = max(1, min(k, 50))
    return ScaleResp(replicas=k, cooldown_sec=30)

@app.post("/decision/placement", response_model=PlacementResp)
def decision_placement(req: PlacementReq):
    scores = {}
    for n in req.candidate_nodes:
        rtt = req.features.get(f"rtt_ms:{n}", 5.0)
        cpu = req.features.get(f"cpu_free:{n}", 0.5)
        warm = req.features.get(f"warm_pool:{n}", 0.0)
        s = (1/(1+rtt)) + 0.7*cpu + 0.3*warm
        scores[n] = s
    best = max(scores, key=scores.get) if scores else None
    return PlacementResp(node_scores=scores, migrate_to=best)

@app.post("/router/choose")
def router_choose(ctx: RouterCtx):
    best, best_score = None, 1e9
    for n in ctx.candidates:
        score = ctx.rtt_ms.get(n, 10.0) + 2.0*ctx.queue_len.get(n, 0.0)
        if score < best_score:
            best_score, best = score, n
    return {"target_node": best, "score": best_score}

