export const previewIdentities = ["111", "222", "333"] as const;
export type PreviewIdentity = string;

let activeIdentity: PreviewIdentity | null = null;

export function setPreviewIdentity(identity: PreviewIdentity | null) {
  activeIdentity = identity;
}

function identityKey(key: string) {
  return `muchen-preview-${activeIdentity ?? "guest"}:${key}`;
}

// Keep drafts, submissions, material states and self-checks isolated per preview identity.
export const previewStorage = {
  getItem(key: string) { return localStorage.getItem(identityKey(key)); },
  setItem(key: string, value: string) { localStorage.setItem(identityKey(key), value); },
  removeItem(key: string) { localStorage.removeItem(identityKey(key)); },
};
