// Runtime opt-in: production remains closed even if the preview flag is copied.
export function localVillagePreviewEnabled(environment: Record<string, string | undefined> = process.env) {
  return environment.APP_ENV === "local" && environment.LOCAL_VILLAGE_PREVIEW === "true";
}
