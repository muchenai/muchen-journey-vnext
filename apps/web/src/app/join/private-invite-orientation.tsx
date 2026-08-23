import styles from "./private-invite-orientation.module.css";

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
      <p className={styles.eyebrow}>Muchen Journey · 01 / 05 · 探索营</p>
      <h2 id={`${descriptionId}-title`} className={styles.title}>
        先完成一次，再理解全部
      </h2>
      <p className={styles.description}>
        整个 Journey 有五张地图。今天只进入第 1 张「探索营」，不用先记住整套系统。
      </p>
      <ol className={styles.route} aria-label="五张地图，当前位于探索营">
        {["探索营", "新手村", "AI学院", "交付线工会", "BOSS副本"].map((name, index) => (
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
