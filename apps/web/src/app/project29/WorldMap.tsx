import { useEffect, useMemo, useRef, useState } from "react"
import "./worldMap.css"
import { worldMapTaskDepartment } from "./world-map-navigation"
import type { TaskDepartmentFilter } from "./taskDepartments"

/** One isolated map instance survives menu and module navigation. */
export function WorldMap({ active = true, contextKey = "default", onViewTasks }: { active?: boolean; contextKey?: string; onViewTasks?: (department: TaskDepartmentFilter) => void }) {
  const frame = useRef<HTMLIFrameElement>(null)
  const [ready, setReady] = useState(false)
  const [error, setError] = useState(false)
  const [attempt, setAttempt] = useState(0)
  // A fresh token also covers A → B → A and re-entering the same module.
  // Hide during render, before effects/messages can expose the previous focus.
  const view = useMemo(() => ({}), [contextKey, active, attempt])
  const [preparedView, setPreparedView] = useState<object | null>(null)
  const [presentedView, setPresentedView] = useState<object | null>(null)
  const prepared = ready && preparedView === view
  const presented = ready && presentedView === view
  const navigation = useRef(onViewTasks)
  const visible = useRef(false)
  const resetSerial = useRef(0)
  const pendingReset = useRef<{requestId: number; view: object; phase: "resetting" | "prepared" | "presenting"} | null>(null)
  useEffect(() => { navigation.current = onViewTasks; visible.current = active && presented }, [onViewTasks, active, presented])
  const syncContext = () => frame.current?.contentWindow?.postMessage({type:"journey-world-map-context", village:Boolean(navigation.current), active:visible.current}, "*")
  useEffect(() => { syncContext() }, [active, onViewTasks, presented])
  useEffect(() => {
    pendingReset.current = null
    if (!ready || !frame.current?.contentWindow) return
    const request = {requestId: ++resetSerial.current, view, phase: "resetting" as const}
    pendingReset.current = request
    frame.current.contentWindow.postMessage({type:"journey-world-map-reset", requestId:request.requestId}, "*")
    return () => { if (pendingReset.current === request) pendingReset.current = null }
  }, [view, ready])
  // A hidden iframe can retain its previous compositor surface. Let it paint
  // the overview behind an opaque cover before exposing this particular view.
  useEffect(() => {
    const request = pendingReset.current
    if (!active || !prepared || !request || request.view !== view || request.phase !== "prepared") return
    request.phase = "presenting"
    frame.current?.contentWindow?.postMessage({type:"journey-world-map-present", requestId:request.requestId}, "*")
  }, [active, prepared, view])
  useEffect(() => {
    const timer = window.setTimeout(() => setError(true), 60000)
    const onMessage = (event: MessageEvent) => {
      if (event.source !== frame.current?.contentWindow) return
      if (event.data?.type === "journey-world-map-reset-complete") {
        const request = pendingReset.current
        if (request && request.phase === "resetting" && event.data.requestId === request.requestId) {
          request.phase = "prepared"
          setPreparedView(request.view)
        }
        return
      }
      if (event.data?.type === "journey-world-map-presented") {
        const request = pendingReset.current
        if (request && request.phase === "presenting" && event.data.requestId === request.requestId) {
          pendingReset.current = null
          setPresentedView(request.view)
        }
        return
      }
      if (event.data?.type === "journey-world-map-tasks") {
        const department = worldMapTaskDepartment(event.data.department)
        if (department && visible.current && navigation.current) {
          // Revoke this presentation before changing the module. A duplicate
          // click or late paint acknowledgement must not re-expose old focus.
          visible.current = false
          pendingReset.current = null
          setPreparedView(null)
          setPresentedView(null)
          navigation.current(department)
        }
        return
      }
      if (event.data?.type === "journey-world-map-error") {window.clearTimeout(timer);setError(true);return}
      if (event.data?.type !== "journey-world-map-ready") return
      window.clearTimeout(timer)
      setReady(true)
      setError(false)
      syncContext()
    }
    window.addEventListener("message", onMessage)
    return () => { window.clearTimeout(timer); window.removeEventListener("message", onMessage) }
  }, [attempt])
  return (
    <section className="world-map-page" aria-label="世界地图">
      <div className="village-world-map">
        <iframe key={attempt} ref={frame} title="沐晨世界地图" src="/api/learner/world-map?tasks=shared" sandbox="allow-scripts" allow="fullscreen *" allowFullScreen data-ready={ready} data-prepared={prepared} data-presented={presented} onLoad={syncContext} onError={() => setError(true)} />
        {ready && !presented && <div className="world-map-presentation-cover" aria-hidden="true" />}
        {!ready && (error ? (
          <div className="module-empty" role="alert">
            <p>世界地图加载失败，请重试。</p>
            <button className="module-secondary" data-page-navigation onClick={() => { setReady(false); setError(false); setAttempt(value => value + 1) }}>重新加载</button>
          </div>
        ) : <p className="module-empty" role="status">世界地图加载中…</p>)}
      </div>
      <div className="world-map-intro">
        <p>EXPLORE THE MUCHEN UNIVERSE</p>
        <h1>世界地图<span>WORLD MAP</span></h1>
        <div className="world-map-description">
          <p>循着星轨，发现沐晨的协作版图。</p>
          <p>点击一处地标，开启新的探索。</p>
        </div>
        <div className="world-map-stats">
          <span><strong>13</strong>探索入口</span>
          <span><strong>01</strong>交付枢纽</span>
        </div>
      </div>
    </section>
  )
}
