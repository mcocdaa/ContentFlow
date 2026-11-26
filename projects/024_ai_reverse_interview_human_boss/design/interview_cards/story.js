// All asset paths are relative to index.html. Each card's duration is in seconds.
window.story = {
  series: '合租事务所',
  issue: '人事档案  /  024',
  sound: 'assets/foley.wav',
  art: {
    meeting: '../../assets/keyframes/kf_hero_interview_16x9.jpg',
    finale: '../../assets/keyframes/kf_finale_64g_16x9.jpg',
    prop: '../../../../library/props/folded_resume_plane.png',
  },
  cards: [
    {
      layout: 'interview', seconds: 6, tab: '初面', label: '面试通知',
      headline: ['老板，', '您被淘汰了。'],
      quote: '“给三个 AI 配一台 24 GB 的电脑？”',
      credit: '面试官  /  弱音', photo: 'meeting',
      caption: '人类老板应聘现场', decision: '退回',
    },
    {
      layout: 'object', seconds: 6, tab: '退件', label: '退件记录',
      headline: ['您的简历', '已原路飞回。'],
      quote: '“下次记得把内存写清楚。”',
      credit: '福利考官  /  大肥鱼', prop: 'prop',
      caption: '折叠简历  ·  一张 A4 纸',
    },
    {
      layout: 'offer', seconds: 6, tab: '复试', label: '录用通知',
      headline: ['老板，', '欢迎入职。'],
      terms: [['内存', '64 GB'], ['伙食', '白米饭管够']],
      quote: '“这位老板，我们三个都同意。”',
      photo: 'finale', caption: '复试当天  /  三票通过', decision: '录用',
    },
  ],
};
