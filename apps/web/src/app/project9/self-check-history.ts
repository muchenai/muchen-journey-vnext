export type SelfCheckRecord = {
  id: string;
  createdAt: string;
  body: string;
  result: string;
};

type HistoryStorage = Pick<Storage, "getItem" | "setItem">;

// Assignment IDs belong to one learner and one stage; names are not identity keys.
export function selfCheckHistoryKey(assignmentId: string, taskVersion: number) {
  return `journey:self-check:v1:${assignmentId}:${taskVersion}`;
}

export function readSelfCheckHistory(storage: HistoryStorage, key: string): SelfCheckRecord[] {
  const raw = storage.getItem(key);
  if (raw === null) return [];
  const records: unknown = JSON.parse(raw);
  if (!Array.isArray(records) || !records.every(item =>
    item && typeof item.id === "string" && typeof item.createdAt === "string"
    && Number.isFinite(Date.parse(item.createdAt)) && typeof item.body === "string"
    && typeof item.result === "string"
  )) throw new Error("Invalid self-check history");
  return records;
}

export function saveSelfCheck(storage: HistoryStorage, key: string, entry: SelfCheckRecord) {
  const records = [entry, ...readSelfCheckHistory(storage, key)];
  storage.setItem(key, JSON.stringify(records));
  return records;
}
