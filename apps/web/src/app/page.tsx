import Link from "next/link";

import journeyProduct from "../../../../config/muchen_journey_product.json";

import { exchangeInvite } from "@/app/actions";
import { apiRequest, CurrentAction, hasValidLearnerSession } from "@/lib/server/api";

export const dynamic = "force-dynamic";

const AUTH_ERRORS: Record<string, string> = {
  IDENTITY_NOT_LINKED: "该身份尚未获得访问权限，请联系运营获取一次性链接。",
  IDENTITY_REVOKED: "该身份的访问权限已撤销，请联系运营确认。",
  IDENTITY_PROVIDER_DISABLED: "身份服务尚未完成环境配置。",
  IDENTITY_PROVIDER_UNAVAILABLE: "身份服务暂时不可用，请稍后再试。",
  SESSION_EXPIRED: "当前会话已失效。业务事实未受影响，请使用对应工作入口重新进入。",
  LEARNER_SESSION_EXPIRED: "会话已失效，但你的成长进度和证据仍然保留。",
};

const JOURNEY_MAPS = journeyProduct.maps.map((map) => ({
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

type HomeState = "visitor" | "active" | "expired" | "unlocked";

type HomeContext = {
  currentMapIndex: number;
  state: HomeState;
};

async function resolveHomeContext(
  hasSession: boolean,
  authError: string | undefined,
): Promise<HomeContext> {
  if (!hasSession) {
    return {
      currentMapIndex: PRODUCT_CURRENT_MAP_INDEX,
      state: authError === "LEARNER_SESSION_EXPIRED" ? "expired" : "visitor",
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
      currentMapIndex,
      state: currentMapIndex > PRODUCT_CURRENT_MAP_INDEX ? "unlocked" : "active",
    };
  } catch {
    return { currentMapIndex: PRODUCT_CURRENT_MAP_INDEX, state: "active" };
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
          : "粘贴你收到的完整链接。系统先验证通行证，再确认身份。"}
      </p>
    </form>
  );
}

function StateAction({ state }: { state: HomeState }) {
  if (state === "visitor" || state === "expired") {
    return <InvitationAction expired={state === "expired"} />;
  }

  return (
    <Link
      className="button primary home-primary-action"
      href="/app"
      prefetch={false}
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
  const [query, hasSession] = await Promise.all([searchParams, hasValidLearnerSession()]);
  const context = await resolveHomeContext(hasSession, query.auth_error);
  const currentMap = JOURNEY_MAPS[context.currentMapIndex] ?? JOURNEY_MAPS[0];
  const completedMap = context.currentMapIndex > 0
    ? JOURNEY_MAPS[context.currentMapIndex - 1]
    : null;
  const isExpired = context.state === "expired";
  const isUnlocked = context.state === "unlocked";
  const stateTitle = isExpired
    ? "你的进度还在，重新验证即可继续"
    : isUnlocked
      ? `${currentMap.name} 已经为你解锁`
      : context.state === "active"
        ? `你正在 ${currentMap.name}`
        : `你的起点是 ${currentMap.name}`;
  const stateDescription = isExpired
    ? "已完成的地图、能力与成长证据不会因会话失效而丢失。"
    : isUnlocked && completedMap
      ? `${completedMap.name} 的成长证据会连续带入 ${currentMap.name}，不必重新开始。`
      : context.state === "active"
        ? "从个人成长中枢回到当前一步，继续留下可核对的成长证据。"
        : "Muchen Journey 采用专属邀请制。验证邀请后，从探索营建立第一份成长基线。";

  return (
    <section className="shared-home" data-home-state={context.state}>
      <header className="home-world-intro">
        <p className="home-world-kicker">Muchen Journey · People AI 成长系统</p>
        <h1>五张地图，走成一个人的长期成长</h1>
        <p>
          从认识方向，到融入岗位、建立 AI 能力、积累交付证据，最后在模拟真实项目中综合演练。
        </p>
      </header>

      <div className="home-world-grid">
        <section className="home-worldboard" aria-labelledby="five-map-heading">
          <div className="home-worldboard-heading">
            <div>
              <p>一家公司 · 一段连续旅程</p>
              <h2 id="five-map-heading">五张相连的成长地图</h2>
            </div>
            <span aria-hidden="true">01—05</span>
          </div>

          <ol className="home-map-rail" aria-label="Muchen Journey 五张成长地图">
            {JOURNEY_MAPS.map((map, index) => {
              const mapState = index < context.currentMapIndex
                ? "completed"
                : index === context.currentMapIndex
                  ? "current"
                  : "future";
              return (
                <li className={`is-${mapState}`} key={map.key}>
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
                        : "后续地图"}
                  </span>
                </li>
              );
            })}
          </ol>
        </section>

        <aside className="home-state-card" aria-labelledby="home-state-heading">
          <div className="home-state-location">
            <span aria-hidden="true" />
            <p>{isExpired ? "会话需要恢复" : isUnlocked ? "下一地图已解锁" : "你现在的位置"}</p>
          </div>
          <h2 id="home-state-heading">{stateTitle}</h2>
          <p className="home-state-description">{stateDescription}</p>
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
              : `${currentMap.name} · ${context.state === "visitor" ? "专属邀请制" : "成长记录已保留"}`}
          </p>
        </aside>
      </div>

      <p className="home-governance-note">
        People AI 只支持培养与反馈；重要人员决定始终由人负责。成长事实、人工判断、AI 建议与系统状态会被清楚区分。
      </p>
    </section>
  );
}
