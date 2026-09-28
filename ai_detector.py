#!/usr/bin/env python3
"""Rileva processi di inferenza AI locale e identifica engine + modello caricato in memoria.

Engine supportati: Ollama, llama.cpp (llama-server/llama-cli), LM Studio, GPT4All,
AnythingLLM, Unsloth Studio, KoboldCpp, vLLM, LocalAI, oobabooga text-generation-webui.

Strategie (in ordine di affidabilità):
1. Scansione processi (psutil) per nomi noti degli engine.
2. Query API locali note con timeout breve:
   - Ollama  ``/api/ps``          -> modelli caricati in memoria + VRAM/RAM occupata
   - OpenAI-compat ``/v1/models`` (LM Studio, llama.cpp, GPT4All, KoboldCpp, vLLM, LocalAI)
   - AnythingLLM ``/api/system``  (solo presenza server)
3. Fallback: parsing della command line (``-m``/``--model`` con estensione .gguf/.ggml/...)
   per la famiglia llama.cpp (copre anche server custom e i processi figli di Unsloth Studio).
4. Se nessun engine è riconosciuto per processo, probe generico delle porte note per
   intercettare server OpenAI-compatibili con nomi di processo non riconoscibili.

Il risultato viene cachato per ``CACHE_TTL_S`` secondi: le query API costano tempo e non
vanno eseguite a ogni refresh della dashboard.
"""

from __future__ import annotations

import json
import re
import threading
import time
import urllib.request
from urllib.error import URLError

import psutil

# ─── Costanti ──────────────────────────────────────────────────────────────────
CACHE_TTL_S = 5.0          # cache del risultato di rilevamento
HTTP_TIMEOUT = 0.4         # timeout per ogni query API locale (secondi)

# Specs degli engine: chiave, etichetta, sottostringhe di match su nome processo/cmdline,
# porte API da provare, path API (None = nessuna query, si usa solo cmdline).
ENGINES = [
    dict(key="ollama",      label="Ollama",         procs=("ollama",),
         ports=(11434,), api_paths=("/api/ps",)),
    dict(key="llama_cpp",   label="llama.cpp",      procs=("llama-server", "llama-cli",
                                                           "llama-server.exe", "llama-cli.exe"),
         exclude=("ollama", "unsloth", "lm studio", "lmstudio", "gpt4all", "anythingllm"),
         ports=(8080,), api_paths=("/v1/models",)),
    dict(key="lm_studio",   label="LM Studio",      procs=("lm studio", "lmstudio"),
         ports=(1234,), api_paths=("/v1/models", "/api/v0/models/loaded")),
    dict(key="gpt4all",     label="GPT4All",        procs=("gpt4all",),
         ports=(4891,), api_paths=("/v1/models",)),
    dict(key="anythingllm", label="AnythingLLM",    procs=("anythingllm",),
         ports=(3001,), api_paths=("/api/system",)),
    dict(key="unsloth",     label="Unsloth Studio", procs=("unsloth",),
         ports=(), api_paths=None),
    dict(key="koboldcpp",   label="KoboldCpp",      procs=("koboldcpp",),
         ports=(5001,), api_paths=("/v1/models",)),
    dict(key="vllm",        label="vLLM",           procs=("vllm",),
         ports=(8000,), api_paths=("/v1/models",)),
    dict(key="localai",     label="LocalAI",        procs=("local-ai", "localai"),
         ports=(8080,), api_paths=("/v1/models",)),
    dict(key="textgen",     label="oobabooga text-gen", procs=("text-generation-webui",),
         ports=(5000,), api_paths=("/v1/models",)),
]

# Porte note per il probe generico: derivate da ENGINES
GENERIC_PORTS = {p: (e["label"], e["api_paths"][0]) for e in ENGINES if e.get("api_paths") for p in e["ports"]}

# Regex per estrarre il modello dalla command line (famiglia llama.cpp)
_MODEL_ARG_RE = re.compile(
    r"(?:-m|--model|--model-file|-mf|--model-path)\s*[= ]\s*[\"']?"
    r"([^\s\"']+\.(?:gguf|ggml|bin|safetensors|onnx)[^\s\"']*)",
    re.IGNORECASE,
)

# ─── Cache ─────────────────────────────────────────────────────────────────────
_lock = threading.Lock()
_cache = {"ts": 0.0, "result": []}


def format_memory(num_bytes: float) -> str:
    """Formatta byte in stringa leggibile (B/KB/MB/GB)."""
    b = float(num_bytes)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if b < 1024:
            return f"{b:,.1f} {unit}"
        b /= 1024
    return f"{b:,.1f} PB"


# ─── Rilevamento ───────────────────────────────────────────────────────────────

def detect_ai_inference(force: bool = False) -> list[dict]:
    """Rileva gli engine di inferenza AI attivi.

    Ritorna una lista di dict:
        engine     -> etichetta dell'engine (es. "Ollama")
        model      -> modello caricato in memoria (stringa, "" se sconosciuto)
        mem_bytes  -> memoria occupata (bytes; 0 se sconosciuta)
        source     -> come è stato trovato il modello: api | cmdline | process
        processes  -> nomi dei processi rilevati
        pids       -> pid dei processi rilevati
    """
    now = time.time()
    with _lock:
        if not force and (now - _cache["ts"]) < CACHE_TTL_S:
            return _cache["result"]
    result = _detect()
    with _lock:
        _cache.update(ts=time.time(), result=result)
    return result


def _detect() -> list[dict]:
    procs = _snapshot_processes()
    engines: list[dict] = []

    for spec in ENGINES:
        matches = [
            p for p in procs
            if _match_process(p, spec["procs"])
            and not _match_process(p, spec.get("exclude") or ())
        ]
        if not matches:
            continue

        model, mem_bytes, source = None, 0, "process"
        if spec.get("api_paths"):
            for port in spec["ports"]:
                for path in spec["api_paths"]:
                    got = _query_api(port, path)
                    if got is not None:
                        model, mem_bytes = got
                        source = "api"
                        break
                if source == "api":
                    break

        if not model:
            model = _model_from_cmdlines([p["cmdline"] for p in matches])
            if model:
                source = "cmdline"
        if not mem_bytes:
            mem_bytes = sum(p["rss"] for p in matches if p["rss"])

        engines.append({
            "engine": spec["label"],
            "model": model or "",
            "mem_bytes": int(mem_bytes),
            "source": source,
            "processes": sorted({p["name"] for p in matches if p["name"]})[:3],
            "pids": sorted(p["pid"] for p in matches if p["pid"])[:5],
        })

    # Nessun engine riconosciuto per processo -> probe generico delle porte note
    if not engines:
        for port, (label, path) in GENERIC_PORTS.items():
            got = _query_api(port, path)
            if got is not None:
                model, mem_bytes = got
                engines.append({
                    "engine": label,
                    "model": model or "",
                    "mem_bytes": int(mem_bytes),
                    "source": "api",
                    "processes": [],
                    "pids": [],
                })
    return engines


# ─── Helpers ───────────────────────────────────────────────────────────────────

def _snapshot_processes() -> list[dict]:
    """Raccoglie pid/name/cmdline/rss di tutti i processi, tollerante agli errori."""
    out = []
    for proc in psutil.process_iter(attrs=["pid", "name", "cmdline", "memory_info"]):
        try:
            info = proc.info
            if not info or info["pid"] is None:
                continue
            out.append({
                "pid": info["pid"],
                "name": info.get("name") or "",
                "cmdline": list(info.get("cmdline") or []),
                "rss": (info.get("memory_info") or None).rss if info.get("memory_info") else 0,
            })
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return out


def _match_process(proc: dict, needles: tuple[str, ...]) -> bool:
    hay = (proc.get("name") or "") + " " + " ".join(proc.get("cmdline") or [])
    hay = hay.lower()
    return any(n.lower() in hay for n in needles)


def _model_from_cmdlines(cmdlines: list[list[str]]) -> str | None:
    """Cerca un modello (.gguf/.ggml/.bin/.safetensors/.onnx) negli argomenti di processo."""
    seen: list[str] = []
    for cmd in cmdlines:
        line = " ".join(cmd)
        for m in _MODEL_ARG_RE.finditer(line):
            path = m.group(1).strip().strip('"').strip("'")
            name = path.replace("\\", "/").rsplit("/", 1)[-1]
            if name and name not in seen:
                seen.append(name)
    return ", ".join(seen) if seen else None


def _query_api(port: int, path: str):
    """Query locale su (port, path). Ritorna (model_str, mem_bytes) o None se irraggiungibile.

    - /api/ps (Ollama): models[].name + size_vram/size
    - /v1/models (OpenAI-compat): data[].id
    - /api/system (AnythingLLM): solo presenza, modello sconosciuto
    """
    url = f"http://127.0.0.1:{port}{path}"
    try:
        req = urllib.request.Request(url, headers={"Accept": "application/json"})
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT) as resp:
            payload = json.loads(resp.read().decode("utf-8", errors="replace"))
    except (URLError, OSError, ValueError, json.JSONDecodeError, TimeoutError):
        return None

    if path == "/api/ps":  # Ollama
        models = payload.get("models") or []
        if not models:
            return "", 0
        names = [m.get("name") or m.get("model") or "" for m in models]
        mem = sum(int(m.get("size_vram") or m.get("size") or 0) for m in models)
        return ", ".join(n for n in names if n), mem

    if path == "/api/system":  # AnythingLLM: presenza soltanto
        return "", 0

    # OpenAI-compat /v1/models (e varianti)
    data = payload.get("data")
    if isinstance(data, list):
        names = [m.get("id") or m.get("name") or "" for m in data if isinstance(m, dict)]
        return ", ".join(n for n in names if n), 0
    return "", 0


if __name__ == "__main__":
    import json as _json
    result = detect_ai_inference(force=True)
    print(_json.dumps(result, indent=2))
    if not result:
        print("Nessun engine di inferenza AI locale rilevato.")
