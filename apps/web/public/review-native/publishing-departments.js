// Business publishing departments are separate from Feishu directory membership and legacy task domains.
export const DEPARTMENT_GROUPS = [["职能部门", ["IT部", "人才开发部", "人才发展部", "客户增长与战略解决方案部", "人事运营与薪酬部", "财务法务合规部", "HRBP与组织发展部", "智能产品方案部", "PMO经营治理办公室", "行政与职场运营部", "总经办", "开发部"]], ["交付线部门", ["多语种数据交付线", "Agent交付与行为轨迹交付线", "代码推理交付线", "高质量数据构建交付线", "多模态数据交付线", "通用模型测评交付线", "方言语音交付线"]]];
export const PUBLISHING_DEPARTMENTS = DEPARTMENT_GROUPS.flatMap(([, names]) => names);
export const isPublishingDepartment = value => PUBLISHING_DEPARTMENTS.includes(value);
export const departmentLabel = value => isPublishingDepartment(value) ? value : '待补充部门';
export function departmentOptions(selected='', placeholder='请选择发布部门') {
  return `<option value="" disabled ${!isPublishingDepartment(selected)?'selected':''}>${placeholder}</option>` + DEPARTMENT_GROUPS.map(([group,names]) => `<optgroup label="${group}">${names.map(name=>`<option value="${name}" ${name===selected?'selected':''}>${name}</option>`).join('')}</optgroup>`).join('');
}
