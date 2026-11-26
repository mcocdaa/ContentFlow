(() => {
  const M = window.whaleMotion;
  const cream = '#f5f1e6', ink = '#143338', teal = '#08665e', coral = '#ad3b26';
  const scenes = [
    ['先猜一张','哪张图真的透明？','把两张图放到同一块底板上。','A / 左图','B / 右图'],
    ['揭晓','换一块底板，看格子去哪了','扫过的是舞台底色，两张素材保持不动。','A / 透明图层','B / 棋盘已经烤进图片'],
    ['取材','先认清设定图和动画素材','原图用来核对造型，再选一张透明单人像。','社区素材入口 / 网页导览','本次使用 / 正面透明立绘'],
    ['取样','点一个像素，读出透明度','A 通道从 0 到 255，分别表示完全透明和完全不透明。'],
    ['边缘','发丝边缘，为何看起来柔和？','放大图中的像素；A 值取自原 PNG 的同一坐标。'],
    ['等比','框可以变宽，人物始终等比','两边使用同一张 370 × 1033 立绘。虚线标出容器，宽框留出侧边空间。','按原图比例定宽','更宽的框 / 两侧留白'],
    ['上浮','只写起点和终点','同一张图，上浮 8 个 CSS 像素。'],
    ['缓动','怎样让它在最高点慢下来？','从零到八，再从八回到零。水平刻度表示时间。'],
    ['支点','把旋转轴移到脚底','为了看清差异，本组将演示角度放大到 10°。','绕中心旋转','绕脚底旋转'],
    ['图层','整张图转了，发梢单独动了吗？','两枚标记跟随同一张平面图。'],
    ['顺序','先画谁，谁就待在下面','两个框执行相同的画图指令，只交换先后。','底色 → 角色','角色 → 底色'],
    ['状态','只让鲸鱼娘旋转','用 save 和 restore 圈住角色绘制，再画水平参考线。'],
    ['换景','背景交叉淡入，人物保持清晰','先填满蓝底，橙色覆盖比例逐步增加，最后画人。'],
    ['修错','忘记还原透明度，会怎样？','把同一段绘制程序停在背景覆盖 50% 的位置。','透明度泄漏 / 50%','背景画完就 restore()'],
    ['回看','把同一秒画两遍','左框冻结参考帧，右框拨走，再回到同一秒。','参考帧 / 01.00 秒','可拖动的时间轴'],
    ['动手','换一张自己的 PNG','示例可以本地选择图片、读取像素、暂停和拖动进度。'],
    ['验收','动起来以后，再做三次检查','换底色、查比例、回到同一帧。'],
    ['导出','要继续换底色，留下哪份？','源 PNG 和 HTML 留着；普通 H.264 视频会把当时的背景一起录下。','网页里的透明源图','导出的画面示意'],
  ];
  let inspector, flat;
  const fixed = {rise:0, angle:0};
  function rect(c,x,y,w,h,color){ c.fillStyle=color; c.fillRect(x,y,w,h); }
  function type(c,t,x,y,size,color=ink,weight=600,align='left') {
    c.fillStyle=color; c.textAlign=align; c.textBaseline='alphabetic';
    c.font=weight+' '+size+'px "Noto Sans CJK SC",sans-serif'; c.fillText(t,x,y);
  }
  function mono(c,t,x,y,size=19,color='#d9f5eb') {
    c.textAlign='left'; c.fillStyle=color; c.textBaseline='alphabetic';
    c.font='500 '+size+'px "Noto Sans Mono CJK SC","DejaVu Sans Mono",monospace'; c.fillText(t,x,y);
  }
  function line(c,x,y,x2,y2,color,w=2) {
    c.beginPath(); c.moveTo(x,y);c.lineTo(x2,y2);c.lineWidth=w;c.strokeStyle=color;c.stroke();
  }
  function mark(c,x,y,text,color) {
    c.fillStyle=color; c.beginPath(); c.arc(x,y,6,0,2*Math.PI);c.fill();
    line(c,x,y,x+23,y-22,color); if(text)type(c,text,x+29,y-19,18,color,800);
  }
  function hint(c,t,x,y) {
    c.font='650 18px "Noto Sans CJK SC",sans-serif';
    const w=c.measureText(t).width+27;
    rect(c,x,y-26,w,35,cream); type(c,t,x+13,y,18,ink,650);
  }
  function wrap(c,s,width,size) {
    c.font='600 '+size+'px "Noto Sans CJK SC",sans-serif';
    const lines=[];let row='';
    for(const ch of s) {
      if(row && c.measureText(row+ch).width>width){lines.push(row);row='';}
      row+=ch;
    }
    if(row)lines.push(row);
    return lines;
  }
  function clipped(c,x,y,w,h,fn) {
    c.save();c.beginPath();c.rect(x,y,w,h);c.clip();fn();c.restore();
  }
  function checkerFixture(img) {
    if(flat) return flat;
    const surface=document.createElement('canvas');surface.width=img.naturalWidth;surface.height=img.naturalHeight;
    const brush=surface.getContext('2d');M.checkers(brush,0,0,surface.width,surface.height,44);
    brush.drawImage(img,0,0);
    // Round-trip the opaque control as a real PNG. Its grid is now image data.
    const control=new Image(); control.src=surface.toDataURL('image/png');
    flat=surface;
    control.decode().then(()=>{flat=control;}).catch(()=>{});
    return flat;
  }
  function panels(c,s,painter) {
    [57,655].forEach((x,i)=>{
      clipped(c,x,183,568,347,()=>painter(x,i));
      type(c,s[3+i],x,566,23,ink,800);
    });
  }
  function backdrop(c,x,withGrid,t) {
    if(withGrid)M.checkers(c,x,183,568,347,16);
    else M.background(c,x,183,568,347,t);
  }
  function comparison(c,img,s,n,t) {
    panels(c,s,(x,i)=>{
      const cx=x+284,feet=511,h=303;
      if(n<2){
        backdrop(c,x,true);
        if(n===1)rect(c,x,183,568*Math.min(1,t/2),347,M.orange);
        if(i===1){const f=checkerFixture(img);c.drawImage(f,cx-h*img.naturalWidth/img.naturalHeight/2,feet-h,h*img.naturalWidth/img.naturalHeight,h);}
        else M.sprite(c,img,cx,feet,h,fixed);
        if(n===0){
          const labels=['仔细看裙边','如果换成橙色？','最后一次下注'];
          hint(c,labels[Math.min(2,Math.floor(t/3.4))],x+16,221);
          rect(c,x,520,568*t/10,10,teal);
        }
      } else if(n===5){
        backdrop(c,x,false,.25);
        const imageWidth=h*img.naturalWidth/img.naturalHeight;
        const boxWidth=i===0?imageWidth:295;
        rect(c,cx-boxWidth/2,feet-h,boxWidth,h,'#f9f5e9');
        c.save();c.strokeStyle=teal;c.lineWidth=2;c.setLineDash([6,4]);
        c.strokeRect(cx-boxWidth/2,feet-h,boxWidth,h);c.restore();
        M.sprite(c,img,cx,feet,h,fixed);
        if(i===1){
          const start=cx-boxWidth/2+8,end=cx-imageWidth/2-5;
          line(c,start,feet-70,end,feet-70,teal);
          line(c,2*cx-end,feet-70,2*cx-start,feet-70,teal);
        }
        hint(c,i===0?'width: auto':'object-fit: contain',x+18,220);
      } else if(n===8){
        backdrop(c,x,false,.2);
        const center=i===0?feet-h/2:feet;
        line(c,x+30,feet,x+538,feet,ink,1);line(c,cx,190,cx,518,'#5a8488',1);
        M.sprite(c,img,cx,feet,h,{rise:0,angle:Math.sin(t*1.35)*Math.PI/18},i===0?'center':'feet');
        mark(c,cx,center,'支点',coral);
      } else if(n===10){
        backdrop(c,x,false,0);M.sprite(c,img,cx,feet,h,fixed);
        if(i===1){const sweep=Math.min(1,t/1.5);rect(c,x,183,568*sweep,347,M.blue);}
      } else if(n===13){
        backdrop(c,x,false,.5);
        M.sprite(c,img,cx,feet,h,M.pose(t),'feet',i===0?.5:1);
        hint(c,i===0?'globalAlpha = 0.5':'globalAlpha = 1',x+16,220);
      } else if(n===14){
        const clock=i===0?1:t<3?1: t<6?1+(t-3)*.8: t<8?3.4-(t-6)*1.2:1;
        backdrop(c,x,false,Math.min(clock/4,1));M.sprite(c,img,cx,feet,h,M.pose(clock));
        hint(c,clock.toFixed(2)+' s',x+18,220);
      } else {
        const mix=i===0?(Math.sin(t*1.2)+1)/2:.55;
        backdrop(c,x,false,mix);M.sprite(c,img,cx,feet,h,M.pose(i===0?t:1));
        hint(c,i===0?'可换底色':'颜色已合成',x+18,220);
      }
    });
  }
  function refScene(c,art,s) {
    panels(c,s,(x,i)=>{
      rect(c,x,183,568,347,i===0?'#fffdf8':M.blue);
      if(i===0){
        rect(c,x,183,568,347,'#e6e9dc');
        type(c,'鲸鱼娘开源资产库',x+28,247,34,ink,850);
        c.drawImage(art.icon,x+441,192,90,90);
        type(c,'首页  /  两套造型参考',x+28,292,22,teal);
        rect(c,x+28,317,220,50,ink);type(c,'Q 版鲸鱼娘',x+42,351,22,cream);
        rect(c,x+268,317,270,50,teal);type(c,'成熟比例鲸鱼娘',x+282,351,22,cream);
        type(c,'头像取自站内收录的桌宠项目',x+28,418,21,ink);
        mono(c,'treapgogo.github.io/',x+28,466,19,teal);
        mono(c,'deepseek-whale-girl/',x+28,493,19,teal);
      } else M.sprite(c,art.whale,x+284,515,316,fixed);
    });
  }
  function pixel(c,img,n,t) {
    if(!inspector)inspector=M.sampler(img);
    const [px,py]=n===4?[55,250]:(t<4?[0,0]:[180,200]);
    const a=inspector(px,py)[3], x=80,y=194,h=347,w=h*img.naturalWidth/img.naturalHeight;
    rect(c,57,182,545,357,M.blue);
    const actualX=x+125;
    c.drawImage(img,actualX,y,w,h);
    mark(c,actualX+px/img.naturalWidth*w,y+py/img.naturalHeight*h,'取样点',coral);
    rect(c,626,182,593,357,ink);
    type(c,'原图像素',651,225,23,'#cfebe3',700);
    mono(c,'x = '+px+'     y = '+py,651,266,24);
    mono(c,'A = '+a,647,373,81,'#ffcc89');
    mono(c,'getImageData(x, y, 1, 1)',651,442,23);
    mono(c,'.data[3]',651,475,23);
    const edgeX=400,edgeY=267;
    M.checkers(c,edgeX,edgeY,146,146,13);
    c.save();c.imageSmoothingEnabled=false;
    clipped(c,edgeX,edgeY,146,146,()=>{
      c.drawImage(img,Math.max(0,px-5),Math.max(0,py-5),11,11,edgeX,edgeY,146,146);
    });c.restore();
    type(c,'像素放大',edgeX,445,19,ink);
  }
  const code = {
    6:['.whale {','  height: 300px;','  width: auto;','  animation: up 2s ease-in-out','             infinite alternate;','}','@keyframes up {','  to { transform: translateY(-8px); }','}'],
    7:['animation-duration: 2s;','animation-direction: alternate;','animation-timing-function:','  ease-in-out;','animation-iteration-count:','  infinite;'],
    9:['角色图层 × 1','旋转与位移一起作用于整张图','发梢  ●────────●  脸','两点的距离保持不变'],
    11:['ctx.save();','ctx.translate(x, feetY);','ctx.rotate(angle);','ctx.drawImage(img,','  -w / 2, -h, w, h);','ctx.restore();'],
    12:['fill(blue);','ctx.save();','ctx.globalAlpha = mix;','fill(orange);','ctx.restore();','drawWhale();'],
    15:['1   选择本地 PNG','2   点图读取 RGBA','3   选背景、播放或拖动','4   换自己的素材再试一次'],
    16:['检查 1    换底色，边缘干净？','检查 2    宽高比等于原图？','检查 3    同秒回放一致？'],
  };
  function teaching(c,img,n,t) {
    const x=57,y=184,w=609,h=355;
    M.background(c,x,y,w,h,n===12?Math.min(1,t/7):n===16?(Math.sin(t*1.1)+1)/2:.17);
    const feet=498,height=273,cx=334;
    const pose=M.pose(t);
    const current=n===6||n===7?{rise:pose.rise,angle:0}:n===16&&t>6.6?M.pose(1):pose;
    if(n===11||n===9)current.angle=Math.sin(t)*.088;
    if(n===15||n===16)M.checkers(c,70,197,96,73,12);
    line(c,97,feet,cx+246,feet,'#567979',1);
    M.sprite(c,img,cx,feet,height,current);
    if(n===9) {
      c.save();c.translate(cx,feet-current.rise);c.rotate(current.angle);
      const ax=-28,ay=-180,bx=3,by=-216;
      line(c,ax,ay,bx,by,coral,3);mark(c,ax,ay,'',coral);mark(c,bx,by,'',coral);c.restore();
    } else if(n===11) mark(c,cx,feet,'脚底坐标',coral);
    else if(n===12)hint(c,'橙色覆盖 '+Math.round(Math.min(1,t/7)*100)+'%',79,227);
    else if(n===7||n===6){
      hint(c,'上浮 '+pose.rise.toFixed(1)+' px',78,224);
      for(let i=0;i<=8;i+=2)line(c,480,feet-i*8,492,feet-i*8,teal,2);
      mark(c,487,feet-pose.rise*8,'8× 刻度',coral);
    } else if(n===16)hint(c,['边缘','比例 370 : 1033','时刻 01.00 秒'][Math.min(2,Math.floor(t/3.3))],76,227);
    else if(n===15)hint(c,'本地文件 / whale.png',78,225);
    rect(c,687,y,532,h,ink);
    const rows=code[n], rowGap=rows.length>7?29:39;
    type(c,n===15?'在示例里动手':n===16?'验收单':n===9?'图层检查':'正在运行的绘制步骤',710,221,22,'#a9e4ce',700);
    rows.forEach((row,i)=>mono(c,row,710,264+i*rowGap,rows.length>7?20:21,i===Math.floor(t/10*rows.length)?'#ffbc7e':'#e3f4e9'));
  }
  window.drawWhaleLesson=({ctx:c,art,card,index:n,local:t})=>{
    const s=scenes[n];
    rect(c,0,0,1280,720,cream);rect(c,0,0,1280,67,ink);
    type(c,'透明像素实验室',55,44,26,'#f7f3e9',800);
    type(c,'鲸鱼娘  /  PNG 动画课',293,43,18,'#a6d9cf');
    type(c,String(n+1).padStart(2,'0')+'   /   18',1220,44,22,'#a6d9cf',700,'right');
    type(c,s[1],55,137,49,ink,900);
    type(c,s[2],58,169,18,teal,600);
    if([0,1,5,8,10,13,14,17].includes(n))comparison(c,art.whale,s,n,t);
    else if(n===2)refScene(c,art,s);
    else if(n===3||n===4)pixel(c,art.whale,n,t);
    else teaching(c,art.whale,n,t);
    rect(c,0,589,1280,131,ink);
    type(c,s[0],57,632,18,'#9ddac9',800);
    const words=n===5?card.text.match(/[^。]+。?/g):wrap(c,card.text,918,27);
    words.forEach((row,i)=>type(c,row,170,639+i*37,27,'#fff9ea',600));
    rect(c,0,712,1280*(n*10+t)/180,8,'#ffa56f');
  };
})();
