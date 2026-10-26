import { useEffect, useRef, useState, type ReactNode } from "react";

export function WelcomeNameDialog({ open, decoration, onSave }: {
  open: boolean;
  decoration: ReactNode;
  onSave: (name: string) => Promise<{ error?: string }>;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const [name, setName] = useState("");
  const [error, setError] = useState("");
  const [saving, setSaving] = useState(false);
  const savingRef = useRef(false);

  useEffect(() => {
    const element = dialog.current;
    if (open && !element?.open) element?.showModal();
    if (!open) element?.close();
    return () => { element?.close(); };
  }, [open]);

  return <dialog ref={dialog} className="module-dialog welcome-name-dialog figma-stroke"
    aria-labelledby="welcome-name-title" aria-describedby="welcome-name-description"
    onCancel={event => event.preventDefault()}>
    {decoration}
    <form onSubmit={async event => {
      event.preventDefault();
      if (savingRef.current) return;
      const value = name.trim();
      if (!value) { setError("请输入您的真实姓名"); return; }
      savingRef.current = true;
      setSaving(true);
      setError("");
      try {
        const result = await onSave(value);
        if (result?.error) setError(result.error);
      }
      catch { setError("姓名保存失败，请稍后重试。"); }
      finally { savingRef.current = false; setSaving(false); }
    }}>
      <div className="welcome-name-kicker">MUCHEN JOURNEY · 探索启程</div>
      <div className="welcome-name-emblem" aria-hidden="true">
        <img src="/assets/project29/82501.webp" alt="" />
      </div>
      <h2 id="welcome-name-title">欢迎加入探索营</h2>
      <p id="welcome-name-description">每一段成长，都从认识你开始。<br />请输入您的真实姓名，开启这次探索旅程。</p>
      <label className="module-field welcome-name-field" htmlFor="welcome-real-name">
        真实姓名 <span>必填</span>
        <input id="welcome-real-name" name="realName" autoComplete="name" autoFocus
          placeholder="请输入您的真实姓名" maxLength={40} required value={name} disabled={saving}
          aria-invalid={Boolean(error)} aria-describedby="welcome-name-error welcome-name-note"
          onChange={event => { setName(event.target.value); setError(""); }} />
      </label>
      <div id="welcome-name-error" className="welcome-name-error" role="status">{error}</div>
      <button type="submit" className="module-primary welcome-name-submit" disabled={saving}>{saving ? "正在保存…" : "确认姓名，进入探索营"} <span aria-hidden="true">→</span></button>
      <p id="welcome-name-note" className="welcome-name-note">姓名将保存至当前账号，再次登录无需重复填写。</p>
    </form>
  </dialog>;
}
