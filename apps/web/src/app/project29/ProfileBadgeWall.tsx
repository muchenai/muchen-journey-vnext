import { ModuleIcon, ModulePanel } from "./ModuleShell";
import { Medal } from "./BadgeShop";
import { badgeArtworkFor, badgeGrades } from "./badgeArtwork";
import type { Badge } from "./badgeEconomy";

const previewLimit = 6;

export function ProfileBadgeWall({ badges, error, onRetry, onShop, onOwned }: {
  badges: Badge[] | null;
  error: string;
  onRetry: () => void;
  onShop: () => void;
  onOwned: () => void;
}) {
  return <ModulePanel className="profile-badge-panel">
    <div className="profile-section-heading">
      <div><span className="badge-eyebrow">MY BADGE COLLECTION</span><h2>我的徽章墙</h2><p>这是属于你的成长收藏。</p></div>
      <button data-page-navigation className="module-secondary" onClick={onShop}>前往徽章商城 →</button>
    </div>
    {error && <div className="profile-badge-error" role="alert">
      <span>{badges ? "刷新未完成，当前显示上次读取的徽章。" : "徽章读取失败，请重试。"}</span>
      <button className="module-secondary" onClick={onRetry}>重新加载</button>
    </div>}
    {badges === null ? !error && <div className="profile-badge-empty" role="status">正在读取已拥有徽章…</div> : <>
      <div className="profile-collection-toolbar"><span>已获得 {badges.length.toLocaleString("zh-CN")} 枚徽章</span></div>
      {badges.length === 0 ? <div className="profile-badge-empty">
        <ModuleIcon file="a03b5" pack="guild" size={40}/><h3>你还没有获得徽章</h3>
        <p>完成任务积累徽章点，前往徽章商城兑换你的第一枚徽章。</p>
      </div> : <ul className="profile-badge-grid" aria-label="已拥有徽章预览">
        {badges.slice(0, previewLimit).map(badge => <li className="profile-badge-item" key={badge.id}>
          <div className="profile-badge-art" data-tone={badge.tone}><Medal badge={badge}/></div>
          <h3>{badge.name}</h3><span className="module-tag">{badgeArtworkFor(badge) ? badgeGrades[badge.tone].label : badge.level}</span>
        </li>)}
      </ul>}
      {badges.length > previewLimit && <div className="profile-collection-footer">
        <span>展示最近获得的 {previewLimit} 枚徽章</span>
        <button data-page-navigation className="module-secondary" onClick={onOwned}>查看全部 →</button>
      </div>}
    </>}
  </ModulePanel>;
}
