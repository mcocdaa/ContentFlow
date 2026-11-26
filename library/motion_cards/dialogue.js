// Motion-comic layouts for a timed dialogue. Coordinates use a 1280 × 720 stage.
window.drawDialogueCard = function ({ctx, art, card, index, local, story}) {
  const paper = '#f7f2e6', ink = '#182028', blue = '#27399b', red = '#bd402b';
  const t = local, progress = t / card.seconds;
  const ease = v => 1 - Math.pow(1 - Math.max(0, Math.min(1, v)), 3);
  function box(x, y, w, h, color) {
    ctx.fillStyle = color; ctx.fillRect(x, y, w, h);
  }
  function text(value, x, y, size, color = ink, weight = 700, align = 'left') {
    ctx.fillStyle = color; ctx.textAlign = align; ctx.textBaseline = 'alphabetic';
    ctx.font = weight + ' ' + size + 'px "Noto Sans CJK SC", sans-serif';
    ctx.fillText(value, x, y);
  }
  function line(x1, y1, x2, y2, color, weight = 1) {
    ctx.strokeStyle = color; ctx.lineWidth = weight; ctx.beginPath();
    ctx.moveTo(x1,y1); ctx.lineTo(x2,y2); ctx.stroke();
  }
  function crop(image, x, y, w, h, focus = [.5,.5,1], drift = 0) {
    const z = focus[2] * (1 + .09 * ease(t / 1.4) + .025 * progress);
    const scale = Math.max(w / image.width, h / image.height) * z;
    const sw = w / scale, sh = h / scale;
    const sx = Math.max(0, Math.min(image.width - sw, image.width * (focus[0] + drift * progress) - sw / 2));
    const sy = Math.max(0, Math.min(image.height - sh, image.height * focus[1] - sh / 2));
    ctx.drawImage(image, sx, sy, sw, sh, x, y, w, h);
  }
  function stamp(word, x, y, when, tint) {
    const impact = ease((t - when) / .25);
    if (!impact) return;
    ctx.save(); ctx.translate(x,y); ctx.rotate(-.14);
    ctx.scale(1 + .55 * (1-impact), 1 + .55 * (1-impact)); ctx.globalAlpha = impact;
    box(-67,-34,134,68,paper); ctx.strokeStyle=tint; ctx.lineWidth=5; ctx.strokeRect(-67,-34,134,68);
    ctx.lineWidth=1; ctx.strokeRect(-61,-28,122,56); text(word,0,15,39,tint,900,'center'); ctx.restore();
  }
  function badge(label, x, y) {
    ctx.font='700 19px "Noto Sans CJK SC",sans-serif';
    const w=ctx.measureText(label).width+34;
    box(x,y,w,38,paper); box(x,y,5,38,red); text(label,x+17,y+26,19,ink);
  }
  function file() {
    box(0,0,1280,555,paper);
    text(card.tag,56,78,23,red);
    const rise=20*(1-ease(t/.55));
    text(card.title[0],48,223+rise,71,ink,900);
    text(card.title[1],48,326+rise,68,blue,900);
    line(55,373,502,373,'#b2b3a7');
    text(card.note,57,421,25,'#515d65',550);
    const image=art[card.art], w=632, h=w*image.height/image.width;
    ctx.save(); ctx.translate(899+38*(1-ease(t/.75)),266);ctx.rotate(-.036+.028*(1-ease(t/.8)));
    ctx.shadowBlur=12;ctx.shadowColor='#1620343b';ctx.shadowOffsetY=5;box(-w/2-10,-h/2-10,w+20,h+48,'#fffdf4');
    ctx.shadowColor='transparent';ctx.shadowBlur=0;ctx.shadowOffsetY=0;
    ctx.drawImage(image,-w/2,-h/2,w,h);
    text(story.issue,-w/2,h/2+25,16,'#495361');ctx.restore();
    stamp(card.stamp,1124,464,.48,index<9?red:blue);
  }
  function scene() {
    crop(art[card.art],0,0,1280,555,card.focus,card.focus[0]>.5?-.023:.02);
    badge(card.tag,48,34);
    if(card.endNote && t>1.45) {
      const x=64-20*(1-ease((t-1.45)/.33));
      box(x,428,353,82,paper);box(x,428,7,82,red);
      text(card.endNote,x+25,482,37,blue,900);
    }
  }
  function meter() {
    const good=card.figure>=64;
    box(0,0,1280,555,good?'#d8e8d8':'#f1dfc7');
    const shift=32*(1-ease(t/.65));
    badge(card.tag,50,39);
    text('工作站内存',56,169,39,ink,800);
    const value=Math.round((good?24:0)+(card.figure-(good?24:0))*ease(t/1.3));
    text(String(value),49,338+shift,162,good?blue:red,900);
    text('GB',294,333+shift,54,ink,800);
    const bar=435;
    box(58,389,bar,25,'#b9b8a9');box(58,389,bar*value/64,25,good?blue:red);
    text(card.caption,58,485,26,ink,600);
    ctx.save();ctx.beginPath();ctx.rect(548,0,732,555);ctx.clip();
    crop(art[card.art],548,0,732,555,[good?.52:.82,.46,good?1.05:1.48],-.025);
    ctx.restore();
    box(548,0,8,555,paper);
  }
  function flight() {
    box(0,0,1280,555,blue);
    for(let x=41;x<1280;x+=31)for(let y=22;y<555;y+=31)box(x,y,1.5,1.5,'#6978bb');
    badge(card.tag,50,39);
    text('简历退回',52,214,69,paper,900);text('目的地　候选人席',56,279,24,'#e9ddce',550);
    const launch=ease(t/1.6),cx=180+724*launch+35*progress,cy=478-246*launch+10*Math.sin(t*1.8);
    ctx.save();ctx.beginPath();ctx.rect(0,0,1280,555);ctx.clip();
    ctx.setLineDash([10,10]);ctx.lineWidth=3;ctx.strokeStyle='#c5d0f7';ctx.beginPath();
    ctx.moveTo(-30,467);ctx.bezierCurveTo(290,534,555,458,cx-77,cy+50);ctx.stroke();ctx.setLineDash([]);
    ctx.translate(cx,cy);ctx.rotate(.07-.17*launch);const sprite=art.plane,w=620;
    ctx.drawImage(sprite,-w/2,-w*sprite.height/sprite.width/2,w,w*sprite.height/sprite.width);ctx.restore();
    if(t>2.0){text('签收地点　面试桌对面',1218,505,19,'#d9e3ff',500,'right');}
  }
  function vote() {
    box(0,0,1280,555,paper);badge(card.tag,50,30);
    const img=art[card.art];
    card.approvals.forEach((item,i)=>{
      const x=56+i*405;
      ctx.save();ctx.beginPath();ctx.rect(x,92,381,323);ctx.clip();
      crop(img,x,92,381,323,[[.205,.43,1.86],[.51,.44,1.85],[.83,.46,1.88]][i]);ctx.restore();
      box(x,415,381,74,blue);
      text(item,x+20,464,30,paper,750);
      if(t>.42+i*.74)stamp('通过',x+297,401,.42+i*.74,red);
    });
  }
  const layouts={file,scene,meter,flight,vote};
  layouts[card.view]();
  const band='#1d2533';
  box(0,555,1280,165,band);
  box(0,555,1280,4,'#e9ad71');
  text(card.who,51,622,25,'#efb784',800);
  text(card.line,49,678,42,'#fff9ee',750);
  text('AI 合成  ·  合租事务所',1227,612,17,'#b8c4d3',550,'right');
  text(String(index+1).padStart(2,'0')+' / '+String(story.cards.length).padStart(2,'0'),1227,673,18,'#b8c4d3',550,'right');
};
