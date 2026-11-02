import { useEffect, useRef, useState } from "react"
import "./worldMap.css"
import { worldMapTaskDepartment } from "./world-map-navigation"
import type { TaskDepartmentFilter } from "./taskDepartments"

/** Load the standalone map only when its menu is opened; isolate its CSS and scripts. */
export function WorldMap({ onViewTasks }: { onViewTasks?: (department: TaskDepartmentFilter) => void }) {
  const frame = useRef<HTMLIFrameElement>(null)
  const [ready, setReady] = useState(false)
  const [error, setError] = useState(false)
  const [attempt, setAttempt] = useState(0)
  useEffect(() => {
    const timer = window.setTimeout(() => setError(true), 20000)
    const onMessage = (event: MessageEvent) => {
      if (event.source !== frame.current?.contentWindow) return
      if (event.data?.type === "journey-world-map-tasks") {
        const department = worldMapTaskDepartment(event.data.department)
        if (department && onViewTasks) onViewTasks(department)
        return
      }
      if (event.data?.type !== "journey-world-map-ready") return
      window.clearTimeout(timer)
      setReady(true)
      setError(false)
    }
    window.addEventListener("message", onMessage)
    return () => { window.clearTimeout(timer); window.removeEventListener("message", onMessage) }
  }, [attempt, onViewTasks])
  return (
    <section className="world-map-page" aria-label="世界地图">
      <div className="village-world-map">
        <iframe key={attempt} ref={frame} title="沐晨世界地图" src={onViewTasks ? "/api/learner/world-map?tasks=village" : "/api/learner/world-map"} sandbox="allow-scripts" allow="fullscreen *" allowFullScreen data-ready={ready} onError={() => setError(true)} />
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
