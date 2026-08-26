import styles from "./private-invite-orientation.module.css";
import journeyProduct from "@/lib/muchen-journey-product.generated.json";
import controlledRelease from "@/lib/muchen-journey-controlled-release.generated.json";

export type OrientationPhase = "VERIFY_INVITE" | "CONFIRM_IDENTITY" | "REENTRY";

const PHASE_COPY: Record<OrientationPhase, { now: string; next: string }> = {
  VERIFY_INVITE: {
    now: "验证专属邀请",
    next: "打开第一份必读材料",
  },
  CONFIRM_IDENTITY: {
    now: "确认这是你的邀请",
    next: "进入探索营第一站",
  },
  REENTRY: {
    now: "确认邀请并恢复进度",
    next: "继续当前一站",
  },
};

const CONTROLLED_MODULE_KEYS = new Set<string>(controlledRelease.modules);
const INVITE_ROUTE = journeyProduct.maps
  .filter((map) => CONTROLLED_MODULE_KEYS.has(map.key))
  .map((map) => map.name);

export function PrivateInviteOrientation({
  phase,
  descriptionId,
}: {
  phase: OrientationPhase;
  descriptionId: string;
}) {
  const copy = PHASE_COPY[phase];

  return (
    <aside id={descriptionId} className={styles.orientation} aria-labelledby={`${descriptionId}-title`}>
      <p className={styles.eyebrow}>Muchen Journey · 四模块受控首发 · 探索营</p>
      <h2 id={`${descriptionId}-title`} className={styles.title}>
        先完成一次，再理解全部
      </h2>
      <p className={styles.description}>
        本次受控首发包含四个模块。今天先进入「探索营」，不用先记住全部流程。
      </p>
      <ol className={styles.route} aria-label="四个受控首发模块，当前位于探索营">
        {INVITE_ROUTE.map((name, index) => (
          <li className={index === 0 ? styles.current : ""} key={name}>
            <span>{String(index + 1).padStart(2, "0")}</span>
            <strong>{name}</strong>
          </li>
        ))}
      </ol>
      <div className={styles.reward}>
        <span>第一站回报</span>
        <strong>一个真实问题 + 一种验证方法</strong>
      </div>
      <p className={styles.nextAction}>
        <span>现在 · {copy.now}</span>
        <span aria-hidden="true">→</span>
        <span>随后 · {copy.next}</span>
      </p>
    </aside>
  );
}
