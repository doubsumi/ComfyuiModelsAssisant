"""
ComfyUI 模型扫描器
==================
Layer 1a: 读取 safetensors 头部 __metadata__
Layer 1b: 基于文件名 + tensor 名称的启发式架构推断
"""
from __future__ import annotations

import json
import re
import struct
from dataclasses import asdict, dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Optional


FILE_EXTS = {".safetensors", ".ckpt", ".pt", ".pth", ".bin", ".gguf", ".sft", ".onnx"}
MAX_HEADER_SIZE = 200 * 1024 * 1024
MAX_TENSOR_SAMPLE = 5000


# ============================================================
# 数据结构
# ============================================================
@dataclass
class ModelEntry:
    file: str
    dir: str
    sizeBytes: int = 0
    mtime: str = ""

    arch: Optional[str] = None
    role: str = "unknown"
    source: str = "heuristic"
    confidence: float = 0.0
    needsLlm: bool = False
    signals: list = field(default_factory=list)
    missingFields: list = field(default_factory=list)

    metadata: dict = field(default_factory=dict)

    compatibleEncoders: Optional[list] = None
    compatibleVaes: Optional[list] = None
    compatibleLoras: Optional[list] = None
    encoderNodeParams: Optional[dict] = None

    triggerWord: Optional[str] = None
    defaultWeight: Optional[float] = None
    defaultParams: Optional[dict] = None

    def to_dict(self) -> dict:
        return asdict(self)


# ============================================================
# Layer 1a: safetensors 头部解析
# ============================================================
def read_safetensors_header(path: Path) -> Optional[dict]:
    try:
        with open(path, "rb") as f:
            size_bytes = f.read(8)
            if len(size_bytes) != 8:
                return None
            header_size = struct.unpack("<Q", size_bytes)[0]
            if header_size <= 0 or header_size > MAX_HEADER_SIZE:
                return None
            raw = f.read(header_size)
            if len(raw) != header_size:
                return None
            return json.loads(raw.decode("utf-8"))
    except (OSError, UnicodeDecodeError, json.JSONDecodeError):
        return None


def extract_tensor_names(header: dict) -> list[str]:
    return [k for k in header.keys() if k != "__metadata__"]


def extract_metadata(header: dict) -> dict:
    raw = header.get("__metadata__", {}) or {}
    if not isinstance(raw, dict):
        return {}

    out: dict[str, Any] = {"_rawKeys": list(raw.keys())}

    if "ss_base_model_version" in raw:
        out["baseModelVersion"] = raw["ss_base_model_version"]
    if "ss_network_module" in raw:
        out["networkModule"] = raw["ss_network_module"]
    if "ss_network_dim" in raw:
        try:
            out["loraRank"] = int(raw["ss_network_dim"])
        except (ValueError, TypeError):
            pass
    if "ss_network_alpha" in raw:
        try:
            out["loraAlpha"] = float(raw["ss_network_alpha"])
        except (ValueError, TypeError):
            pass
    if "modelspec.architecture" in raw:
        out["modelspecArch"] = raw["modelspec.architecture"]
    if "modelspec.title" in raw:
        out["title"] = raw["modelspec.title"]
    if "ss_trained_words" in raw:
        try:
            words = json.loads(raw["ss_trained_words"])
            if isinstance(words, list) and words:
                out["triggerWord"] = words[0]
        except (json.JSONDecodeError, TypeError):
            pass

    return out


# ============================================================
# Layer 1b: 启发式推断
# ============================================================
# 文件名模式（优先级最高，命中即返回）
NAME_PATTERNS: list[tuple[str, str, str]] = [
    # (正则, 架构 ID, 角色)
    (r"krea2",                          "krea2",              "unet"),
    (r"boogu",                          "boogu",              "unet"),
    (r"minimax_h3_fl2va",               "minimax_h3_fl2va",   "unet"),
    (r"minimax_h3_ref2va",              "minimax_h3_ref2va",  "unet"),
    (r"minimax_h3_hybrid",              "minimax_h3_fl2va",   "unet"),
    (r"minimax_h3_video_vae",           "minimax_h3",         "videoVae"),
    (r"minimax_h3_audio_vae",           "minimax_h3",         "audioVae"),
    (r"qwen3vl_",                       "qwen3vl",            "encoder"),
    (r"qwen_image_vae",                 "qwen_image",         "vae"),
    (r"^ae\.safetensors$",              "flux",               "vae"),
    (r"flux.*lora|lora.*flux",          "flux",               "lora"),
]


# tensor 名称特征签名
ARCH_SIGNATURES: dict[str, dict[str, list[tuple[str, int]]]] = {
    "flux": {
        "positive": [
            (r"^double_blocks\.\d+\.", 12),
            (r"^single_blocks\.\d+\.", 12),
            (r"^img_in\.weight$", 8),
            (r"^txt_in\.weight$", 8),
            (r"^time_in\.", 5),
        ],
        "negative": [
            (r"^model\.diffusion_model\.input_blocks", -25),
            (r"^encoder\.down_blocks", -20),
        ],
    },
    "sd15_sdxl": {
        "positive": [
            (r"^model\.diffusion_model\.input_blocks\.", 10),
            (r"^model\.diffusion_model\.middle_block\.", 10),
            (r"^model\.diffusion_model\.output_blocks\.", 10),
            (r"^first_stage_model\.", 6),
        ],
        "negative": [
            (r"^double_blocks", -20),
        ],
    },
    "qwen3vl": {
        "positive": [
            (r"^visual\.", 10),
            (r"^model\.layers\.\d+\.self_attn", 8),
            (r"^model\.embed_tokens\.weight$", 6),
            (r"^lm_head\.weight$", 6),
        ],
        "negative": [
            (r"^model\.diffusion_model", -20),
        ],
    },
    "minimax_h3": {
        "positive": [
            (r"^video_", 8),
            (r"^audio_", 8),
            (r"^transformer_blocks?\.\d+\.", 5),
            (r"^patch_embed", 5),
            (r"^joint_blocks", 6),
        ],
        "negative": [
            (r"^model\.diffusion_model\.input_blocks", -15),
            (r"^double_blocks", -15),
        ],
    },
    "vae": {
        "positive": [
            (r"^encoder\.down_blocks\.", 10),
            (r"^decoder\.up_blocks\.", 10),
            (r"^encoder\.conv_in\.weight$", 8),
            (r"^decoder\.conv_out\.weight$", 8),
            (r"^quant_conv\.", 5),
            (r"^post_quant_conv\.", 5),
        ],
        "negative": [],
    },
    "lora": {
        "positive": [
            (r"\.lora_A\.weight$", 12),
            (r"\.lora_B\.weight$", 12),
            (r"\.lora_down\.weight$", 12),
            (r"\.lora_up\.weight$", 12),
            (r"\.lora_alpha$", 6),
            (r"^lora_unet_", 10),
            (r"^lora_te_", 8),
        ],
        "negative": [],
    },
}

# 预编译正则
_COMPILED_SIGS: dict[str, dict[str, list[tuple[re.Pattern, int]]]] = {}
for _arch, _sig in ARCH_SIGNATURES.items():
    _COMPILED_SIGS[_arch] = {
        "positive": [(re.compile(p), w) for p, w in _sig["positive"]],
        "negative": [(re.compile(p), w) for p, w in _sig["negative"]],
    }

_COMPILED_NAMES = [(re.compile(p), a, r) for p, a, r in NAME_PATTERNS]


def _score_signature(tensor_names: list[str], sig: dict) -> tuple[float, list[str]]:
    score = 0.0
    hits: list[str] = []
    sample = tensor_names[:MAX_TENSOR_SAMPLE]

    for rx, weight in sig["positive"]:
        matched = sum(1 for t in sample if rx.search(t))
        if matched > 0:
            score += weight * min(matched, 5) / 5
            hits.append(f"+{rx.pattern}")
    for rx, weight in sig["negative"]:
        if any(rx.search(t) for t in sample):
            score += weight
            hits.append(f"-{rx.pattern}")
    return score, hits


def infer_architecture(tensor_names: list[str], file_name: str) -> tuple[Optional[str], str, float, list[str]]:
    """返回 (arch, role, confidence, signals)"""
    name_lower = file_name.lower()

    # 1) 文件名优先
    for rx, arch, role in _COMPILED_NAMES:
        if rx.search(name_lower):
            return arch, role, 0.95, [f"filename:{rx.pattern}"]

    # 2) tensor 名称推断
    results: list[tuple[str, float, list[str]]] = []
    for arch, sig in _COMPILED_SIGS.items():
        score, hits = _score_signature(tensor_names, sig)
        if score > 0:
            results.append((arch, score, hits))

    if not results:
        return None, "unknown", 0.0, []

    results.sort(key=lambda x: -x[1])
    top_arch, top_score, top_hits = results[0]
    second_score = results[1][1] if len(results) > 1 else 0
    gap = top_score - second_score
    confidence = min(1.0, max(0.0, (top_score / 100) * (gap / max(top_score, 1) + 0.5)))

    # sd15 / sdxl 区分
    if top_arch == "sd15_sdxl":
        has_clipg = any("conditioner.embedders.1" in t for t in tensor_names[:MAX_TENSOR_SAMPLE])
        top_arch = "sdxl" if has_clipg else "sd15"

    role = _infer_role(top_arch, tensor_names)
    return top_arch, role, confidence, top_hits


def _infer_role(arch: str, tensor_names: list[str]) -> str:
    sample = tensor_names[:500]
    if arch in ("vae", "minimax_h3"):
        if any("vae" in t.lower() for t in sample):
            return "vae"
    if arch == "qwen3vl":
        return "encoder"
    if arch in ("sd15", "sdxl"):
        has_clip = any("cond_stage_model" in t or "text_encoder" in t for t in sample)
        return "checkpoint" if has_clip else "unet"
    return "unet"


def _normalize_arch_hint(hint: str) -> Optional[str]:
    h = hint.lower()
    mapping = [
        ("flux", "flux"),
        ("krea", "krea2"),
        ("boogu", "boogu"),
        ("qwen", "qwen_image"),
        ("minimax", "minimax_h3_fl2va"),
        ("sdxl", "sdxl"),
        ("sd 1.5", "sd15"),
        ("sd1.5", "sd15"),
    ]
    for k, v in mapping:
        if k in h:
            return v
    return None


# ============================================================
# 扫描器
# ============================================================
class ModelScanner:
    def __init__(self, confidence_threshold: float = 0.6):
        self.confidence_threshold = confidence_threshold

    def scan_single(self, abs_path: Path, models_dir: Path, threshold: float | None = None) -> ModelEntry:
        threshold = threshold if threshold is not None else self.confidence_threshold
        try:
            rel = abs_path.relative_to(models_dir)
        except ValueError:
            rel = Path(abs_path.name)
        parts = rel.parts
        dir_name = parts[0] if len(parts) >= 2 else "."

        try:
            stat = abs_path.stat()
            size_bytes = stat.st_size
            mtime = datetime.fromtimestamp(stat.st_mtime).isoformat()
        except OSError:
            size_bytes = 0
            mtime = ""

        entry = ModelEntry(
            file=abs_path.name,
            dir=dir_name,
            sizeBytes=size_bytes,
            mtime=mtime,
        )

        if abs_path.suffix.lower() != ".safetensors":
            arch, role, conf, signals = infer_architecture([], abs_path.name)
            entry.arch = arch
            entry.role = role
            entry.confidence = conf
            entry.signals = signals
            entry.source = "heuristic"
            entry.needsLlm = (conf < threshold or not arch)
            self._fill_missing(entry, threshold)
            return entry

        header = read_safetensors_header(abs_path)
        if header is None:
            entry.source = "heuristic"
            entry.needsLlm = True
            entry.missingFields = ["无法读取 safetensors 头部"]
            return entry

        # Layer 1a
        metadata = extract_metadata(header)
        entry.metadata = metadata

        # 从 metadata 得到线索
        arch_hint = metadata.get("modelspecArch") or metadata.get("baseModelVersion")
        if arch_hint:
            norm = _normalize_arch_hint(arch_hint)
            if norm:
                entry.arch = norm
                entry.source = "metadata"
                entry.confidence = 0.9

        # Layer 1b
        tensor_names = extract_tensor_names(header)
        inferred_arch, role, confidence, signals = infer_architecture(tensor_names, abs_path.name)

        if not entry.arch:
            entry.arch = inferred_arch
            entry.confidence = confidence
            entry.source = "heuristic"

        entry.role = role
        entry.signals = signals
        entry.metadata["_tensorCount"] = len(tensor_names)

        if metadata.get("triggerWord"):
            entry.triggerWord = metadata["triggerWord"]

        self._fill_missing(entry, threshold)
        return entry

    def _fill_missing(self, entry: ModelEntry, threshold: float) -> None:
        missing = []
        if not entry.arch:
            missing.append("arch")
        if entry.role == "unknown":
            missing.append("role")
        if entry.role == "unet":
            if not entry.compatibleEncoders:
                missing.append("compatibleEncoders")
            if not entry.compatibleVaes:
                missing.append("compatibleVaes")
        if entry.role == "lora":
            if not entry.triggerWord:
                missing.append("triggerWord")
        if entry.role == "encoder" and not entry.encoderNodeParams:
            missing.append("encoderNodeParams")

        entry.missingFields = missing
        entry.needsLlm = (entry.confidence < threshold) or bool(missing)

    def scan_directory(self, models_dir: str | Path, threshold: float | None = None) -> list[ModelEntry]:
        root = Path(models_dir)
        if not root.is_dir():
            raise FileNotFoundError(f"目录不存在: {root}")

        threshold = threshold if threshold is not None else self.confidence_threshold
        entries: list[ModelEntry] = []
        for p in root.rglob("*"):
            if not p.is_file():
                continue
            if p.suffix.lower() not in FILE_EXTS:
                continue
            rel = p.relative_to(root)
            if len(rel.parts) < 2:
                continue
            try:
                entries.append(self.scan_single(p, root, threshold))
            except Exception as e:
                print(f"[scan] 失败 {p}: {e}")

        entries.sort(key=lambda e: (e.dir, e.file))
        return entries


def scan_directory(models_dir: str | Path, threshold: float = 0.6) -> list[dict]:
    """对外便捷函数，返回 dict 列表"""
    scanner = ModelScanner(threshold)
    return [e.to_dict() for e in scanner.scan_directory(models_dir, threshold)]