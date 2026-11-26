# 透明像素实验室

* **主选分区**：知识 → 计算机技术
* **主标题**：这2张鲸鱼娘PNG，哪张是假透明？3分钟把真图做成动画
* **简介**：
  左右两张鲸鱼娘都带棋盘格。把桌面换成橙色，哪一张还会背着格子走？先猜，再用同一张立绘读像素、看发丝、做个会呼吸的网页角色。

  00:00 猜左右，换底色揭晓
  00:30 点像素看透明度，为什么发梢读到 158？
  00:50 让原图等比上浮，把摇摆的支点移到脚底
  01:40 先画人还是先画底？现场修一次透明度泄漏
  02:20 回到同一秒复查，换自己的图验收

  【可以直接抄的小实验】
  把自己的透明图命名为 whale.png，和新建的 fish.html 放在同一文件夹。复制下面三行到 fish.html，保存后用浏览器打开。鼠标移到角色身上，它会从脚边轻轻摆动；移开就回到原位。把 #92cadd 改成 #ffac70，再看一次发梢。

  <!doctype html><meta charset="utf-8"><title>鲸鱼娘摇摆实验</title>
  <style>body{background:#92cadd}img{height:220px;width:auto;transform-origin:50% 100%;transition:transform 1s}img:hover{transform:translateY(-8px) rotate(3deg)}</style>
  <img src="whale.png" alt="鲸鱼娘">

  【借物表 (Credits)】
  鲸鱼娘角色原型「溟月」由上善无形创作，DeepSeek 女仆造型由 ZipZipPipe 二次设计。正面图取自 ContentFlow 定型立绘，本期用于像素取样、对照合成和运动演示，相关美术改编按 CC BY-NC-SA 4.0 署名、非商业、相同方式共享。原作说明 https://www.bilibili.com/video/BV1tE9XBbErS/
  Q 版鲸鱼娘取自 pokerface-1224 维护的桌宠项目。封面和离线示例使用正面原画 https://github.com/pokerface-1224/deepseek-whale-girl-pet/blob/main/art/raw/front.png ，片中素材导览展示项目图标 https://github.com/pokerface-1224/deepseek-whale-girl-pet/blob/main/icon.png 。美术许可 CC BY-NC-SA 4.0，https://creativecommons.org/licenses/by-nc-sa/4.0/
  参考入口为鲸鱼娘开源资产库。片中以自绘导览标明入口。https://treapgogo.github.io/deepseek-whale-girl/index.html#top
  网页实验、图层合成、动效和课程脚本由 ContentFlow 制作。中文讲解使用 hexgrad/Kokoro-82M-v1.1-zh（Apache-2.0）合成，声音为单独人声讲解，无背景音乐。字体 Noto Sans CJK SC（SIL OFL 1.1）。

  【AIGC 标识】
  依据 GB 45438-2025 声明，本片含人工智能辅助制作的角色美术及中文合成讲解。画中像素数值和动画由示例程序实时绘制。
* **标签**：PNG, HTML, CSS动画, Canvas, 网页动画, 透明背景, 大肥鱼, 编程教程, 像素
* **置顶评论**：
  开场你押了左图还是右图？如果你的图换底色后冒白边，告诉我它在哪种底色上最明显。简介有能直接保存运行的三行小实验。
