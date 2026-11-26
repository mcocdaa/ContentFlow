// Use PLAYWRIGHT_MODULE and CHROMIUM_PATH for an existing browser installation.
const {spawn} = require('node:child_process');
const fs = require('node:fs/promises');
const path = require('node:path');
const {performance} = require('node:perf_hooks');
const {fileURLToPath, pathToFileURL} = require('node:url');

const fps = 60;
const usage = 'Usage: node scripts/render_motion_cards.cjs <index.html> <new-output.mp4> [startFrame endFrame]';

function frameRange(args) {
  if (!args.length) return null;
  if (args.length !== 2 || !args.every(s => /^\d+$/.test(s))) throw new Error(usage);
  const [start, end] = args.map(Number);
  if (!Number.isSafeInteger(start) || !Number.isSafeInteger(end) || end <= start) {
    throw new Error('Expected a nonempty [startFrame, endFrame) interval of safe integers');
  }
  return {start, end};
}

async function render(input, output, range) {
  const {chromium} = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
  await fs.access(input);
  const pageUrl = pathToFileURL(path.resolve(input));
  pageUrl.searchParams.set('export', '1');
  const dest = path.resolve(output);
  await fs.mkdir(path.dirname(dest), {recursive: true});
  try {
    await fs.lstat(dest);
    throw new Error('Output already exists: ' + dest);
  } catch (err) {
    if (err.code !== 'ENOENT') throw err;
  }
  const tempDir = await fs.mkdtemp(path.join(path.dirname(dest), '.motion-'));
  const tempVideo = path.join(tempDir, 'preview.mp4');
  const abort = new AbortController();
  let browser, encoder, closed;
  function stop(signal) {
    if (abort.signal.aborted) return;
    abort.abort(new Error('Render interrupted by ' + signal));
    process.exitCode = signal === 'SIGINT' ? 130 : 143;
    if (encoder && encoder.exitCode === null) encoder.kill('SIGTERM');
    if (browser) browser.close().catch(() => {});
  }
  const interrupt = () => stop('SIGINT');
  const terminate = () => stop('SIGTERM');
  process.on('SIGINT', interrupt);
  process.on('SIGTERM', terminate);
  try {
    browser = await chromium.launch({
      executablePath: process.env.CHROMIUM_PATH || undefined,
      args: ['--allow-file-access-from-files'],
      handleSIGINT: false, handleSIGTERM: false,
    });
    abort.signal.throwIfAborted();
    const page = await browser.newPage({viewport: {width: 1920, height: 1080}});
    await page.goto(pageUrl.href);
    const config = await page.evaluate(async () => {
      await window.motionCardsReady;
      return {duration: window.motionCards.duration, sound: window.story.sound};
    });
    const frames = Math.round(config.duration * fps);
    if (!Number.isSafeInteger(frames) || frames < 1) throw new Error('Invalid story duration');
    const {start, end} = range || {start: 0, end: frames};
    if (end > frames) throw new Error('Requested endFrame ' + end + ' exceeds the timeline of ' + frames + ' frames');
    const args = ['-nostdin', '-loglevel', 'error', '-f', 'image2pipe', '-framerate', String(fps), '-c:v', 'mjpeg', '-i', 'pipe:0'];
    if (!range && config.sound) {
      const audioFile = fileURLToPath(new URL(config.sound, pageUrl));
      await fs.access(audioFile);
      args.push('-i', audioFile, '-af', 'apad', '-c:a', 'aac', '-ar', '48000', '-ac', '2', '-b:a', '192k');
    }
    if (range) args.push('-an', '-frames:v', String(end-start));
    else args.push('-t', String(config.duration));
    args.push('-vf', 'scale=1920:1080:force_original_aspect_ratio=decrease:force_divisible_by=2:in_color_matrix=bt601:out_color_matrix=bt709:in_range=pc:out_range=tv,pad=1920:1080:(ow-iw)/2:(oh-ih)/2,setsar=1',
      '-c:v', 'libx264', '-preset', 'fast', '-threads', '2', '-crf', '17', '-pix_fmt', 'yuv420p',
      '-colorspace', 'bt709', '-color_primaries', 'bt709', '-color_trc', 'bt709', '-movflags', '+faststart', tempVideo);
    abort.signal.throwIfAborted();
    encoder = spawn('ffmpeg', args, {stdio: ['pipe', 'ignore', 'inherit']});
    closed = new Promise(resolve => {
      encoder.once('error', error => resolve({error}));
      encoder.once('close', (code, signal) => resolve({code, signal}));
    });
    // write callbacks also reject the current frame if the encoder closes its pipe.
    encoder.stdin.on('error', () => {});
    const began = performance.now();
    let nextLog = began + 10000;
    console.log('Rendering global frames [' + start + ', ' + end + ') of ' + frames);
    for (let i=start; i<end; i++) {
      abort.signal.throwIfAborted();
      const jpeg = await page.evaluate(t => {
        window.motionCards.draw(t);
        return document.querySelector('canvas').toDataURL('image/jpeg', 0.95).split(',')[1];
      }, i / fps);
      await new Promise((resolve, reject) => encoder.stdin.write(Buffer.from(jpeg, 'base64'), e => e ? reject(e) : resolve()));
      const now = performance.now();
      if (now >= nextLog) {
        const elapsed = (now-began)/1000, done = i-start+1;
        console.log('Frames ' + done + '/' + (end-start) + ', next global frame ' + (i+1) + ', elapsed ' + elapsed.toFixed(1) + 's, ' + (done/elapsed).toFixed(1) + ' frames/s');
        nextLog = now + 10000;
      }
    }
    encoder.stdin.end();
    const result = await closed;
    if (result.error) throw result.error;
    if (result.code !== 0) throw new Error('FFmpeg exited with ' + (result.signal || result.code));
    abort.signal.throwIfAborted();
    // Atomic publication avoids exposing unfinished MP4s or replacing a completed chunk.
    await fs.link(tempVideo, dest);
    console.log((end-start) + ' frames exported to ' + dest);
  } finally {
    try {
      if (encoder && encoder.exitCode === null && encoder.signalCode === null) {
        encoder.kill('SIGKILL');
        await closed;
      }
      if (browser) await browser.close();
    } finally {
      process.off('SIGINT', interrupt);
      process.off('SIGTERM', terminate);
      await fs.rm(tempDir, {recursive: true, force: true});
    }
  }
}

async function main() {
  const [input, output, ...bounds] = process.argv.slice(2);
  if (!input || !output) throw new Error(usage);
  await render(input, output, frameRange(bounds));
}
main().catch(err => { console.error(err.message); process.exitCode ||= 1; });
