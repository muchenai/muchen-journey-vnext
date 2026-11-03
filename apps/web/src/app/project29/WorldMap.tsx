import { useEffect, useRef, useState } from "react"
import "./worldMap.css"
import { worldMapTaskDepartment } from "./world-map-navigation"
import type { TaskDepartmentFilter } from "./taskDepartments"

/** One isolated map instance survives menu and module navigation. */
export function WorldMap({ active = true, onViewTasks }: { active?: boolean; onViewTasks?: (department: TaskDepartmentFilter) => void }) {
  const frame = useRef<HTMLIFrameElement>(null)
  const [ready, setReady] = useState(false)
  const [error, setError] = useState(false)
  const [attempt, setAttempt] = useState(0)
  const navigation = useRef(onViewTasks)
  const visible = useRef(active)
  useEffect(() => { navigation.current = onViewTasks; visible.current = active }, [onViewTasks, active])
  const syncContext = () => frame.current?.contentWindow?.postMessage({type:"journey-world-map-context", village:Boolean(navigation.current), active:visible.current}, "*")
  useEffect(() => { syncContext() }, [active, onViewTasks, ready])
  useEffect(() => {
    const timer = window.setTimeout(() => setError(true), 60000)
    const onMessage = (event: MessageEvent) => {
      if (event.source !== frame.current?.contentWindow) return
      if (event.data?.type === "journey-world-map-tasks") {
        const department = worldMapTaskDepartment(event.data.department)
        if (department && visible.current) navigation.current?.(department)
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
        <iframe key={attempt} ref={frame} title="沐晨世界地图" src="/api/learner/world-map?tasks=shared" sandbox="allow-scripts" allow="fullscreen *" allowFullScreen data-ready={ready} onLoad={syncContext} onError={() => setError(true)} />
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
