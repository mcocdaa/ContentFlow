/* Canvas coordinates are referenced to a 1920 × 1080 master. */
(() => {
  const sourceWidth = 1920, sourceHeight = 1080, cropWidth = 1440;
  const leftGuide = 460, rightGuide = 1790, centered = 240, chosen = 390;
  const ink = '#152d33', teal = '#006d65', cream = '#f9f5e9', amber = '#ffcb56';
  const red = '#ac3729', pale = '#d1e4dd', white = '#fffdf4';
  const clamp = x => Math.max(0, Math.min(1, x));
  const ease = x => { const v = clamp(x); return v*v*(3-2*v); };
  let master;
  function masterImage(img) {
    if (!master) master=window.coverCrop.wideMaster(img);
    return master;
  }
  const headings = ['哪张图，裁掉了星星？','A 的右边缘，放大看','先做一张横版母图','居中裁，少了哪两块？','把想留下的东西圈起来','裁框可以从哪里起步？','向右挪 150 像素','两份成图，一张参数卡'];
  const sections = ['盲选','揭晓','母图','居中','焦点','验算','重裁','导出'];
  // Shared with the separately delivered machine-readable narration timeline.
  const subtitles = [[0.25,4.35,"看右边的星星，哪张封面把它切掉了？"],[5,9.35,"暂停选 A 或 B，只看纸飞机和发饰。"],[10.25,14.75,"答案是 A。猫娘的脸还在，星星却被裁掉了。"],[15,19.3,"看两份裁图的右边缘，差别就在这儿。"],[20.25,24.25,"我们从这张宽屏原图重新裁一次。"],[25,29.35,"原图做成一九二零乘一零八零。"],[30.25,34.4,"高度不变，四比三的宽就是一四四零。"],[35,39.35,"剩下四百八十像素，居中就两边平分。"],[40.25,44.45,"先标出想留下的范围，左边从机翼开始。"],[45,49.3,"右边越过整颗星星，两端都留一点余量。"],[50.25,54.45,"左边界至少三百五十，才能装下星星。"],[55,59.35,"也别超过四百六十，否则会碰到机翼。"],[60.25,64.3,"我取三百九十，把裁框向右挪。"],[65,69.35,"宽高没变，原图也没拉伸，发饰完整了。"],[70.25,74.4,"横版保留全图，方一点的版本单独导出。"],[75,79.35,"收藏这张参数卡，下次把左右坐标换成你的。"]];
  function renderCard({ctx:c,art,index,local}) {
    const im=masterImage(art.source), sec=index*10+local, dark=index===1 || index===6;
    const bg=dark ? ink:cream, fg=dark?white:ink, muted=dark?pale:'#486469', accent=dark?amber:teal;
    function block(x,y,w,h,color){c.fillStyle=color;c.fillRect(x,y,w,h);}
    function border(x,y,w,h,color,lw=2){c.strokeStyle=color;c.lineWidth=lw;c.strokeRect(x,y,w,h);}
    function type(s,x,y,size,color=fg,bold=600,align='left'){
      c.font=bold+' '+size+'px "Noto Sans CJK SC",sans-serif'; c.textAlign=align; c.textBaseline='alphabetic'; c.fillStyle=color;c.fillText(s,x,y);
    }
    function rule(x,y,X,Y,color,lw=2){c.beginPath();c.moveTo(x,y);c.lineTo(X,Y);c.lineWidth=lw;c.strokeStyle=color;c.stroke();}
    function drawPart(sx,sy,sw,sh,x,y,w,h) {c.drawImage(im,sx,sy,sw,sh,x,y,w,h);}
    function card(crop,x,y,w,label,zoom=0){
      const h=w*.75;
      block(x+5,y+7,w,h,'#223b3460');
      if(zoom>0) {const sw=cropWidth+(390-cropWidth)*zoom, sh=sw*.75; drawPart(crop+cropWidth-sw,245*zoom,sw,sh,x,y,w,h);}
      else window.coverCrop.draw(c,im,crop,x,y,w,h);
      border(x,y,w,h,dark?'#c9dbd1':ink,2);
      block(x+10,y+10,46,40,ink);type(label,x+33,y+40,24,white,850,'center');
      return y+h;
    }
    function panelPhoto(x,y,w,offset=null,guides=false,visible=cropWidth){
      const h=w*9/16, k=w/sourceWidth;
      drawPart(0,0,sourceWidth,sourceHeight,x,y,w,h);
      if(offset!==null){
        block(x,y,k*offset,h,'rgba(12,30,34,.68)');
        block(x+k*(offset+visible),y,k*(sourceWidth-offset-visible),h,'rgba(12,30,34,.68)');
        border(x+k*offset,y+1,k*visible,h-2,amber,3);
      }
      if(guides){
        const left=index===4?leftGuide*ease(local/2.8):leftGuide;
        const right=index===4?sourceWidth+(rightGuide-sourceWidth)*ease((local-3.5)/2.8):rightGuide;
        for(const [s,tag] of [[left,'L'],[right,'R']]){
          const at=x+k*s;rule(at,y,at,y+h,white,5);rule(at,y,at,y+h,teal,2);
          block(at-16,y+h-35,32,34,teal);type(tag,at,y+h-9,20,white,800,'center');
        }
      }
      border(x,y,w,h,dark?pale:ink,2);
      return y+h;
    }
    function number(s,x,y,desc){type(s,x,y,40,accent,850);type(desc,x,y+38,23,muted,550);}
    function small(s,x,y){type(s,x,y,22,muted,600);}
    function rangeRow(y,a,b,color,label,progress){
      const x=122,w=975,k=w/sourceWidth;
      rule(x,y,x+w,y,dark?pale:'#a0b2a9',2);
      block(x+a*k,y-8,(b-a)*k*ease(progress),16,color);
      rule(x+a*k,y-14,x+a*k,y+16,fg,2);rule(x+b*k,y-14,x+b*k,y+16,fg,2);
      type(label,x,y-19,21,fg,650);
      type(String(a),x+a*k,y+42,20,fg,700,'center');type(String(b),x+b*k,y+42,20,fg,700,'center');
    }
    block(0,0,1280,720,bg);
    block(43,29,9,22,accent);type('封面裁图实验',64,48,19,muted,650);
    type(sections[index],1234,48,19,accent,750,'right');
    type(headings[index],44,104,42,fg,900);
    if(index===0 || index===1){
      const zoom=index===1?ease(local/2.5)*(1-ease((local-5.8)/2.7)):1-ease(local/2.9);
      const macro=index===1 && zoom>.5;
      const w=568,end=card(centered,45,138,w,'A',zoom);
      card(chosen,667,138,w,'B',zoom);
      if(index===0){small('暂停盲选',45,end+40);type('看发饰，也看机翼',1234,end+40,22,muted,600,'right');}
      else {
        type(macro?'右缘局部  ·  x = 1680':'居中裁  ·  右缘 x = 1680',45,end+40,24,amber,700);
        type(macro?'右缘局部  ·  x = 1830':'手动裁  ·  右缘 x = 1830',667,end+40,24,pale,700);
      }
    } else if(index===2){
      const w=754+70*ease(local/4);panelPhoto(44+(824-w)/2,147+(824-w)*.28125,w);
      number('16 : 9',900,223,'横版母图');number('1920',900,352,'宽度 / 像素');number('1080',900,480,'高度 / 像素');
      rule(898,540,1228,540,'#8ea19a');small('画面等比缩放',900,583);
    } else if(index===3){
      const amount=ease(local/4.8), offset=Math.round(centered*amount);
      const x=44,y=140,w=776,bottom=panelPhoto(x,y,w,offset,false,sourceWidth-2*offset);
      const scale=w/sourceWidth;
      for(const [start,end] of [[0,offset],[sourceWidth-offset,sourceWidth]]){
        const a=x+start*scale, b=x+end*scale;
        rule(a,bottom+12,b,bottom+12,teal,3);type(String(offset),(a+b)/2,bottom+39,19,teal,800,'center');
      }
      number('1440 × 1080',902,236,'4 : 3 成图');small('1080 × 4 ÷ 3',902,363);type('= 1440',902,416,36,teal,800);
      small('1920 − 1440 = 480',902,513);small('480 ÷ 2 = 240',902,560);
    } else if(index===4){
      panelPhoto(44,150,829,null,true);
      number('L = 460',906,239,'机翼左侧余量');number('R = 1790',906,378,'星星右侧余量');
      small('焦点总跨度',906,516);type('1330 像素',906,570,33,teal,800);
    } else if(index===5){
      rangeRow(185,leftGuide,rightGuide,teal,'须保留的范围',local/2.3);
      rangeRow(308,rightGuide-cropWidth,rightGuide,'#e1a52d','贴住最右焦点',(local-1.5)/3);
      rangeRow(431,leftGuide,leftGuide+cropWidth,'#e1a52d','贴住最左焦点',(local-4.4)/3.5);
      block(44,526,1190,80,ink);
      type('左边界可选',75,578,26,white,700);type('350  ≤  起点  ≤  460',345,582,37,amber,850);
      type('本图单位  px',1198,578,21,pale,600,'right');
    } else if(index===6){
      const v=ease((local-.65)/4.5), left=Math.round(centered+(chosen-centered)*v);
      panelPhoto(44,162,782,left,true);
      type('实时裁切结果',865,179,24,pale,700);
      const w=365;drawPart(left,0,cropWidth,sourceHeight,865,211,w,w*.75);border(865,211,w,w*.75,pale,2);
      type('X = '+left,865,552,38,amber,850);type('宽 1440   高 1080',865,600,21,pale,600);
    } else {
      const v=ease((local-2.5)/3), layerWidth=sourceWidth+(cropWidth-sourceWidth)*v;
      const h=318,w=h*layerWidth/sourceHeight,x=44+(565-w)/2;
      drawPart(chosen*v,0,layerWidth,sourceHeight,x,146,w,h);border(x,146,w,h,ink,2);
      type(v<.5?'横版':'裁切版',44,502,29,teal,850);small(v<.5?'1920 × 1080':'1440 × 1080',155,503);
      block(649,146,584,459,ink);
      type('4 : 3 裁切参数',676,202,34,white,850);
      rule(676,225,1206,225,'#668080');
      const rows=[['输入','1920 × 1080'],['裁框','1440 × 1080'],['左上角','(390, 0)'],['右边缘','x = 1830']];
      rows.forEach(([a,b],i)=>{const y=281+58*i;type(a,678,y,23,pale,600);type(b,1202,y,28,white,750,'right');});
      type('R − 裁框宽  ≤  起点  ≤  L',677,560,27,amber,800);
      small('L、R 为焦点左右边缘',44,567);small('本图起点须在 0～480 内',44,606);
    }
    const sub=subtitles.find(([start,stop])=>sec>=start && sec<stop);
    if(sub){
      c.font='700 27px "Noto Sans CJK SC",sans-serif';
      const w=Math.min(1200,c.measureText(sub[2]).width+52);
      block((1280-w)/2,636,w,53,'#132b2ff5');type(sub[2],640,672,27,white,700,'center');
    }
    block(0,711,1280,9,dark?'#3f595c':'#d7dace');block(0,711,1280*sec/80,9,dark?amber:teal);
  }
  window.story={sound:new URLSearchParams(location.search).has('export')?null:'assets/episode.wav',
    art:{source:'../../assets/interview_original.jpg'},cards:sections.map(tab=>({tab,seconds:10})),renderCard};
})();
