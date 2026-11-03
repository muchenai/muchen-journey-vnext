import { useEffect, useRef, useState } from "react";
import { ModulePanel } from "./ModuleShell";
import { JourneyDialogSurface } from "./JourneyDialogSurface";
import { type BadgeArtworkLevel } from "./badgeArtwork";
import {
  badgeCatalogCategories, badgeCatalogGroups, catalogDisplayLevel, filterBadgeCatalog, connectBadgeCatalog,
  type BadgeCatalogEntry, type BadgeCatalogGroup,
} from "./badgeCatalog";
import type { Badge, BadgeWallet } from "./badgeEconomy";
import "./badgeCatalog.css";
import { BadgeArtworkImage } from "./BadgeArtworkImage";

const appearances: { level: BadgeArtworkLevel; label: string; color: string }[] = [
  { level: 0, label: "未解锁", color: "灰色" }, { level: 1, label: "一级", color: "蓝色" },
  { level: 2, label: "二级", color: "紫色" }, { level: 3, label: "三级", color: "金色" },
];

export function BadgeCatalogGallery({ wallet, badges, query, onPublication }: {
  wallet: BadgeWallet;
  badges: Badge[];
  query: string;
  onPublication: (badge: Badge) => void;
}) {
  const [group, setGroup] = useState<BadgeCatalogGroup>("all");
  const [category, setCategory] = useState("all");
  const [preview, setPreview] = useState<BadgeCatalogEntry | null>(null);
  const [appearance, setAppearance] = useState<BadgeArtworkLevel>(0);
  const modal = useRef<HTMLDialogElement>(null);
  const grid = useRef<HTMLDivElement>(null);
  const badgeCatalogEntries = connectBadgeCatalog(badges, wallet.owned);
  const visible = filterBadgeCatalog(group, category, query, badgeCatalogEntries);
  const published = badgeCatalogEntries.filter(entry => entry.publication?.published).length;
  const categories = badgeCatalogCategories.filter(item => group === "all" || item.group === group);

  useEffect(() => {
    const element = modal.current;
    if (preview) element?.showModal();
    else element?.close();
    return () => element?.close();
  }, [preview]);
  useEffect(() => { grid.current?.scrollTo({ top: 0 }); }, [group, category, query]);

  return <div className="badge-catalog-gallery">
    <div className="badge-catalog-summary">
      <div><strong>{badgeCatalogEntries.length} 款完整图鉴</strong><span>{badgeCatalogCategories.length} 个类别 · 每款包含四种状态</span></div>
      <small>已发布 {published} 款 · 未上架 {badgeCatalogEntries.length - published} 款</small>
    </div>
    <div className="badge-catalog-groups" role="group" aria-label="徽章图鉴分组">
      {badgeCatalogGroups.map(item => <button key={item.id} className={group === item.id ? "is-active" : ""} aria-pressed={group === item.id}
        onClick={() => { setGroup(item.id); setCategory("all"); }}>
        {item.name}<span>{badgeCatalogEntries.filter(entry => item.id === "all" || entry.artwork.section === item.id).length}</span>
      </button>)}
    </div>
    <div className="badge-catalog-controls">
      <label>具体类别<select aria-label="徽章图鉴类别" value={category} onChange={event => setCategory(event.target.value)}>
        <option value="all">全部类别</option>{categories.map(item => <option key={item.id} value={item.id}>{item.name}</option>)}
      </select></label>
      <span role="status">匹配 {visible.length} 款{query && ` · 搜索“${query}”`}</span>
    </div>
    <p className="badge-catalog-state-note">未获得的徽章统一显示灰色；已获得按一级蓝、二级紫、三级金展示。待发布素材可预览外观，不能兑换。</p>
    <div ref={grid} className="badge-card-grid badge-artwork-grid" role="region" tabIndex={0} aria-label="全部徽章图鉴，可滚动浏览">
      {visible.map(entry => {
        const { artwork, publication } = entry;
        const level = catalogDisplayLevel(entry, wallet.owned);
        return <ModulePanel key={artwork.id} className="badge-card badge-catalog-artwork-card">
          <div className="badge-card-art" data-artwork-id={artwork.id}>
            <span className="badge-rarity">{appearances[level].label}{level > 0 && ` · ${appearances[level].color}`}</span>
            {!publication ? <span className="badge-catalog-pending-label">待发布</span> : level > 0 && <span className="badge-owned-label">已拥有</span>}
            <BadgeArtworkImage path={artwork.path} level={level} />
            <span className="badge-card-index">{artwork.id}</span>
          </div>
          <div className="badge-card-copy">
            <h3>{artwork.name}</h3><span className="badge-catalog-category">{artwork.categoryName}</span>
            <p>{artwork.description}</p>
            <small className="badge-catalog-publication">{publication ? `现有发布名：${publication.name}` : "素材已收录，兑换条件尚未配置"}</small>
            <div className="badge-card-bottom"><span>{publication ? "沿用现有兑换条件" : "暂不可兑换"}</span><button className="module-secondary"
              aria-label={`查看${artwork.name} · ${artwork.categoryName}`}
              onClick={() => {
                if (publication) onPublication(publication);
                else { setAppearance(0); setPreview(entry); }
              }}>{publication ? "查看详情" : "预览外观"}</button></div>
          </div>
        </ModulePanel>;
      })}
      {!visible.length && <div className="badge-catalog-no-results"><h3>没有匹配的徽章</h3><p>可以重置分类，或调整顶部搜索框中的关键词。</p><button className="module-secondary" onClick={() => { setGroup("all"); setCategory("all"); }}>重置分类</button></div>}
    </div>
    <dialog ref={modal} className="module-dialog journey-dialog badge-catalog-dialog" aria-labelledby="badge-catalog-preview-title" onCancel={() => setPreview(null)}>
      <JourneyDialogSurface>
        <div className="module-dialog-heading"><span className="badge-eyebrow">BADGE ARTWORK PREVIEW</span><button aria-label="关闭徽章外观预览" onClick={() => setPreview(null)}>关闭</button></div>
        {preview && <>
          <h2 id="badge-catalog-preview-title">{preview.artwork.name}</h2>
          <p className="badge-catalog-preview-category">{preview.artwork.sectionName} · {preview.artwork.categoryName}</p>
          <div className="badge-dialog-medal"><BadgeArtworkImage path={preview.artwork.path} level={appearance} large /></div>
          <div className="badge-preview-levels" role="group" aria-label="徽章外观状态预览">
            {appearances.map(item => <button key={item.level} data-preview-level={item.level} aria-pressed={appearance === item.level}
              className={`module-secondary${appearance === item.level ? " is-active" : ""}`} onClick={() => setAppearance(item.level)}>{item.label}<small>{item.color}</small></button>)}
          </div>
          <p className="badge-catalog-preview-description">{preview.artwork.description}</p>
          <div className="badge-catalog-preview-warning"><strong>仅预览外观，不代表已解锁</strong><p>该素材尚未配置发布者、兑换类型及数量。目前不能领取或兑换，预览不会扣点、发奖或授予认证。</p></div>
          <button className="module-secondary badge-catalog-unavailable" disabled>待发布 · 暂不可兑换</button>
        </>}
      </JourneyDialogSurface>
    </dialog>
  </div>;
}
