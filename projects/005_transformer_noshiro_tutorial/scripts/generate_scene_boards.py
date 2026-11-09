#!/usr/bin/env python3
"""Custom High-Tech Holographic Whiteboard Generator for 9 Scenes (Clean Typography).

Generates 1920x1080 scene slides with:
- Noshiro character in her studio pose on the left (composited in front of board)
- Glowing cyber-holographic whiteboard on the right (x: 835 to 1815, y: 40 to 665)
- Custom crisp diagrams, badges, formulas, matrix heatmaps for each of the 9 scenes.
- Clean RGBA transparent whiteboard overlays (board_overlay_1.png .. board_overlay_9.png)
  for compositing over 60FPS AI-generated Noshiro teaching videos.
- 100% pure standard ASCII + CJK characters (Zero square box glyph failures).
"""

import math
from pathlib import Path
from PIL import Image, ImageDraw, ImageFilter, ImageFont

SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR.parent

FONT_BOLD = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
FONT_REG = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"

WB_BOX = [835, 40, 1815, 665]


def get_font(size: int, bold: bool = True):
    path = FONT_BOLD if bold else FONT_REG
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()


def draw_badge(d, xy, text, bg_color, border_color, text_color=(255, 255, 255), font_size=16):
    font = get_font(font_size, True)
    bbox = font.getbbox(text)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    pad_x, pad_y = 12, 5
    x1, y1 = xy[0], xy[1]
    x2, y2 = x1 + tw + pad_x * 2, y1 + th + pad_y * 2
    d.rounded_rectangle([x1, y1, x2, y2], radius=6, fill=bg_color, outline=border_color, width=2)
    d.text((x1 + pad_x, y1 + pad_y - 2), text, font=font, fill=text_color)
    return x2, y2


def draw_card(d, bbox, fill_color, border_color, radius=8, width=1):
    d.rounded_rectangle(bbox, radius=radius, fill=fill_color, outline=border_color, width=width)


def prepare_whiteboard_canvas(base_img: Image.Image) -> Image.Image:
    """Creates base image with fresh glowing holographic glass canvas covering the full board."""
    canvas = base_img.copy()
    # Blur underlying whiteboard region so zero ghost text from scene_cover.jpg bleeds through
    x1, y1, x2, y2 = WB_BOX
    blurred_sub = canvas.crop((x1, y1, x2, y2)).filter(ImageFilter.GaussianBlur(radius=22))
    canvas.paste(blurred_sub, (x1, y1))

    overlay = Image.new("RGBA", canvas.size, (0, 0, 0, 0))
    od = ImageDraw.Draw(overlay)

    # Full holographic glass area: x from 835 to 1815, y from 40 to 665
    od.rounded_rectangle(WB_BOX, radius=12, fill=(12, 28, 42, 246), outline=(50, 200, 240, 250), width=3)
    od.rounded_rectangle(
        [WB_BOX[0] + 4, WB_BOX[1] + 4, WB_BOX[2] - 4, WB_BOX[3] - 4],
        radius=10,
        fill=None,
        outline=(30, 140, 180, 140),
        width=1,
    )

    canvas.paste(overlay, (0, 0), overlay)
    return canvas


def extract_board_overlay(scene_img_no_fg: Image.Image) -> Image.Image:
    """Extracts a 1920x1080 RGBA overlay containing only the holographic whiteboard [835, 40, 1815, 665]."""
    rgba = scene_img_no_fg.convert("RGBA")
    mask = Image.new("L", rgba.size, 0)
    md = ImageDraw.Draw(mask)
    md.rounded_rectangle(WB_BOX, radius=12, fill=248)
    out = Image.new("RGBA", rgba.size, (0, 0, 0, 0))
    out.paste(rgba, (0, 0), mask)
    return out


def composite_noshiro_foreground(canvas: Image.Image, cutout: Image.Image) -> Image.Image:
    """Overlays Noshiro character so her arm and laser pointer sit in front of the board."""
    target_h = 1080
    target_w = int(cutout.width * (target_h / cutout.height))
    resized_cutout = cutout.resize((target_w, target_h), Image.Resampling.LANCZOS)
    canvas.paste(resized_cutout, (384, 0), resized_cutout)
    return canvas


def render_scene_1(base_img: Image.Image) -> Image.Image:
    img = prepare_whiteboard_canvas(base_img)
    d = ImageDraw.Draw(img)

    # Header
    draw_badge(d, (935, 68), "架构演进", (180, 40, 40, 240), (255, 90, 90), font_size=15)
    d.text((1040, 65), "传统循环网络 (RNN) 瓶颈 vs Transformer", font=get_font(23, True), fill=(255, 255, 255))

    # Card 1: RNN Sequential Chain
    draw_card(d, [935, 118, 1775, 285], (20, 38, 55, 200), (40, 100, 140), radius=8)
    d.text((960, 134), "传统 RNN/LSTM 单向串行链条 (Sequential Dependency)", font=get_font(17, True), fill=(240, 180, 80))

    # Step blocks
    tokens = ["x1", "x2", "x3", "x4", "x_T"]
    for i, tok in enumerate(tokens):
        bx = 965 + i * 155
        by = 175
        draw_card(d, [bx, by, bx + 108, by + 48], (30, 60, 85), (60, 150, 200), radius=6)
        d.text((bx + 36, by + 12), f"h{i+1}", font=get_font(18, True), fill=(100, 230, 255))
        d.text((bx + 38, by + 54), tok, font=get_font(15, True), fill=(200, 200, 200))
        if i < len(tokens) - 1:
            d.line([(bx + 113, by + 24), (bx + 150, by + 24)], fill=(255, 100, 100), width=3)
            d.polygon([(bx + 150, by + 24), (bx + 142, by + 19), (bx + 142, by + 29)], fill=(255, 100, 100))

    d.text((960, 250), "[!] 串行排队: 时间复杂度 O(N)，完全无法发挥 GPU 千核并行优势！", font=get_font(15, True), fill=(255, 120, 120))

    # Card 2: Pain Points & Solution
    draw_card(d, [935, 300, 1775, 462], (35, 25, 30, 200), (160, 60, 60), radius=8)
    d.text((960, 315), "致命痛点: 长距离信息衰减 (Vanishing Gradient & Forgetting)", font=get_font(17, True), fill=(255, 110, 110))
    d.text((960, 350), "• 单词经过数十步递归传递后，开头的关键主语与语义记忆彻底被稀释丢失", font=get_font(15, False), fill=(230, 230, 230))
    d.text((960, 382), "• 梯度在反向传播时连续矩阵相乘，产生指数级梯度消失，无法支持长文本", font=get_font(15, False), fill=(230, 230, 230))
    d.text((960, 414), "• 无法处理十万、百万级 Token 上下文！", font=get_font(15, True), fill=(255, 160, 160))

    # Card 3: Transformer Revolution
    draw_card(d, [935, 480, 1775, 638], (20, 50, 40, 220), (50, 200, 120), radius=8)
    d.text((960, 496), "[>] Transformer 颠覆破局: 全对称自注意力 (Self-Attention)", font=get_font(19, True), fill=(100, 255, 180))
    d.text((960, 538), "[OK] 任意两词之间路径跨度始终为 O(1)，一眼纵览全篇！", font=get_font(16, True), fill=(255, 255, 255))
    d.text((960, 575), "[OK] 全部 Token 并行矩阵计算，彻底引爆千卡集群算力！", font=get_font(16, True), fill=(255, 255, 255))

    return img


def render_scene_2(base_img: Image.Image) -> Image.Image:
    img = prepare_whiteboard_canvas(base_img)
    d = ImageDraw.Draw(img)

    # Header
    draw_badge(d, (935, 68), "数据底座", (30, 100, 160), (80, 180, 255), font_size=15)
    d.text((1040, 65), "Tokenization 与 4096 维 高维词嵌入 (Embedding)", font=get_font(23, True), fill=(255, 255, 255))

    # Step 1: Text to Tokens
    draw_card(d, [935, 118, 1775, 268], (20, 40, 60, 200), (60, 140, 200), radius=8)
    d.text((960, 134), "Step 1: 文本切分为 Token (BPE / Byte-Pair Encoding)", font=get_font(17, True), fill=(120, 220, 255))

    tokens_text = [("Attention", 1532), (" Is", 318), (" All", 2039), (" You", 499), (" Need", 1421)]
    for i, (wrd, tid) in enumerate(tokens_text):
        bx = 960 + i * 156
        by = 176
        draw_card(d, [bx, by, bx + 135, by + 62], (30, 65, 95), (80, 170, 220), radius=6)
        d.text((bx + 18, by + 10), wrd, font=get_font(17, True), fill=(255, 255, 255))
        d.text((bx + 25, by + 35), f"ID: {tid}", font=get_font(13, True), fill=(255, 200, 80))

    # Step 2: Embedding Matrix
    draw_card(d, [935, 286, 1775, 455], (25, 45, 70, 200), (80, 160, 220), radius=8)
    d.text((960, 302), "Step 2: 查表映射为稠密向量 (Word Embedding Lookup)", font=get_font(17, True), fill=(120, 220, 255))
    d.text((960, 342), "W_E in R^{Vocab x d_model}   (词表大小 V ≈ 128,000, 向量维度 d = 4096)", font=get_font(17, True), fill=(255, 220, 100))
    d.text((960, 378), "每个 Token ID 对应矩阵的一行，转化为 4096 个浮点数空间坐标！", font=get_font(15, False), fill=(220, 240, 255))
    d.text((960, 410), "例如: Token(1532) -> [ 0.042, -0.128, 0.891, ..., 0.015 ] in R^4096", font=get_font(15, True), fill=(160, 255, 180))

    # Step 3: Vector Space Geometry
    draw_card(d, [935, 474, 1775, 638], (20, 55, 45, 200), (60, 180, 130), radius=8)
    d.text((960, 490), "高维几何宇宙的魔法: 语义越相近，向量余弦距离越近", font=get_font(17, True), fill=(100, 255, 180))
    d.text((960, 532), "[*] 经典语义向量算术:   Vector(King) - Vector(Man) + Vector(Woman) ≈ Vector(Queen)", font=get_font(16, True), fill=(255, 255, 255))
    d.text((960, 574), "[*] 几何聚类: 计算机虽然不懂人类概念，但通过空间距离完美理解词义关联！", font=get_font(15, False), fill=(220, 240, 255))

    return img


def render_scene_3(base_img: Image.Image) -> Image.Image:
    img = prepare_whiteboard_canvas(base_img)
    d = ImageDraw.Draw(img)

    # Header
    draw_badge(d, (935, 68), "时序注入", (140, 50, 160), (220, 100, 255), font_size=15)
    d.text((1040, 65), "时空暗号: 正弦位置编码 与 旋转编码 (RoPE)", font=get_font(23, True), fill=(255, 255, 255))

    # Card 1: The Problem
    draw_card(d, [935, 118, 1775, 248], (35, 30, 55, 200), (100, 80, 160), radius=8)
    d.text((960, 134), "核心挑战: 自注意力机制具有完全排列不变性 (Permutation Invariance)", font=get_font(17, True), fill=(255, 180, 100))
    d.text((960, 170), "如果打乱词序: 『猫吃鱼』 与 『鱼吃猫』 产生的注意力权重完全相同！", font=get_font(16, True), fill=(255, 120, 120))
    d.text((960, 202), "必须主动向模型注入显式的顺序信息，这就是『位置编码 (Positional Encoding)』！", font=get_font(15, False), fill=(220, 220, 240))

    # Card 2: Sinusoidal Positional Encoding
    draw_card(d, [935, 264, 1775, 432], (25, 45, 75, 200), (70, 140, 220), radius=8)
    d.text((960, 280), "经典方案: 正弦余弦三角函数编码 (Vaswani et al., 2017)", font=get_font(17, True), fill=(100, 220, 255))
    d.text((960, 315), "PE(pos, 2i)   = sin( pos / 10000^{2i / d_model} )", font=get_font(17, True), fill=(255, 220, 80))
    d.text((960, 345), "PE(pos, 2i+1) = cos( pos / 10000^{2i / d_model} )", font=get_font(17, True), fill=(255, 220, 80))

    # Wave points
    for x_step in range(0, 680, 8):
        y_val1 = int(25 * math.sin(x_step * 0.08))
        y_val2 = int(25 * math.cos(x_step * 0.08))
        d.point((960 + x_step, 400 + y_val1), fill=(100, 230, 255))
        d.point((960 + x_step, 400 + y_val2), fill=(255, 200, 80))
    d.text((1580, 390), "周期波形叠加", font=get_font(13, True), fill=(200, 200, 200))

    # Card 3: Modern RoPE
    draw_card(d, [935, 450, 1775, 638], (20, 50, 45, 200), (50, 180, 140), radius=8)
    d.text((960, 466), "现代大模型标配: 旋转位置编码 (RoPE / Rotary Position Embedding)", font=get_font(17, True), fill=(100, 255, 180))
    d.text((960, 502), "q_m = R_m * (W_q * x_m) ,    k_n = R_n * (W_k * x_n)", font=get_font(17, True), fill=(255, 255, 255))
    d.text((960, 542), "[OK] 通过复数平面旋转向量，点积 <q_m, k_n> 极其自然地蕴含相对距离 (m - n)！", font=get_font(15, True), fill=(160, 255, 200))
    d.text((960, 578), "[OK] LLaMA, DeepSeek, Qwen 全面采用，外推性更强、长文本外推天花板！", font=get_font(15, False), fill=(220, 240, 255))

    return img


def render_scene_4(base_img: Image.Image) -> Image.Image:
    img = prepare_whiteboard_canvas(base_img)
    d = ImageDraw.Draw(img)

    # Header
    draw_badge(d, (935, 68), "核心心脏", (200, 120, 20), (255, 180, 40), font_size=15)
    d.text((1040, 65), "自注意力机制核心: 缩放点积注意力 (Q, K, V)", font=get_font(23, True), fill=(255, 255, 255))

    # Iconic Formula Card
    draw_card(d, [935, 118, 1775, 232], (20, 45, 70, 220), (60, 160, 240), radius=8)
    d.text((960, 134), "[*] 改变整个人工智能历史的公式 (Attention Is All You Need):", font=get_font(15, True), fill=(140, 220, 255))
    d.text((1050, 166), "Attention(Q, K, V) = Softmax(  Q * K^T  /  sqrt(d_k)  ) * V", font=get_font(23, True), fill=(255, 225, 80))

    # The 3 Pillars (Q, K, V) - Clean 2-line wrapped descriptions inside 268px cards
    qkv_data = [
        ("Query (Q) 寻宝雷达", "当前 Token 想要寻找什么样的\n上下文信息？", (30, 60, 90), (60, 150, 220), (100, 220, 255)),
        ("Key (K) 宝藏标签", "其他每个 Token 拥有什么关键\n属性与特征？", (50, 35, 80), (130, 80, 200), (220, 150, 255)),
        ("Value (V) 宝物真身", "一旦相关度匹配成功，真正提取\n的语义内容。", (20, 60, 50), (40, 160, 100), (120, 255, 180)),
    ]
    for i, (title, desc, bg, bdr, tc) in enumerate(qkv_data):
        bx = 935 + i * 286
        by = 248
        draw_card(d, [bx, by, bx + 268, by + 172], bg, bdr, radius=8)
        d.text((bx + 18, by + 18), title, font=get_font(17, True), fill=tc)
        d.multiline_text((bx + 18, by + 62), desc, font=get_font(15, False), fill=(225, 235, 245), spacing=10)

    # Step by step execution
    draw_card(d, [935, 438, 1775, 638], (20, 35, 55, 200), (40, 120, 180), radius=8)
    d.text((960, 455), "计算三步曲 (Step-by-Step Mechanism):", font=get_font(17, True), fill=(255, 210, 80))
    d.text((960, 495), "1. 点积算相似: Q * K^T 计算每对词之间的语义匹配度得分 (内积相似度)", font=get_font(15, False), fill=(255, 255, 255))
    d.text((960, 532), "2. 缩放与归一: 除以 sqrt(d_k) 防止点积过大，Softmax 转化为注意力概率权重", font=get_font(15, False), fill=(255, 255, 255))
    d.text((960, 569), "3. 加权提真身: 乘以 V 矩阵加权求和，输出汇聚全篇焦点的动态上下文向量！", font=get_font(15, True), fill=(100, 255, 180))

    return img


def render_scene_5(base_img: Image.Image) -> Image.Image:
    img = prepare_whiteboard_canvas(base_img)
    d = ImageDraw.Draw(img)

    # Header
    draw_badge(d, (935, 68), "兼听则明", (30, 130, 160), (60, 220, 255), font_size=15)
    d.text((1040, 65), "多头注意力机制 (Multi-Head Attention)", font=get_font(23, True), fill=(255, 255, 255))

    # Card 1: Why Multi-Head?
    draw_card(d, [935, 118, 1775, 238], (20, 40, 65, 200), (50, 130, 200), radius=8)
    d.text((960, 134), "为什么单个注意力头远远不够？", font=get_font(17, True), fill=(255, 190, 80))
    d.text((960, 170), "• 语言具有多维复杂性: 同一个词在语法结构、代词指代、逻辑因果、情感色彩中角色完全不同！", font=get_font(15, False), fill=(230, 240, 255))
    d.text((960, 202), "• 单头注意力会被单一最大权重主导，导致『一叶障目』，无法兼顾立体语义！", font=get_font(15, True), fill=(255, 130, 130))

    # Card 2: 8 Parallel Heads breakdown
    draw_card(d, [935, 254, 1775, 480], (25, 45, 75, 200), (80, 150, 220), radius=8)
    d.text((960, 270), "8 ~ 32 个并行注意力头 (Parallel Representation Subspaces):", font=get_font(17, True), fill=(120, 230, 255))

    heads = [
        ("Head 1", "句法主谓宾骨架", (40, 80, 130)),
        ("Head 2", "代词指代 (it->dog)", (70, 50, 120)),
        ("Head 3", "因果逻辑修饰", (30, 90, 80)),
        ("Head 4", "专有名词与实体", (110, 70, 40)),
        ("Head 5", "长程语义关联", (40, 100, 110)),
        ("Head 6", "动宾搭配锁定", (80, 60, 100)),
        ("Head 7", "时态与语气感知", (60, 90, 50)),
        ("Head 8", "情感与风格色彩", (100, 50, 80)),
    ]
    for i, (h_name, h_desc, c) in enumerate(heads):
        row = i // 4
        col = i % 4
        bx = 960 + col * 198
        by = 310 + row * 75
        draw_card(d, [bx, by, bx + 186, by + 65], c, (100, 180, 240), radius=6)
        d.text((bx + 14, by + 10), h_name, font=get_font(16, True), fill=(255, 220, 80))
        d.text((bx + 14, by + 35), h_desc, font=get_font(13, False), fill=(230, 230, 230))

    # Card 3: Concat & Projection
    draw_card(d, [935, 495, 1775, 638], (20, 55, 40, 220), (50, 180, 120), radius=8)
    d.text((960, 510), "最终拼合投影: MultiHead(Q, K, V) = Concat(head1, ..., head_h) * W_O", font=get_font(17, True), fill=(100, 255, 180))
    d.text((960, 550), "[OK] 把所有维度的观察结果无缝拼接，通过输出矩阵 W_O 融会贯通，产生极致立体的上下文理解！", font=get_font(15, True), fill=(255, 255, 255))
    d.text((960, 586), "[OK] 各司其职，兼听则明！", font=get_font(15, False), fill=(220, 240, 255))

    return img


def render_scene_6(base_img: Image.Image) -> Image.Image:
    img = prepare_whiteboard_canvas(base_img)
    d = ImageDraw.Draw(img)

    # Header
    draw_badge(d, (935, 68), "稳定之锚", (40, 140, 80), (80, 255, 140), font_size=15)
    d.text((1040, 65), "残差连接与层归一化 (Add & Norm)", font=get_font(23, True), fill=(255, 255, 255))

    # Card 1: The Depth Dilemma
    draw_card(d, [935, 118, 1775, 248], (30, 35, 55, 200), (80, 90, 150), radius=8)
    d.text((960, 134), "千亿大模型的百层深度诅咒: 为什么网络能叠到 80~128 层？", font=get_font(17, True), fill=(255, 180, 80))
    d.text((960, 170), "传统深度网络堆叠上百层，梯度反向传播会发生连续矩阵连乘，", font=get_font(15, False), fill=(220, 230, 240))
    d.text((960, 202), "梯度值会像瀑布跌落一样迅速归零 (Vanishing Gradient)，导致浅层参数根本无法学习！", font=get_font(15, True), fill=(255, 120, 120))

    # Card 2: Residual Skip Connection (Green Highway)
    draw_card(d, [935, 264, 1775, 445], (20, 50, 40, 200), (40, 160, 100), radius=8)
    d.text((960, 280), "残差连接 (Residual Shortcut): 绕过复杂计算的绿色高速天桥", font=get_font(17, True), fill=(100, 255, 180))
    d.text((960, 320), "公式表达:   Output = x + Sublayer(x)", font=get_font(21, True), fill=(255, 220, 80))
    d.text((960, 365), "求导数学证明:   dL / dx  =  dL / dOutput * ( I  +  dSublayer / dx )", font=get_font(17, True), fill=(255, 255, 255))
    d.text((960, 405), "[*] 哪怕非线性层导数极小，恒等矩阵 I 保证梯度始终拥有直通底层的『保底通道』！", font=get_font(15, True), fill=(160, 255, 200))

    # Card 3: RMSNorm & LayerNorm
    draw_card(d, [935, 460, 1775, 638], (25, 45, 75, 200), (70, 140, 220), radius=8)
    d.text((960, 476), "层归一化 (LayerNorm / RMSNorm): 动态数值稳定安全阀", font=get_font(17, True), fill=(100, 220, 255))
    d.text((960, 515), "• 约束激活值的均值与方差，防止百层堆叠中数值爆炸 (Explosion) 或下溢", font=get_font(15, False), fill=(230, 240, 255))
    d.text((960, 550), "• 现代大模型 (LLaMA, DeepSeek) 全面采用 RMSNorm: 舍去均值中心化，性能提升 20%！", font=get_font(15, True), fill=(255, 220, 100))
    d.text((960, 586), "• 采用 Pre-Norm 结构，模型初始化无需精细调优即可稳定收敛！", font=get_font(15, False), fill=(200, 255, 220))

    return img


def render_scene_7(base_img: Image.Image) -> Image.Image:
    img = prepare_whiteboard_canvas(base_img)
    d = ImageDraw.Draw(img)

    # Header
    draw_badge(d, (935, 68), "记忆中枢", (160, 60, 140), (240, 100, 220), font_size=15)
    d.text((1040, 65), "前馈神经网络 (FFN) 与 SwiGLU 参数知识库", font=get_font(23, True), fill=(255, 255, 255))

    # Card 1: Division of Labor
    draw_card(d, [935, 118, 1775, 248], (30, 40, 65, 200), (60, 120, 190), radius=8)
    d.text((960, 134), "大模型的大脑分工: 注意力机制 vs 前馈网络", font=get_font(17, True), fill=(255, 190, 80))
    d.text((960, 170), "• 自注意力层 (Self-Attention): 动态工作记忆 (临时在上下文当前对话中搜集线索)", font=get_font(15, False), fill=(220, 230, 255))
    d.text((960, 204), "• 前馈网络层 (Feed-Forward Network): 长期知识库 (真正存储大模型百亿、万亿参数知识！)", font=get_font(15, True), fill=(100, 255, 180))

    # Card 2: Dimension Expansion
    draw_card(d, [935, 264, 1775, 430], (25, 45, 75, 200), (70, 140, 220), radius=8)
    d.text((960, 280), "高维特征升维与提炼 (Dimension Expansion & Contraction):", font=get_font(17, True), fill=(100, 220, 255))

    stages = [
        ("d_model (4096)", "输入特征空间", (40, 80, 120)),
        ("8/3 x d_model (14336)", "高维概念膨胀激活", (100, 60, 140)),
        ("d_model (4096)", "知识压缩输出", (40, 100, 90)),
    ]
    for i, (dim, desc, c) in enumerate(stages):
        bx = 965 + i * 265
        by = 320
        draw_card(d, [bx, by, bx + 225, by + 75], c, (120, 180, 240), radius=6)
        d.text((bx + 15, by + 12), dim, font=get_font(15, True), fill=(255, 220, 80))
        d.text((bx + 15, by + 42), desc, font=get_font(13, False), fill=(230, 230, 230))
        if i < len(stages) - 1:
            d.line([(bx + 230, by + 37), (bx + 260, by + 37)], fill=(100, 230, 255), width=3)
            d.polygon([(bx + 260, by + 37), (bx + 252, by + 32), (bx + 252, by + 42)], fill=(100, 230, 255))

    # Card 3: SwiGLU
    draw_card(d, [935, 445, 1775, 638], (20, 50, 45, 200), (50, 180, 140), radius=8)
    d.text((960, 460), "现代大模型标配激活函数: SwiGLU (Shazeer, 2020)", font=get_font(17, True), fill=(100, 255, 180))
    d.text((960, 500), "FFN_SwiGLU(x) = ( (x * W_gate) * Swish(x * W_up) ) * W_down", font=get_font(19, True), fill=(255, 225, 80))
    d.text((960, 545), "[OK] 双线性门控单元: 引入门控控制信息通断，非线性表达能力碾压传统 ReLU！", font=get_font(15, True), fill=(255, 255, 255))
    d.text((960, 582), "[OK] 大模型学习到的常识、代码规范与世界事实，大半都在 FFN 的权重矩阵中被检索。", font=get_font(15, False), fill=(200, 255, 220))

    return img


def render_scene_8(base_img: Image.Image) -> Image.Image:
    img = prepare_whiteboard_canvas(base_img)
    d = ImageDraw.Draw(img)

    # Header
    draw_badge(d, (935, 68), "现代终局", (200, 80, 30), (255, 140, 60), font_size=15)
    d.text((1040, 65), "为什么现代大模型全员采用纯 Decoder-Only 架构？", font=get_font(23, True), fill=(255, 255, 255))

    # Card 1: Three Paradigms
    draw_card(d, [935, 118, 1775, 255], (30, 40, 65, 200), (60, 120, 190), radius=8)
    d.text((960, 134), "历史三大流派终极对决:", font=get_font(17, True), fill=(255, 190, 80))
    d.text((960, 170), "• Encoder-Decoder (T5, 原始Transformer): 双塔结构，适合翻译，但在长程涌现上乏力", font=get_font(14, False), fill=(200, 200, 200))
    d.text((960, 198), "• Encoder-Only (BERT): 双向理解强，但天生无法流畅高效地生成长文本", font=get_font(14, False), fill=(200, 200, 200))
    d.text((960, 226), "• Decoder-Only (GPT, DeepSeek, LLaMA): 统一自回归统一天下，成为 Scaling Law 最终赢家！", font=get_font(15, True), fill=(100, 255, 180))

    # Card 2: Causal Attention Mask
    draw_card(d, [935, 270, 1775, 470], (25, 45, 75, 200), (80, 150, 220), radius=8)
    d.text((960, 285), "因果掩码 (Causal Attention Mask): 严禁偷窥未来！", font=get_font(17, True), fill=(100, 220, 255))
    d.text((960, 325), "在自回归预测下一个词时，当前位置只能关注自身及前面的词，后面的词全部掩盖为 -inf", font=get_font(14, False), fill=(220, 230, 240))

    m_x, m_y = 960, 360
    d.text((m_x, m_y), "下三角因果矩阵 (Lower Triangular):", font=get_font(14, True), fill=(255, 200, 80))
    for r in range(4):
        for c in range(4):
            val = "1" if c <= r else "0"
            col_c = (80, 255, 120) if c <= r else (100, 100, 100)
            d.text((m_x + 300 + c * 45, m_y + r * 22), val, font=get_font(16, True), fill=col_c)
    d.text((m_x + 520, m_y + 30), "上三角置为 -inf\nSoftmax 后权重为 0", font=get_font(14, False), fill=(255, 120, 120))

    # Card 3: Autoregressive Next Token
    draw_card(d, [935, 485, 1775, 638], (20, 55, 40, 220), (50, 180, 120), radius=8)
    d.text((960, 500), "单向自回归下一个 Token 预测 (Next Token Prediction):", font=get_font(17, True), fill=(100, 255, 180))
    d.text((960, 538), "目标极简: 给出上下文 w1, ..., wt，最大化下一个词概率 P(w_{t+1} | w_{<=t})", font=get_font(16, True), fill=(255, 255, 255))
    d.text((960, 576), "[*] 最纯粹的目标反而催生了最强大的通用智能涌现！", font=get_font(16, True), fill=(255, 220, 80))

    return img


def render_scene_9(base_img: Image.Image) -> Image.Image:
    img = prepare_whiteboard_canvas(base_img)
    d = ImageDraw.Draw(img)

    # Header
    draw_badge(d, (935, 68), "全景总结", (40, 150, 120), (80, 255, 200), font_size=15)
    d.text((1040, 65), "Transformer 全景架构总览 与 下期彩蛋预告", font=get_font(23, True), fill=(255, 255, 255))

    # Card 1: Checklist of Components (Zero overlap between label and description)
    draw_card(d, [935, 118, 1775, 352], (20, 45, 65, 200), (50, 140, 200), radius=8)
    d.text((960, 134), "大模型 7 大核心骨架一览表 (Architecture Checklist):", font=get_font(17, True), fill=(255, 200, 80))

    checks = [
        ("Tokenizer 词嵌入", "文本升维映射为 4096 维坐标"),
        ("RoPE 旋转编码", "复数空间旋转注入相对距离"),
        ("Q/K/V 自注意力", "雷达标签点积萃取关键上下文"),
        ("多头注意力机制", "并行 32 头兼听主谓指代与因果"),
        ("残差跳线连接", "百层网络反向传播保底通道"),
        ("RMSNorm 归一化", "极速锁死数值稳定杜绝失真"),
        ("SwiGLU 前馈网络", "双线性门控知识记忆库与归纳"),
    ]
    lbl_font = get_font(14, True)
    desc_font = get_font(13, False)
    for i, (name, desc) in enumerate(checks):
        col = i // 4
        row = i % 4
        bx = 955 + col * 405
        by = 176 + row * 40
        lbl_txt = f"[OK] {name}:"
        d.text((bx, by), lbl_txt, font=lbl_font, fill=(100, 255, 180))
        d.text((bx + 178, by + 1), desc, font=desc_font, fill=(215, 230, 245))

    # Card 2: Next Episode Teaser
    draw_card(d, [935, 368, 1775, 638], (45, 25, 60, 230), (220, 80, 255), radius=10, width=2)
    d.text((960, 388), "[!] 下期进阶预告 (NEXT EPISODE PREVIEW)", font=get_font(21, True), fill=(255, 130, 255))
    d.text((960, 434), "为什么大模型生成文字越长，显存越吃紧？甚至直接 OOM 崩溃？", font=get_font(17, True), fill=(255, 220, 100))
    d.text((960, 474), "[>] 深度揭秘推理加速黑科技: KV Cache 与 FlashAttention", font=get_font(19, True), fill=(100, 255, 220))
    d.text((960, 518), "• 到底什么是 Key-Value 缓存？如何避免从头重复计算平方级注意力？", font=get_font(15, False), fill=(240, 240, 255))
    d.text((960, 554), "• GPU SRAM 片上显存调度如何创造 10 倍加速神话？", font=get_font(15, False), fill=(240, 240, 255))
    d.text((960, 594), "[*] 觉得有用记得点赞、收藏、投币三连，能代在下期等你！", font=get_font(16, True), fill=(255, 200, 80))

    return img


def main():
    base_cover = PROJECT_ROOT / "assets" / "scene_cover.jpg"
    cutout_file = PROJECT_ROOT / "assets" / "noshiro_transparent.png"
    if not base_cover.exists():
        print(f"[-] Base cover not found: {base_cover}")
        return

    # Resize base to 1920x1080 high-def
    base_img = Image.open(base_cover).convert("RGB").resize((1920, 1080), Image.Resampling.LANCZOS)
    cutout = Image.open(cutout_file).convert("RGBA") if cutout_file.exists() else None

    out_dir = PROJECT_ROOT / "images"
    out_dir.mkdir(parents=True, exist_ok=True)

    generators = [
        (1, render_scene_1),
        (2, render_scene_2),
        (3, render_scene_3),
        (4, render_scene_4),
        (5, render_scene_5),
        (6, render_scene_6),
        (7, render_scene_7),
        (8, render_scene_8),
        (9, render_scene_9),
    ]

    for idx, fn in generators:
        out_file = out_dir / f"scene_{idx}.jpg"
        overlay_file = out_dir / f"board_overlay_{idx}.png"

        scene_img = fn(base_img)

        # Save transparent RGBA board overlay for AI video compositing
        board_overlay = extract_board_overlay(scene_img)
        board_overlay.save(overlay_file, format="PNG")

        # Composite Noshiro foreground so her laser pointer and arm are in front of board
        if cutout:
            scene_img = composite_noshiro_foreground(scene_img, cutout)
        scene_img.convert("RGB").save(out_file, quality=95)
        print(
            f"[+] Rendered Scene {idx} -> {out_file.name} ({out_file.stat().st_size / 1024:.1f} KB) "
            f"& {overlay_file.name} ({overlay_file.stat().st_size / 1024:.1f} KB)"
        )


if __name__ == "__main__":
    main()
