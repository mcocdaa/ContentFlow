// The player and the video exporter call the same deterministic drawing function.
(() => {
  const story = window.story;
  const canvas = document.querySelector('canvas');
  const ctx = canvas.getContext('2d');
  const audio = document.querySelector('audio');
  const play = document.querySelector('#play');
  const mute = document.querySelector('#mute');
  const seek = document.querySelector('#seek');
  const clock = document.querySelector('#time');
  const paper = '#f6f2e7', ink = '#1b222a', blue = '#21339a', red = '#bd3e27';
  const art = {};
  const width = 1280, height = 720;
  const duration = story.cards.reduce((sum, card) => sum + card.seconds, 0);
  let position = 0, started = 0, running = false, frameId = 0;
  if (new URLSearchParams(location.search).has('export')) document.body.classList.add('export');

  function rect(x, y, w, h, color) {
    ctx.fillStyle = color;
    ctx.fillRect(x, y, w, h);
  }
  function rule(x, y, endX, endY, color, weight = 1) {
    ctx.strokeStyle = color;
    ctx.lineWidth = weight;
    ctx.beginPath(); ctx.moveTo(x, y); ctx.lineTo(endX, endY); ctx.stroke();
  }
  function type(str, x, y, size, weight = 500, color = ink, align = 'left') {
    ctx.fillStyle = color;
    ctx.font = weight + ' ' + size + 'px "Noto Sans CJK SC", sans-serif';
    ctx.textAlign = align;
    ctx.textBaseline = 'alphabetic';
    ctx.fillText(str, x, y);
  }
  function ease(n) {
    return 1 - Math.pow(1 - Math.max(0, Math.min(1, n)), 3);
  }
  function header(index, dark) {
    const fg = dark ? paper : ink;
    const soft = dark ? '#a3b1e6' : '#777b77';
    rect(52, 38, 9, 21, dark ? '#ffbe86' : red);
    type(story.series, 73, 58, 22, 800, fg);
    type(story.issue, 218, 57, 15, 550, soft);
    const firstTab = Math.max(0, Math.min(index - 1, story.cards.length - 3));
    story.cards.slice(firstTab, firstTab + 3).forEach((card, slot) => {
      const i = firstTab + slot;
      const x = 968 + slot * 88;
      if (i === index) rect(x, 32, 80, 34, dark ? paper : ink);
      type(card.tab, x + 40, 55, 16, 650, i === index ? (dark ? blue : paper) : soft, 'center');
    });
    rule(52, 82, 1224, 82, dark ? '#7083c7' : '#a6a79c');
  }
  function footer(index, dark) {
    const soft = dark ? '#bac5ef' : '#525a60';
    const start = 52, finish = 1144;
    rule(start, 680, finish, 680, dark ? '#576cb4' : '#ccc9bd', 2);
    rule(start, 680, start + (finish - start) * (position / duration), 680, dark ? '#f1ab82' : red, 3);
    type(String(index + 1).padStart(2, '0') + ' / ' + String(story.cards.length).padStart(2, '0'), 1224, 686, 16, 650, soft, 'right');
  }
  function sectionLabel(label, x, y, dark = false) {
    const c = dark ? '#f4bc9b' : red;
    rule(x, y - 6, x + 32, y - 6, c, 3);
    type(label, x + 46, y, 19, 750, c);
  }

  // A photographic print with a caption margin. The entire source remains in frame.
  function printPhoto(card, x, y, w, tilt, local) {
    const image = art[card.photo];
    const h = w * image.height / image.width;
    ctx.save();
    ctx.translate(x + w / 2 + (1 - ease(local / 0.65)) * 42, y + h / 2);
    ctx.rotate(tilt + (1 - ease(local / 0.65)) * 0.035 + 0.003 * Math.sin(local * 0.75));
    ctx.shadowColor = '#20212a35'; ctx.shadowBlur = 18; ctx.shadowOffsetY = 8;
    rect(-w / 2 - 10, -h / 2 - 10, w + 20, h + 65, '#fffdf4');
    ctx.shadowColor = 'transparent'; ctx.shadowBlur = 0; ctx.shadowOffsetY = 0;
    ctx.drawImage(image, -w / 2, -h / 2, w, h);
    type(card.caption, -w / 2 + 4, h / 2 + 35, 18, 650, '#3d4650');
    ctx.restore();
  }
  function stamp(text, x, y, local, dark = false) {
    if (local < 0) return;
    const impact = ease(local / 0.22);
    ctx.save();
    ctx.translate(x, y);
    ctx.rotate(-0.13);
    ctx.scale(1.65 - 0.65 * impact, 1.65 - 0.65 * impact);
    ctx.globalAlpha = impact * 0.97;
    ctx.strokeStyle = dark ? blue : red;
    ctx.lineWidth = 5;
    ctx.strokeRect(-68, -34, 136, 68);
    ctx.lineWidth = 1;
    ctx.strokeRect(-61, -27, 122, 54);
    type(text, 0, 15, 40, 900, dark ? blue : red, 'center');
    ctx.restore();
  }
  function interview(card, t) {
    rect(0, 0, width, height, paper);
    sectionLabel(card.label, 64, 173);
    const slide = 14 * (1 - ease(t / 0.5));
    type(card.headline[0], 56, 307 + slide, 84, 900);
    type(card.headline[1], 56, 411 + slide, 78, 900, blue);
    rule(62, 461, 487, 461, '#a8aa9f');
    type(card.quote, 58, 516, 24, 600);
    type(card.credit, 65, 559, 18, 550, '#626b70');
    printPhoto(card, 565, 182, 628, -0.035, t);
    stamp(card.decision, 1120, 556, t - 2.4);
  }
  function object(card, t) {
    rect(0, 0, width, height, blue);
    for (let x = 510; x <= 1224; x += 30) {
      for (let y = 116; y < 642; y += 30) rect(x, y, 1.7, 1.7, '#6e7fc1');
    }
    sectionLabel(card.label, 64, 173, true);
    type(card.headline[0], 56, 307, 75, 900, paper);
    type(card.headline[1], 56, 408, 74, 900, paper);
    rule(64, 461, 482, 461, '#889ad4');
    type(card.quote, 59, 517, 25, 550, paper);
    type(card.credit, 65, 560, 18, 550, '#bdc9f2');

    const launch = ease((t - 0.22) / 1.45);
    const float = Math.sin(Math.min(t, 6) * 1.24);
    const cx = 883 - 285 * (1 - launch) + 16 * t / card.seconds;
    const cy = 340 + 108 * (1 - launch) + 7 * float;
    ctx.save();
    ctx.beginPath(); ctx.rect(510, 100, 714, 520); ctx.clip();
    ctx.strokeStyle = '#bac7ee'; ctx.lineWidth = 2; ctx.setLineDash([8, 10]);
    ctx.beginPath(); ctx.moveTo(475, 508); ctx.bezierCurveTo(645, 527, 661, 442, cx - 72, cy + 48); ctx.stroke();
    ctx.setLineDash([]);
    ctx.translate(cx, cy);
    ctx.rotate(-0.10 + 0.17 * (1 - launch) + 0.013 * float);
    const image = art[card.prop];
    const w = 682, h = w * image.height / image.width;
    ctx.drawImage(image, -w / 2, -h / 2, w, h);
    ctx.restore();
    rule(815, 570, 859, 570, '#eab084', 2);
    type(card.caption, 875, 577, 17, 600, '#e1e7ff');
  }
  function offer(card, t) {
    rect(0, 0, width, height, paper);
    printPhoto(card, 64, 165, 597, -0.035, t);
    sectionLabel(card.label, 723, 157);
    type(card.headline[0], 715, 257, 66, 900);
    type(card.headline[1], 715, 339, 70, 900, blue);
    card.terms.forEach(([label, value], i) => {
      const y = 391 + i * 52;
      rule(723, y, 1208, y, '#bcbcaf');
      type(label, 724, y + 34, 21, 600, '#626b70');
      type(value, 1198, y + 34, 25, 750, ink, 'right');
    });
    type(card.quote, 718, 550, 24, 600);
    stamp(card.decision, 542, 521, t - 2.2, true);
  }
  const layouts = {interview, object, offer};
  function draw(seconds) {
    position = Math.max(0, Math.min(duration, seconds));
    let index = 0, local = position;
    while (index < story.cards.length - 1 && local >= story.cards[index].seconds) {
      local -= story.cards[index].seconds;
      index++;
    }
    const card = story.cards[index], dark = card.layout === 'object';
    ctx.setTransform(canvas.width / width, 0, 0, canvas.height / height, 0, 0);
    if (story.renderCard) {
      story.renderCard({ctx, art, card, index, local, story});
    } else {
      layouts[card.layout](card, local);
      header(index, dark); footer(index, dark);
    }
    // A short paper edge carries cuts without a flash.
    if (index && local < 0.24) {
      rect(1280 * ease(local / 0.24), 0, 13 * (1 - ease(local / 0.24)), 720, '#e69f76');
    }
    seek.value = position;
    clock.value = new Date(position * 1000).toISOString().slice(14, 19);
  }
  function pause() {
    running = false;
    cancelAnimationFrame(frameId);
    audio.pause();
    play.textContent = position >= duration ? '重播' : '播放';
  }
  function tick(now) {
    if (!running) return;
    draw((now - started) / 1000);
    if (position >= duration) pause();
    else frameId = requestAnimationFrame(tick);
  }
  function toggle() {
    if (running) return pause();
    if (position >= duration) draw(0);
    if (story.sound) {
      audio.currentTime = position;
      audio.play().catch(() => { document.querySelector('#status').textContent = '音轨暂时无法播放，画面可继续预览。'; });
    }
    started = performance.now() - position * 1000;
    running = true; play.textContent = '暂停';
    frameId = requestAnimationFrame(tick);
  }
  window.motionCardsReady = (async () => {
    await Promise.all(Object.entries(story.art).map(async ([key, src]) => {
      const img = new Image(); img.src = src; await img.decode(); art[key] = img;
    }));
    if (story.sound) audio.src = story.sound;
    seek.max = duration; play.disabled = false;
    play.onclick = toggle;
    mute.onclick = () => {
      audio.muted = !audio.muted;
      mute.textContent = audio.muted ? '开启声音' : '静音';
      mute.setAttribute('aria-pressed', String(audio.muted));
    };
    seek.oninput = () => {
      draw(Number(seek.value));
      if (story.sound && audio.readyState) audio.currentTime = position;
      started = performance.now() - position * 1000;
    };
    window.motionCards = {draw, duration};
    draw(0);
  })();
  window.motionCardsReady.catch(() => { document.querySelector('#status').textContent = '素材加载失败，请检查 story.js 中的文件路径。'; });
})();
