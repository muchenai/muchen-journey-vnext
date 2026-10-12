// Owner-supplied learner destinations, 2026-10-12. Keep content versions and
// completion keys intact: this catalog changes only the URLs opened by the UI.
export const explorationLinks: Record<string, { materials: readonly [string, string]; taskDetails: string }> = {
  "DAY-0": {
    materials: [
      "https://zx6w57w0j34.feishu.cn/wiki/MpxDwemUwiOY0fk9jM5cqRYRn3b",
      "https://zx6w57w0j34.feishu.cn/wiki/YpaGw0EgqidJUykHcqxcLgCvnvc",
    ],
    taskDetails: "https://zx6w57w0j34.feishu.cn/docx/B9f2d0P0ior6UBxTeFRc2ELmnlg",
  },
  "TRE-001-COMPANY-VALUES": {
    materials: [
      "https://zx6w57w0j34.feishu.cn/wiki/TUV1wbptdiXmapkfDsOcRrvknme",
      "https://zx6w57w0j34.feishu.cn/file/PewIbRCP3oDKAIx7MS9cSqUMnod",
    ],
    taskDetails: "https://zx6w57w0j34.feishu.cn/docx/N1CmdNwvtoF6ubxGGK6cztvnnpg",
  },
  "TRE-002-AI-DATA-BASICS": {
    materials: [
      "https://zx6w57w0j34.feishu.cn/docx/EDm2dFzmco58SJx10Xeceo0WnIc",
      "https://zx6w57w0j34.feishu.cn/docx/SYzrd6dS2oUd2Sx70dqcNcqOn9f",
    ],
    taskDetails: "https://zx6w57w0j34.feishu.cn/docx/B9uhdkLwUoqqIYxeh9TcWErbnHd",
  },
  "TRE-003-PROJECT-AWARENESS": {
    materials: [
      "https://zx6w57w0j34.feishu.cn/docx/HDoidinI9oTlmzxw5H7cqQbqnCF",
      "https://zx6w57w0j34.feishu.cn/file/QcEqbZ3NlolbaTxvmc0cZNeYnvc",
    ],
    taskDetails: "https://zx6w57w0j34.feishu.cn/docx/Tsq7daDoIoPhNoxXBDbcTMaRnEc?from=from_parent_sheet",
  },
  "TRE-004-DELIVERY-FIT": {
    materials: [
      "https://zx6w57w0j34.feishu.cn/wiki/Lu9ZwEM9kij7fdk7eOMcInNenld",
      "https://zx6w57w0j34.feishu.cn/minutes/obcnk5wa15l826747rlb55rr",
    ],
    taskDetails: "https://zx6w57w0j34.feishu.cn/docx/StsEdbAXzorBNUxxX89cQPgcnyg",
  },
  "ASM-001-RULE-BREAKDOWN": {
    materials: [
      "https://zx6w57w0j34.feishu.cn/wiki/Fxccw68nAipuM3kK8gJcqiyDnRJ",
      "https://zx6w57w0j34.feishu.cn/minutes/obcnk68g8j32fn4f8af53752",
    ],
    taskDetails: "https://zx6w57w0j34.feishu.cn/wiki/WEXlw0EoPizH2FkLx4ccCsvnngc?from=from_parent_sheet",
  },
  "ASM-002-MODEL-JUDGEMENT": {
    materials: [
      "https://zx6w57w0j34.feishu.cn/docx/NbGRdVd6aolCDRxkmodcHoMLnlg",
      "https://zx6w57w0j34.feishu.cn/minutes/obcnj65w46z681x365gyo3wu",
    ],
    taskDetails: "https://zx6w57w0j34.feishu.cn/docx/KEe7dazYooA2J2x0zPUcGhshnhb",
  },
  "ASM-003-DATA-CONSTRUCTION": {
    materials: [
      "https://zx6w57w0j34.feishu.cn/docx/Hx8HdBHYmoSFOexbyoxc9A3dn0c",
      "https://lcnf4xe7p1h6.feishu.cn/minutes/obcnk1s9uh3y25xle6723aq3",
    ],
    taskDetails: "https://zx6w57w0j34.feishu.cn/docx/JGyrdojJEoFSGuxxfULc46gfnvd?from=from_parent_sheet",
  },
};

export function learnerMaterialDestinations<T extends { url: string | null }>(stageKey: string, materials: T[]): T[] {
  const links = explorationLinks[stageKey];
  if (!links || materials.length !== 2) return materials;
  return materials.map((material, index) => ({ ...material, url: links.materials[index] }));
}
