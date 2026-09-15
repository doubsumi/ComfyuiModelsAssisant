"""
内置提示词模板
=============
每个模板针对某个图谱的 category + 场景。
id 以 builtin: 前缀标识，与用户模板区分。
"""


BUILTIN_TEMPLATES = [
    # ============== 文生图：Krea2 ==============
    {
        "id": "builtin:krea2_t2i:ink_wash",
        "ecosystemId": "krea2_t2i",
        "name": "国漫·水墨仙侠",
        "builtin": True,
        "tags": ["水墨", "仙侠", "国风"],
        "positive": (
            "Chinese ink wash painting style, xianxia anime, elegant composition, "
            "flowing ink brush strokes, misty mountain background, a young cultivator "
            "in white hanfu with long flowing hair, standing on a cliff, serene "
            "expression, soft rim light, muted palette of ink black, ash purple and "
            "pale blue, masterpiece, best quality, ultra detailed"
        ),
        "negative": (
            "photorealistic, western style, 3d render, plastic texture, ugly, "
            "deformed, blurry, low quality, watermark, text, signature"
        ),
        "notes": "适合仙侠、修行、山水场景。构图偏纵向，建议 1024×1280 或 832×1216。",
    },
    {
        "id": "builtin:krea2_t2i:gongbi",
        "ecosystemId": "krea2_t2i",
        "name": "国漫·工笔人物",
        "builtin": True,
        "tags": ["工笔", "人物", "国风"],
        "positive": (
            "Traditional Chinese gongbi painting style, detailed brush strokes, "
            "a beautiful young woman in elaborate hanfu, ornate gold hairpins, "
            "delicate floral patterns on silk, gentle makeup, half-lidded eyes, "
            "cream and jade-green palette, soft diffused lighting, masterpiece, "
            "best quality, ultra detailed, 8k"
        ),
        "negative": (
            "western style, anime, cartoon, plastic, glossy, deformed, blurry, "
            "low quality, watermark, text"
        ),
        "notes": "工笔人物特写。建议 832×1216 或 1024×1024。",
    },
    {
        "id": "builtin:krea2_t2i:storyboard",
        "ecosystemId": "krea2_t2i",
        "name": "国漫·分镜场景",
        "builtin": True,
        "tags": ["分镜", "场景", "国风"],
        "positive": (
            "Chinese animation storyboard panel, cinematic composition, wide shot, "
            "ancient bamboo forest with sunlight beams through leaves, a lone "
            "swordsman walking on a stone path, misty atmosphere, muted green and "
            "golden palette, painterly style, masterpiece, high quality"
        ),
        "negative": (
            "photorealistic, western, 3d, plastic, text, watermark, logo, "
            "signature, low quality"
        ),
        "notes": "适合短片分镜/场景设定图。建议 1344×768 宽屏。",
    },

    # ============== 视频：MiniMax H3 fl2va ==============
    {
        "id": "builtin:minimax_h3_fl2va:action",
        "ecosystemId": "minimax_h3_fl2va",
        "name": "国漫·打斗镜头",
        "builtin": True,
        "tags": ["动作", "打斗", "仙侠"],
        "positive": (
            "Chinese ink wash xianxia animation. 2.5D guofeng aesthetic, ink brush "
            "texture, muted palette of ink black, ash purple, dark indigo. "
            "A young cultivator in flowing white robes leaps through the air, "
            "sword energy trailing pink light, robes fluttering in the wind, "
            "particles of ink mist swirling, dynamic diagonal composition. "
            "Hard cuts only, no dissolves. Audio: wind whoosh, sword hum, "
            "low taiko drum accents on each strike."
        ),
        "negative": "",
        "videoPrompt": "",
        "notes": "建议 5-8 秒，1344×768。提示词里写清时间轴和镜头切换点。",
    },
    {
        "id": "builtin:minimax_h3_fl2va:emotion",
        "ecosystemId": "minimax_h3_fl2va",
        "name": "国漫·情绪特写",
        "builtin": True,
        "tags": ["情绪", "特写", "人物"],
        "positive": (
            "Chinese ink wash animation, 2.5D guofeng aesthetic, close-up portrait "
            "shot. A young woman in pale blue hanfu looks at the camera with "
            "restrained emotion, a single tear forms at the corner of her eye, "
            "hair strands gently moving in the breeze, background is a soft "
            "blurred landscape of misty mountains. Slow subtle camera push-in. "
            "Audio: quiet wind, faint distant guqin note."
        ),
        "negative": "",
        "videoPrompt": "",
        "notes": "建议 3-5 秒，768×1344 竖版或 1024×1024。情绪片段的节奏要慢。",
    },
    {
        "id": "builtin:minimax_h3_fl2va:scene",
        "ecosystemId": "minimax_h3_fl2va",
        "name": "国漫·场景空镜",
        "builtin": True,
        "tags": ["场景", "空镜", "环境"],
        "positive": (
            "Chinese ink wash animation, wide establishing shot. A misty valley at "
            "dawn, floating mountains in the distance, ancient pine trees with "
            "gnarled branches, a narrow stone bridge crossing a river of clouds, "
            "warm morning light filtering through mist. Slow camera drift. "
            "Audio: wind, distant birdsong, soft ambient drone."
        ),
        "negative": "",
        "videoPrompt": "",
        "notes": "适合做短片转场或环境铺垫。建议 4-6 秒，1344×768。",
    },
]


def get_builtin_templates(ecosystem_id: str | None = None) -> list[dict]:
    if ecosystem_id:
        return [t for t in BUILTIN_TEMPLATES if t.get("ecosystemId") == ecosystem_id]
    return list(BUILTIN_TEMPLATES)