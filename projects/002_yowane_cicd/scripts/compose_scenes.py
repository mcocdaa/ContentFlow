import sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageFilter

FONT_BOLD = "/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc"
FONT_REG = "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc"

def get_font(size, bold=False):
    path = FONT_BOLD if bold else FONT_REG
    try:
        return ImageFont.truetype(path, size)
    except Exception:
        return ImageFont.load_default()

def draw_badge(d, xy, text, bg_color, border_color, text_color=(255, 255, 255), font_size=18):
    font = get_font(font_size, True)
    bbox = font.getbbox(text)
    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]
    pad_x, pad_y = 14, 6
    x1, y1 = xy[0], xy[1]
    x2, y2 = x1 + tw + pad_x * 2, y1 + th + pad_y * 2
    d.rounded_rectangle([x1, y1, x2, y2], radius=6, fill=bg_color, outline=border_color, width=1)
    d.text((x1 + pad_x, y1 + pad_y - 1), text, font=font, fill=text_color)
    return x2

def draw_status_icon(d, center_x, center_y, status="pass", radius=10):
    if status == "pass":
        # Green circle with checkmark
        d.ellipse([center_x - radius, center_y - radius, center_x + radius, center_y + radius], fill=(30, 180, 80, 255))
        # Draw checkmark
        d.line([(center_x - 5, center_y), (center_x - 1, center_y + 4), (center_x + 6, center_y - 4)], fill=(255, 255, 255, 255), width=2)
    elif status == "fail":
        # Red circle with cross
        d.ellipse([center_x - radius, center_y - radius, center_x + radius, center_y + radius], fill=(220, 40, 40, 255))
        # Draw cross
        d.line([(center_x - 4, center_y - 4), (center_x + 4, center_y + 4)], fill=(255, 255, 255, 255), width=2)
        d.line([(center_x + 4, center_y - 4), (center_x - 4, center_y + 4)], fill=(255, 255, 255, 255), width=2)
    elif status == "warn":
        # Amber circle with exclamation
        d.ellipse([center_x - radius, center_y - radius, center_x + radius, center_y + radius], fill=(230, 140, 20, 255))
        d.line([(center_x, center_y - 5), (center_x, center_y + 1)], fill=(255, 255, 255, 255), width=2)
        d.ellipse([center_x - 1, center_y + 3, center_x + 1, center_y + 5], fill=(255, 255, 255, 255))

def render_whiteboard_scene1():
    img = Image.new("RGBA", (1389, 781), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    
    # Header shifted to start at x=340 to clear character
    d.text((340, 95), "CI/CD PIPELINE STATUS", font=get_font(28, True), fill=(255, 120, 120, 255))
    draw_badge(d, (720, 93), "CRITICAL FAILED", (180, 25, 25, 220), (255, 80, 80, 255), font_size=20)
    
    d.text((340, 140), "项目：Core-App (main)  |  触发源：开发者肉身手动敲命令发包", font=get_font(17), fill=(200, 205, 215, 220))
    
    # Terminal Log Box
    d.rounded_rectangle([340, 180, 850, 490], radius=10, fill=(16, 20, 28, 235), outline=(240, 70, 70, 180), width=2)
    d.text((360, 195), "terminal ~ git push origin main && ./deploy.sh", font=get_font(17, True), fill=(160, 190, 225, 255))
    d.line([(360, 225), (830, 225)], fill=(60, 75, 95, 200), width=1)
    
    logs = [
        ("[INFO]  Starting manual deploy pipeline at 02:30 AM...", (150, 185, 215)),
        ("[WARN]  Env mismatch: local Node v18 vs server Node v14", (255, 190, 60)),
        ("[ERROR] SyntaxError: Unexpected token '?' at app.ts:142", (255, 90, 90)),
        ("[FAIL]  Unit Tests: 14 failed, 3 passed (AssertionError)", (255, 70, 70)),
        ("[FATAL] Build aborted! Broken code leaked into main!", (255, 50, 50)),
        ("[EMERG] Production 502 Bad Gateway! 线上服务崩溃!", (255, 40, 40)),
        ("[PANIC] 缺少自动化质量门禁，深夜抢修 Bug 中...", (255, 130, 130)),
    ]
    y_off = 240
    for text, col in logs:
        d.text((360, y_off), text, font=get_font(16), fill=(*col, 255))
        y_off += 34
        
    # Right Side: Pipeline Breakdown
    d.rounded_rectangle([870, 180, 1280, 490], radius=10, fill=(20, 24, 34, 235), outline=(240, 80, 80, 140), width=2)
    d.text((890, 195), "流水线崩溃节点排查", font=get_font(20, True), fill=(255, 160, 160, 255))
    
    stages = [
        ("Stage 1", "Git Push", "代码已提交", "pass"),
        ("Stage 2", "Lint & Scan", "代码规范拦截", "warn"),
        ("Stage 3", "Unit Tests", "单元测试暴雷", "fail"),
        ("Stage 4", "Deploy 502", "线上发布崩溃", "fail"),
    ]
    sy = 240
    for s_tag, s_name, s_desc, s_stat in stages:
        d.rounded_rectangle([890, sy, 1260, sy + 50], radius=6, fill=(28, 32, 44, 220), outline=(70, 80, 100, 180), width=1)
        d.text((905, sy + 14), s_tag, font=get_font(15, True), fill=(180, 200, 230, 255))
        d.text((990, sy + 14), s_name, font=get_font(16, True), fill=(255, 255, 255, 255))
        d.text((1110, sy + 14), s_desc, font=get_font(14), fill=(200, 200, 200, 220))
        draw_status_icon(d, 1240, sy + 25, s_stat, radius=8)
        sy += 60
        
    # Bottom Alert Banner
    d.rounded_rectangle([340, 515, 1280, 610], radius=10, fill=(120, 25, 25, 210), outline=(255, 90, 90, 240), width=2)
    draw_status_icon(d, 370, 562, "warn", radius=14)
    d.text((395, 532), "避坑第一条：肉身敲命令发包、深夜发布、缺单元测试，脱发三大元凶！", font=get_font(20, True), fill=(255, 255, 255, 255))
    d.text((395, 568), "核心病因：缺乏统一的自动化 CI 门禁，不合格代码直接流入主干并发布线上。", font=get_font(16), fill=(255, 210, 210, 220))
    
    return img

def render_whiteboard_scene2():
    img = Image.new("RGBA", (1389, 781), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    
    # Header shifted to start at x=340 to clear character
    d.text((340, 95), "CI/CD 避坑实战指南", font=get_font(28, True), fill=(255, 180, 60, 255))
    draw_badge(d, (640, 93), "三大玄学重灾区", (210, 110, 20, 220), (255, 200, 80, 255), font_size=20)
    d.text((340, 140), "弱音老师教鞭警告：以下致命痛点，你中招了几个？", font=get_font(17), fill=(220, 220, 220, 220))
    
    cards = [
        ("坑点 1 · 分支合并像拆盲盒", "多分支长期不合入主干，上线前通宵解冲突，代码被意外覆盖。", "秘诀：小步快跑，主干开发，每天多次自动触发集成验证。", (255, 100, 100)),
        ("坑点 2 · '我本地运行明明没问题'", "开发者本地环境与生产服务器 OS、依赖版本存在微小玄学差异。", "秘诀：容器化标准化构建（Docker/OCI），打包镜像到处运行。", (255, 160, 60)),
        ("坑点 3 · 裸奔上线，坏代码溜进主干", "缺少单元测试与静态扫描自动化拦截，Bug 频频直冲生产环境。", "秘诀：设置 CI 强制准入门禁，全部绿灯才允许合并发布。", (100, 190, 255)),
    ]
    
    cy = 180
    for title, desc, sol, col in cards:
        d.rounded_rectangle([340, cy, 1280, cy + 125], radius=10, fill=(20, 26, 38, 235), outline=(*col, 180), width=2)
        draw_badge(d, (360, cy + 14), title, (*col, 40), (*col, 220), (*col, 255), font_size=18)
        d.text((365, cy + 58), f"痛点分析：{desc}", font=get_font(17), fill=(230, 230, 230, 240))
        d.text((365, cy + 90), f"避坑指南：{sol}", font=get_font(17, True), fill=(120, 245, 175, 255))
        cy += 140
        
    d.rounded_rectangle([340, 615, 1280, 660], radius=8, fill=(35, 45, 65, 210), outline=(100, 190, 255, 160), width=1)
    d.text((365, 626), "记住核心口诀：自动化不是锦上添花，而是程序员早下班的救命稻草！", font=get_font(18, True), fill=(255, 230, 140, 255))
    return img

def render_whiteboard_scene3():
    img = Image.new("RGBA", (1389, 781), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    
    # Header shifted to start at x=340
    d.text((340, 95), "CI CONTINUOUS INTEGRATION", font=get_font(28, True), fill=(100, 245, 160, 255))
    draw_badge(d, (790, 93), "自动化质量门禁", (20, 140, 70, 220), (80, 255, 150, 255), font_size=20)
    d.text((340, 140), "Git Push 自动触发，全绿方准入主干，代码健康 100% 数字化透明", font=get_font(17), fill=(200, 230, 215, 220))
    
    # 4 Pipeline Stages
    nodes = [
        ("Git Push", "代码提交", "feat/order", (100, 180, 255)),
        ("Lint & Sec", "规范与安全", "0 Vulnerabilities", (120, 230, 160)),
        ("Unit Tests", "单元测试套件", "128 Passed (94%)", (80, 240, 140)),
        ("Build & Gate", "质量门禁审核", "ALL GREEN PASS", (60, 255, 120)),
    ]
    
    nx = 340
    ny = 185
    nw = 215
    nh = 145
    
    for i, (n_title, n_sub, n_stat, n_col) in enumerate(nodes):
        d.rounded_rectangle([nx, ny, nx + nw, ny + nh], radius=10, fill=(18, 28, 36, 240), outline=(*n_col, 200), width=2)
        d.rounded_rectangle([nx + 12, ny + 12, nx + 80, ny + 36], radius=5, fill=(*n_col, 40), outline=(*n_col, 200), width=1)
        d.text((nx + 20, ny + 15), f"Stage {i+1}", font=get_font(13, True), fill=(*n_col, 255))
        draw_status_icon(d, nx + nw - 20, ny + 24, "pass", radius=7)
        
        d.text((nx + 14, ny + 46), n_title, font=get_font(19, True), fill=(245, 250, 255, 255))
        d.text((nx + 14, ny + 76), n_sub, font=get_font(15), fill=(180, 200, 215, 220))
        d.text((nx + 14, ny + 106), n_stat, font=get_font(14, True), fill=(*n_col, 255))
        
        if i < len(nodes) - 1:
            ax = nx + nw + 3
            ay = ny + nh // 2
            d.line([(ax, ay), (ax + 18, ay)], fill=(120, 240, 180, 255), width=3)
            d.polygon([(ax + 18, ay - 5), (ax + 26, ay), (ax + 18, ay + 5)], fill=(120, 240, 180, 255))
        nx += nw + 28
        
    # Detail Principles
    d.rounded_rectangle([340, 360, 1280, 600], radius=10, fill=(16, 26, 32, 235), outline=(80, 220, 140, 150), width=1)
    d.text((365, 380), "现代 CI 自动化三大刚性原则：", font=get_font(20, True), fill=(140, 255, 180, 255))
    
    rules = [
        ("1. 极速反馈循环", "流水线执行控制在 5 分钟以内，开发者刚提交即可收到精准的测试通过或拦截反馈。"),
        ("2. 确定性隔离沙箱", "每次构建基于纯净容器环境，彻底杜绝宿主机残留缓存导致的偶发假失败。"),
        ("3. 主干强门禁保护", "主干分支强制设置保护锁，未获得 CI 全绿灯和同行评审严禁合并（No Merge Without Green）。"),
    ]
    ry = 420
    for r_title, r_desc in rules:
        d.text((375, ry), r_title, font=get_font(17, True), fill=(255, 255, 255, 255))
        d.text((540, ry), r_desc, font=get_font(16), fill=(195, 220, 215, 230))
        ry += 42
        
    d.rounded_rectangle([365, 550, 1255, 585], radius=6, fill=(20, 65, 42, 210), outline=(80, 240, 140, 180), width=1)
    d.text((380, 556), "CI 核心价值：在代码写完的第 1 分钟拦截 Bug，修复成本比线上故障低 100 倍！", font=get_font(16, True), fill=(120, 255, 180, 255))
    
    return img

def render_whiteboard_scene4():
    img = Image.new("RGBA", (1389, 781), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    
    # Header shifted to start at x=340
    d.text((340, 95), "CD CONTINUOUS DELIVERY", font=get_font(28, True), fill=(100, 205, 255, 255))
    draw_badge(d, (750, 93), "容器标准化交付", (20, 90, 150, 220), (80, 190, 255, 255), font_size=20)
    d.text((340, 140), "一次打包，到处运行 · 彻底终结'在我电脑上好好的'环境玄学", font=get_font(17), fill=(200, 225, 245, 220))
    
    # 4 Architecture Steps
    steps = [
        ("Dockerfile", "声明式环境依赖", "app:v2.4.0", (100, 185, 255)),
        ("OCI Image", "不可变交付物", "SHA256:7f9a...", (120, 220, 240)),
        ("Canary Rollout", "渐进式金丝雀", "5% -> 25% -> 100%", (140, 240, 200)),
        ("Health Watchdog", "秒级探针与自愈", "异常自动回滚", (100, 255, 160)),
    ]
    
    sx = 340
    sy = 185
    sw = 215
    sh = 145
    for i, (stitle, ssub, sval, scol) in enumerate(steps):
        d.rounded_rectangle([sx, sy, sx + sw, sy + sh], radius=10, fill=(18, 28, 44, 235), outline=(*scol, 200), width=1)
        d.rounded_rectangle([sx + 12, sy + 12, sx + 80, sy + 36], radius=5, fill=(*scol, 40), outline=(*scol, 200), width=1)
        d.text((sx + 20, sy + 15), f"Step {i+1}", font=get_font(13, True), fill=(*scol, 255))
        draw_status_icon(d, sx + sw - 20, sy + 24, "pass", radius=7)
        
        d.text((sx + 14, sy + 46), stitle, font=get_font(18, True), fill=(240, 245, 255, 255))
        d.text((sx + 14, sy + 76), ssub, font=get_font(15), fill=(180, 200, 220, 220))
        d.text((sx + 14, sy + 106), sval, font=get_font(13, True), fill=(*scol, 255))
        
        if i < len(steps) - 1:
            ax = sx + sw + 3
            ay = sy + sh // 2
            d.line([(ax, ay), (ax + 18, ay)], fill=(100, 200, 255, 255), width=3)
            d.polygon([(ax + 18, ay - 5), (ax + 26, ay), (ax + 18, ay + 5)], fill=(100, 200, 255, 255))
        sx += sw + 28
        
    # Bottom 2 feature cards
    d.rounded_rectangle([340, 360, 790, 600], radius=10, fill=(18, 28, 46, 235), outline=(100, 180, 255, 140), width=1)
    d.text((360, 380), "环境强一致性保障", font=get_font(20, True), fill=(120, 220, 255, 255))
    d.text((360, 420), "• 操作系统内核、基础库、运行时版本由 Docker 固化", font=get_font(16), fill=(210, 225, 240, 220))
    d.text((360, 460), "• 开发、测试、预发、生产完全使用同一份 Image Digest", font=get_font(16), fill=(210, 225, 240, 220))
    d.text((360, 500), "• 彻底杜绝运维人员手动配机器带来的环境配置漂移", font=get_font(16), fill=(210, 225, 240, 220))
    d.text((360, 540), "• 无论在哪台机器运行，表现都百分之百确定", font=get_font(16, True), fill=(140, 240, 200, 255))
    
    d.rounded_rectangle([820, 360, 1280, 600], radius=10, fill=(18, 28, 46, 235), outline=(80, 240, 180, 140), width=1)
    d.text((840, 380), "零停机平滑发布与自愈", font=get_font(20, True), fill=(100, 255, 180, 255))
    d.text((840, 420), "• 金丝雀发布先导流 5% 真实流量，观察指标 10 分钟", font=get_font(16), fill=(210, 240, 225, 220))
    d.text((840, 460), "• 错误率一旦突破 0.5% 阈值，看门狗 100ms 自动回滚", font=get_font(16), fill=(210, 240, 225, 220))
    d.text((840, 500), "• 丝滑平滑过渡，普通用户完全感知不到新旧版本交替", font=get_font(16), fill=(210, 240, 225, 220))
    d.text((840, 540), "• 自动健康巡检，彻底杜绝线上黑屏事故", font=get_font(16, True), fill=(120, 255, 190, 255))
    
    return img

def render_whiteboard_scene5():
    img = Image.new("RGBA", (1389, 781), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    
    # Header shifted to start at x=340
    d.text((340, 95), "CI/CD 避坑总结 · 准点下班第一法则", font=get_font(28, True), fill=(255, 220, 100, 255))
    draw_badge(d, (860, 93), "100% 自动化成功", (200, 140, 20, 220), (255, 230, 80, 255), font_size=20)
    d.text((340, 140), "从今天起，把重复机械的打包部署交给流水线，把宝贵时间留给生活！", font=get_font(17), fill=(240, 235, 215, 220))
    
    # Summary Points
    d.rounded_rectangle([340, 180, 1280, 420], radius=10, fill=(25, 28, 38, 235), outline=(255, 210, 100, 160), width=2)
    d.text((365, 198), "现代工程师的高效避坑闭环", font=get_font(21, True), fill=(255, 230, 120, 255))
    
    points = [
        ("持续集成（CI）", "每一次 Git Push 都自动完成代码风格、单元测试与安全扫描，全绿方准入主干。"),
        ("持续交付（CD）", "基于 Docker 容器统一交付物，杜绝环境玄学，金丝雀灰度发布保障平滑平稳。"),
        ("自动化自愈（Auto-Heal）", "监控告警与流水线深度联动，异常毫秒级自动回滚，再无深夜紧急抢修。"),
        ("准点下班早自由", "解放双手，告别 996 肉身运维，喝杯咖啡，准点下班！"),
    ]
    py = 240
    for ptitle, pdesc in points:
        d.rounded_rectangle([365, py, 1255, py + 36], radius=5, fill=(35, 40, 52, 220))
        draw_status_icon(d, 385, py + 18, "pass", radius=7)
        d.text((405, py + 8), ptitle, font=get_font(16, True), fill=(100, 245, 180, 255))
        d.text((630, py + 8), pdesc, font=get_font(15), fill=(230, 235, 245, 230))
        py += 42
        
    # Call to Action Card
    d.rounded_rectangle([340, 445, 1280, 620], radius=10, fill=(28, 22, 38, 235), outline=(255, 140, 200, 180), width=2)
    d.text((370, 465), "喜欢弱音的技术干货分享吗？", font=get_font(23, True), fill=(255, 180, 220, 255))
    d.text((370, 508), "一键三连【点赞 + 收藏 + 关注】支持弱音", font=get_font(19, True), fill=(255, 255, 255, 255))
    d.text((370, 550), "下期实战：手把手带你从零搭建一条完整的 GitHub Actions 自动化流水线！不见不散~", font=get_font(17), fill=(230, 210, 230, 220))
    
    return img

def compose_all_scenes():
    bg = Image.open("projects/002_yowane_cicd/assets/decomposed_layers/layer_0_z0_background.jpg").convert("RGBA")
    board_chassis = Image.open("projects/002_yowane_cicd/assets/decomposed_layers/layer_1_z1_全息大屏底板.png").convert("RGBA")
    
    renders = [
        ("yowane_v3_scene1.jpg", render_whiteboard_scene1(), "projects/002_yowane_cicd/assets/yowane_alluring_transparent.png"),
        ("yowane_v3_scene2.jpg", render_whiteboard_scene2(), "projects/002_yowane_cicd/assets/yowane_pose2_transparent.png"),
        ("yowane_v3_scene3.jpg", render_whiteboard_scene3(), "projects/002_yowane_cicd/assets/yowane_pose3_transparent.png"),
        ("yowane_v3_scene4.jpg", render_whiteboard_scene4(), "projects/002_yowane_cicd/assets/yowane_pose4_transparent.png"),
        ("yowane_v3_scene5.jpg", render_whiteboard_scene5(), "projects/002_yowane_cicd/assets/yowane_pose5_transparent.png"),
    ]
    
    out_dir = Path("projects/002_yowane_cicd/assets")
    
    for filename, board_content, char_path in renders:
        print(f"[*] Composing {filename} with character cutout {char_path}...")
        
        # 1. Start with clean background
        scene = bg.copy()
        
        # 2. Merge whiteboard content into whiteboard chassis
        board = board_chassis.copy()
        board.alpha_composite(board_content)
        
        # 3. Place whiteboard at (585, 78)
        scene.alpha_composite(board, (585, 78))
        
        # 4. Process character cutout
        if Path(char_path).exists():
            char_img = Image.open(char_path).convert("RGBA")
            bbox = char_img.getbbox()
            if bbox:
                char_crop = char_img.crop(bbox)
                target_h = 1180
                scale = target_h / char_crop.height
                target_w = int(char_crop.width * scale)
                char_scaled = char_crop.resize((target_w, target_h), Image.Resampling.LANCZOS)
                
                char_x = 180
                char_y = 1380 - target_h
                
                # Pedestal contact shadow
                shadow = Image.new("RGBA", scene.size, (0, 0, 0, 0))
                sdraw = ImageDraw.Draw(shadow)
                pedestal_w = int(target_w * 0.72)
                pedestal_cx = char_x + target_w // 2
                pedestal_cy = char_y + target_h - 15
                sdraw.ellipse([pedestal_cx - pedestal_w//2, pedestal_cy - 18, pedestal_cx + pedestal_w//2, pedestal_cy + 18], fill=(10, 15, 25, 130))
                shadow = shadow.filter(ImageFilter.GaussianBlur(12))
                
                scene.alpha_composite(shadow)
                scene.alpha_composite(char_scaled, (char_x, char_y))
        else:
            print(f"[!] Warning: {char_path} does not exist yet!")
            
        dest_path = out_dir / filename
        scene.convert("RGB").save(dest_path, quality=95)
        print(f"[+] Saved {dest_path} ({scene.size})")

if __name__ == "__main__":
    compose_all_scenes()
