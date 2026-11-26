/* Both the tutorial and the interactive editor work on the same wide master. */
window.coverCrop = {
  wideMaster(img) {
    const out=document.createElement('canvas'); out.width=1920; out.height=1080;
    const ratio=out.width/out.height;
    const sw=Math.min(img.naturalWidth,img.naturalHeight*ratio), sh=sw/ratio;
    out.getContext('2d').drawImage(img,(img.naturalWidth-sw)/2,(img.naturalHeight-sh)/2,sw,sh,0,0,out.width,out.height);
    return out;
  },
  feasibleInterval(left,right) { return [Math.max(0,right-1440),Math.min(left,480)]; },
  draw(context,master,left,x,y,w,h) { context.drawImage(master,left,0,1440,1080,x,y,w,h); }
};
