const fs = require('node:fs');
const path = require('node:path');
const {pathToFileURL} = require('node:url');
const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const root = path.resolve(__dirname, '..');
const opts = {headless:true};
if (process.env.CHROMIUM_PATH) opts.executablePath = process.env.CHROMIUM_PATH;

(async () => {
 const browser = await chromium.launch(opts);
 try {
  const page = await browser.newPage({viewport:{width:1920,height:1080},deviceScaleFactor:1});
  await page.goto(pathToFileURL(path.join(root,'鲸鱼专注钟.html')).href+'?export');
  await page.evaluate(() => window.FocusTimer.ready);
  const output = path.join(root,'output'), delivery = path.join(root,'delivery');
  fs.mkdirSync(output,{recursive:true});
  fs.mkdirSync(delivery,{recursive:true});
  for(let i=0;i<4;i++){
   await page.evaluate(i=>window.FocusTimer.renderBase(i),i);
   await page.screenshot({path:path.join(output,'base_'+i+'.png')});
  }
  await page.evaluate(()=>window.FocusTimer.renderAt(0));
  await page.screenshot({path:path.join(output,'clock_preview.png')});
  const covers = await page.evaluate(() => {
   window.FocusTimer.renderCover();
   const wide = document.querySelector('canvas');
   const narrow = document.createElement('canvas');
   narrow.width = 1440; narrow.height = 1080;
   narrow.getContext('2d').drawImage(wide, 240, 0, 1440, 1080, 0, 0, 1440, 1080);
   return [wide, narrow].map(canvas => canvas.toDataURL('image/jpeg', .96).split(',')[1]);
  });
  for (const [i, name] of ['鲸鱼专注钟_cover.jpg', '鲸鱼专注钟_cover_4x3.jpg'].entries()) {
   fs.writeFileSync(path.join(delivery, name), Buffer.from(covers[i], 'base64'));
  }
  await page.goto(pathToFileURL(path.join(root,'鲸鱼专注钟.html')).href);
  await page.getByRole('button',{name:'开始专注'}).click();
  await page.getByRole('button',{name:'暂停'}).click();
  await page.getByRole('button',{name:'继续专注'}).click();
  await page.getByRole('button',{name:'重新计时'}).click();
  if (!await page.getByRole('button',{name:'开始专注'}).isVisible()) throw new Error('reset failed');
  const times=await page.evaluate(()=>[0,59,60,420,540,599.9,600-1/60,600].map(t=>[t,FocusTimer.digits(t)]));
  console.log(JSON.stringify(times));
 } finally {await browser.close();}
})().catch(e=>{console.error(e);process.exitCode=1});
