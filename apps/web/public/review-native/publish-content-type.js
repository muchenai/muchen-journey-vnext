const courseReward = {label:'整套课程奖励', unit:'套', hint:'看完所有章节的全部视频后，一次性发放。纯图文课程学完全部材料后发放。填 0 表示不发经验。'};
const taskReward = {label:'任务奖励', unit:'项', hint:''};

export const publicationReward = (scope, required) => scope === 'village' && !required ? taskReward : courseReward;

export function renderVillagePublishType(active, busy = false) {
  const choices = [['required','必修课程','全员学习，完成必修后解锁普通任务'],['elective','普通任务','领取任务，按要求提交成果']];
  return `<div class="form-field full village-publish-type">
    <div class="village-publish-heading"><span id="village-publish-label" class="field-label">发布类型</span>
    </div>
    <div class="village-publish-options" role="radiogroup" aria-labelledby="village-publish-label">
    ${choices.map(([kind,title,note])=>`<label class="village-publish-option">
      <input type="radio" name="village-course-kind" data-publish-kind="${kind}" value="${kind}" ${active===kind?'checked':''} ${busy?'disabled':''}>
      <span><strong>${title}</strong><span>${note}</span></span></label>`).join('')}
    </div></div>`;
}
