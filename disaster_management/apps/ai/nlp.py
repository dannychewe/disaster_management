# nlp.py
from sentence_transformers import SentenceTransformer
import numpy as np

# Small multilingual model; loads ~90MB
_model = SentenceTransformer("sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")

# crude keyword priors to start; replace with logistic regression later
_PRIORS = {
    "flood": ["river burst", "water level", "inundated", "washed away", "bridge submerged"],
    "fire":  ["flames", "smoke", "burning", "bushfire", "wildfire"],
    "drought":["dry wells","no rain","crop failure","parched","water scarcity"],
    "storm": ["strong winds","storm","lightning","thunder","hail"],
}

def text_severity_prob(text: str, hazard: str) -> float:
    """Return 0..1 severity likelihood from text using cosine sim to hazard priors."""
    if not text:
        return 0.2
    q = _model.encode([text])[0]
    priors = _PRIORS.get(hazard, [])
    if not priors:
        return 0.3
    P = _model.encode(priors)
    sims = np.dot(P, q) / (np.linalg.norm(P, axis=1) * np.linalg.norm(q) + 1e-8)
    s = float(np.clip(np.max(sims), 0, 1))
    # stretch a bit so “very close” reads stronger
    return float(np.clip(0.1 + 0.9 * s, 0, 1))
