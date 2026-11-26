// The lesson, the interactive demo and the exported video use the same functions.
(() => {
  const blue = '#92cadd';
  const orange = '#ffac70';
  function pose(seconds) {
    const phase = (1 - Math.cos(Math.PI * seconds / 2)) / 2;
    return {rise: 8 * phase, angle: (phase * 2 - 1) * 3 * Math.PI / 180};
  }
  function background(ctx, x, y, w, h, mix) {
    ctx.save();
    ctx.fillStyle = blue;
    ctx.fillRect(x, y, w, h);
    ctx.globalAlpha = Math.max(0, Math.min(1, mix));
    ctx.fillStyle = orange;
    ctx.fillRect(x, y, w, h);
    ctx.restore();
  }
  function sprite(ctx, img, feetX, feetY, height, motion, pivot = 'feet', opacity = 1) {
    const width = height * img.naturalWidth / img.naturalHeight;
    const anchorY = pivot === 'feet' ? height : height / 2;
    ctx.save();
    ctx.globalAlpha *= opacity;
    ctx.translate(feetX, feetY - height + anchorY - motion.rise);
    ctx.rotate(motion.angle);
    ctx.drawImage(img, -width / 2, -anchorY, width, height);
    ctx.restore();
  }
  function checkers(ctx, x, y, w, h, pitch = 15) {
    ctx.save();
    ctx.beginPath(); ctx.rect(x, y, w, h); ctx.clip();
    ctx.fillStyle = '#f1f2e9'; ctx.fillRect(x, y, w, h);
    ctx.fillStyle = '#bcc2b9';
    for (let row = 0; row < h / pitch; row++)
      for (let col = row % 2; col < w / pitch; col += 2)
        ctx.fillRect(x + col * pitch, y + row * pitch, pitch, pitch);
    ctx.restore();
  }
  function sampler(img) {
    const plane = document.createElement('canvas');
    plane.width = img.naturalWidth; plane.height = img.naturalHeight;
    const brush = plane.getContext('2d', {willReadFrequently: true});
    brush.drawImage(img, 0, 0);
    return (x, y) => Array.from(brush.getImageData(x, y, 1, 1).data);
  }
  window.whaleMotion = {pose, background, sprite, checkers, sampler, blue, orange};
})();
