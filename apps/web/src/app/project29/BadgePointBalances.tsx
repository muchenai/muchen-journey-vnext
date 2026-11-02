import { badgePointLabel, badgePointTypes, type BadgeWallet } from "./badgeEconomy";
import { ModuleIcon } from "./ModuleShell";

export function BadgePointBalances({ balances, compact = false }: {
  balances: BadgeWallet["balances"];
  compact?: boolean;
}) {
  return <div className={`badge-point-balances${compact ? " is-compact" : ""}`} role="region" tabIndex={0} aria-label="18 种独立徽章点余额，可滚动查看">
    {badgePointTypes.map(type => <div key={type} className="badge-point-balance">
      <span><ModuleIcon file="a03b5" pack="guild" size={12} />{badgePointLabel(type)}</span>
      <strong>{balances[type] ?? 0}</strong>
    </div>)}
  </div>;
}
