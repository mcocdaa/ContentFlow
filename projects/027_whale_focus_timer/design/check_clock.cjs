// Pure timing / scene-contract tests. No encoder, browser or image decoder.
const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const os = require('node:os');
const {segments, remainingAt, writeScene} = require('./render_media.cjs');

test('all 36,000 frames are assigned exactly one stage and a continuous countdown', () => {
 const plan=segments(0,600);
 assert.equal(plan.length,20);
 let frame=0, previous=600;
 for(const seg of plan){
  assert.equal(seg.start*60,frame);
  assert.equal(seg.length,30);
  for(let n=0;n<seg.length*60;n++,frame++){
   const stage=frame<3600?0:frame<25200?1:frame<32400?2:3;
   assert.equal(seg.base,'output/base_'+stage+'.png');
   const now=remainingAt(frame);
   assert.ok(previous-now===0 || previous-now===1);
   previous=now;
  }
 }
 assert.equal(frame,36000);
 assert.deepEqual([0,3599,3600,25199,25200,32399,32400,35998,35999].map(remainingAt),
    [600,541,540,181,180,61,60,1,0]);
});
test('a preview crossing a page turn splits at its exact authored boundary',()=>{
 assert.deepEqual(segments(419,3).map(({start,length,base})=>[start,length,base]),[
    [419,1,'output/base_1.png'],[420,2,'output/base_2.png']]);
 assert.throws(()=>segments(599,3));
});
test('vector tide and progress use global phase on either side of a segment join',()=>{
 const temp=fs.mkdtempSync(path.join(os.tmpdir(),'cf027-clock-'));
 try{
  const [a,b]=segments(30,60);
  const displacements=seg=>{
   const file=path.join(temp,seg.start+'.ass');writeScene(seg,file);
   const lines=fs.readFileSync(file,'utf8').split('\n').filter(s=>s.startsWith('Dialogue:'));
   return index=>lines.filter(s=>s.startsWith('Dialogue: '+index+',')).map(s=>s.match(/\\move\(([^)]+)\)/)[1].split(',').map(Number));
  };
  const left=displacements(a),right=displacements(b);
  for(const layer of [0,1,2,3,4,5])assert.deepEqual(left(layer).at(-1).slice(2),right(layer)[0].slice(0,2));
 }finally{fs.rmSync(temp,{recursive:true,force:true})}
});
