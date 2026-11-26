// Rebuild the standalone editor with node projects/026_cover_crop_focus_lab/build-source.cjs
const fs = require('node:fs');
const path = require('node:path');
const { deliverables } = require('./brief.json');

const demo = path.join(__dirname, 'demo');
const template = fs.readFileSync(path.join(demo, 'index.html'), 'utf8');
const script = fs.readFileSync(path.join(demo, 'crop.js'), 'utf8');
const imagePath = '../assets/interview_original.jpg';
const scriptTag = '<script src="crop.js"></script>';
if (!template.includes(imagePath) || !template.includes(scriptTag)) {
  throw new Error('The editor template must reference crop.js and the interview image.');
}
const image = fs.readFileSync(path.resolve(demo, imagePath)).toString('base64');
const html = template
  .replace(scriptTag, () => '<script>\n' + script + '\n</script>')
  .replace(imagePath, () => 'data:image/jpeg;base64,' + image);

const output = path.join(__dirname, deliverables.offline_demo);
fs.mkdirSync(path.dirname(output), { recursive: true });
fs.writeFileSync(output, html);
