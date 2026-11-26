import { ModuleStatus } from "./ModuleShell"
import type { VillageChapterCourse, VillageTask } from "./useVillageTasks"

function CourseRow({ course, required = false, locked = false }: { course: VillageChapterCourse; required?: boolean; locked?: boolean }) {
  return <li>
    <div>
      <span className="module-tag">{required ? "必修课程" : "普通任务"}</span>
      <h3>{course.title}</h3>
      {course.summary && <p>{course.summary}</p>}
    </div>
    <div className="village-required-action">
      <small>{course.chapters} 章 · {course.completed ? "已完成" : `已学 ${course.progress}%`}</small>
      {locked && !course.completed
        ? <button type="button" className="module-secondary" disabled>待解锁</button>
        : <a className="module-secondary" href={`/app?view=village&course=${encodeURIComponent(course.id)}`}>
            {required ? (course.completed ? "回看课程" : course.progress > 0 ? "继续学习" : "开始学习") : (course.completed ? "回看任务" : course.progress > 0 ? "继续任务" : "开始任务")} →
          </a>}
    </div>
  </li>
}

function courseMatches(course: VillageChapterCourse, term: string) {
  return (course.title + course.summary).toLocaleLowerCase().includes(term)
}

export function VillageOrdinaryCourses({courses,locked}: {courses: VillageChapterCourse[]; locked: boolean}) {
  if (!courses.length) return null
  return <ul className="village-required-list" aria-label="普通任务">
    {courses.map(course => <CourseRow key={course.id} course={course} locked={locked} />)}
  </ul>
}

export function VillageCourseCatalog({requiredCourses,tasks,query,mine,onTask}: {
  requiredCourses: VillageChapterCourse[]
  tasks: VillageTask[]
  query: string
  mine: boolean
  onTask: (task: VillageTask) => void
}) {
  const term = query.trim().toLocaleLowerCase()
  const entries = requiredCourses.filter(course => courseMatches(course, term))
  const visibleTasks = tasks.filter(task => (task.title + task.description).toLocaleLowerCase().includes(term))
  return <>
    <section className="village-required-learning" aria-labelledby="village-course-catalog">
      <div className="village-task-list-heading">
        <h2 id="village-course-catalog">{mine ? "我的必修课程" : "必修课程"}</h2>
      </div>
      <ul className="village-required-list">
        {entries.map(course => <CourseRow key={course.id} course={course} required />)}
      </ul>
      {!entries.length && <p className="village-required-empty">{term ? "没有匹配的课程。" : mine ? "还没有开始学习必修课程。" : "当前没有已发布的必修课程。"}</p>}
    </section>
    {visibleTasks.length > 0 && <section className="village-required-learning" aria-labelledby="village-required-tasks">
      <h2 id="village-required-tasks">必修任务</h2>
      <ul className="village-required-list">
      {visibleTasks.map(task => <li key={task.id}>
        <div>
          <span className="module-tag">必修任务</span>
          <h3>{task.title}</h3>
          {task.description && <p>{task.description}</p>}
        </div>
        <div className="village-required-action">
          <ModuleStatus status={task.status}/>
          <button className="module-secondary" onClick={() => onTask(task)}>
            {task.status === "completed" ? "回看任务" : task.status === "active" ? "继续任务" : task.status === "returned" ? "修改提交" : task.status === "available" ? "查看并领取" : "查看详情"} →
          </button>
        </div>
      </li>)}
      </ul>
    </section>}
  </>
}
