"""
Prompt Builder
==============
把当前注册表状态 + 待补全目标渲染成一段详细的 LLM 提示词。

设计原则：
1. 给 LLM 充分的上下文：架构定义、已注册的参考模型、目录约定
2. 明确区分"新模型"和"缺字段模型"两类目标
3. 提供完整的真实示例，让 LLM 有可参考的范本
4. 用强约束条款防止 LLM 自创架构 ID 或修改 file/dir
"""
from __future__ import annotations

import json
from typing import Any, Optional


# ============================================================
# 提示词模板（分段组装）
# ============================================================
PROMPT_INTRO = """你是一个 ComfyUI 模型兼容性专家，任务是分析用户下载的模型文件，输出一个 JSON Patch 用于补全模型注册表。

用户正在构建一个本地模型组合探索工具，需要准确知道每个模型文件的架构、角色、以及它能和其他哪些模型搭配。你的输出将直接决定工具能否正确生成可运行的工作流。

下面是完整的任务说明，请仔细阅读后输出。
"""


FIELD_SPEC = """# 字段定义

## `arch`（架构 ID）
- **主模型（role=unet）**：必须是「已注册架构」表中的某个 ID（如 `krea2`、`boogu`、`minimax_h3_fl2va`）。不确定就填 `null`。
- **编码器（role=encoder）**：填模型族名（如 `qwen3vl`、`clip_l`），不要填具体生态名。
- **VAE（role=vae / videoVae / audioVae）**：填模型族名（如 `qwen_image_vae`、`minimax_h3_video_vae`）。
- **LoRA（role=lora）**：填它所训练的底模架构 ID（如 `krea2`、`flux`、`minimax_h3_fl2va`）。

## `role`（角色）
- `unet`：扩散模型主模型（通常在 `diffusion_models/` 或 `unet/`）
- `encoder`：文本/视觉编码器（通常在 `text_encoders/` 或 `clip/`）
- `vae`：通用 VAE（通常在 `vae/`，纯图像用）
- `videoVae`：视频专用 VAE（通常在 `vae/`，配合视频模型）
- `audioVae`：音频专用 VAE（通常在 `vae/`，配合视频模型）
- `lora`：LoRA 权重（通常在 `loras/`）
- `checkpoint`：一体化底模（通常在 `checkpoints/`）

## `compatibleEncoders`（仅 role=unet）
这个主模型需要哪些编码器文件。填**已注册的编码器文件名**（见下方参考列表），不要编造。

## `compatibleVaes`（仅 role=unet）
这个主模型需要哪些 VAE 文件。填**已注册的 VAE 文件名**。视频模型可能需要多个（videoVae + audioVae）。

## `compatibleLoras`（仅 role=unet）
这个主模型能用哪些架构的 LoRA。填**架构 ID**（如 `["krea2"]`），不是文件名。

## `encoderNodeParams`（仅 role=encoder）
这个编码器在 ComfyUI 中使用时需要给 `CLIPLoader` 节点传什么 `type` 参数。例如 `{"type": "krea2"}`。

## `triggerWord`（仅 role=lora）
LoRA 的触发词。如果不知道，留空字符串，不要编造。

## `defaultWeight`（仅 role=lora）
LoRA 的推荐权重，范围 `[0.0, 2.0]`。一般风格 LoRA 用 0.8-1.0，加速 LoRA 用 1.0-1.8。

## `defaultParams`（仅 role=unet）
推荐采样参数。包含 `steps`、`cfg`、`sampler`、`scheduler` 四个字段。参考已注册的同类模型。
"""


CONSTRAINTS = """# 强约束（违反将导致 Patch 被拒绝）

1. **`patchVersion` 必须严格等于目标值**，否则整个 Patch 被拒绝。
2. **`file` 和 `dir` 必须与「待处理目标」列表完全一致**，不得修改、缩写、或编造。
3. **`arch` 必须是「已注册架构」表中存在的 ID，或 `null`**。不得自创架构 ID。
4. **`compatibleEncoders` / `compatibleVaes` 只能引用「参考模型」列表中真实存在的文件**。不得编造文件名。
5. **不要输出任何 JSON 之外的内容**，不要加解释性文字、不要加 Markdown 标题、不要用多个代码块。
"""


# ============================================================
# 渲染：架构定义
# ============================================================
def _render_architectures(architectures: dict, compatibility: dict) -> str:
    if not architectures:
        return "（当前没有已注册的架构）\n"

    lines = []
    for arch_id in sorted(architectures.keys()):
        info = architectures[arch_id]
        label = info.get("label", arch_id)
        unet_folder = info.get("unetFolder", "?")
        encoders = info.get("encoders", [])
        encoder_node = info.get("encoderNode", "?")
        encoder_params = info.get("encoderNodeParams", {})
        vae = info.get("vae")
        dp = info.get("defaultParams", {})
        compat = compatibility.get(arch_id, {})
        compat_loras = compat.get("compatibleLoras", [])

        lines.append(f"## `{arch_id}` — {label}")
        lines.append(f"- 主模型目录: `{unet_folder}/`")
        lines.append(f"- 编码器加载节点: `{encoder_node}`")
        if encoder_params:
            lines.append(f"- 编码器节点参数: `{json.dumps(encoder_params, ensure_ascii=False)}`")
        if encoders:
            lines.append(f"- 已知可用编码器: {', '.join(f'`{e}`' for e in encoders)}")
        if isinstance(vae, list):
            lines.append(f"- 需要 VAE: {', '.join(f'`{v}`' for v in vae)}")
        elif vae:
            lines.append(f"- 需要 VAE: `{vae}`")
        if compat_loras:
            lines.append(f"- 兼容的 LoRA 架构: {', '.join(f'`{a}`' for a in compat_loras)}")
        if dp:
            lines.append(f"- 推荐默认参数: `{json.dumps(dp, ensure_ascii=False)}`")
        lines.append("")

    return "\n".join(lines)


# ============================================================
# 渲染：参考模型（帮助 LLM 推荐 compatibleEncoders/Vaes）
# ============================================================
REFERENCE_LIMIT_PER_ROLE = 20

# ============================================================
# 辅助函数
# ============================================================
def _was_registered(target: dict, known_models: list[dict]) -> bool:
    """判断某个 target 是否在已注册列表中（即属于"缺字段"而非"新模型"）"""
    key = (target.get("file"), target.get("dir"))
    for m in known_models:
        if (m.get("file"), m.get("dir")) == key:
            return True
    return False


def _dedupe(items: list[dict]) -> list[dict]:
    seen = set()    
    out = []
    for m in items:
        key = (m.get("file"), m.get("dir"))
        if key in seen:
            continue
        seen.add(key)
        out.append(m)
    return out


def _fmt_size(n: int) -> str:
    if not n:
        return "—"
    if n >= 1024 ** 3:
        return f"{n / 1024**3:.2f} GB"
    if n >= 1024 ** 2:
        return f"{n / 1024**2:.1f} MB"
    return f"{n / 1024:.1f} KB"


def _render_output_spec(registry_version: str) -> str:
    """输出格式说明。使用 chr(96) 拼接反引号，避免源码依赖反引号字面量。"""
    BT = chr(96)
    BTC = BT * 3
    lines = [
        "# 输出格式",
        "",
        f"输出一个 JSON 对象，用 {BTC}json 和 {BTC} 包裹。结构如下：",
        "",
        BTC + "json",
        "{",
        f'  "patchVersion": "{registry_version}",',
        '  "source": "llm",',
        '  "sourceModel": "<你的模型名称，如 claude-sonnet-4>",',
        '  "timestamp": "<ISO8601 时间戳，例如 2026-09-15T10:30:00Z>",',
        '  "models": [',
        "    {",
        '      "file": "<文件名，与目标列表一致>",',
        '      "dir": "<目录名，与目标列表一致>",',
        '      "arch": "<架构 ID 或 null>",',
        '      "role": "<unet | encoder | vae | videoVae | audioVae | lora | checkpoint>",',
        '      "compatibleEncoders": ["<encoder 文件名>"],',
        '      "compatibleVaes": ["<vae 文件名>"],',
        '      "compatibleLoras": ["<架构 ID>"],',
        '      "encoderNodeParams": { "type": "<CLIPLoader type 值>" },',
        '      "triggerWord": "<触发词，无则空字符串>",',
        '      "defaultWeight": 1.0,',
        '      "defaultParams": {',
        '        "steps": 20,',
        '        "cfg": 1.0,',
        '        "sampler": "euler",',
        '        "scheduler": "simple"',
        "      },",
        '      "_note": "<可选：说明你的判断依据>"',
        "    }",
        "  ]",
        "}",
        BTC,
        "",
    ]
    return "\n".join(lines)


def _render_example() -> str:
    """完整示例。同样用 chr(96) 拼接反引号。"""
    BT = chr(96)
    BTC = BT * 3
    lines = [
        "# 完整示例",
        "",
        f"假设用户新增了一个 {BT}flux1-dev-fp8.safetensors{BT} 文件，位于 {BT}diffusion_models/{BT}。",
        f"参考模型中已有 {BT}clip_l.safetensors{BT}、{BT}t5xxl_fp8_e4m3fn.safetensors{BT}"
        f"（都在 {BT}text_encoders/{BT}）和 {BT}ae.safetensors{BT}（在 {BT}vae/{BT}）。",
        f"已注册架构中有 {BT}flux{BT} 架构，其 {BT}compatibleLoras{BT} 是 {BT}[\"flux\"]{BT}。",
        "",
        "正确的输出：",
        "",
        BTC + "json",
        "{",
        '  "patchVersion": "1.0.0",',
        '  "source": "llm",',
        '  "sourceModel": "claude-sonnet-4",',
        '  "timestamp": "2026-09-15T10:30:00Z",',
        '  "models": [',
        "    {",
        '      "file": "flux1-dev-fp8.safetensors",',
        '      "dir": "diffusion_models",',
        '      "arch": "flux",',
        '      "role": "unet",',
        '      "compatibleEncoders": ["clip_l.safetensors", "t5xxl_fp8_e4m3fn.safetensors"],',
        '      "compatibleVaes": ["ae.safetensors"],',
        '      "compatibleLoras": ["flux"],',
        '      "defaultParams": {',
        '        "steps": 20,',
        '        "cfg": 1.0,',
        '        "sampler": "euler",',
        '        "scheduler": "simple"',
        "      },",
        '      "_note": "FLUX.1 dev 主模型，需要双文本编码器（CLIP-L + T5-XXL），VAE 使用 ae.safetensors"',
        "    }",
        "  ]",
        "}",
        BTC,
        "",
        "注意：",
        "",
        f"- {BT}compatibleEncoders{BT} 中的文件名必须是参考模型列表中真实存在的",
        f"- {BT}compatibleLoras{BT} 是架构 ID 列表，不是文件名列表",
        f"- 如果某个字段不确定，{BT}{BT}直接省略该字段{BT}{BT}，不要编造",
        "",
    ]
    return "\n".join(lines)


def build_update_prompt(
    registry: dict,
    targets: list[dict],
    known_models: Optional[list[dict]] = None,
) -> str:
    """
    生成完整的更新提示词。

    Args:
        registry: 注册表（含 architectures 和 compatibilityMatrix）
        targets: 待处理的目标模型列表（未注册 + 缺字段）
        known_models: 已注册且已补全的模型列表。若不传，则从 registry["models"] 中过滤。
    """
    if not targets:
        return ""

    registry_version = registry.get("version", "1.0.0")
    architectures = registry.get("architectures", {}) or {}
    compatibility = registry.get("compatibilityMatrix", {}) or {}

    if known_models is None:
        known_models = [m for m in registry.get("models", []) if not m.get("needsLlm")]

    new_targets = [
        t for t in targets
        if not _was_registered(t, known_models)
    ]
    incomplete_targets = [
        t for t in targets
        if _was_registered(t, known_models)
    ]

    new_targets = _dedupe(new_targets)
    incomplete_targets = _dedupe(incomplete_targets)

    sections = [
        PROMPT_INTRO,
        "",
        "# 一、当前已注册的架构",
        "",
        _render_architectures(architectures, compatibility),
        "",
        "# 二、参考模型（已注册且已补全）",
        "",
        "下方模型可用于填充 `compatibleEncoders` / `compatibleVaes` 字段。只能引用这里出现的文件名。",
        "",
        _render_reference_models(known_models),
        "",
        "# 三、待处理目标",
        "",
    ]

    if new_targets:
        sections.extend([
            "## 类别 A：全新未注册的模型",
            "",
            "这些文件的架构、角色、配套关系都待你判断。",
            "",
            _render_new_targets(new_targets),
            "",
        ])

    if incomplete_targets:
        sections.extend([
            "## 类别 B：已注册但字段不完整",
            "",
            "这些文件已经有初步信息，但缺少关键字段。请只补充缺失字段，不要覆盖已有字段。",
            "",
            _render_incomplete_targets(incomplete_targets),
            "",
        ])

    sections.extend([
        "# 四、字段说明",
        "",
        FIELD_SPEC,
        "",
        "# 五、目录 → 角色的常见对应",
        "",
        "根据文件所在目录快速判断角色：",
        "",
        "| 目录 | 常见角色 |",
        "|---|---|",
        "| `diffusion_models/` | unet（少数是 videoVae / audioVae，看文件名） |",
        "| `unet/` | unet |",
        "| `text_encoders/` | encoder |",
        "| `clip/` | encoder |",
        "| `vae/` | vae / videoVae / audioVae（看文件名） |",
        "| `loras/` | lora |",
        "| `checkpoints/` | checkpoint |",
        "",
        "# 六、输出格式",
        "",
        _render_output_spec(registry_version),
        "",
        "# 七、完整示例",
        "",
        _render_example(),
        "",
        "# 八、强约束",
        "",
        CONSTRAINTS,
        "",
        "现在请分析上述目标并输出 JSON Patch。",
    ])

    return "\n".join(sections)


def _render_reference_models(known_models: list[dict]) -> str:
    """把已注册且已补全的模型按角色分组展示。
    只列 encoder / vae 系列——它们才是被 unet 引用的对象。
    lora / unet / checkpoint 不属于被引用对象，列出只会增加噪声。"""
    if not known_models:
        return "（当前没有已注册的参考模型）\n"

    allowed_roles = ("encoder", "vae", "videoVae", "audioVae")

    by_role: dict[str, list[dict]] = {}
    for m in known_models:
        if m.get("needsLlm"):
            continue
        role = m.get("role", "unknown")
        if role not in allowed_roles:
            continue
        by_role.setdefault(role, []).append(m)

    if not by_role:
        return "（当前没有可引用的 encoder / vae 参考模型）\n"

    lines = []
    for role in allowed_roles:
        items = by_role.get(role, [])
        if not items:
            continue

        lines.append(f"### {role}")
        lines.append("")
        lines.append("| 文件名 | 目录 | 架构标签 | 备注 |")
        lines.append("|---|---|---|---|")

        for m in items[:REFERENCE_LIMIT_PER_ROLE]:
            file_ = m["file"]
            dir_ = m["dir"]
            arch = m.get("arch") or "—"
            note_parts = []
            if m.get("encoderNodeParams", {}).get("type"):
                note_parts.append(f"type: {m['encoderNodeParams']['type']}")
            note = "; ".join(note_parts) if note_parts else "—"
            lines.append(f"| `{file_}` | `{dir_}/` | `{arch}` | {note} |")

        if len(items) > REFERENCE_LIMIT_PER_ROLE:
            lines.append(f"| …还有 {len(items) - REFERENCE_LIMIT_PER_ROLE} 个 | | | |")
        lines.append("")

    return "\n".join(lines)


def _render_new_targets(items: list[dict]) -> str:
    if not items:
        return "（无）\n"

    lines = []
    for i, m in enumerate(items, 1):
        lines.append(f"### A{i}. `{m['file']}`")
        lines.append(f"- 目录: `{m['dir']}/`")
        lines.append(f"- 大小: {_fmt_size(m.get('sizeBytes', 0))}")

        if m.get("arch"):
            conf = m.get("confidence", 0.0)
            lines.append(f"- 自动推断架构: `{m['arch']}` (置信度 {conf:.2f})")
        if m.get("role") and m["role"] != "unknown":
            lines.append(f"- 自动推断角色: `{m['role']}`")

        signals = m.get("signals") or []
        if signals:
            display = signals[:5]
            lines.append(f"- 推断依据: {', '.join('`' + s + '`' for s in display)}")

        meta = m.get("metadata") or {}
        if meta.get("_tensorCount"):
            lines.append(f"- tensor 数量: {meta['_tensorCount']}")
        if meta.get("_rawKeys"):
            keys = meta["_rawKeys"][:8]
            lines.append(f"- 头部元数据键: `{', '.join(keys)}`")
        for k, label in [
            ("baseModelVersion", "base_model_version"),
            ("networkModule", "ss_network_module"),
            ("loraRank", "LoRA rank"),
            ("modelspecArch", "modelspec 架构"),
            ("title", "标题"),
            ("triggerWord", "已有触发词"),
        ]:
            if meta.get(k):
                lines.append(f"- {label}: `{meta[k]}`")

        lines.append("- **请补全以下字段**: `arch`, `role`, 以及该 role 对应的所有字段")
        lines.append("")

    return "\n".join(lines)


def _render_incomplete_targets(items: list[dict]) -> str:
    if not items:
        return "（无）\n"

    lines = []
    for i, m in enumerate(items, 1):
        lines.append(f"### B{i}. `{m['file']}`")
        lines.append(f"- 目录: `{m['dir']}/`")
        lines.append(f"- 当前架构: `{m.get('arch') or '未确定'}`")
        lines.append(f"- 当前角色: `{m.get('role', 'unknown')}`")
        lines.append(f"- 当前 source: `{m.get('source', 'heuristic')}`")
        lines.append(f"- 当前置信度: {m.get('confidence', 0):.2f}")

        missing = m.get("missingFields") or []
        if missing:
            lines.append(f"- **需要补充的字段**: {', '.join(f'`{x}`' for x in missing)}")

        # 显示已有的字段（不要被 LLM 覆盖）。
        # 注意：0.0 / False / 空字符串不是"缺失"，只有 None 才是。空列表和空字典也算缺失。
        existing_fields = []
        for k in ("compatibleEncoders", "compatibleVaes", "compatibleLoras",
                  "encoderNodeParams", "triggerWord", "defaultWeight", "defaultParams"):
            if k not in m:
                continue
            v = m.get(k)
            if v is None:
                continue
            if v == "":
                continue
            if isinstance(v, (list, dict)) and len(v) == 0:
                continue
            existing_fields.append(
                f"    - `{k}` = `{json.dumps(v, ensure_ascii=False)}`"
            )
        if existing_fields:
            lines.append("- 已有字段（不要覆盖）:")
            lines.extend(existing_fields)

        lines.append("")

    return "\n".join(lines)
