// Each pair is one act. The second shot answers the first speaker.
const cuts = [
  {view:'file', art:'meeting', tag:'初面 / 通知', title:['老板，','您被淘汰了。'], note:'应聘岗位　人类老板', stamp:'退回', who:'弱音', line:'老板，您被淘汰了。'},
  {view:'scene', art:'meeting', focus:[.51,.46,1.12], tag:'初面 / 候选席', who:'老板', line:'等会儿，我才刚坐下啊！'},
  {view:'scene', art:'meeting', focus:[.82,.43,1.67], tag:'初面 / 配置核查', who:'猫娘', line:'三个人用一台电脑？'},
  {view:'meter', art:'meeting', figure:24, names:['剪片','直播','开饭'], caption:'一台电脑，三个人排班。', tag:'初面 / 硬件清单', who:'老板', line:'二十四个 G，错峰上班。'},
  {view:'scene', art:'mid', focus:[.22,.31,1.62], tag:'初面 / 福利考官', who:'大肥鱼', line:'她剪片，我就得下班？'},
  {view:'scene', art:'mid', focus:[.82,.48,1.76], tag:'初面 / 增长考官', who:'猫娘', line:'你一开饭，我就掉帧。'},
  {view:'file', art:'mid', tag:'退件 / 人事决定', title:['这份简历，','请您签收。'], note:'投递方式　航空快递', stamp:'退件', who:'弱音', line:'简历退给您，请签收。'},
  {view:'flight', tag:'退件 / 航空快递', who:'老板', line:'你们管这叫航空快递？'},
  {view:'file', art:'end', tag:'复试 / 再投一次', title:['等一下！','还有第二份。'], note:'申请材料　硬件增配单', stamp:'复试', who:'老板', line:'等等，我换一份简历！'},
  {view:'meter', art:'end', figure:64, names:['剪片','直播','余量'], caption:'这次，大家可以一起开工。', tag:'复试 / 硬件清单', who:'猫娘', line:'这回写了六十四个 G。'},
  {view:'scene', art:'meeting', focus:[.21,.53,1.55], tag:'复试 / 最后一问', who:'大肥鱼', line:'最后一项，员工餐呢？'},
  {view:'file', art:'end', tag:'复试 / 员工餐', title:['米饭管够。','锅也管够。'], note:'福利清单　电饭锅一台', stamp:'包饭', who:'老板', line:'米饭管够，电饭锅归你。'},
  {view:'vote', art:'meeting', approvals:['硬件','伙食','福利'], tag:'终审 / 会签', who:'弱音', line:'内存过关，伙食过关。'},
  {view:'file', art:'end', tag:'终审 / 录用通知', title:['三票同意。','欢迎入职！'], note:'面试结果　全票通过', stamp:'录用', who:'猫娘', line:'三票同意，老板请入职。'},
  {view:'scene', art:'end', focus:[.51,.42,1.03], tag:'入职 / 第一天', who:'老板', line:'我上班第一件事做什么？'},
  {view:'scene', art:'end', focus:[.23,.46,1.99], tag:'入职 / 第一项工作', endNote:'今日待办　淘米', who:'大肥鱼', line:'先淘米。锅在你手边。'},
];
window.story = {
  // The master assembler supplies the normalized soundtrack after picture export.
  sound:new URLSearchParams(location.search).has('export') ? null : 'assets/episode.wav',
  series:'合租事务所', issue:'人事档案 024', renderCard:window.drawDialogueCard,
  art:{meeting:'../../assets/keyframes/kf_hero_interview_16x9.jpg',mid:'../../assets/keyframes/kf_mid_airplane_16x9.jpg',end:'../../assets/keyframes/kf_finale_64g_16x9.jpg',plane:'../../../../library/props/folded_resume_plane.png'},
  cards:cuts.map(c=>({...c,seconds:4.25})),
};
