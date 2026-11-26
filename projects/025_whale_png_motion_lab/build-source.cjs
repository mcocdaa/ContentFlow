// Prepare offline inputs. Usage: node projects/025_whale_png_motion_lab/build-source.cjs
const fs = require('node:fs');
const path = require('node:path');
const root = __dirname;
const episode = path.join(root, 'design/episode');
const cues = JSON.parse(fs.readFileSync(path.join(episode, 'narration.json'), 'utf8'));
fs.writeFileSync(path.join(episode, 'narration-data.js'),
  'window.lessonCaptions = ' + JSON.stringify(cues.map(({text}) => ({text})), null, 2) + ';\n');
const demo = path.join(root, 'demo');
let html = fs.readFileSync(path.join(demo, 'index.html'), 'utf8');
const script = fs.readFileSync(path.join(demo,'motion.js'),'utf8');
html = html.replace('<script src="motion.js"></script>', () => '<script>\n'+script+'\n</script>');
for (const relative of ['../../../library/characters/deepseek_dafeiyu/dafeiyu_canonical_front_cutout.png','../assets/whale-pet-front.png']) {
  const data = fs.readFileSync(path.resolve(demo, relative)).toString('base64');
  html = html.replace(relative, ()=>'data:image/png;base64,'+data);
}
fs.mkdirSync(path.join(root,'delivery'), {recursive:true});
fs.writeFileSync(path.join(root,'delivery','鲸鱼娘透明像素实验室.html'),html);
