import { randomBytes } from "node:crypto"
import { readFile } from "node:fs/promises"
import path from "node:path"
import { worldMapTaskBridge, worldMapSharedTaskBridge } from "@/app/project29/world-map-navigation"
import { worldMapReadyBridge, worldMapVisibilityBridge, worldMapInstantResetBridge } from "@/app/project29/world-map-loading"

export const dynamic = "force-dynamic"

// This endpoint serves only the bundled static illustration, never account data.
// A separate document keeps the map's policy independent of the app's CSP.
export async function GET(request: Request) {
  const nonce = randomBytes(24).toString("base64")
  const source = await readFile(path.join(process.cwd(), "public/world-map/index.html"), "utf8")
  const ready = `<script nonce="${nonce}">${worldMapReadyBridge}</script>`
  // Keep the original black starfield and all bundled map geometry unchanged.
  const embedded = `<style nonce="${nonce}">
    .universe{height:100svh;min-height:0}
    html[data-map-resetting] .universe,html[data-map-resetting] .universe *,html[data-map-resetting] .universe *::before,html[data-map-resetting] .universe *::after{transition:none!important;animation:none!important}
    html[data-map-departing] .universe,html[data-map-departing] .universe *{visibility:hidden!important;pointer-events:none!important}
    .universe-coordinate,.universe-fineprint{display:none}
    .planet-detail .detail-return[data-village-task-link]{justify-content:center;text-align:center;min-height:38px;padding:8px 14px;border:1px solid #6ff2ff;border-radius:6px;background:linear-gradient(90deg,#2ed3e9,#56e7f8);color:#07334c;font-size:12px!important;line-height:20px;letter-spacing:0;box-shadow:0 0 16px #31def56b,inset 0 1px 0 #ffffff2e;transition:background .18s,box-shadow .18s}
    .planet-detail .detail-return[data-village-task-link]:hover{background:linear-gradient(90deg,#42dff2,#70efff);box-shadow:0 0 20px #31def580,inset 0 1px 0 #ffffff40}
    .map-fullscreen-intro{display:none;position:fixed;top:5%;left:4.6%;z-index:4;pointer-events:none;color:#eff6ff;font-family:Source Han Sans SC,Microsoft YaHei,sans-serif;text-shadow:0 2px 18px #02091c}
    :root:fullscreen .map-fullscreen-intro{display:block}
    .map-fullscreen-intro .eyebrow{font-size:9px;letter-spacing:3px;color:#9ab0c6}
    .map-fullscreen-intro h1{margin:23px 0 0;font-size:clamp(32px,2.9vw,56px);font-weight:400;letter-spacing:10px;line-height:1.3}
    .map-fullscreen-intro h1 span{display:block;margin-top:15px;font-size:10px;letter-spacing:10px;color:#9ab0c6}
    .map-fullscreen-intro .description{margin-top:35px;font-size:12px;line-height:2.2;letter-spacing:1px;color:#9ab0c6}
    .map-fullscreen-intro p{margin:0}
    .map-fullscreen-intro .stats{display:flex;gap:38px;margin-top:25px;padding-top:23px;position:relative;font-size:11px;color:#9ab0c6}
    .map-fullscreen-intro .stats:before{content:'';position:absolute;top:0;left:0;width:42px;height:1px;background:#9ab0c64d}
    .map-fullscreen-intro strong{margin-right:9px;font-size:22px;font-weight:500;color:#eff6ff}
    .map-fullscreen-notice{position:fixed;bottom:100px;right:4%;z-index:30;padding:12px 18px;background:#0e192b;border:1px solid #71c5ff;color:#eff6ff;border-radius:8px;font:13px sans-serif}
  </style>`
  const fullscreenIntro = `<aside class="map-fullscreen-intro" aria-label="世界地图介绍"><p class="eyebrow">EXPLORE THE MUCHEN UNIVERSE</p><h1>世界地图<span>WORLD MAP</span></h1><div class="description"><p>循着星轨，发现沐晨的协作版图。</p><p>点击一处地标，开启新的探索。</p></div><div class="stats"><span><strong>13</strong>探索入口</span><span><strong>01</strong>交付枢纽</span></div></aside>`
  const controls = `<script nonce="${nonce}">(()=>{
    const selector='button[aria-label="切换沉浸视图"],button[data-map-fullscreen-control]';
    let pending=false;
    const sync=()=>{const button=document.querySelector(selector);if(!button)return;button.dataset.mapFullscreenControl='true';const active=Boolean(document.fullscreenElement);button.setAttribute('aria-label',active?'退出全屏':'全屏显示地图');button.setAttribute('aria-pressed',String(active));button.title=active?'退出全屏（Esc）':'全屏显示地图';};
    const observer=new MutationObserver(sync);observer.observe(document.body,{childList:true,subtree:true});sync();
    document.addEventListener('fullscreenchange',sync);
    document.addEventListener('click',async event=>{
      if(!(event.target instanceof Element)||!event.target.closest(selector))return;
      event.preventDefault();event.stopImmediatePropagation();if(pending)return;pending=true;
      try{if(document.fullscreenElement){await document.exitFullscreen()}else{await document.documentElement.requestFullscreen()}}
      catch{document.querySelector('.map-fullscreen-notice')?.remove();const notice=document.createElement('div');notice.className='map-fullscreen-notice';notice.setAttribute('role','alert');notice.textContent='浏览器暂不支持全屏，请使用桌面浏览器打开。';document.body.append(notice);setTimeout(()=>notice.remove(),4500)}
      finally{pending=false;sync()}
    },true);
  })();${worldMapInstantResetBridge}</script>`
  const mode = new URL(request.url).searchParams.get("tasks")
  const taskNavigation = mode === "village" ? `<script nonce="${nonce}">${worldMapTaskBridge}</script>`
    : mode === "shared" ? `<script nonce="${nonce}">${worldMapSharedTaskBridge}${worldMapVisibilityBridge}</script>` : ""
  const html = source.replace(/<(script|style)\b/g, `<$1 nonce="${nonce}"`).replace("</head>", `${embedded}</head>`).replace("</body>", `${fullscreenIntro}${ready}${controls}${taskNavigation}</body>`)
  return new Response(html, { headers: {
    "Content-Type": "text/html; charset=utf-8",
    "Cache-Control": "no-store",
    "X-Frame-Options": "SAMEORIGIN",
    "Content-Security-Policy": [
      "default-src 'none'",
      `script-src 'nonce-${nonce}'`,
      `style-src 'nonce-${nonce}'`,
      "style-src-attr 'unsafe-inline'",
      "img-src 'self' data:",
      "font-src data:",
      "connect-src 'none'",
      "object-src 'none'",
      "base-uri 'none'",
      "form-action 'none'",
      "frame-ancestors 'self'",
    ].join("; "),
  } })
}
