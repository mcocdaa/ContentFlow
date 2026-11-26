// Use preview [start] [length], picture, boundaries, audio or check from any working directory.
const fs = require('node:fs');
const path = require('node:path');
const {spawnSync} = require('node:child_process');
const root = path.resolve(__dirname, '..');
const layout = require('./clock_layout.json');
const design = path.join(root, 'design');
const output = path.join(root, 'output');
const assets = path.join(design, 'episode', 'assets');
const {width, height, fps, duration_seconds:seconds, duration_frames:frames} = layout;
const mode = process.argv[2];

function ff(args) {
 const result=spawnSync(process.env.FFMPEG || 'ffmpeg', ['-hide_banner','-loglevel','warning','-nostdin','-y',...args],{stdio:'inherit'});
 if(result.error)throw result.error;
 if(result.status!==0)throw Error('FFmpeg exited '+result.status+(result.signal?' ('+result.signal+')':''));
}
// One still input and one filter chain per encoder. Only completed, probed segments are cached.
const crypto = require('node:crypto');
const segmentSeconds = 30;
function subtitlesTime(seconds) {
 const cs = Math.round(seconds*100);
 return Math.floor(cs/360000)+':'+String(Math.floor(cs/6000)%60).padStart(2,'0')+':'+
   String(Math.floor(cs/100)%60).padStart(2,'0')+'.'+String(cs%100).padStart(2,'0');
}
function seaPath(foam=false) {
 const upper = [];
 const lower = [];
 for(let x=0;x<=2240;x+=8) {
  const y = Math.round(39+13*Math.sin(x/175)+5*Math.sin(x/73+.4)+4*Math.sin(x/363));
  upper.push([x,y]);
  if(foam) lower.unshift([x,y+2]);
 }
 if(!foam)lower.push([2240,160],[0,160]);
 return 'm '+upper[0].join(' ')+' l '+upper.slice(1).concat(lower).flat().join(' ');
}
function disc(r) {
 const d=2*r,k=Number((r*.552285).toFixed(1)),lo=r-k,hi=r+k;
 return 'm '+r+' 0 b '+[hi,0,d,lo,d,r,d,hi,hi,d,r,d,lo,d,0,hi,0,r,0,lo,lo,0,r,0].join(' ');
}
function scaleProgress(t) {return Math.min(1,t/(seconds-1/fps));}
function sourceStage(t) {return layout.stages.find(stage=>t>=stage.start&&t<stage.end);}
function writeScene(segment, scenePath) {
 const {start,length} = segment;
 const lines = [
  '[Script Info]', 'ScriptType: v4.00+', 'PlayResX: 1920', 'PlayResY: 1080', 'ScaledBorderAndShadow: yes',
  '', '[V4+ Styles]',
  'Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding',
  'Style: T,Noto Sans CJK SC,28,&H00FFFFFF,&H00FFFFFF,&H00000000,&H00000000,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1',
  '', '[Events]', 'Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text'
 ];
 const sea=seaPath(),foam=seaPath(true);
 function vector(layer,a,b,x0,y0,x1,y1,bgr,alpha,shape,clip='') {
  const xy=[x0,y0,x1,y1].map(v=>Math.round(v*100)/100).join(',');
  const tags='{\\an7\\bord0\\shad0\\move('+xy+')\\1c&H'+bgr+'&\\1a&H'+alpha+'&'+clip+'\\p1}';
  lines.push('Dialogue: '+[layer,subtitlesTime(a),subtitlesTime(b),'T','','0','0','0','',tags+shape].join(','));
 }
 // Short linear spans approximate the slow tide; their endpoints share precisely the same global position.
 const tide = t=>[-155+65*Math.sin(t/14)+24*Math.sin(t/32),963+4*Math.sin(t/8)+2*Math.sin(t/22)];
 for(let a=0;a<length;a+=2) {
  const b=Math.min(length,a+2),[x0,y0]=tide(start+a),[x1,y1]=tide(start+b);
  vector(0,a,b,x0,y0,x1,y1,'7A7427','9B',sea);
  vector(1,a,b,x0,y0,x1,y1,'D5E7C1','B3',foam);
 }
 const pos=t=>185+920*scaleProgress(t);
 const from=pos(start),to=pos(start+length);
 vector(2,0,length,from-920,698,to-920,698,'787E17','00','m 0 0 l 920 0 920 12 0 12','\\clip(185,690,1105,720)');
 for(const [layer,r,bgr,alpha] of [[3,14,'94AF48','C8'],[4,7,'787E17','00'],[5,4,'D8F7DF','00']]) {
  vector(layer,0,length,from-r,704-r,to-r,704-r,bgr,alpha,disc(r));
 }
 fs.writeFileSync(scenePath,lines.join('\n')+'\n');
}
function segments(start,length) {
 if(!Number.isInteger(start)||!Number.isInteger(length)||start<0||length<=0||start+length>seconds)
  throw Error('Use integer seconds within the 600-second session.');
 const out=[];
 const end=start+length;
 while(start<end) {
  const stage=sourceStage(start);
  const stop=Math.min(end,stage.end,start+segmentSeconds);
  out.push({start,length:stop-start,base:stage.base});
  start=stop;
 }
 return out;
}
function remainingAt(frame) {return frame===frames-1?0:seconds-Math.floor(frame/fps);}
function packetCount(file,expected) {
 if(!fs.existsSync(file))return false;
 const result=spawnSync(process.env.FFPROBE || 'ffprobe',['-v','error','-select_streams','v:0','-count_packets',
  '-show_entries','stream=start_pts,width,height,codec_name,r_frame_rate,avg_frame_rate,sample_aspect_ratio,display_aspect_ratio,pix_fmt,color_space,color_transfer,color_primaries,time_base,duration_ts,nb_read_packets',
  '-of','json',file],{encoding:'utf8'});
 if(result.status!==0)return false;
 const s=JSON.parse(result.stdout).streams?.[0];
 if(!s||s.codec_name!=='h264'||s.width!==width||s.height!==height||s.start_pts!==0||
    s.sample_aspect_ratio!=='1:1'||s.display_aspect_ratio!=='16:9'||s.pix_fmt!=='yuv420p'||
    ![s.color_space,s.color_transfer,s.color_primaries].every(x=>x==='bt709'))return false;
 const [n,d]=s.time_base.split('/').map(Number);
 return s.r_frame_rate===fps+'/1'&&s.avg_frame_rate===fps+'/1'&&Number(s.nb_read_packets)===expected&&
   Number(s.duration_ts)*n*fps===expected*d;
}
const clockFont=process.env.CLOCK_FONT||'/usr/share/fonts/opentype/noto/NotoSansCJK-Bold.ttc';
function fingerprint() {
 const hash=crypto.createHash('sha256').update(fs.readFileSync(__filename));
 hash.update(fs.readFileSync(path.join(design,'clock_layout.json'))).update(fs.readFileSync(clockFont));
 for(const stage of layout.stages)hash.update(fs.readFileSync(stage.base));
 hash.update([process.env.ENCODER_PRESET||'veryfast',process.env.ENCODER_THREADS||'3'].join(':'));
 return hash.digest('hex').slice(0,16);
}
function encodeSegment(seg,cache) {
 const stem=path.join(cache,'part-'+String(seg.start).padStart(3,'0')+'-'+seg.length);
 const target=stem+'.mp4',expected=fps*seg.length;
 if(packetCount(target,expected)){console.log('Reuse '+target);return target;}
 writeScene(seg,stem+'.ass');
 const global='(n+'+(seg.start*fps)+')';
 const rem='if(gte('+global+','+(frames-1)+'),0,'+seconds+'-floor('+global+'/'+fps+'))';
 fs.writeFileSync(stem+'.clock','%{eif:floor(('+rem+')/60):d:2}:%{eif:mod('+rem+',60):d:2}');
 const filters=[
  // loop caches a single decoded still. All following timestamps are local to this segment.
  'loop=loop=-1:size=1:start=0','settb=1/'+fps,'setpts=N','setsar=1',
  'scale='+width+':'+height+':out_color_matrix=bt709:out_range=tv','format=yuv420p',
  'ass=filename='+stem+'.ass',
  'drawtext=fontfile='+clockFont+':textfile='+stem+'.clock:fontsize=168:fontcolor=0x164552:x=(643-text_w/2):y=\'478-text_h/2+26*pow(max(0,1-(t+'+seg.start+')/0.88),2)\''
 ].join(',');
 fs.writeFileSync(stem+'.filters',filters);
 console.log('Encode '+seg.start+'–'+(seg.start+seg.length)+'s');
 const temp=stem+'.new.mp4';
 ff(['-filter_threads','1','-framerate',String(fps),'-i',seg.base,'-filter_script:v',stem+'.filters','-frames:v',String(expected),
  '-r',String(fps),'-an','-c:v','libx264','-threads',process.env.ENCODER_THREADS||'3','-preset',process.env.ENCODER_PRESET||'veryfast',
  '-crf','17','-g','120','-vsync','cfr','-video_track_timescale','60000',
  '-color_primaries','bt709','-colorspace','bt709','-color_trc','bt709',temp]);
 if(!packetCount(temp,expected))throw Error('Segment failed CFR/duration/stream metadata validation: '+temp);
 fs.renameSync(temp,target);return target;
}
function picture(preview) {
 const start=preview?Number(process.argv[3]||0):0,length=preview?Number(process.argv[4]||3):seconds;
 if(preview&&length>30)throw Error('Preview limit is 30 seconds.');
 const runs=segments(start,length);
 const cache=path.join('output','timer_segments',fingerprint());fs.mkdirSync(cache,{recursive:true});
 const parts=runs.map(s=>encodeSegment(s,cache));
 const outputName=preview?'timer_preview_'+start+'_'+length:'timer_picture';
 const dest=path.join('output',outputName+'.mp4'),temp=path.join('output',outputName+'.new.mp4');
 if(parts.length===1)fs.copyFileSync(parts[0],temp);
 else{
  const list=path.join(cache,outputName+'.ffconcat');
  fs.writeFileSync(list,"ffconcat version 1.0\n"+parts.map(s=>"file '"+path.basename(s)+"'").join('\n')+'\n');
  ff(['-f','concat','-safe','0','-i',list,'-map','0:v:0','-an','-c:v','copy','-video_track_timescale','60000','-movflags','+faststart',temp]);
 }
 if(!packetCount(temp,length*fps))throw Error('Final packet/timestamp check failed.');
 fs.renameSync(temp,dest);console.log(dest);
}
function boundaries() {
 const dest=path.join(output,'clock_boundaries');fs.mkdirSync(dest,{recursive:true});
 for(const n of [0,3599,3600,25199,25200,32399,32400,35998,35999]){
  const seek=Math.max(0,n/fps-0.000001);
  const label=remainingAt(n);
  ff(['-ss',seek.toFixed(6),'-i','output/timer_picture.mp4','-frames:v','1','-threads','1','-update','1',
   path.join(dest,'frame_'+String(n).padStart(5,'0')+'_remaining_'+label+'.png')]);
 }
}
function audio() {
 const blocks=[];
 const noise=(filter,color,seed,chain)=>blocks.push('anoisesrc=r=48000:d='+seconds+':c='+color+':s='+seed+','+chain+'['+filter+']');
 // A common low surf bed anchors the stereo image. Higher breaking foam is independent at each ear.
 // Varying periods and phase modulation create swells without copying an audio loop.
 noise('bed','pink',2701,"highpass=f=42,lowpass=f=390,volume='0.60+0.22*sin(0.43*t+0.79*sin(0.093*t))+0.14*sin(0.227*t+0.4)':eval=frame");
 blocks.push('[bed]asplit=2[bedL][bedR]');
 for (const [side,seed,phase] of [['L',2737,0],['R',2763,.53]]) {
  const swell='(0.5+0.5*sin(0.49*t+'+phase+'+0.87*sin(0.073*t)+0.32*sin(0.185*t)))';
  const foam='(0.5+0.5*sin(0.51*t+'+(phase+.61)+'+1.1*sin(0.077*t)+0.29*sin(0.177*t)))';
  noise('surf'+side,'pink',seed,"highpass=f=125,lowpass=f=2700,volume='0.20+0.72*pow("+swell+",1.55)':eval=frame");
  noise('foam'+side,'white',seed+157,"highpass=f=660,lowpass=f=4050,volume='0.012+0.115*pow("+foam+",3.3)':eval=frame");
  blocks.push('[bed'+side+'][surf'+side+'][foam'+side+']amix=inputs=3:normalize=0:duration=shortest['+side+']');
 }
 blocks.push('[L][R]join=inputs=2:channel_layout=stereo:map=0.0-FL|1.0-FR,volume=0.73,afade=t=in:st=0:d=1.8,afade=t=out:st=596:d=4[out]');
 fs.writeFileSync(path.join(output,'ocean.filters'),blocks.join(';\n'));
 ff(['-filter_complex_threads','2','-filter_complex_script','output/ocean.filters','-map','[out]','-t',String(seconds),'-ar','48000','-ac','2','-c:a','pcm_s16le','design/episode/assets/ocean.tmp.wav']);
 fs.renameSync(path.join(assets,'ocean.tmp.wav'),path.join(assets,'episode.wav'));
}
function check() {
 const tc = remainingAt;
 for(const n of [0,1,59,60,3599,3600,25199,25200,32399,32400,35998,35999]){
  const left=tc(n),stage=layout.stages.find(s=>n/fps<s.end);
  console.log(String(n).padStart(5)+'  '+String(Math.floor(left/60)).padStart(2,'0')+':'+String(left%60).padStart(2,'0')+'  '+stage.label);
 }
 if(tc(0)!==600 || tc(35999)!==0 || layout.stages.at(-1).end!==seconds)throw Error('clock bounds');
}
module.exports = {segments, remainingAt, writeScene};
if(require.main===module){
 process.chdir(root);
 fs.mkdirSync(output,{recursive:true});fs.mkdirSync(assets,{recursive:true});
if(mode==='picture')picture(false);else if(mode==='preview')picture(true);else if(mode==='boundaries')boundaries();else if(mode==='audio')audio();else if(mode==='check')check();else throw Error('Use preview [start] [length], picture, boundaries, audio or check.');
}
