import Link from "next/link";

import journeyProduct from "@/lib/muchen-journey-product.generated.json";
import controlledRelease from "@/lib/muchen-journey-controlled-release.generated.json";

import { exchangeInvite } from "@/app/actions";
import { FactLabel, FactLegend } from "@/app/human-experience";
import {
  apiRequest,
  CurrentAction,
  LearnerSessionState,
  resolveLearnerSessionState,
} from "@/lib/server/api";

export const dynamic = "force-dynamic";

const AUTH_ERRORS: Record<string, string> = {
  IDENTITY_NOT_LINKED: "该身份尚未获得访问权限，请联系运营获取一次性链接。",
  IDENTITY_REVOKED: "该身份的访问权限已撤销，请联系运营确认。",
  IDENTITY_PROVIDER_DISABLED: "身份服务尚未完成环境配置。",
  IDENTITY_PROVIDER_UNAVAILABLE: "身份服务暂时不可用，请稍后再试。",
  SESSION_EXPIRED: "当前会话已失效。业务事实未受影响，请使用对应工作入口重新进入。",
  LEARNER_SESSION_EXPIRED: "会话已失效，但你的成长进度和证据仍然保留；已提交的任务与评审事实仍然保留。",
};

const CONTROLLED_MODULE_KEYS = new Set<string>(controlledRelease.modules);
const JOURNEY_MAPS = journeyProduct.maps.filter((map) => CONTROLLED_MODULE_KEYS.has(map.key)).map((map) => ({
  key: map.key,
  mission: map.mission,
  name: map.name,
  order: map.order,
  output: map.people_ai_output,
}));

const PRODUCT_CURRENT_MAP_INDEX = Math.max(
  0,
  JOURNEY_MAPS.findIndex((map) => map.key === journeyProduct.current_map),
);

type HomeState = "visitor" | "active" | "expired" | "unlocked" | "unavailable";

type HomeContext = {
  action: CurrentAction | null;
  currentMapIndex: number;
  state: HomeState;
};

async function resolveHomeContext(
  session: LearnerSessionState,
  authError: string | undefined,
): Promise<HomeContext> {
  if (session.status === "UNAVAILABLE") {
    return {
      action: null,
      currentMapIndex: PRODUCT_CURRENT_MAP_INDEX,
      state: "unavailable",
    };
  }
  if (session.status !== "VALID") {
    return {
      action: null,
      currentMapIndex: PRODUCT_CURRENT_MAP_INDEX,
      state: session.status === "INVALID" || authError === "LEARNER_SESSION_EXPIRED"
        ? "expired"
        : "visitor",
    };
  }

  try {
    const action = await apiRequest<CurrentAction>("/api/v1/me/current-action", "LEARNER");
    const stableKey = action.journey?.stable_key;
    const authoritativeMapIndex = stableKey
      ? JOURNEY_MAPS.findIndex((map) => stableKey.includes(map.key))
      : PRODUCT_CURRENT_MAP_INDEX;
    const currentMapIndex = authoritativeMapIndex >= 0
      ? authoritativeMapIndex
      : PRODUCT_CURRENT_MAP_INDEX;

    return {
      action,
      currentMapIndex,
      state: currentMapIndex > PRODUCT_CURRENT_MAP_INDEX ? "unlocked" : "active",
    };
  } catch {
    return {
      action: null,
      currentMapIndex: PRODUCT_CURRENT_MAP_INDEX,
      state: "unavailable",
    };
  }
}

function InvitationAction({ expired = false }: { expired?: boolean }) {
  const fieldId = expired ? "reentry-link" : "invitation-link";

  return (
    <form action={exchangeInvite} className="home-invite-form">
      <label htmlFor={fieldId}>{expired ? "一次性重新进入链接" : "完整专属邀请链接"}</label>
      <div>
        <input
          id={fieldId}
          name="token"
          type="url"
          minLength={32}
          maxLength={2048}
          autoComplete="off"
          inputMode="url"
          placeholder="https://…/join#token=…"
          spellCheck={false}
          required
        />
        <button className="button primary home-primary-action" type="submit">
          {expired ? "使用重新进入链接" : "我已有专属邀请"}
          <span aria-hidden="true">→</span>
        </button>
      </div>
      <p>
        {expired
          ? "向运营获取一次性重新进入链接；验证后回到原进度，不会创建重复记录。"
          : "从专属邀请开始：粘贴你收到的完整链接。系统先验证通行证，再确认身份。"}
      </p>
    </form>
  );
}

function StateAction({ state }: { state: HomeState }) {
  if (state === "visitor" || state === "expired") {
    return <InvitationAction expired={state === "expired"} />;
  }

  if (state === "unavailable") {
    return (
      <Link className="button primary home-primary-action" href="/" prefetch={false}>
        重试状态读取
        <span aria-hidden="true">→</span>
      </Link>
    );
  }

  return (
    <Link
      className="button primary home-primary-action"
      href="/app"
      prefetch={false}
      aria-label={state === "unlocked" ? "进入下一张地图" : "继续旅程"}
    >
      {state === "unlocked" ? "进入下一张地图" : "继续当前旅程"}
      <span aria-hidden="true">→</span>
    </Link>
  );
}

export default async function Home({
  searchParams,
}: {
  searchParams: Promise<{ auth_error?: string }>;
}) {
  const [query, session] = await Promise.all([searchParams, resolveLearnerSessionState()]);
  const context = await resolveHomeContext(session, query.auth_error);
  const currentMap = JOURNEY_MAPS[context.currentMapIndex] ?? JOURNEY_MAPS[0];
  const completedMap = context.currentMapIndex > 0
    ? JOURNEY_MAPS[context.currentMapIndex - 1]
    : null;
  const isExpired = context.state === "expired";
  const isUnlocked = context.state === "unlocked";
  const isUnavailable = context.state === "unavailable";
  const stateTitle = isUnavailable
    ? "状态暂时无法确认"
    : isExpired
    ? "你的进度还在，重新验证即可继续"
    : isUnlocked
      ? `${currentMap.name} 已经为你解锁`
      : context.state === "active"
        ? `你正在 ${currentMap.name}`
        : `你的起点是 ${currentMap.name}`;
  const stateDescription = isUnavailable
    ? "未能取得服务端权威状态；页面不会猜测进度、解锁模块或显示成功。"
    : isExpired
    ? "已完成的地图、能力与成长证据不会因会话失效而丢失。"
    : isUnlocked && completedMap
      ? `${completedMap.name} 的成长证据会连续带入 ${currentMap.name}，不必重新开始。`
      : context.state === "active"
        ? "从个人成长中枢回到当前一步，继续留下可核对的成长证据。"
        : "Muchen Journey 采用专属邀请制。验证邀请后，从探索营建立第一份成长基线。";

  return (
    <section className="shared-home" data-home-state={context.state}>
      <header className="home-world-intro">
        <p className="journey-whisper">It&apos;s a long game.</p>
        <p className="home-world-kicker">Muchen Journey · People AI 成长系统</p>
        <h1>这里，没有标准答案。</h1>
        <p>
          <strong>四个模块，共用一条真实任务闭环。</strong>
          一天，八站。带走四份认知与三项真实能力证据；从 Day 0 · 启程开始，
          从认识方向，到融入岗位、建立 AI 能力、积累交付证据；本次只开放受控首发范围，
          每个正式结果都需要真实实操、证据与真人签署。
        </p>
      </header>

      <div className="home-world-grid">
        <section className="home-worldboard" aria-labelledby="controlled-modules-heading">
          <div className="home-worldboard-heading">
            <div>
              <p>一家公司 · 一段连续旅程</p>
              <h2 id="controlled-modules-heading">四个受控首发模块</h2>
            </div>
            <span aria-hidden="true">01—04</span>
          </div>

          <ol className="home-map-rail" aria-label="Muchen Journey 四个受控首发模块">
            {JOURNEY_MAPS.map((map, index) => {
              const mapState = isUnavailable
                ? "unknown"
                : index < context.currentMapIndex
                ? "completed"
                : index === context.currentMapIndex
                  ? "current"
                  : "future";
              return (
                <li
                  className={`is-${mapState}`}
                  data-hint={`${map.name} · ${map.mission}`}
                  key={map.key}
                >
                  <span className="home-map-number" aria-hidden="true">
                    {String(map.order).padStart(2, "0")}
                  </span>
                  <span className="home-map-copy">
                    <strong>{map.name}</strong>
                    <small>{map.mission}</small>
                  </span>
                  <span className="home-map-state">
                    {mapState === "completed"
                      ? "已完成"
                      : mapState === "current"
                        ? index === 0 ? "当前起点" : "当前位置"
                        : mapState === "unknown" ? "状态待确认" : "后续地图"}
                  </span>
                </li>
              );
            })}
          </ol>
        </section>

        <aside className="home-state-card" aria-labelledby="home-state-heading">
          <div className="home-state-location">
            <span aria-hidden="true" />
            <p>{isUnavailable ? "权威状态读取失败" : isExpired ? "会话需要恢复" : isUnlocked ? "下一地图已解锁" : "你现在的位置"}</p>
          </div>
          <FactLabel kind="system" />
          <h2 id="home-state-heading">{stateTitle}</h2>
          <p className="home-state-description">{stateDescription}</p>
          {context.action ? (
            <dl className="home-action-facts">
              <div><dt>当前任务</dt><dd>{context.action.title}</dd></div>
              <div><dt>为什么现在做</dt><dd>{context.action.reason}</dd></div>
              <div><dt>责任与反馈</dt><dd>{context.action.responsible_party} · {context.action.feedback_expectation}</dd></div>
            </dl>
          ) : null}
          <StateAction state={context.state} />
          {query.auth_error ? (
            <div
              className={isExpired ? "home-state-error home-state-error-sr" : "home-state-error"}
              role="alert"
            >
              {AUTH_ERRORS[query.auth_error] ?? "身份验证没有完成，请使用专属链接重新进入。"}
            </div>
          ) : null}
          <p className="home-state-note">
            {isUnlocked && completedMap
              ? `${completedMap.name} → ${currentMap.name} · 证据连续`
              : isUnavailable
                ? "未确认的状态不会写入或覆盖成长事实"
              : `${currentMap.name} · ${context.state === "visitor" ? "专属邀请制" : "成长记录已保留"}`}
          </p>
        </aside>
      </div>

      <p className="home-governance-note">
        People AI 只支持培养与反馈；重要人员决定始终由人负责。成长事实、人工判断、AI 建议与系统状态会被清楚区分。
      </p>
      <FactLegend />
    </section>
  );
}
