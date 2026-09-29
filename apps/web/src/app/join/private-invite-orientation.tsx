import styles from "./private-invite-orientation.module.css";
import journeyProduct from "@/lib/muchen-journey-product.generated.json";
import controlledRelease from "@/lib/muchen-journey-controlled-release.generated.json";
import type { JoinLocale } from "./language-switcher";

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

const PHASE_COPY_EN: Record<OrientationPhase, { now: string; next: string }> = {
  VERIFY_INVITE: {
    now: "Verify your private invitation",
    next: "Open the first required reading",
  },
  CONFIRM_IDENTITY: {
    now: "Confirm this invitation is yours",
    next: "Enter the first Exploration Camp stop",
  },
  REENTRY: {
    now: "Confirm and restore your progress",
    next: "Continue your current stop",
  },
};

const CONTROLLED_MODULE_KEYS = new Set<string>(controlledRelease.modules);
const INVITE_ROUTE = journeyProduct.maps
  .filter((map) => CONTROLLED_MODULE_KEYS.has(map.key))
  .map((map) => map.name);

export function PrivateInviteOrientation({
  phase,
  descriptionId,
  locale,
}: {
  phase: OrientationPhase;
  descriptionId: string;
  locale: JoinLocale;
}) {
  const isEnglish = locale === "en";
  const copy = isEnglish ? PHASE_COPY_EN[phase] : PHASE_COPY[phase];

  return (
    <aside id={descriptionId} className={styles.orientation} aria-labelledby={`${descriptionId}-title`}>
      <p className={styles.eyebrow}>Muchen Quest · {isEnglish ? "Controlled release · Exploration Camp" : "四模块受控首发 · 探索营"}</p>
      <h2 id={`${descriptionId}-title`} className={styles.title}>
        {isEnglish ? "A real-world quest for AI talent" : "AI 数据公司真实世界闯关计划"}
      </h2>
      <p className={styles.description}>
        {isEnglish
          ? "Let every step of growth be seen."
          : "让每一个成长都被看见"}
      </p>
      <ul className={styles.features} aria-label={isEnglish ? "Experience highlights" : "体验亮点"}>
        <li>
          <span aria-hidden="true" className={styles.featureIcon}>
            <svg viewBox="0 0 24 24"><path d="M4 19V11h3v8H4Zm6 0V5h3v14h-3Zm6 0V8h3v11h-3Z" /></svg>
          </span>
          <div><strong>{isEnglish ? "Real business scenarios" : "真实业务场景"}</strong><small>{isEnglish ? "Learn by doing" : "在实践中学习，在挑战中成长"}</small></div>
        </li>
        <li>
          <span aria-hidden="true" className={styles.featureIcon}>
            <svg viewBox="0 0 24 24"><path d="M8.2 11.2a3.4 3.4 0 1 0 0-6.8 3.4 3.4 0 0 0 0 6.8Zm7.7-.7a2.7 2.7 0 1 0 0-5.4 2.7 2.7 0 0 0 0 5.4ZM2.5 19.6c0-3.7 2.4-6 5.7-6s5.7 2.3 5.7 6H2.5Zm11.5 0c-.1-1.9-.7-3.5-1.8-4.7.9-1.2 2.2-1.8 3.8-1.8 3 0 5.1 2.3 5.1 6.5H14Z" /></svg>
          </span>
          <div><strong>{isEnglish ? "Rich mission system" : "丰富任务体系"}</strong><small>{isEnglish ? "Work with AI and unlock possibilities" : "与 AI 协作，解锁更多可能"}</small></div>
        </li>
        <li>
          <span aria-hidden="true" className={styles.featureIcon}>
            <svg viewBox="0 0 24 24"><path d="m12 2.8 2.7 5.5 6.1.9-4.4 4.3 1 6.1-5.4-2.9-5.4 2.9 1-6.1-4.4-4.3 6.1-.9L12 2.8Z" /></svg>
          </span>
          <div><strong>{isEnglish ? "Your growth path" : "专属成长路径"}</strong><small>{isEnglish ? "Build evidence for your future" : "积累真实能力，打造未来的你"}</small></div>
        </li>
      </ul>
      <ol className={styles.route} aria-label={isEnglish ? "Four release modules; Exploration Camp is current" : "四个模块受控首发，当前位于探索营"}>
        {INVITE_ROUTE.map((name, index) => (
          <li className={index === 0 ? styles.current : ""} key={name}>
            <span>{String(index + 1).padStart(2, "0")}</span>
            <strong>{isEnglish ? ["Exploration", "Newcomer", "AI Academy", "Delivery"][index] ?? name : name}</strong>
          </li>
        ))}
      </ol>
      <div className={styles.reward}>
        <span>{isEnglish ? "YOUR FIRST REWARD" : "第一站回报"}</span>
        <strong>{isEnglish ? "A real problem + a way to verify it" : "一个真实问题 + 一种验证方法"}</strong>
      </div>
      <p className={styles.nextAction}>
        <span>{isEnglish ? "Now" : "现在"} · {copy.now}</span>
        <span aria-hidden="true">→</span>
        <span>{isEnglish ? "Next" : "随后"} · {copy.next}</span>
      </p>
    </aside>
  );
}
