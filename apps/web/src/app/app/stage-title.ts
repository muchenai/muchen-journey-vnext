export function stageUserFacingTitle(title: string) {
  return title.replace(/^Day\s*0\b/iu, "Day 1");
}

export function stageDisplayTitle(title: string) {
  return stageUserFacingTitle(title).replace(/^(?:Day\s*1|宝藏[一二三四]|(?:能力)?评测[一二三])\s*[｜：]\s*/iu, "");
}
