import { useState, useEffect, type ReactNode } from "react";
import { executionTasks } from "./ExecutionPages";
import type { PreviewIdentity } from "./previewStorage";
import { useJourney, useTaskStatus } from "./journey-context";
import { learningStreak } from "./taskRecords";

import { DashboardTaskGrid, dashboardStatusLabels, prioritizeDashboardTasks } from "./DashboardTaskGrid";
import "./updatedDashboard.css";
const assetPathPrefix = "/assets/project29/home-4062";
const img0454321 = `${assetPathPrefix}/0ba79.webp`;
const imgImage44 = "/assets/project29/6f233.webp";
const imgImage67 = "/assets/project29/96be2.webp";
const imgImage62 = "/assets/project29/82501.webp";
const imgImage77 = "/assets/project29/d6a61.webp";
const imgImage87 = "/assets/project29/dashboard-2047/07842.webp";
const imgImage88 = "/assets/project29/dashboard-2047/c8f76.webp";
const imgIcon = `${assetPathPrefix}/bfb49.svg`;
const imgIcon1 = `${assetPathPrefix}/095be.svg`;
const imgIcon2 = `${assetPathPrefix}/99dd2.svg`;
const imgIcon3 = `${assetPathPrefix}/a2a2a.svg`;
const imgIcon4 = `${assetPathPrefix}/e7bbd.svg`;
const imgLine1 = `${assetPathPrefix}/c5fda.svg`;
const imgRectangle50 = `${assetPathPrefix}/27eec.svg`;
const imgRectangle60 = "/assets/project29/home-4062/603f5.svg";
const imgRectangle61 = `${assetPathPrefix}/603f5.svg`;
const imgFrame = `${assetPathPrefix}/8c48a.svg`;
const imgFrame1 = "/assets/project29/eec40.svg";
const imgFrame2 = `${assetPathPrefix}/93f75.svg`;
const imgFrame3 = "/assets/project29/643cc.svg";
const imgFrame4 = `${assetPathPrefix}/0c76d.svg`;
const imgFrame5 = "/assets/project29/f4e78.svg";
const imgVectorStroke = `${assetPathPrefix}/3de75.svg`;
const imgLine4 = `${assetPathPrefix}/9780a.svg`;
const imgFrame6 = `${assetPathPrefix}/50b61.svg`;
const imgEllipse2 = `${assetPathPrefix}/6d7ea.svg`;
const imgEllipse3 = `${assetPathPrefix}/e4045.svg`;
const imgVector = `${assetPathPrefix}/7fe67.svg`;
const imgLine2 = `${assetPathPrefix}/cdb2b.svg`;
const imgRectangle64 = `${assetPathPrefix}/1172b.svg`;
const imgFrame7 = `${assetPathPrefix}/d8189.svg`;
const imgEllipse4 = `${assetPathPrefix}/ca7a2.svg`;
const imgVector1 = `${assetPathPrefix}/38294.svg`;
const imgVector2 = `${assetPathPrefix}/5f2a4.svg`;
const imgVector3 = `${assetPathPrefix}/02781.svg`;
const imgFrame8 = `${assetPathPrefix}/dafc4.svg`;
const imgFrame9 = `${assetPathPrefix}/35d7d.svg`;


export function UpdatedDashboard({ identity, decoration, activeNavigationDecoration, idleNavigationDecoration }: {
  identity: PreviewIdentity | null;
  decoration: ReactNode;
  activeNavigationDecoration: ReactNode;
  idleNavigationDecoration: ReactNode;
}) {
const { experience, learnerName } = useJourney();
const taskStatus = useTaskStatus();
const submissions = (experience?.activityRecords ?? []).flatMap(item => {
  const task = executionTasks[item.position - 1];
  return task ? [{task, index:item.position - 1, evidence:{record:item.body, submittedAt:item.submittedAt, status:item.status}}] : [];
});
const completed = experience?.completedStages ?? 0;
const inProgress = executionTasks.filter((_, index) => ["active", "revision"].includes(taskStatus(index))).length;
const pending = submissions.filter(item => ["SUBMITTED", "IN_REVIEW"].includes(item.evidence.status))
  .sort((a,b)=>Date.parse(b.evidence.submittedAt)-Date.parse(a.evidence.submittedAt));
const feedback = (experience?.reviewFeedback ?? []).flatMap(item => item.records.map(record => ({
  ...record, task:executionTasks[item.position - 1], index:item.position - 1,
  assignmentId:item.assignmentId, createdAt:record.reviewedAt, message:record.comment,
}))).filter(item=>item.task).sort((a,b)=>Date.parse(b.createdAt)-Date.parse(a.createdAt));
const streak = learningStreak(submissions.map(item=>item.evidence.submittedAt));
const formatRecordDate = (date: string) => new Date(date).toLocaleString("zh-CN", {
  month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
});

const orderedTasks = prioritizeDashboardTasks(executionTasks.map((task, index) => ({ task, index, status: taskStatus(index) })));
const currentEntry = orderedTasks[0];
const currentTaskIndex = currentEntry.index;
const task = currentEntry.task;
const activity = submissions.map(item=>({id:item.task.id, actorId:learnerName.slice(-2),actorName:learnerName,
  taskTitle:item.task.title,action:"submitted",createdAt:item.evidence.submittedAt}));
  return (
    <div className="updated-dashboard content-stretch flex flex-col items-center justify-center relative size-full" data-node-id="4062:426" style={{ backgroundImage: "linear-gradient(203.81643124441072deg, rgb(0, 6, 12) 30.098%, rgb(21, 45, 76) 82.87%, rgb(0, 8, 17) 95.576%), url(\"data:image/svg+xml;utf8,<svg viewBox='0 0 1920 1080' xmlns='http://www.w3.org/2000/svg' preserveAspectRatio='none'><rect x='0' y='0' height='100%' width='100%' fill='url(%23grad)' opacity='1'/><defs><radialGradient id='grad' gradientUnits='userSpaceOnUse' cx='0' cy='0' r='10' gradientTransform='matrix(0 -106.96 -190.15 0 1305.6 302.4)'><stop stop-color='rgba(11,67,132,1)' offset='0'/><stop stop-color='rgba(9,51,103,1)' offset='0.135'/><stop stop-color='rgba(6,35,73,1)' offset='0.27'/><stop stop-color='rgba(3,19,41,1)' offset='0.63'/></radialGradient></defs></svg>\"), linear-gradient(180deg, rgb(4, 24, 46) 0%, rgb(2, 14, 30) 100%)" }} data-name="学习成长中枢">
      <div className="h-[1080px] relative shrink-0 w-full" data-node-id="4043:10" data-name="Container">
        <div className="absolute h-[1080px] right-0 top-0 w-[1920px]" data-node-id="4062:428" data-name="04543-2 1">
          <div className="absolute inset-0 overflow-hidden pointer-events-none">
            <img alt="" className="absolute h-[105.26%] left-[-3.01%] max-w-none top-0 w-[107.44%]" src={img0454321} />
          </div>
        </div>
        <div className="figma-stroke figma-stroke-task absolute border border-[rgba(30,57,97,0.85)] border-solid h-[240px] left-[1416px] overflow-clip rounded-[10px] top-[82px] w-[480px]" data-node-id="4062:579" style={{ backgroundImage: "linear-gradient(267.19338617657695deg, rgba(14, 25, 43, 0.86) 1.1026%, rgba(22, 39, 71, 0.76) 16.424%, rgba(12, 26, 44, 0.86) 62.839%, rgba(10, 35, 76, 0.84) 98.83%)" }} data-name="Section">{decoration}
          <div className="absolute content-stretch flex h-[25px] items-center left-[14.34px] right-[14.34px] top-[14.34px]" data-node-id="4062:580" data-name="Heading 3">
            <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] font-black leading-[normal] not-italic relative shrink-0 text-[#eff6ff] text-[17.536px] whitespace-nowrap" data-node-id="4062:581">
              探索营进度
            </p>
          </div>
          <div className="absolute content-stretch flex gap-[11.69px] h-[78.23px] items-center left-[14.34px] pt-[11.69px] right-[14.34px] top-[43.34px]" data-node-id="4062:582" data-name="Container">
            <div className="content-stretch flex flex-col items-start relative shrink-0 size-[66.54px]" data-node-id="4062:583" data-name="Container:transform">
              <div className="absolute left-[0.37px] size-[66.49px] top-0" data-node-id="4062:584" data-name="image 77">
                <div className="absolute inset-0 overflow-hidden pointer-events-none">
                  <img alt="" className="absolute h-[349.08%] left-[-51.25%] max-w-none top-[-232.01%] w-[618.44%]" src={imgImage77} />
                </div>
              </div>
            </div>
            <div className="content-stretch flex flex-col items-start relative shrink-0" data-node-id="4062:585" data-name="Bold Text">
              <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] font-black leading-[normal] not-italic relative shrink-0 text-[#8ed8ff] text-[15.587px] whitespace-nowrap" data-node-id="4062:586">完成{completed}项</p>
            </div>
            <div className="bg-[#152f4d] border-[#6a90af] border-[0.974px] border-solid content-stretch flex flex-[232.484_0_0] flex-col h-[8.768px] items-start min-w-px overflow-clip relative rounded-[4.871px]" data-node-id="4062:587" data-name="Container">
              <div className="bg-gradient-to-r from-[#1eb8e6] h-[6.819px] relative shadow-[0px_0px_9.742px_0px_#4adfff] shrink-0 to-[#68edff] w-[72.472px]" style={{ width: `${completed / executionTasks.length * 100}%` }} data-node-id="4062:588" data-name="Italic Text" />
            </div>
            <div className="content-stretch flex flex-col items-start relative shrink-0" data-node-id="4062:589" data-name="Small">
              <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] font-normal leading-[normal] not-italic relative shrink-0 text-[#eff6ff] text-[12.989px] whitespace-nowrap" data-node-id="4062:590">{completed}/{executionTasks.length}</p>
            </div>
          </div>
          <div className="absolute content-stretch flex flex-col items-start left-[14.34px] pt-[11.69px] right-[14.34px] top-[125.57px]" data-node-id="4062:591" data-name="Container:margin">
            <div className="gap-x-[9.803516387939453px] gap-y-[9.803516387939453px] grid grid-cols-[___143.05px_143.05px_143.05px] grid-rows-[_62.09px] h-[85px] relative shrink-0 w-full" data-node-id="4062:592" data-name="Container">
              <div className="border-[#274c73] border-[1.089px] border-solid col-1 content-stretch flex flex-col h-[85px] items-start justify-self-stretch px-[8.714px] py-[7.625px] relative rounded-[6.536px] row-1 self-start shrink-0" data-node-id="4062:593" data-name="Container">
                <div className="h-[15.256px] relative shrink-0 w-full" data-node-id="4062:594" data-name="Container">
                  <p className="[word-break:break-word] absolute font-['Source_Han_Sans_SC'] font-normal leading-[normal] left-0 not-italic text-[#a0b7d1] text-[10.893px] top-0 whitespace-nowrap" data-node-id="4062:595">
                    🔥 连续学习
                  </p>
                </div>
                <div className="content-stretch flex flex-col h-[29.422px] items-start pt-[10px] relative shrink-0 w-[123.399px]" data-node-id="4062:596" data-name="Bold Text">
                  <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] font-black leading-[0] not-italic relative shrink-0 text-[#ffd65d] text-[0px] whitespace-nowrap" data-node-id="4062:597"><span className="leading-[normal] text-[19.607px]">{streak} </span><span className="leading-[normal] text-[13.071px] text-white">天</span></p>
                </div>
              </div>
              <div className="border-[#274c73] border-[1.089px] border-solid col-2 content-stretch flex flex-col h-[85px] items-start justify-self-stretch px-[8.714px] py-[7.625px] relative rounded-[6.536px] row-1 self-start shrink-0" data-node-id="4062:598" data-name="Container">
                <div className="h-[16.345px] relative shrink-0 w-full" data-node-id="4062:599" data-name="Container">
                  <p className="[word-break:break-word] absolute font-['Source_Han_Sans_SC'] font-normal leading-[normal] left-0 not-italic text-[#a0b7d1] text-[10.893px] top-[1.09px] whitespace-nowrap" data-node-id="4062:600">
                    ▥ 完成任务
                  </p>
                </div>
                <div className="content-stretch flex flex-col h-[29.422px] items-start pt-[10px] relative shrink-0 w-[123.399px]" data-node-id="4062:601" data-name="Bold Text">
                  <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] font-black leading-[0] not-italic relative shrink-0 text-[#ffd65d] text-[0px] whitespace-nowrap" data-node-id="4062:602"><span className="leading-[normal] text-[19.607px]">{completed} </span><span className="leading-[normal] text-[13.071px] text-white">个</span></p>
                </div>
              </div>
              <div className="border-[#274c73] border-[1.089px] border-solid col-3 content-stretch flex flex-col h-[85px] items-start justify-self-stretch px-[8.714px] py-[7.625px] relative rounded-[6.536px] row-1 self-start shrink-0" data-node-id="4062:603" data-name="Container">
                <div className="h-[15.256px] relative shrink-0 w-full" data-node-id="4062:604" data-name="Container">
                  <p className="[word-break:break-word] absolute font-['Source_Han_Sans_SC'] font-normal leading-[normal] left-0 not-italic text-[#a0b7d1] text-[10.893px] top-0 whitespace-nowrap" data-node-id="4062:605">
                    ♛ 累计获得经验
                  </p>
                </div>
                <div className="content-stretch flex flex-col h-[29.422px] items-start pt-[10px] relative shrink-0 w-[123.399px]" data-node-id="4062:606" data-name="Bold Text">
                  <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] font-black leading-[normal] not-italic relative shrink-0 text-[#ffd65d] text-[19.607px] whitespace-nowrap" data-node-id="4062:607">— 经验</p>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div className="figma-stroke figma-stroke-task absolute border border-[rgba(30,57,97,0.85)] border-solid h-[318px] left-[1416px] rounded-[10px] top-[338px] w-[480px]" data-node-id="4043:172" style={{ backgroundImage: "linear-gradient(267.88107159712285deg, rgba(14, 25, 43, 0.86) 1.1026%, rgba(22, 39, 71, 0.76) 16.424%, rgba(12, 26, 44, 0.86) 62.839%, rgba(10, 35, 76, 0.84) 98.83%)" }} data-name="Section">{decoration}
          <div className="absolute content-stretch flex h-[25px] items-center left-[14.34px] right-[14.34px] top-[14.34px]" data-node-id="4043:173" data-name="Heading 3">
            <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] font-black leading-[normal] not-italic relative shrink-0 text-[#eff6ff] text-[17.536px] whitespace-nowrap" data-node-id="4043:174">待审核任务 · {pending.length}</p>
          </div>
          <div className="dashboard-records" data-node-id="2006:153">
              {pending.length === 0 ? <p className="dashboard-record-empty">暂无待审核任务，提交任务后将在这里显示。</p> : pending.map(({ task, index, evidence }) => <div className="dashboard-record" key={task.id}>
                <button type="button" className="dashboard-record-title" data-action="open-task" data-task-index={index}>{task.title} →</button>
                <div className="dashboard-record-meta"><time dateTime={evidence.submittedAt}>{formatRecordDate(evidence.submittedAt)} 提交</time><span>待审核</span></div>
                <p className="dashboard-record-preview">{evidence.record}</p>

              </div>)}
            </div>
        </div>
        <div className="figma-stroke figma-stroke-task absolute border border-[rgba(30,57,97,0.85)] border-solid content-stretch flex flex-col h-[375px] items-start left-[1416px] p-[13.639px] rounded-[10px] top-[673px] w-[480px]" data-node-id="4043:185" style={{ backgroundImage: "linear-gradient(268.2029186205031deg, rgba(14, 25, 43, 0.86) 1.1026%, rgba(22, 39, 71, 0.76) 16.424%, rgba(12, 26, 44, 0.86) 62.839%, rgba(10, 35, 76, 0.84) 98.83%)" }} data-name="Section">{decoration}
          <div className="content-stretch flex items-center relative shrink-0 w-full" data-node-id="4043:186" data-name="Heading 3">
            <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] font-black leading-[normal] not-italic relative shrink-0 text-[#eff6ff] text-[17.536px] whitespace-nowrap" data-node-id="4043:187">
              任务反馈
            </p>
          </div>
          <div className="dashboard-records" data-node-id="2006:166">
              {feedback.length === 0 ? <p className="dashboard-record-empty">暂无任务反馈。审核完成后将在这里显示。</p> : feedback.map(entry => <div className="dashboard-record" key={`${entry.task.id}-${entry.id}`}>
                <button type="button" className="dashboard-record-title" data-action="review-feedback" data-assignment-id={entry.assignmentId}>{entry.task.title} →</button>
                <div className="dashboard-record-meta"><time dateTime={entry.createdAt}>{formatRecordDate(entry.createdAt)}</time><span>{entry.decision === "PASS" ? "审核通过" : "退回修改"}</span></div>
                <p className="dashboard-record-message">{entry.message}</p>
              </div>)}
            </div>
        </div>
        <div className="absolute contents left-[276px] top-[338px]" data-node-id="4043:200">
          <div className="absolute contents left-[276px] top-[338px]" data-node-id="4043:201">
            <div className="figma-stroke figma-stroke-task -translate-y-1/2 absolute border border-[rgba(30,57,97,0.85)] border-solid h-[318px] left-[276px] rounded-[10px] top-[calc(50%-43px)] w-[708.526px]" data-node-id="4043:202" style={{ backgroundImage: "linear-gradient(266.87393614749124deg, rgba(14, 25, 43, 0.86) 1.1026%, rgba(22, 39, 71, 0.76) 16.424%, rgba(12, 26, 44, 0.86) 62.839%, rgba(10, 35, 76, 0.84) 98.83%)" }}>{decoration}</div>
            <p className="[word-break:break-word] absolute font-['Source_Han_Sans_SC'] font-black leading-[normal] left-[308.08px] not-italic text-[#eff6ff] text-[24.094px] top-[361.01px] whitespace-nowrap" data-node-id="4043:203">
              当前任务
            </p><span className="dashboard-current-status" data-status={currentEntry.status}>{dashboardStatusLabels[currentEntry.status]}</span>
            <div className="absolute contents left-[423.14px] top-[369.38px]" data-node-id="4043:204">
              <div className="dashboard-current-task-tag" data-node-id="4043:205"><span data-node-id="4043:206">探索任务·{String(currentTaskIndex + 1).padStart(2, "0")}</span></div>
            </div>
            <div className="absolute border-[1.49px] border-[rgba(30,57,97,0.85)] border-solid h-[140.808px] left-[308.08px] rounded-[13.41px] top-[417.88px] w-[119.947px]" data-node-id="4043:207" data-name="image 87">
              <div className="absolute inset-0 overflow-hidden pointer-events-none rounded-[13.41px]">
                <img alt="" className="absolute h-[108.09%] left-[-7.39%] max-w-none top-[-4.62%] w-[113.72%]" src={imgImage87} />
              </div>
            </div>
            <p className="[word-break:break-word] absolute font-['Source_Han_Sans_SC'] font-bold leading-[normal] left-[447.55px] not-italic text-[#eff6ff] text-[20.921px] top-[414.01px] tracking-[0.9489px] whitespace-nowrap" data-node-id="4043:208">{currentTaskIndex === 0 ? "公司基础介绍材料" : task.name}</p>
            <p className="[word-break:break-word] absolute font-['Source_Han_Sans_SC'] font-normal h-[87.171px] leading-[normal] left-[447.55px] not-italic text-[#9ab0c6] text-[13.947px] text-justify top-[460.04px] tracking-[2.0921px] w-[223.855px]" data-node-id="4043:209">{task.description.trim()}</p>
            <div className="[word-break:break-word] absolute contents left-[703.49px] not-italic top-[417.8px]" data-node-id="4043:210">
              <p className="absolute font-['Source_Han_Sans_SC'] font-normal leading-[normal] left-[703.49px] text-[#9ab0c6] text-[8.91px] top-[417.8px] whitespace-nowrap" data-node-id="4043:211">
                ◷ 预计用时
              </p>
              <p className="absolute font-['Source_Han_Sans_SC'] font-black leading-[normal] left-[703.49px] text-[#ebf5ff] text-[10.395px] top-[437.99px] whitespace-nowrap" data-node-id="4043:212">
                {experience?.stagePosition === currentTaskIndex + 1 ? `${experience.estimatedMinutes} 分钟` : "—"}
              </p>
              <p className="absolute font-['Source_Han_Sans_SC'] font-normal leading-[normal] left-[703.49px] text-[#9ab0c6] text-[8.91px] top-[459.75px] whitespace-nowrap" data-node-id="4043:213">
                ▣ 截止时间
              </p>
              <p className="absolute font-['Source_Han_Sans_SC'] font-black leading-[normal] left-[703.49px] text-[#ebf5ff] text-[10.395px] top-[479.94px] whitespace-nowrap" data-node-id="4043:214">
                —
              </p>
              <p className="absolute font-['Source_Han_Sans_SC'] font-normal leading-[normal] left-[703.49px] text-[#9ab0c6] text-[8.91px] top-[501.7px] whitespace-nowrap" data-node-id="4043:215">
                任务星级
              </p>
              <p className="absolute font-['Source_Han_Sans_SC'] font-black leading-[0] left-[703.49px] text-[#ebf5ff] text-[10.395px] top-[521.89px] tracking-[1.4851px] whitespace-nowrap" data-node-id="4043:216">
                <span className="leading-[10.395px]">—</span>
                <span className="leading-[10.395px] text-[#40526b]"></span>
              </p>
              <p className="absolute font-['Source_Han_Sans_SC'] font-normal h-[24.556px] leading-[normal] left-[771.85px] text-[#9ab0c6] text-[8.91px] top-[417.8px] w-[43.655px]" data-node-id="4043:217">
                任务奖励
              </p>
              <div className="absolute contents font-['Source_Han_Sans_SC'] font-normal left-[771.85px] top-[438.77px] whitespace-nowrap" data-node-id="4043:218">
                <div className="-translate-x-1/2 -translate-y-1/2 absolute flex flex-col justify-center leading-[0] left-[778.35px] text-[#ffc34d] text-[12.714px] text-center top-[446.27px]" data-node-id="4043:219">
                  <p className="leading-[14.76px]">◈</p>
                </div>
                <p className="absolute leading-[normal] left-[786.61px] text-[#b9cce1] text-[9.653px] top-[439.55px]" data-node-id="4043:220">
                  —
                </p>
              </div>
              <div className="absolute contents font-['Source_Han_Sans_SC'] font-normal left-[771.85px] top-[479.94px] whitespace-nowrap" data-node-id="4043:221">
                <p className="absolute leading-[14.76px] left-[771.85px] text-[#82a1ff] text-[12.714px] top-[479.94px]" data-node-id="4043:222">
                  ⬢
                </p>
                <p className="absolute leading-[normal] left-[787.39px] text-[#b9cce1] text-[9.653px] top-[482.27px]" data-node-id="4043:223">
                  —
                </p>
              </div>
              <div className="absolute contents font-['Source_Han_Sans_SC'] font-normal left-[771.85px] top-[519.56px] whitespace-nowrap" data-node-id="4043:224">
                <p className="absolute leading-[14.76px] left-[771.85px] text-[#ffc34d] text-[12.714px] top-[519.56px]" data-node-id="4043:225">
                  ★
                </p>
                <p className="absolute leading-[normal] left-[788.94px] text-[#b9cce1] text-[9.653px] top-[521.89px]" data-node-id="4043:226">
                  —
                </p>
              </div>
            </div>
            <button type="button" className="absolute bg-gradient-to-r border-[#75f5ff] border-[0.611px] border-solid content-stretch flex from-[#42dced] h-[38.679px] items-center justify-center left-[308.08px] px-[3.667px] py-[0.611px] rounded-[6.722px] shadow-[0px_0px_9.778px_0px_#2edfff,0px_0px_19.556px_0px_rgba(18,195,255,0.55)] to-[#5ceeff] top-[586.1px] via-[#31c9f5] via-[45%] w-[500.013px]" data-action="open-task" data-task-index={currentTaskIndex} data-node-id="4043:227" data-name="Button">
              <div className="content-stretch flex gap-[6.329px] items-center relative shrink-0" data-node-id="4043:228">
                <div className="h-[14.667px] relative shrink-0 w-[12.833px]" data-node-id="4043:229" data-name="Vector (Stroke)">
                  <img alt="" className="absolute block inset-0 max-w-none size-full" src={imgVectorStroke} />
                </div>
                <p className="font-['Source_Han_Sans_SC'] font-black leading-[normal] not-italic relative shrink-0 text-[#03245f] text-[12.833px] text-center tracking-[2.4444px] w-max whitespace-nowrap" data-node-id="4043:230">
                  点击查看当前任务详情
                </p>
              </div>
            </button>
            <p className="[word-break:break-word] absolute font-['Source_Han_Sans_SC'] font-medium leading-[normal] left-[880.63px] not-italic text-[#eff6ff] text-[19.787px] top-[384.72px] tracking-[1.0355px] whitespace-nowrap" data-node-id="4043:231">
              审核人
            </p>
            <div className="[word-break:break-word] absolute font-['Source_Han_Sans_SC'] font-normal leading-[0] left-[855.51px] not-italic text-[#9ab0c6] text-[12.426px] top-[530.84px] whitespace-nowrap" data-node-id="4043:232">
              <p className="leading-[normal] mb-0">“期待看到你的思考</p>
              <p className="leading-[normal]">和独特视角!”</p>
            </div>
            <p className="[word-break:break-word] absolute font-['Source_Han_Sans_SC'] font-normal leading-[normal] left-[880.63px] not-italic text-[#b1cae3] text-[12.426px] top-[472.24px] whitespace-nowrap" data-node-id="4043:233">
              李魔王老师
            </p>
            <p className="[word-break:break-word] absolute font-['Source_Han_Sans_SC'] font-normal leading-[normal] left-[874.54px] not-italic text-[#69c9d6] text-[12.426px] top-[498.12px] whitespace-nowrap" data-node-id="4043:234">
              产品设计导师
            </p>
            <div className="absolute border-[#86bbdf] border-[0.902px] border-solid grid grid-cols-[_33.38px] grid-rows-[_33.38px] left-[893.56px] rounded-[17.591px] size-[35.181px] top-[428.1px]" data-node-id="4043:235" style={{ backgroundImage: "linear-gradient(145.0000003379585deg, rgb(240, 217, 192) 6.1733%, rgb(85, 115, 143) 93.827%)" }} data-name="Container">
              <p className="[word-break:break-word] col-1 font-['Source_Han_Sans_SC'] font-black justify-self-center leading-[normal] not-italic relative row-1 self-center shrink-0 text-[#09223c] text-[14.433px] whitespace-nowrap" data-node-id="4043:236">
                李
              </p>
            </div>
            <div className="absolute flex h-[263.605px] items-center justify-center left-[837.38px] top-[361.01px] w-0" data-node-id="4043:237">
              <div className="flex-none rotate-90">
                <div className="h-0 relative w-[263.605px]">
                  <div className="absolute inset-[-0.68px_0_0_0]">
                    <img alt="" className="block max-w-none size-full" src={imgLine4} />
                  </div>
                </div>
              </div>
            </div>
            <div className="absolute contents left-[859px] top-[592.54px]" data-node-id="4043:238">
              <button type="button" className="absolute border-[1.395px] border-[rgba(30,57,97,0.85)] border-solid h-[32.079px] left-[859px] rounded-[12.553px] top-[592.54px] w-[104.605px]" data-action="mentor-profile" data-node-id="4043:239" style={{ backgroundImage: "linear-gradient(265.4300515964736deg, rgba(14, 25, 43, 0.86) 1.1026%, rgba(22, 39, 71, 0.76) 16.424%, rgba(12, 26, 44, 0.86) 62.839%, rgba(10, 35, 76, 0.84) 98.83%)" }}></button>
              <button type="button" className="absolute flex items-center justify-center font-['Source_Han_Sans_SC'] font-normal leading-none left-[859px] h-[32.079px] w-[104.605px] not-italic text-[#b1cae3] text-[12.426px] top-[592.54px] whitespace-nowrap" data-action="mentor-profile" data-node-id="4043:240">
                查看导师资料
              </button>
            </div>
          </div>
        </div>
        <div className="absolute contents left-[466px] top-[180.86px]" data-node-id="4062:677">
          <div className="absolute contents left-[466px] top-[180.86px]" data-node-id="4062:678">
            <div className="absolute border-[0.907px] border-[rgba(30,57,97,0.85)] border-solid h-[52.264px] left-[492.13px] rounded-[8.162px] top-[180.86px] w-[127.055px]" data-node-id="4062:679" style={{ backgroundImage: "linear-gradient(268.097420286487deg, rgba(0, 22, 58, 0.9) 4.2063%, rgba(0, 12, 34, 0.8) 27.99%, rgba(2, 18, 38, 0.86) 64.305%, rgba(4, 19, 44, 0.84) 99.341%)" }} />
            <p className="[word-break:break-word] absolute font-['Source_Han_Sans_SC'] font-normal leading-[normal] left-[520.07px] not-italic text-[#44e7f1] text-[14.972px] top-[185.36px] tracking-[-1.3475px] whitespace-nowrap" data-node-id="4062:680">
              01
            </p>
            <p className="[word-break:break-word] absolute font-['Source_Han_Sans_SC'] font-medium leading-[normal] left-[541.03px] not-italic text-[#fefefe] text-[14.972px] top-[185.36px] whitespace-nowrap" data-node-id="4062:681">
              探索启航
            </p>
            <p className="[word-break:break-word] absolute font-['Source_Han_Sans_SC'] font-normal leading-[normal] left-[541.03px] not-italic text-[#51d0c5] text-[11.5px] top-[208.94px] whitespace-nowrap" data-node-id="4062:682">
              进行中
            </p>
            <div className="absolute h-[12.227px] left-[520.07px] top-[211.56px] w-[13.974px]" data-node-id="4062:683" data-name="Frame">
              <img alt="" className="absolute block inset-0 max-w-none size-full" src={imgFrame6} />
            </div>
            <div className="absolute left-[466px] size-[41.049px] top-[185.82px]" data-node-id="4062:687">
              <div className="absolute inset-[-35.56%]">
                <img alt="" className="block max-w-none size-full" src={imgEllipse2} />
              </div>
            </div>
            <div className="absolute left-[477.35px] size-[16.594px] top-[198.05px]" data-node-id="4062:688">
              <img alt="" className="absolute block inset-0 max-w-none size-full" src={imgEllipse3} />
            </div>
            <div className="absolute inset-[18.32%_74.3%_80.8%_25.04%]" data-node-id="4062:689" data-name="Vector">
              <div className="absolute inset-[-9.22%_-6.9%_0.53%_-6.9%]">
                <img alt="" className="block max-w-none size-full" src={imgVector} />
              </div>
            </div>
            <div className="absolute flex items-center justify-center left-[492.64px] size-[1.747px] top-[199.79px]" data-node-id="4062:690">
              <div className="flex-none rotate-135">
                <div className="h-0 relative w-[2.47px]">
                  <div className="absolute inset-[-0.87px_-35.36%]">
                    <img alt="" className="block max-w-none size-full" src={imgLine2} />
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div className="absolute flex items-center justify-center left-[467.8px] size-[35.814px] top-[215.1px]" data-node-id="4062:691">
            <div className="flex-none rotate-[45.85deg]">
              <div className="h-[25.333px] relative w-[25.322px]">
                <div className="absolute inset-[-32.01%_-32.59%_-32.67%_-32.03%]">
                  <img alt="" className="block max-w-none size-full" src={imgRectangle64} />
                </div>
              </div>
            </div>
          </div>
        </div>
<div className="absolute contents left-[572px] top-[104px]" data-node-id="4062:692">
          <div className="absolute border-[0.907px] border-[rgba(30,57,97,0.85)] border-solid h-[52.264px] left-[598.13px] rounded-[8.162px] top-[104px] w-[127.055px]" data-node-id="4062:693" style={{ backgroundImage: "linear-gradient(268.097420286487deg, rgba(0, 22, 58, 0.9) 4.2063%, rgba(0, 12, 34, 0.8) 27.99%, rgba(2, 18, 38, 0.86) 64.305%, rgba(4, 19, 44, 0.84) 99.341%)" }} />
          <p className="[word-break:break-word] absolute font-['Source_Han_Sans_SC'] font-normal leading-[normal] left-[626.07px] not-italic text-[#5a7c9a] text-[14.972px] top-[108.51px] tracking-[-1.3475px] whitespace-nowrap" data-node-id="4062:694">
            02
          </p>
          <p className="[word-break:break-word] absolute font-['Source_Han_Sans_SC'] font-medium leading-[normal] left-[647.03px] not-italic text-[#809bc3] text-[14.972px] top-[108.51px] whitespace-nowrap" data-node-id="4062:695">
            能力进阶
          </p>
          <p className="[word-break:break-word] absolute font-['Source_Han_Sans_SC'] font-normal leading-[normal] left-[647.03px] not-italic text-[#5a7c9a] text-[11.5px] top-[132.09px] whitespace-nowrap" data-node-id="4062:696">
            待解锁
          </p>
          <div className="absolute h-[12.227px] left-[626.07px] top-[134.71px] w-[13.974px]" data-node-id="4062:697" data-name="Frame">
            <img alt="" className="absolute block inset-0 max-w-none size-full" src={imgFrame7} />
          </div>
          <div className="absolute contents left-[572px] top-[108.96px]" data-node-id="4062:701">
            <div className="absolute contents left-[572px] top-[108.96px]" data-node-id="4062:702">
              <div className="absolute contents left-[572px] top-[108.96px]" data-node-id="4062:703">
                <div className="absolute left-[572px] size-[41.049px] top-[108.96px]" data-node-id="4062:704">
                  <img alt="" className="absolute block inset-0 max-w-none size-full" src={imgEllipse4} />
                </div>
              </div>
            </div>
            <div className="absolute contents inset-[10.95%_68.7%_87.45%_30.49%]" data-node-id="4062:705">
              <div className="absolute contents inset-[10.95%_68.7%_87.45%_30.49%]" data-node-id="4062:706">
                <div className="absolute inset-[11.67%_68.7%_87.45%_30.49%]" data-node-id="4062:707" data-name="Vector">
                  <div className="absolute inset-[-9.22%_-5.56%]">
                    <img alt="" className="block max-w-none size-full" src={imgVector1} />
                  </div>
                </div>
                <div className="absolute inset-[10.95%_68.88%_88.33%_30.67%]" data-node-id="4062:708" data-name="Vector">
                  <div className="absolute inset-[-11.26%_-10%]">
                    <img alt="" className="block max-w-none size-full" src={imgVector2} />
                  </div>
                </div>
                <div className="absolute inset-[11.99%_69.11%_87.77%_30.89%]" data-node-id="4062:709" data-name="Vector">
                  <div className="absolute inset-[-33.79%_-0.87px]">
                    <img alt="" className="block max-w-none size-full" src={imgVector3} />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
<div className="absolute contents left-[935px] top-[154px]" data-node-id="4062:710">
          <div className="absolute border-[0.907px] border-[rgba(30,57,97,0.85)] border-solid h-[52.264px] left-[961.13px] rounded-[8.162px] top-[154px] w-[127.055px]" data-node-id="4062:711" style={{ backgroundImage: "linear-gradient(268.097420286487deg, rgba(0, 22, 58, 0.9) 4.2063%, rgba(0, 12, 34, 0.8) 27.99%, rgba(2, 18, 38, 0.86) 64.305%, rgba(4, 19, 44, 0.84) 99.341%)" }} />
          <p className="[word-break:break-word] absolute font-['Source_Han_Sans_SC'] font-normal leading-[normal] left-[989.07px] not-italic text-[#5a7c9a] text-[14.972px] top-[158.51px] tracking-[-1.3475px] whitespace-nowrap" data-node-id="4062:712">
            03
          </p>
          <p className="[word-break:break-word] absolute font-['Source_Han_Sans_SC'] font-medium leading-[normal] left-[1010.03px] not-italic text-[#809bc3] text-[14.972px] top-[158.51px] whitespace-nowrap" data-node-id="4062:713">
            专业深耕
          </p>
          <p className="[word-break:break-word] absolute font-['Source_Han_Sans_SC'] font-normal leading-[normal] left-[1010.03px] not-italic text-[#5a7c9a] text-[11.5px] top-[182.09px] whitespace-nowrap" data-node-id="4062:714">
            待解锁
          </p>
          <div className="absolute h-[12.227px] left-[989.07px] top-[184.71px] w-[13.974px]" data-node-id="4062:715" data-name="Frame">
            <img alt="" className="absolute block inset-0 max-w-none size-full" src={imgFrame8} />
          </div>
          <div className="absolute contents left-[935px] top-[158.96px]" data-node-id="4062:719">
            <div className="absolute contents left-[935px] top-[158.96px]" data-node-id="4062:720">
              <div className="absolute contents left-[935px] top-[158.96px]" data-node-id="4062:721">
                <div className="absolute left-[935px] size-[41.049px] top-[158.96px]" data-node-id="4062:722">
                  <img alt="" className="absolute block inset-0 max-w-none size-full" src={imgEllipse4} />
                </div>
              </div>
            </div>
            <div className="absolute contents inset-[15.56%_49.79%_82.84%_49.39%]" data-node-id="4062:723">
              <div className="absolute contents inset-[15.56%_49.79%_82.84%_49.39%]" data-node-id="4062:724">
                <div className="absolute inset-[16.28%_49.79%_82.84%_49.39%]" data-node-id="4062:725" data-name="Vector">
                  <div className="absolute inset-[-9.22%_-5.56%]">
                    <img alt="" className="block max-w-none size-full" src={imgVector1} />
                  </div>
                </div>
                <div className="absolute inset-[15.56%_49.97%_83.72%_49.57%]" data-node-id="4062:726" data-name="Vector">
                  <div className="absolute inset-[-11.26%_-10%]">
                    <img alt="" className="block max-w-none size-full" src={imgVector2} />
                  </div>
                </div>
                <div className="absolute inset-[16.6%_50.2%_83.16%_49.8%]" data-node-id="4062:727" data-name="Vector">
                  <div className="absolute inset-[-33.79%_-0.87px]">
                    <img alt="" className="block max-w-none size-full" src={imgVector3} />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
<div className="absolute contents left-[1047px] top-[224px]" data-node-id="4062:728">
          <div className="absolute border-[0.907px] border-[rgba(30,57,97,0.85)] border-solid h-[52.264px] left-[1073.13px] rounded-[8.162px] top-[224px] w-[127.055px]" data-node-id="4062:729" style={{ backgroundImage: "linear-gradient(268.097420286487deg, rgba(0, 22, 58, 0.9) 4.2063%, rgba(0, 12, 34, 0.8) 27.99%, rgba(2, 18, 38, 0.86) 64.305%, rgba(4, 19, 44, 0.84) 99.341%)" }} />
          <p className="[word-break:break-word] absolute font-['Source_Han_Sans_SC'] font-normal leading-[normal] left-[1101.07px] not-italic text-[#5a7c9a] text-[14.972px] top-[228.51px] tracking-[-1.3475px] whitespace-nowrap" data-node-id="4062:730">
            04
          </p>
          <p className="[word-break:break-word] absolute font-['Source_Han_Sans_SC'] font-medium leading-[normal] left-[1122.03px] not-italic text-[#809bc3] text-[14.972px] top-[228.51px] whitespace-nowrap" data-node-id="4062:731">
            蜕变沉淀
          </p>
          <p className="[word-break:break-word] absolute font-['Source_Han_Sans_SC'] font-normal leading-[normal] left-[1122.03px] not-italic text-[#5a7c9a] text-[11.5px] top-[252.09px] whitespace-nowrap" data-node-id="4062:732">
            待解锁
          </p>
          <div className="absolute h-[12.227px] left-[1101.07px] top-[254.71px] w-[13.974px]" data-node-id="4062:733" data-name="Frame">
            <img alt="" className="absolute block inset-0 max-w-none size-full" src={imgFrame9} />
          </div>
          <div className="absolute contents left-[1047px] top-[228.96px]" data-node-id="4062:737">
            <div className="absolute contents left-[1047px] top-[228.96px]" data-node-id="4062:738">
              <div className="absolute contents left-[1047px] top-[228.96px]" data-node-id="4062:739">
                <div className="absolute left-[1047px] size-[41.049px] top-[228.96px]" data-node-id="4062:740">
                  <img alt="" className="absolute block inset-0 max-w-none size-full" src={imgEllipse4} />
                </div>
              </div>
            </div>
            <div className="absolute contents inset-[21.93%_43.96%_76.47%_55.22%]" data-node-id="4062:741">
              <div className="absolute contents inset-[21.93%_43.96%_76.47%_55.22%]" data-node-id="4062:742">
                <div className="absolute inset-[22.65%_43.96%_76.47%_55.23%]" data-node-id="4062:743" data-name="Vector">
                  <div className="absolute inset-[-9.22%_-5.56%]">
                    <img alt="" className="block max-w-none size-full" src={imgVector1} />
                  </div>
                </div>
                <div className="absolute inset-[21.93%_44.14%_77.35%_55.41%]" data-node-id="4062:744" data-name="Vector">
                  <div className="absolute inset-[-11.26%_-10%]">
                    <img alt="" className="block max-w-none size-full" src={imgVector2} />
                  </div>
                </div>
                <div className="absolute inset-[22.97%_44.37%_76.79%_55.63%]" data-node-id="4062:745" data-name="Vector">
                  <div className="absolute inset-[-33.79%_-0.87px]">
                    <img alt="" className="block max-w-none size-full" src={imgVector3} />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
<div className="absolute h-[118.642px] left-[1222px] top-[22px] w-[190.619px]" data-node-id="4062:746" data-name="image 88">
          <img alt="" className="absolute inset-0 max-w-none object-cover pointer-events-none size-full" src={imgImage88} />
        </div>
<div className="-translate-x-1/2 [word-break:break-word] absolute font-['Source_Han_Sans_SC'] font-medium leading-[0] left-[808px] not-italic text-[#a4f6ff] text-[0px] text-center top-[262px] whitespace-nowrap" data-node-id="4062:747">
          <p className="leading-[100.1500015258789%] mb-0 text-[19.824px]">成长之路</p>
          <p className="leading-[100.1500015258789%] text-[9.011px]">A BRIGHTER YOU</p>
        </div>
        <div className="absolute content-stretch flex gap-[12px] items-center left-[275px] top-[21px]" data-node-id="4043:312" data-name="Container">
          <div className="content-stretch flex flex-col items-start relative shrink-0" data-node-id="4043:313" data-name="Bold Text">
          </div>
          <div className="relative shrink-0 size-[12px]" data-node-id="4043:315" data-name="Icon" />
          <div className="h-[20px] relative shrink-0 w-[60px]" data-node-id="4043:316" data-name="Bold Text" />
        </div>
        <div className="figma-stroke figma-stroke-task absolute border border-[rgba(30,57,97,0.85)] border-solid content-stretch flex flex-col h-[318px] items-start left-[1004px] p-[13.639px] rounded-[10px] top-[338px] w-[394px]" data-node-id="4043:317" style={{ backgroundImage: "linear-gradient(268.2604542563795deg, rgba(14, 25, 43, 0.86) 1.1026%, rgba(22, 39, 71, 0.76) 16.424%, rgba(12, 26, 44, 0.86) 62.839%, rgba(10, 35, 76, 0.84) 98.83%)" }} data-name="Section">{decoration}
          <div className="content-stretch flex items-center relative shrink-0 w-full" data-node-id="4043:318" data-name="Heading 3">
            <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] font-black leading-[normal] not-italic relative shrink-0 text-[#eff6ff] text-[17.536px] whitespace-nowrap" data-node-id="4043:319">
              日志
            </p>
          </div>
          <div className="dashboard-task-activity" data-node-id="2047:4538" tabIndex={0} role="region" aria-label="任务操作日志">
            {activity.length === 0 ? <p className="dashboard-task-activity-empty">暂无任务日志，完成或修改任务后将在这里显示。</p> : activity.map(entry => <div className="dashboard-task-activity-row" key={entry.id}>
              <div className="dashboard-task-activity-avatar" aria-hidden="true">{entry.actorId}</div>
              <div className="dashboard-task-activity-content">
                <p><strong>{entry.actorName}</strong> 提交了任务 <span>{entry.taskTitle}</span></p>
                <time dateTime={entry.createdAt}>{new Date(entry.createdAt).toLocaleString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false })}</time>
              </div>
            </div>)}
          </div>
        </div>
        <DashboardTaskGrid key={identity} entries={orderedTasks.filter(entry => entry.index !== currentTaskIndex)} decoration={decoration} />
      </div>
    </div>
  );
}
