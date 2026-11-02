import { useActionState, useEffect, useRef } from "react";
import { JourneyDialogSurface } from "./JourneyDialogSurface";
import { ModuleIcon } from "./ModuleShell";
import { logoutSession } from "../actions";
import "./accountSwitch.css";

export function AccountSwitchDialog({ open, onClose }: { open:boolean; onClose:()=>void }) {
  const dialog=useRef<HTMLDialogElement>(null);
  const [state,action,busy]=useActionState(logoutSession,{});
  useEffect(()=>{ const element=dialog.current; if(open)element?.showModal();else element?.close();return()=>element?.close() },[open]);
  return <dialog ref={dialog} className="module-dialog account-switch-dialog journey-dialog" aria-labelledby="account-switch-title" onCancel={onClose}>
    <JourneyDialogSurface>
      <div className="module-dialog-heading"><span className="badge-eyebrow">CHOOSE YOUR IDENTITY</span><button onClick={onClose} aria-label="关闭身份选择">关闭</button></div>
      <h2 id="account-switch-title">以哪种身份继续探索？</h2>
      <p>选择员工账号，继续成长；或前往 NPC 管理端。</p>
      <form className="account-switch-options" action={action}>
        <button type="submit" disabled={busy}><span className="account-switch-icon"><ModuleIcon file="a2a2a" size={26}/></span><span><strong>{busy?"正在退出…":"切换账号"}</strong><small>返回登录页，登录其他员工账号</small></span><span aria-hidden="true">→</span></button>
        <a href="/review" target="_blank" rel="noopener noreferrer"><span className="account-switch-icon"><ModuleIcon file="f4e78" size={26}/></span><span><strong>登录 NPC 管理端</strong><small>管理员入口 · 与学员端分开登录</small></span><span aria-hidden="true">↗</span></a>
      </form>
      {state.error&&<p role="alert" className="account-switch-notice">{state.error}</p>}
      <p className="account-switch-footnote">切换员工账号不会清除该身份已保存的任务进度。</p>
    </JourneyDialogSurface>
  </dialog>;
}
