export function stageDisplayTitle(title: string) {
  return title.replace(/^(?:Day\s*0|宝藏[一二三四]|(?:能力)?评测[一二三])\s*[｜：]\s*/iu, "");
}
