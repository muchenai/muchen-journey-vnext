"use client";

import { useEffect } from "react";
import { AcademyLegacyStudyPage } from "./AcademyLegacyStudyPage";
import { AcademyStudyPage } from "./AcademyStudyPage";
import { useAcademy } from "./useAcademy";
import "./academyLearning.css";

const academyCatalog = "/app?view=academy";

function returnToCatalog(villageCourse: boolean) {
  const catalog=villageCourse ? "/app?view=village" : academyCatalog;
  const referringPage = document.referrer ? new URL(document.referrer) : undefined;
  if (!history.state?.journeyStudyCourse && referringPage?.origin === location.origin && referringPage.pathname === "/app"
      && referringPage.searchParams.get("view") === (villageCourse ? "village" : "academy") && !referringPage.searchParams.has("course")
      && history.length > 1) {
    history.back();
  } else {
    location.replace(catalog);
  }
}

export function AcademyCourseEntry({ courseId, villageCourse=false }: { courseId: string; villageCourse?: boolean }) {
  const academy = useAcademy(true, villageCourse ? "village" : "academy");
  const catalog=villageCourse ? "/app?view=village" : academyCatalog;
  const close=()=>returnToCatalog(villageCourse);
  const locked=academy.lockedCourses?.find(item=>item.id===courseId);
  const course = academy.courses.find(item => item.id === courseId);

  useEffect(() => {
    if (!course?.title) return;
    const originalTitle = document.title;
    document.title = course.title + (villageCourse ? " · 新手村" : " · AI 学院") + " · Muchen Journey";
    return () => { document.title = originalTitle; };
  }, [course?.title,villageCourse]);

  return <div className="academy-study-entry-content">
    {course?.enhanced ? <AcademyStudyPage key={course.id + ":" + course.revision} course={course} villageCourse={villageCourse}
      onClose={close} onFavorite={item=>academy.favorite(item.id,!item.favorite)} favoriteBusy={false} learn={academy.learn} refresh={academy.refresh} />
      : course ? <AcademyLegacyStudyPage key={course.id + ":" + course.revision} course={course} villageCourse={villageCourse}
      onClose={close} onFavorite={item => academy.favorite(item.id, !item.favorite)}
      onProgress={academy.progress} /> : <section className="academy-course-state">
        <a className="learner-back-control" href={catalog}>{villageCourse ? "返回新手村" : "返回 AI 学院"}</a>
        {academy.loading ? <p role="status">正在加载课程…</p>
          : academy.error ? <><p className="academy-error" role="alert">{academy.error}</p>
              <button type="button" className="module-secondary" onClick={() => void academy.refresh()}>重新加载</button></>
          : locked ? <><h1>{locked.title}</h1><p>完成新手村全部必修后即可开始普通任务。</p></>
          : <><h1>课程暂不可用</h1><p>此课程可能已下架，或当前学习账号没有访问权限。</p></>}
      </section>}
  </div>;
}
