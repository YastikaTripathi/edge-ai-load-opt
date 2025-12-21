import math
import time
from typing import Dict, List, Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel, field_validator

app = FastAPI(title="Decision Engine", version="0.1.0")


class ScaleReq(BaseModel):
    function_id: str
    qps_hat: float = 10.0
    p95_cpu_ms: float = 5.0
    cpu_ms_per_pod: float = 50.0
    headroom: float = 0.2

    @field_validator("qps_hat", "p95_cpu_ms", "cpu_ms_per_pod")
    @classmethod
    def positive(cls, v: float) -> float:
        if v <= 0:
            raise ValueError("must be > 0")
        return v

    @field_validator("headroom")
    @classmethod
    def headroom_range(cls, v: float) -> float:
        if not (0.0 <= v < 1.0):
            raise ValueError("headroom must be in [0,1)")
        return v


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
    # simple log
    print(
        f"[scale] func={req.function_id} qps_hat={req.qps_hat} "
        f"p95_cpu_ms={req.p95_cpu_ms} cpu_ms_per_pod={req.cpu_ms_per_pod} headroom={req.headroom}"
    )
    demand = req.qps_hat * req.p95_cpu_ms
    denom = max(req.cpu_ms_per_pod * (1 - req.headroom), 1e-6)
    k = math.ceil(demand / denom)
    k = max(1, min(k, 50))
    return ScaleResp(replicas=k, cooldown_sec=30)


@app.post("/decision/placement", response_model=PlacementResp)
def decision_placement(req: PlacementReq):
    if not req.candidate_nodes:
        raise HTTPException(status_code=400, detail="no candidate nodes")
    scores: Dict[str, float] = {}
    for n in req.candidate_nodes:
        rtt = req.features.get(f"rtt_ms:{n}", 5.0)
        cpu = req.features.get(f"cpu_free:{n}", 0.5)
        warm = req.features.get(f"warm_pool:{n}", 0.0)
        s = (1 / (1 + rtt)) + 0.7 * cpu + 0.3 * warm
        scores[n] = float(s)
    best = max(scores, key=scores.get) if scores else None
    print(f"[place] func={req.function_id} scores={scores} best={best}")
    return PlacementResp(node_scores=scores, migrate_to=best)


@app.post("/router/choose")
def router_choose(ctx: RouterCtx):
    if not ctx.candidates:
        raise HTTPException(status_code=400, detail="no candidates")
    best, best_score = None, 1e9
    for n in ctx.candidates:
        score = ctx.rtt_ms.get(n, 10.0) + 2.0 * ctx.queue_len.get(n, 0.0)
        if score < best_score:
            best_score, best = score, n
    print(f"[route] func={ctx.function_id} target={best} score={best_score}")
    return {"target_node": best, "score": best_score}
