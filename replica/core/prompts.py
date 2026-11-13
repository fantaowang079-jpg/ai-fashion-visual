"""提示词模板：服装分析、试穿、多角度、视频。

模板来自参考项目 shop-tryon-skill（MIT），做了结构化和少量可读性整理。
"""
from __future__ import annotations

# ── 服装分析 ──────────────────────────────────────────────
GARMENT_ANALYSIS_PROMPT = """\
你是一位专业的服装分析师。请仔细观察这张服装图片，输出以下信息：

1. **服装类型**：具体款式名称（如：圆领短袖T恤、A字半裙、连帽卫衣、西装外套等）
2. **服装分类**：上装 / 下装 / 全身（连衣裙/套装算全身）
3. **颜色与图案**：主色调、配色、是否有印花/条纹/纯色等
4. **面料质感**：看起来像什么材质（棉、涤纶、丝绸、牛仔、针织等）
5. **风格标签**：2~4 个风格关键词（如：休闲、正式、运动、甜美、街头、复古等）
6. **适合性别**：男装 / 女装 / 中性
7. **适合季节**：春夏 / 秋冬 / 四季
8. **适合场景**：日常通勤、约会、运动、正式场合等
9. **一句话描述**：用一句自然语言描述这件服装，适合直接作为 AI 生图的 prompt 输入

请用 JSON 格式输出，字段如下：
```json
{
  "type": "圆领短袖T恤",
  "category": "top",
  "color": "白色，胸前有蓝色几何印花",
  "fabric": "纯棉",
  "style": ["休闲", "街头", "日系"],
  "gender": "female",
  "season": "春夏",
  "occasion": "日常、逛街",
  "description": "白色纯棉短袖T恤，胸前饰有蓝色几何印花，版型宽松，日系休闲风格"
}
```

只输出 JSON，不要其他文字。"""

# ── 模特提示词 ────────────────────────────────────────────
MODEL_PROMPTS = {
    "asian_studio": (
        "Young Asian female, average figure, standing upright, arms slightly away from body, "
        "neutral expression, facing camera, full body head to toe, pure white studio background, "
        "soft even lighting, photorealistic, high resolution, no clothing"
    ),
    "western_studio": (
        "Young Caucasian female model, average figure, relaxed natural pose, full body visible, "
        "light gray seamless background, natural soft light, photorealistic, fashion photography, no clothing"
    ),
    "male_studio": (
        "Young Asian male model, average build, standing straight, arms relaxed at sides, "
        "neutral expression, facing camera, full body head to toe, pure white background, "
        "studio lighting, photorealistic, no clothing"
    ),
    "neutral_white": (
        "Female model, average figure, standing straight, arms relaxed at sides, pure white background, "
        "even studio lighting, full body, photorealistic, no clothing, neutral expression, facing forward"
    ),
}

# ── 一致性 / 方向 ─────────────────────────────────────────
CONSISTENCY = (
    "consistent outfit styling, same shoes and accessories throughout, "
    "same hairstyle, no random changes to appearance, "
    "photorealistic e-commerce fashion photography, "
    "clean white or light gray studio background, bright even studio lighting, "
    "absolutely no black background, no dark background, no shadowy environment, "
)

ORIENT = {
    "portrait": "vertical portrait, 9:16 aspect ratio, full body visible head to toe, clean bright background,",
    "tryon": (
        "vertical full body portrait, 9:16 aspect ratio, complete outfit visible from head to toe, "
        "clean white studio background, bright even lighting, no dark or black background,"
    ),
    "garment": "square flat lay product photo, 1:1 aspect ratio, pure white background, bright even lighting,",
    "landscape": "horizontal wide shot, 16:9 aspect ratio, bright clean background,",
}

# ── 服装部位锁定前缀 ──────────────────────────────────────
GARMENT_LOCK = {
    "top": (
        "Using reference image 1 (model) and reference image 2 (top garment): "
        "dress the model from image 1 in the EXACT top/upper-body garment shown in image 2. "
        "Preserve every detail of image 2 — color, cut, neckline, sleeves, fabric texture, "
        "collar, cuffs, and any logos or prints. "
        "Keep the model's original lower-body clothing (pants/skirt/shoes) unchanged. "
        "Do NOT replace or alter the garment. "
    ),
    "bottom": (
        "Using reference image 1 (model) and reference image 2 (bottom garment): "
        "dress the model from image 1 in the EXACT bottom garment shown in image 2. "
        "Preserve every detail of image 2 — color, cut, length, waistband, fabric texture, "
        "pleats, and any patterns or prints. "
        "Keep the model's original upper-body clothing and accessories unchanged. "
        "Do NOT replace or alter the garment. "
    ),
    "one_piece": (
        "Using reference image 1 (model) and reference image 2 (one-piece garment): "
        "dress the model from image 1 in the EXACT one-piece garment shown in image 2. "
        "Preserve every detail of image 2 — color, cut, neckline, hemline, fabric texture, "
        "and any patterns, prints, or embellishments. "
        "Do NOT replace or alter the garment. "
    ),
    "full": (
        "Using reference image 1 (model) and reference image 2 (full outfit): "
        "dress the model from image 1 in the EXACT complete outfit shown in image 2. "
        "Preserve every detail of both upper and lower garments in image 2 — colors, cuts, "
        "fabric textures, and any logos, patterns, or prints. "
        "Do NOT replace or alter any part of the outfit. "
    ),
}

# ── 服装部位描述 ──────────────────────────────────────────
GARMENT_PART_PROMPTS = {
    "top": (
        "穿着这件上装（衬衫/外套/T恤/卫衣等）在上半身，服装自然垂合，"
        "下半身搭配中性色修身长裤，上装细节（领口/袖口/版型）清晰可见，"
        "全身可见从头到脚。"
        " | Wearing this TOP garment on upper body with natural drape and fit, "
        "paired with neutral pants on lower body, full body head to toe."
    ),
    "bottom": (
        "穿着这件下装（裤子/半裙/短裙/阔腿裤等）在下半身，服装自然垂合，"
        "上半身搭配简约白色T恤，下装细节（裤腿/裙摆/腰线）清晰可见，"
        "全身可见从头到脚。"
        " | Wearing this BOTTOM garment on lower body with natural drape and fit, "
        "paired with plain white t-shirt on top, full body head to toe."
    ),
    "full": (
        "穿着完整上下装套装：上装在上半身，下装在下半身，"
        "上下搭配自然协调，整体轮廓清晰，全身可见从头到脚。"
        " | Wearing COMPLETE OUTFIT: top garment on upper body, "
        "bottom garment on lower body, perfectly coordinated, full body head to toe."
    ),
    "one_piece": (
        "穿着这件单件连体服装（连衣裙/连体裤/长裙/连体短裙等），"
        "服装从肩部延伸至膝盖或脚踝，整件服装轮廓和细节（裙摆/腰线/领口）完整清晰，"
        "全身可见从头到脚。"
        " | Wearing this ONE-PIECE garment (dress/jumpsuit/romper/maxi-skirt), "
        "flowing from shoulders to knees/ankles, "
        "full silhouette and garment details visible, full body head to toe."
    ),
}


def build_tryon_prompt(garment_desc: str = "", part: str = "top") -> str:
    """参考项目 tryon_runner._build_tryon_prompt 的等价实现。"""
    part_text = GARMENT_PART_PROMPTS.get(part, GARMENT_PART_PROMPTS["top"])
    desc_note = f"服装描述：{garment_desc}。" if garment_desc else ""
    return (
        "使用参考图1（模特）和参考图2（服装），创建一张超现实的全身时尚照片。"
        f"{desc_note}"
        f"试穿部位：{part_text}"
        "关键要求：服装必须自然地垂在模特身上，贴合其姿势并产生逼真的褶皱；"
        "极其精确地保留服装的原始面料质感、颜色和任何标志；"
        "通过完美匹配环境光、色温和阴影方向，将服装融入模特照片中。"
        "摄影风格：干净的电商产品画册（Lookbook）风格，"
        "使用佳能EOS R5相机和50mm f/1.8镜头拍摄，呈现自然、专业的外观。"
        "背景：纯白色或浅灰色摄影棚，均匀柔和的打光，绝对不要黑色或深色背景。"
        "full body head to toe, 9:16 vertical portrait, white studio background, "
        "bright and clean lighting, no dark or black background."
    )


# ── 多角度预设 ────────────────────────────────────────────
ANGLE_PRESETS = {
    "ecommerce": {
        "name": "电商标准拍",
        "desc": "正面+侧面+背面，适合电商主图和详情页",
        "angles": [
            {"label": "front", "scene": "正面站立",
             "suffix": "front view, facing camera directly, standing straight, full body"},
            {"label": "side", "scene": "侧面展示",
             "suffix": "three-quarter side view, slight turn right, natural standing pose, full body"},
            {"label": "back", "scene": "背面转身",
             "suffix": "back view, model looking over left shoulder toward camera, full body"},
        ],
    },
    "catwalk": {
        "name": "走秀动态",
        "desc": "行走+转身+定点pose，适合视频素材",
        "angles": [
            {"label": "walking", "scene": "T台行走",
             "suffix": "confident catwalk stride, full body, fashion runway lighting"},
            {"label": "turn", "scene": "转身回眸",
             "suffix": "turning around, looking over shoulder, elegant pose, full body"},
            {"label": "pose", "scene": "定点造型",
             "suffix": "fashion editorial pose, hand on hip, slight hip tilt, full body"},
        ],
    },
    "detail": {
        "name": "细节特写",
        "desc": "面料+领口+全身，适合展示工艺细节",
        "angles": [
            {"label": "fabric", "scene": "面料特写",
             "suffix": "close-up on fabric texture and material detail, upper body"},
            {"label": "collar", "scene": "领口细节",
             "suffix": "upper body close-up, showing collar, neckline, and stitching details"},
            {"label": "full", "scene": "全身正面",
             "suffix": "front view, full body head to toe, showing complete outfit details"},
        ],
    },
    "lifestyle": {
        "name": "生活场景",
        "desc": "自然姿态+坐姿+行走，呈现日常穿搭感",
        "angles": [
            {"label": "casual", "scene": "自然站立",
             "suffix": "relaxed natural standing pose, slight smile, full body"},
            {"label": "sitting", "scene": "坐姿展示",
             "suffix": "seated pose on stool, legs crossed, showing outfit drape, full body visible"},
            {"label": "walking", "scene": "街头漫步",
             "suffix": "casual walking pose, natural stride, full body"},
        ],
    },
}


def build_angle_prompt(part: str, angle_suffix: str, base_desc: str = "") -> str:
    """多角度 prompt：服装锁定 + 人物锁定 + 角度差异。"""
    lock = GARMENT_LOCK.get(part, GARMENT_LOCK["top"])
    desc = f"{base_desc}, " if base_desc else ""
    return (
        f"{lock}"
        "Keep exactly the same model face, hairstyle, clothing, shoes, "
        "and accessories as the reference images. "
        "Do not add or remove any clothing items or accessories. "
        f"{desc}{angle_suffix}. "
        "Photorealistic, e-commerce fashion photography, "
        "9:16 vertical portrait, full body head to toe, "
        "consistent styling throughout."
    )


# ── AI 换装 / 指令编辑 ────────────────────────────────────
RESTYLE_GUARD = (
    "严格保持人物的面部、发型、姿势、体型和背景完全不变；"
    "只修改服装区域，新服装必须自然贴合身体并产生真实褶皱；"
    "准确还原新服装的版型、颜色、图案和面料质感；"
    "保持原图的光线方向、色温和画质；"
    "不要添加文字、logo、水印，不要改变人物肤色和表情。"
)

RESTYLE_PART_CN = {
    "top": "上装",
    "bottom": "下装",
    "one_piece": "连衣裙或连体装",
    "full": "整套上下装",
}


def build_tryon_edit_prompt(part: str = "top", desc: str = "") -> str:
    """通用图像编辑试衣：人物图 + 服装图直接换装。"""
    desc_text = (desc or "").strip()
    if part == "full":
        head = (
            "图1是人物照片，图2是上装，图3是下装。"
            "请让图1中的人物穿上图2的上装和图3的下装，"
            "仔细还原两件服装的颜色、版型、领口、袖型、长度、图案和面料质感，"
            "服装需自然垂合在人物身上，符合其姿势和体型。"
        )
    else:
        part_cn = RESTYLE_PART_CN.get(part, RESTYLE_PART_CN["top"])
        head = (
            f"图1是人物照片，图2是目标{part_cn}。"
            f"请让图1中的人物穿上图2中的{part_cn}，"
            "仔细还原目标服装的颜色、版型、领口、袖型、长度、图案和面料质感，"
            "服装需自然垂合在人物身上，符合其姿势和体型。"
        )
    if desc_text:
        head += f"服装参考描述：{desc_text}。"
    return head + RESTYLE_GUARD


def build_restyle_prompt(
    instruction: str = "",
    part: str = "top",
    has_garment_reference: bool = False,
    garment_ref_index: int = 2,
) -> str:
    """换装提示词：固定保护前缀 + 用户指令 / 目标服装图说明。

    两种模式：
    - 指令换装：直接描述要换成什么（换色、换款、加外套、换场景）。
    - 参考服装换衣：图1 人物 + 图N 目标服装，要求精准还原服装细节。
    """
    part_cn = RESTYLE_PART_CN.get(part, RESTYLE_PART_CN["top"])
    instruction = (instruction or "").strip()

    if has_garment_reference:
        head = (
            f"图1是人物照片，图{garment_ref_index}是目标{part_cn}。"
            f"请让图1中的人物穿上图{garment_ref_index}中的{part_cn}，"
            "仔细还原目标服装的颜色、版型、领口、袖型、长度、图案和面料质感，"
            "服装需自然垂合在人物身上，符合其姿势和体型。"
        )
        if instruction:
            head += f"补充要求：{instruction}。"
        return head + RESTYLE_GUARD

    if not instruction:
        raise ValueError("指令换装需要提供 instruction，或提供目标服装图")
    return f"按照以下指令修改图1中人物的服装：{instruction}。{RESTYLE_GUARD}"


# ── 视频 ─────────────────────────────────────────────────
VIDEO_FULL_BODY_LOCK = (
    "full body always visible from head to toe throughout entire video, "
    "model centered in frame with 10% margin top and bottom, "
    "camera stays wide and fixed, absolutely no zoom in, no close-up, no cropping, "
    "camera only pans slowly or stays static, "
    "9:16 vertical format maintained throughout, "
    "smooth natural human motion only, physically realistic movement, "
    "head and body rotate naturally in clockwise direction only, "
    "never reversed or counterclockwise head rotation, "
    "no unnatural body distortion, no impossible physics, "
    "clean white or light studio background, no black or dark background, "
    "clothing details clearly visible at all times, consistent outfit throughout. "
    "全身始终完整可见从头到脚，相机保持广角固定，禁止推近和特写，"
    "仅允许轻微平移或静止，9:16竖版比例全程保持，"
    "人物动作必须符合真实物理规律，头部和身体只允许自然方向转动，"
    "禁止逆时针旋转头部等违反物理的动作，"
    "背景保持明亮干净，禁止黑色或深色背景，服装细节清晰可见。"
)


def build_wan_video_prompt(garment_desc: str = "服装") -> str:
    """百炼万相图生视频的简短中文提示词。"""
    return (
        f"模特穿着{garment_desc}自然缓慢转身，展示服装正面与侧面，"
        "全身始终完整出现在画面中，镜头稳定不推近，背景明亮干净，"
        "动作符合真实物理规律，服装细节清晰，画面连贯自然。"
    )


def build_video_prompt(garment_desc: str = "服装", multi: bool = False) -> str:
    if multi:
        return (
            VIDEO_FULL_BODY_LOCK
            + f"Show the same {garment_desc} outfit in different scenes. "
            "Create a smooth fashion showcase video transitioning between scenes. "
            "Each scene shows full body from head to toe. "
            "No zoom in, camera stays wide at all times. "
            "Bright clean background, physically natural motion only."
        )
    return (
        VIDEO_FULL_BODY_LOCK
        + f"model wearing {garment_desc}, "
        "slowly turns clockwise to show front and side, smooth natural catwalk movement, "
        "professional fashion showcase, static or very slight camera pan only, "
        "bright clean studio background, physically natural human motion"
    )
