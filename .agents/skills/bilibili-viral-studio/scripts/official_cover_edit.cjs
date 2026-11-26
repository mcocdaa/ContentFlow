// Install on the owner's existing Playwright page before using the official editor.
// This module never opens a session, uploads a file, clicks submit or constructs an edit POST.
const fs = require('node:fs');
const path = require('node:path');
const { createHash } = require('node:crypto');

const member = 'https://member.bilibili.com';
const editPath = '/x/vu/web/edit';
const digest = value => createHash('sha256').update(value).digest('hex');
const read = file => JSON.parse(fs.readFileSync(file, 'utf8'));
class GuardError extends Error {}
const requireTrue = (condition, message) => { if (!condition) throw new GuardError(message); };
const normalized = value => String(value ?? '').replace(/\s+/gu, ' ').trim();
const nativeLines = value => String(value ?? '').replace(/\r\n?/g, '\n');
const tags = value => String(value || '').split(',').sort();
const parts = videos => (videos || []).map(v => [Number(v.cid), v.filename || '', v.title || '', v.desc || '']);
const scalarId = obj => Number(typeof obj === 'object' && obj !== null ? obj.id : obj);

function protectedFields(archive, videos, elec) {
  return {
    aid: Number(archive.aid), dtime: Number(archive.dtime),
    title: archive.title, desc: normalized(archive.desc), tags: tags(archive.tag),
    category: scalarId(archive.human_type2), legacyTid: Number(archive.tid),
    statement: scalarId(archive.creation_statement), copyright: Number(archive.copyright),
    noReprint: Number(archive.no_reprint), elec: Number(elec), videos: parts(videos),
    dynamic: normalized(archive.dynamic), topic: Number(archive.topic_id || 0), mission: Number(archive.mission_id || 0),
    interactive: Number(archive.interactive || 0),
  };
}

function checkPayload(payload, baseline) {
  // The official form omits open_elec when disabled; only a confirmed zero can use that default.
  const current = protectedFields(payload, payload.videos, payload.open_elec ?? 0);
  const changed = Object.keys(baseline).filter(k => JSON.stringify(current[k]) !== JSON.stringify(baseline[k]));
  requireTrue(!changed.length, '原稿字段变化：' + changed.join(', '));
  requireTrue(Number(payload.new_web_edit) === 1 && baseline.videos.length > 0 && baseline.videos.every(v => v[0] > 0),
    '编辑态或分P身份无法确认');
  requireTrue(baseline.dtime > Date.now() / 1000, '原排期已过');
}

function reviseCredits(description, witness) {
  const {from, to} = witness;
  requireTrue([from, to].every(s => typeof s === 'string' && s.trim() && !/[\r\n]/.test(s)) &&
    from !== to && !to.trimStart().startsWith('【'), '借物表改动需两条不同的完整单行');
  const lines = nativeLines(description).split('\n');
  const start = lines.findIndex(s => /^\s*【借物表/.test(s));
  const nextHeading = lines.findIndex((s, i) => i > start && /^\s*【/.test(s));
  const index = lines.indexOf(from);
  requireTrue(start >= 0 && index > start && (nextHeading === -1 || index < nextHeading) &&
    lines.lastIndexOf(from) === index && !lines.includes(to), '原借物表必须恰含一次旧整行，且尚无新整行');
  lines[index] = to;
  return lines.join('\n');
}

function publicCover(value) {
  const u = new URL(value, member);
  requireTrue(['https:', 'http:'].includes(u.protocol) && !u.username && !u.password && !u.port &&
    /^(?:[a-z\d-]+\.)+(?:hdslb|biliimg)\.com$/i.test(u.hostname) && u.pathname.startsWith('/bfs/'), '封面来源未知');
  return 'https://' + u.hostname + u.pathname;
}

function save(file, record) {
  const tmp = file + '.tmp';
  const fd = fs.openSync(tmp, 'w', 0o600);
  try {
    fs.writeFileSync(fd, JSON.stringify(record, null, 2) + '\n');
    fs.fsyncSync(fd);
  } finally { fs.closeSync(fd); }
  fs.renameSync(tmp, file);
  const parent = fs.openSync(path.dirname(file), 'r');
  try { fs.fsyncSync(parent); } finally { fs.closeSync(parent); }
}

async function coverDistance(page, url, bytes, aspect) {
  const result = await page.request.get(publicCover(url), { headers: {Cookie: ''}, maxRedirects: 0, timeout: 15000 });
  requireTrue(result.status() === 200, '公开 CDN 未提供封面');
  const remote = await result.body();
  requireTrue(remote.length < 10_000_000 && remote.length > 0, '线上图片大小异常');
  const metrics = await page.evaluate(async ({remote, local, aspect}) => {
    const bitmaps = await Promise.all([remote, local].map(async b64 => {
      const bytes = Uint8Array.from(atob(b64), c => c.charCodeAt(0));
      return createImageBitmap(new Blob([bytes]));
    }));
    try {
      const validRatios = bitmaps.every(b => Math.abs(b.width / b.height - aspect) < 0.01);
      if (!validRatios) return { validRatios, mae: null };
      const canvas = document.createElement('canvas');
      canvas.width = 192; canvas.height = Math.round(192 / aspect);
      const ctx = canvas.getContext('2d', {willReadFrequently: true});
      const [a, b] = bitmaps.map(bitmap => {
        ctx.drawImage(bitmap, 0, 0, canvas.width, canvas.height);
        return ctx.getImageData(0, 0, canvas.width, canvas.height).data;
      });
      let total = 0;
      for (let i = 0; i < a.length; i++) if (i % 4 !== 3) total += Math.abs(a[i] - b[i]);
      return {validRatios, mae: Number((total / (canvas.width * canvas.height * 3)).toFixed(4))};
    } finally { bitmaps.forEach(b => b.close()); }
  }, {remote: remote.toString('base64'), local: bytes.toString('base64'), aspect});
  return {...metrics, remote_sha256: digest(remote)};
}

async function installCoverEditGuard(page, project, bvid, {execute = false, revisedCredits = null} = {}) {
  project = path.resolve(project);
  const verified = read(path.join(project, 'delivery/bilibili_verify_receipt.json'));
  requireTrue(verified.status === 'verified' && verified.bvid === bvid && verified.aid > 0, '需要原稿已核验的 BVID/AID');
  const dir = path.join(project, 'output/creator-reconciliation');
  const receipt = path.join(dir, 'official-cover-edit.json');
  const {deliverables} = read(path.join(project, 'brief.json'));
  const local = [deliverables.cover_16x9, deliverables.cover_4x3].map(f => fs.readFileSync(path.resolve(project, f)));
  const sourceHashes = local.map(digest);
  const getDetails = async () => {
    const r = await page.request.get(member + '/x/vupre/web/archive/view', {params: {aid: verified.aid}, maxRedirects: 0});
    const j = await r.json();
    const data = j.data;
    requireTrue(r.status() === 200 && j.code === 0 && data?.archive?.bvid === bvid &&
      Number(data.archive.aid) === verified.aid, '现网稿号不符或不可读取');
    const fields = protectedFields(data.archive, data.videos, data.arc_elec?.state);
    requireTrue(fields.dtime === verified.requested_dtime && fields.statement === verified.creation_statement_id &&
      fields.category === verified.human_type2_id && fields.noReprint === 0 && fields.elec === 0, '原稿排期或合规设置已变动');
    return { fields, description: data.archive.desc, urls: [data.archive.cover, data.archive.cover43].map(publicCover) };
  };
  const start = await getDetails();
  const signature = fields => digest(JSON.stringify(fields));
  const baseline = signature(start.fields);
  let sent = false, claimed = false;
  const audit = async urls => {
    const measured = [];
    for (const [i, aspect] of [16 / 9, 4 / 3].entries()) {
      const measurement = await coverDistance(page, urls[i], local[i], aspect);
      requireTrue(measurement.validRatios && measurement.mae <= 6, i ? '4:3 线上图与验收图不符' : '16:9 线上图与验收图不符');
      measured.push(measurement);
    }
    return measured;
  };
  // Install before navigating to the edit form; any new-archive or UPOS action is an error for this operation.
  const handler = async route => {
    const req = route.request();
    const u = new URL(req.url());
    if (u.origin !== member) return route.fallback();
    if (u.pathname === '/preupload') return route.abort('blockedbyclient');
    if (['GET','HEAD','OPTIONS'].includes(req.method())) return route.fallback();
    if (u.pathname === '/x/vu/web/cover/up') return execute ? route.fallback() : route.abort('blockedbyclient');
    if (u.pathname !== editPath) {
      if (/\/(?:add|submit|edit|update|del|delete|revoke|withdraw)(?:\/|$)/.test(u.pathname)) return route.abort('blockedbyclient');
      return route.fallback();
    }
    // All local failures must abort the intercepted POST. Never retry a POST after the adapter received it.
    if (!execute || claimed || req.method() !== 'POST') return route.abort('blockedbyclient');
    claimed = true;
    try {
      const prior = fs.existsSync(receipt) ? read(receipt) : {};
      requireTrue(!prior.status || (prior.status === 'verified' &&
        JSON.stringify(prior.source_sha256) !== JSON.stringify(sourceHashes)), '该封面版本已有编辑记录，请先核对原稿');
      const fresh = await getDetails();
      requireTrue(signature(fresh.fields) === baseline && JSON.stringify(fresh.urls) === JSON.stringify(start.urls), '编辑期间现网稿件已改变');
      const q = req.postDataJSON();
      const expectedDescription = revisedCredits ? reviseCredits(fresh.description, revisedCredits) : null;
      const target = expectedDescription === null ? fresh.fields : {...fresh.fields, desc: normalized(expectedDescription)};
      checkPayload(q, target);
      if (revisedCredits) requireTrue(nativeLines(q.desc) === expectedDescription, '借物表之外的字符或换行已变化');
      const urls = [q.cover, q.cover43].map(publicCover);
      requireTrue(urls.every((s,i) => new URL(s).pathname !== new URL(fresh.urls[i]).pathname), '两张替换图尚未齐全');
      const metrics = await audit(urls);
      const record = {status:'pending', aid:verified.aid, bvid, baseline, expected:signature(target),
        source_sha256:sourceHashes, submitted_covers:metrics};
      if (revisedCredits) record.revised_credits = {from_sha256:digest(revisedCredits.from),
        to_sha256:digest(revisedCredits.to), expected_description_sha256:digest(expectedDescription)};
      save(receipt, record);
      sent = true;
    } catch (error) {
      claimed = false;
      console.error('封面编辑已在本机拦截。', error instanceof GuardError ? error.message : '平台回读、编辑包或图片暂不可核验');
      return route.abort('blockedbyclient');
    }
    return route.continue();
  };
  await page.route('https://member.bilibili.com/**', handler);
  page.on('response', async response => {
    const u = new URL(response.url());
    if (!sent || u.origin !== member || u.pathname !== editPath || response.request().method() !== 'POST') return;
    try {
      const record = read(receipt);
      if (record.status !== 'pending') return;
      const reply = await response.json();
      if (response.status() >= 500 || !Number.isInteger(reply.code) ||
        (reply.data?.bvid && reply.data.bvid !== bvid) ||
        (reply.data?.aid && Number(reply.data.aid) !== verified.aid)) return;
      save(receipt, {...record, status:reply.code === 0 ? 'accepted' : 'rejected', code:reply.code, http:response.status()});
    } catch { /* An unreadable response keeps the pending receipt. */ }
  });
  return {
    editUrl: member + '/platform/upload/video/frame?type=edit&bvid=' + encodeURIComponent(bvid),
    verify: async () => {
      const r = read(receipt);
      requireTrue(r.bvid === bvid && ['pending','accepted','verified'].includes(r.status) &&
        JSON.stringify(r.source_sha256) === JSON.stringify(sourceHashes), '没有对应封面版本的待核对回执');
      const now = await getDetails();
      requireTrue(signature(now.fields) === (r.expected || r.baseline), '更新后原稿受保护字段不符');
      if (r.revised_credits) requireTrue(digest(nativeLines(now.description)) === r.revised_credits.expected_description_sha256,
        '更新后简介出现额外字符或换行差异');
      const metrics = await audit(now.urls);
      requireTrue(metrics.every((v,i) => v.remote_sha256 === r.submitted_covers[i].remote_sha256), '平台尚未回显新封面');
      save(receipt, {...r, status:'verified', checked_at:new Date().toISOString(), readback_covers:metrics});
      return {bvid, status:'verified', covers:metrics};
    },
  };
}

module.exports = {installCoverEditGuard, protectedFields, checkPayload, reviseCredits};
