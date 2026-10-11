import { useJourney, useTaskStatus } from "./journey-context";
import type { ReactNode } from 'react';
import { effectiveCharacterCount } from "@/lib/text-length";

const taskDefinitions = [
  {
    "id": "3059",
    "taskLink": "https://zx6w57w0j34.feishu.cn/docx/B9f2d0P0ior6UBxTeFRc2ELmnlg",
    "title": "Day 1｜启程-公司基础介绍材料",
    "label": "DAY 1",
    "name": "启程",
    "description": " 建立业务范围、发展历程与经营理念的基础认知。阅读材料后，可以填写读后感或文档链接作为任务证据。",
    "materials": [
      {
        "title": "给 Muchener 的一封信",
        "description": "了解旅程的起点与真实问题。"
      },
      {
        "title": "公司基础介绍材料",
        "description": "建立对公司业务与工作方式的基础认知。"
      }
    ]
  },
  {
    "id": "3117",
    "taskLink": "https://zx6w57w0j34.feishu.cn/wiki/WEXlw0EoPizH2FkLx4ccCsvnngc",
    "title": "评测一/规则拆解",
    "label": "评测一",
    "name": "规则拆解",
    "description": "规则不是用来背诵的，是用来拆解的 —— 看清任务目标，拆出判断维度，认出不能碰的红线，也知道哪里必须停下来问。",
    "materials": [
      {
        "title": "项目规则文档拆解作业 SOP",
        "description": "项目规则文档标准化拆解流程的文档"
      },
      {
        "title": "项目规则文档拆解教学视频",
        "description": "项目规则文档标准化拆解流程的视频"
      }
    ]
  },
  {
    "id": "3175",
    "taskLink": "https://zx6w57w0j34.feishu.cn/docx/KEe7dazYooA2J2x0zPUcGhshnhb",
    "title": "评测二/模型判断",
    "label": "评测二",
    "name": "模型判断",
    "description": "拒绝 \"我觉得\"。在 A 与 B 之间，按维度比较、拿证据说话，把判断写成别人能复核的理由。",
    "materials": [
      {
        "title": "模型回答判断与理由书写",
        "description": "AI 数据项目里如何按照统一标准进行判定的文档"
      },
      {
        "title": "模型回答质量判断教学视频",
        "description": "AI 数据项目里如何按照统一标准进行判定的视频"
      }
    ]
  },
  {
    "id": "3233",
    "taskLink": "https://zx6w57w0j34.feishu.cn/docx/JGyrdojJEoFSGuxxfULc46gfnvd",
    "title": "评测三/数据构造",
    "label": "评测三",
    "name": "数据构造",
    "description": "从约束出发，亲手构造一份结构清晰、内容扎实的数据；做完不是结束 —— 自检、记录、再修正，才算交付。",
    "materials": [
      {
        "title": "通用数据构造讲义",
        "description": "安全可核验数据集构造培训讲义"
      },
      {
        "title": "通用数据构造教学视频",
        "description": "安全可核验数据集构造培训视频"
      }
    ]
  },
  {
    "id": "3291",
    "taskLink": "https://zx6w57w0j34.feishu.cn/docx/N1CmdNwvtoF6ubxGGK6cztvnnpg",
    "title": "宝藏一｜公司价值",
    "label": "宝藏一",
    "name": "公司价值",
    "description": "系统了解沐晨AI的业务版图、服务对象及在AI数据服务领域的战略定位，深入理解公司以真实客户需求为导向、以AI数据服务与人才培养为核心的发展理念。",
    "materials": [
      {
        "title": "使命愿景价值观",
        "description": "了解沐晨 AI 的使命、愿景与核心价值观。"
      },
      {
        "title": "公司价值体现视频",
        "description": "文档的讲解视频"
      }
    ]
  },
  {
    "id": "3349",
    "taskLink": "https://zx6w57w0j34.feishu.cn/docx/B9uhdkLwUoqqIYxeh9TcWErbnHd?from=from_parent_sheet",
    "title": "宝藏二/AI与数据基础",
    "label": "宝藏二",
    "name": "AI与数据基础",
    "description": "在大模型流利回答一切之前，先学会看见它的边界 —— 理解为什么 AI 时代，人的判断与证据不可替代",
    "materials": [
      {
        "title": "AI与数据基础文档",
        "description": "掌握行业运作、工具并对AI输出负责的基本方法"
      },
      {
        "title": "AI与数据基础视频",
        "description": "文档的讲解视频"
      }
    ]
  },
  {
    "id": "3407",
    "taskLink": "https://zx6w57w0j34.feishu.cn/docx/StsEdbAXzorBNUxxX89cQPgcnyg",
    "title": "宝藏四/交付边界",
    "label": "宝藏四",
    "name": "交付边界",
    "description": "规则之内独立判断，规则之外及时提报 —— 这是你与团队协作的第一份专业",
    "materials": [
      {
        "title": "项目中的关键角色与新人责任边界",
        "description": "掌握项目角色分工、新人职责边界与工作红线"
      },
      {
        "title": "项目交付与责任边界视频",
        "description": "文档的讲解视频"
      }
    ]
  },
  {
    "id": "3465",
    "taskLink": "https://zx6w57w0j34.feishu.cn/docx/Tsq7daDoIoPhNoxXBDbcTMaRnEc?from=from_parent_sheet",
    "title": "宝藏三/项目认知",
    "label": "宝藏三",
    "name": "项目认知",
    "description": "从客户的真实问题出发，看清 AI 数据如何在业务里创造价值，也找到你在这条质量链条上的位置",
    "materials": [
      {
        "title": "MDOS 项目经理全流程操作指引",
        "description": "了解项目经理的全流程操作"
      },
      {
        "title": "项目认知视频",
        "description": "文档的讲解视频"
      }
    ]
  }
];
const taskOrder = ["3059", "3291", "3349", "3465", "3407", "3117", "3175", "3233"];
export const executionTasks = taskOrder.map(id => taskDefinitions.find(task => task.id === id)!);
export function TaskCards() {
  const taskStatus = useTaskStatus();
  const { experience } = useJourney();
  return <div className="journey-task-grid">
    {executionTasks.map((task, index) => {
      const status = taskStatus(index);
      const node = experience?.journeyTasks.find(item => item.position === index + 1);
      const pending = ["SUBMITTED", "IN_REVIEW"].includes(node?.assignmentStatus ?? "");
      const revising = node?.isRevising;
      const needsRevision = node?.assignmentStatus === "NEEDS_REVISION";
      return <button type="button" key={task.id} className={`journey-task-card journey-task-${status}`}
        data-action="open-task" data-task-index={index} aria-disabled={status === "locked"}
        data-node-id={status === "completed" ? "2039:4147" : status === "locked" ? "2039:4162" : "2039:4177"}>
        <span className="journey-task-icon"><img src="/assets/project9/d6a61.png" alt="" /></span>
        <span className="journey-task-status">{needsRevision ? "待修改" : revising ? "修改中" : pending ? "待审核" : status === "completed" ? "已完成" : status === "locked" ? "未解锁" : "进行中"}</span>
        <span className="journey-task-number">{String(index + 1).padStart(2, "0")}</span>
        <span className="journey-task-title">{task.title}</span>
        <span className="journey-task-description">{task.description.trim()}</span>
        <span className="journey-task-footer">
          <span>{needsRevision || revising ? "修改后重新提交审核" : pending ? "已提交，等待审核" : status === "locked" ? "需要提交上一任务" : status === "completed" ? "审核已通过" : "提交后解锁下一关"}</span>
          <strong>{needsRevision || revising ? "继续修改 →" : pending ? "查看提交 →" : status === "completed" ? "回看任务 →" : status === "locked" ? "需要提交上一任务" : "进入任务 →"}</strong>
        </span>
      </button>;
    })}
  </div>;
}
export type ExecutionTask = (typeof executionTasks)[number];
type ExecutionProps = { task: ExecutionTask; panelDecoration: ReactNode; backDecoration: ReactNode };

const assetPathPrefix = "/assets/project9";
const imgImage74 = `${assetPathPrefix}/90975.png`;
const imgRectangle60 = `${assetPathPrefix}/execution/59316.svg`;

const imgCyanGlow = '/assets/project9/b8c95.svg';
const imgPurpleGlow = '/assets/project9/aa530.svg';
const imgButton = '/assets/project9/f6723.svg';
const imgVectorStroke = '/assets/project9/1bed3.svg';

function ExecutionSidebar({ task, backDecoration }: Pick<ExecutionProps, 'task' | 'backDecoration'>) {
const { learnerName } = useJourney();
return <><button type="button" className="col-1 grid-cols-[max-content] grid-rows-[max-content] inline-grid ml-[114px] mt-[105px] place-items-start relative row-1" data-action="return-tasks" data-node-id="2038:3103">
          <div className="col-1 grid-cols-[max-content] grid-rows-[max-content] inline-grid ml-0 mt-0 place-items-start relative row-1" data-node-id="2038:3104">
            <div className="border-[#e8f6ff] border-[1.6px] border-solid col-1 h-[68px] ml-0 mt-0 pointer-events-none relative rounded-[16px] row-1 w-[261px] figma-stroke figma-stroke-back" data-node-id="2038:3105">{backDecoration}
              <div aria-hidden className="absolute inset-0 rounded-[16px]" style={{ backgroundImage: "linear-gradient(255.0525143236887deg, rgba(201, 231, 255, 0.49) 2.4688%, rgba(52, 113, 195, 0.202) 14.255%, rgba(1, 14, 105, 0.407) 44.37%, rgba(10, 0, 153, 0.49) 90.024%)" }} />
              <div className="absolute inset-0 rounded-[inherit] shadow-[inset_16px_3px_44.8px_2px_rgba(114,133,255,0.64)]" />
            </div>
          </div>
          <div className="col-1 content-stretch flex gap-[24px] items-center justify-center ml-[20px] mt-[19px] relative row-1 w-[221.245px]" data-node-id="2038:3106">
            <div className="flex h-[20.956px] items-center justify-center relative shrink-0 w-[20.961px]" data-node-id="2038:3107">
              <div className="-scale-y-100 flex-none rotate-[134.03deg]">
                <div className="h-[14.922px] relative w-[14.722px]">
                  <div className="absolute inset-[-6.7%_-6.79%]">
                    <img alt="" className="block max-w-none" src={imgRectangle60} />
                  </div>
                </div>
              </div>
            </div>
            <div className="content-stretch flex items-center relative shrink-0" data-node-id="2038:3108">
              <div className="content-stretch flex flex-col items-start relative shrink-0 w-[124px]" data-node-id="2038:3109">
                <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] font-medium leading-[normal] not-italic relative shrink-0 text-[21px] text-white w-[141px]" data-node-id="2038:3110">
                  返回任务列表
                </p>
              </div>
            </div>
          </div>
        </button>
        <div className="col-1 grid-cols-[max-content] grid-rows-[max-content] inline-grid ml-[107px] mt-[348px] place-items-start relative row-1" data-node-id="2038:3111">
          <div className="bg-[#1a4669] col-1 h-[41.999px] ml-0 mt-0 relative row-1 w-[294.529px]" data-node-id="2038:3112" data-name="Text">
            <p className="[word-break:break-word] absolute font-['Source_Han_Sans_SC'] font-normal leading-[29.518px] left-[16.98px] not-italic text-[#8defff] text-[17.89px] top-[4.75px] tracking-[2.1468px] whitespace-nowrap" data-node-id="2038:3113">
              你好，{learnerName} · 你的成长航线
            </p>
          </div>
          <div className="col-1 content-stretch flex flex-col items-center justify-center max-w-[515.375px] ml-0 mt-[75px] relative row-1" data-node-id="2038:3114" data-name="Heading 1">
            <div className="[word-break:break-word] font-['Source_Han_Sans_SC'] font-black leading-[0] not-italic relative shrink-0 text-[#f2fcff] text-[0px] tracking-[3.36px] whitespace-nowrap" data-node-id="2038:3115" style={{ fontWeight: task.label.startsWith('宝藏') ? 700 : 900 }}>
              <p className="leading-[75px] mb-0 text-[#3ed8ef] text-[68px]">{task.label}</p>
              <p className="leading-[75px] text-[68px]">{task.name}</p>
            </div>
          </div>
          <p className="[word-break:break-word] col-1 font-['Source_Han_Sans_SC'] font-normal leading-[28.8px] ml-0 mt-[258px] not-italic relative row-1 text-[#9bbad3] text-[20px] w-[367px]" data-node-id="2038:3116">{task.description}</p>
        </div></>;
}

export function ExecutionDetail({ task, panelDecoration, backDecoration, openedMaterials }: ExecutionProps & { openedMaterials: [boolean, boolean] }) {
  return (
    <div className="content-stretch flex flex-col items-start relative size-full" data-node-id="2038:3059" data-name="day1 任务详情" data-material-one-opened={openedMaterials[0]} data-material-two-opened={openedMaterials[1]}>
      <div className="grid-cols-[max-content] grid-rows-[max-content] inline-grid leading-[0] place-items-start relative shrink-0" data-node-id="2038:3060">
        <div className="col-1 h-[1080px] ml-0 mt-0 relative row-1 w-[1920px]" data-node-id="2038:3061" data-name="image 74">
          <img alt="" className="absolute inset-0 max-w-none object-cover pointer-events-none size-full" src={imgImage74} />
        </div>
        <div className="border-[#e8f6ff] border-[1.6px] border-solid col-1 content-stretch flex flex-col items-start ml-[654px] mt-[105px] p-[24px] relative rounded-[16px] row-1 shadow-[0px_0px_39.9px_0px_rgba(0,112,191,0.66)] w-[1180px] figma-stroke figma-stroke-panel holo-panel" data-node-id="2038:3062" data-name="Section">{panelDecoration}
          <div aria-hidden className="absolute inset-0 pointer-events-none rounded-[16px]" style={{ backgroundImage: "linear-gradient(264.5472023483291deg, rgba(0, 50, 91, 0.41) 2.4688%, rgba(36, 77, 132, 0.169) 14.255%, rgba(0, 7, 55, 0.34) 44.37%, rgba(7, 1, 94, 0.41) 90.024%)" }} />
          <div className="border-[rgba(65,164,214,0.25)] border-b border-solid h-[169px] relative shrink-0 w-full" data-node-id="2038:3063" data-name="Header">
            <div className="absolute content-stretch flex flex-col items-start left-0 top-0 w-[150px]" data-node-id="2038:3064" data-name="Container">
              <div className="h-[26.391px] relative shrink-0 w-full" data-node-id="2038:3065" data-name="Container">
                <p className="-translate-x-full [word-break:break-word] absolute font-['Source_Han_Sans_SC'] font-normal leading-[31.906px] left-[65.4px] not-italic text-[#59e6f4] text-[19.337px] text-right top-[4px] tracking-[3.4806px] whitespace-nowrap" data-node-id="2038:3066">
                  探索营
                </p>
              </div>
              <div className="content-stretch flex flex-col h-[36px] items-start pt-[4px] relative shrink-0 w-full" data-node-id="2038:3067" data-name="Heading 2">
                <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] font-bold leading-[82.014px] not-italic relative shrink-0 text-[#e9f9ff] text-[49.706px] text-right whitespace-nowrap" data-node-id="2038:3068">{task.title}</p>
              </div>
            </div>
            <div className="absolute h-[22px] left-[1055.8px] top-[40.39px] w-[73px]" data-node-id="2038:3069" data-name="Small" />
            <p className="[word-break:break-word] absolute font-['Source_Han_Sans_SC'] font-normal leading-[28.8px] left-[0.4px] not-italic text-[#b2c0db] text-[16px] top-[116.4px] whitespace-nowrap" data-node-id="2038:3070">
              验证新人可以先完成学习输入，再留下当前阶段的结构化证据并继续旅程。
            </p>
          </div>
          <div className="h-[639.6px] relative shrink-0 w-[1095.57px]" data-node-id="2038:3071" data-name="Container:margin">
            <div className="absolute h-[681.334px] left-0 right-0 top-[21.35px]" data-node-id="2038:3072" data-name="Container">
              <div className="absolute gap-x-[26.432388305664062px] gap-y-[26.432388305664062px] grid-cols-[__528.65px_528.65px] grid-rows-[_372px] inline-grid left-[19.4px] top-[15.05px]" data-node-id="2038:3073" data-name="Container">
                <div className="border border-[#31b7a9] border-solid col-1 content-stretch flex flex-col items-start justify-self-stretch p-[19px] relative rounded-[8px] row-1 self-stretch shrink-0" data-node-id="2038:3074" style={{ backgroundImage: "linear-gradient(153.76941883082628deg, rgba(6, 65, 72, 0.74) 6.1733%, rgba(3, 38, 46, 0.84) 50%, rgba(0, 17, 26, 0.94) 93.827%)" }} data-name="Article">
                  <div className="content-stretch flex items-center justify-between relative shrink-0 w-full" data-node-id="2038:3075" data-name="Header">
                    <div className="content-stretch flex flex-col items-start relative shrink-0" data-node-id="2038:3076" data-name="Text">
                      <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] font-normal leading-[31.152px] not-italic relative shrink-0 text-[#72a9c8] text-[18.88px] tracking-[2.2656px] whitespace-nowrap" data-node-id="2038:3077">
                        材料 01
                      </p>
                    </div>
                    <div className="content-stretch flex flex-col items-start relative shrink-0" data-node-id="2038:3078" data-name="Bold Text">
                      <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] font-black leading-[39.6px] not-italic relative shrink-0 text-[#77ffcf] text-[24px] text-right whitespace-nowrap" data-node-id="2038:3079">
                        {openedMaterials[0] ? "已完成" : "进行中"}
                      </p>
                    </div>
                  </div>
                  <div className="content-stretch flex flex-col h-[117.058px] items-start min-h-[90.62533569335938px] pt-[26.432px] relative shrink-0 w-[464.455px]" data-node-id="2038:3080" data-name="Heading 2">
                    <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] font-black leading-[45.313px] not-italic relative shrink-0 text-[#eefcff] text-[30.208px] whitespace-nowrap" style={{ fontWeight: task.id === '3349' || task.id === '3407' ? 700 : 900 }} data-node-id="2038:3081">{task.materials[0].title}</p>
                  </div>
                  <div className="content-stretch flex flex-col h-[77.409px] items-start pb-[28.32px] pt-[13.216px] relative shrink-0 w-[464.455px]" data-node-id="2038:3082" data-name="Paragraph">
                    <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] font-normal leading-[34.268px] not-italic relative shrink-0 text-[#799db8] text-[20.768px] whitespace-nowrap" data-node-id="2038:3083">{task.materials[0].description}</p>
                  </div>
                  <button type="button" className="bg-[rgba(39,151,181,0.17)] border-[#75f5ff] border-[1.888px] border-solid content-stretch flex h-[83.811px] items-center justify-center min-h-[75.52111053466797px] px-[22.656px] py-[15.104px] relative rounded-[11.328px] shrink-0 w-[464.455px]" data-action="material-1" data-node-id="2038:3084" data-name="Link">
                    <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] font-black leading-[49.844px] not-italic relative shrink-0 text-[#dffcff] text-[30.208px] whitespace-nowrap" data-node-id="2038:3085">
                      {openedMaterials[0] ? "重新打开材料 01" : "打开材料 01"}
                    </p>
                  </button>
                </div>
                <div className="border border-[#48eaff] border-solid col-2 content-stretch flex flex-col items-start justify-self-stretch p-[19px] relative rounded-[8px] row-1 self-stretch shadow-[0px_0px_18px_0px_rgba(46,223,255,0.2)] shrink-0" data-node-id="2038:3086" data-name="Article">
                  <div aria-hidden className="absolute inset-0 pointer-events-none rounded-[8px]" style={{ backgroundImage: "linear-gradient(153.76941883082628deg, rgba(12, 38, 68, 0.9) 6.1733%, rgba(1, 11, 24, 0.94) 93.827%)" }} />
                  <div className="content-stretch flex items-center justify-between relative shrink-0 w-full" data-node-id="2038:3087" data-name="Header">
                    <div className="content-stretch flex flex-col items-start relative shrink-0" data-node-id="2038:3088" data-name="Text">
                      <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] font-normal leading-[31.152px] not-italic relative shrink-0 text-[#72a9c8] text-[18.88px] tracking-[2.2656px] whitespace-nowrap" data-node-id="2038:3089">
                        材料 02
                      </p>
                    </div>
                    <div className="content-stretch flex flex-col items-start relative shrink-0" data-node-id="2038:3090" data-name="Bold Text">
                      <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] font-black leading-[39.6px] not-italic relative shrink-0 text-[#a7ccdf] text-[24px] text-right whitespace-nowrap" data-node-id="2038:3091">
                        {openedMaterials[1] ? "已完成" : "进行中"}
                      </p>
                    </div>
                  </div>
                  <div className="content-stretch flex flex-col h-[117.058px] items-start min-h-[90.62533569335938px] pt-[26.432px] relative shrink-0 w-[464.455px]" data-node-id="2038:3092" data-name="Heading 2">
                    <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] font-black leading-[45.313px] not-italic relative shrink-0 text-[#eefcff] text-[30.208px] whitespace-nowrap" style={{ fontWeight: task.id === '3349' || task.id === '3407' ? 700 : 900 }} data-node-id="2038:3093">{task.materials[1].title}</p>
                  </div>
                  <div className="content-stretch flex flex-col h-[77.409px] items-start pb-[28.32px] pt-[13.216px] relative shrink-0 w-[464.455px]" data-node-id="2038:3094" data-name="Paragraph">
                    <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] font-normal leading-[34.268px] not-italic relative shrink-0 text-[#799db8] text-[20.768px] whitespace-nowrap" data-node-id="2038:3095">{task.materials[1].description}</p>
                  </div>
                  <button type="button" className="bg-[rgba(39,151,181,0.17)] border-[#75f5ff] border-[1.888px] border-solid content-stretch flex h-[83.811px] items-center justify-center min-h-[75.52111053466797px] px-[22.656px] py-[15.104px] relative rounded-[11.328px] shrink-0 w-[464.455px]" data-action="material-2" data-node-id="2038:3096" data-name="Link">
                    <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] font-black leading-[49.844px] not-italic relative shrink-0 text-[#dffcff] text-[30.208px] whitespace-nowrap" data-node-id="2038:3097">
                      {openedMaterials[1] ? "重新打开材料 02" : "打开材料 02"}
                    </p>
                  </button>
                  <div className="absolute inset-0 pointer-events-none rounded-[inherit] shadow-[inset_0px_0px_28px_0px_rgba(35,176,241,0.13)]" />
                </div>
              </div>
              <button type="button" className="-translate-x-1/2 absolute bg-gradient-to-r border-[#75f5ff] border-[2.149px] border-solid from-[#42dced] h-[104px] left-[calc(50%+0.12px)] rounded-[15.042px] shadow-[0px_0px_30.084px_0px_#2edfff,0px_0px_55.871px_0px_rgba(18,195,255,0.55)] to-[#5ceeff] top-[462.05px] via-[#31c9f5] via-[45%] w-[585px]" data-action="view-task" data-node-id="2038:3098" data-name="Link">
                <div className="-translate-x-1/2 -translate-y-1/2 absolute content-stretch flex gap-[14px] items-center justify-center left-[calc(50%+0.5px)] top-[calc(50%+0.5px)]" data-node-id="2038:3099">
                  <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] font-black leading-[56.73px] not-italic relative shrink-0 text-[#03245f] text-[34.382px] tracking-[2.7505px] whitespace-nowrap" data-node-id="2038:3100">
                    查看任务详情并提交证据
                  </p>
                  <div className="content-stretch flex flex-col items-start relative shrink-0" data-node-id="2038:3101" data-name="Text">
                    <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] font-black leading-[56.73px] not-italic relative shrink-0 text-[#03245f] text-[34.382px] tracking-[2.7505px] whitespace-nowrap" data-node-id="2038:3102">
                      →
                    </p>
                  </div>
                </div>
              </button>
            </div>
          </div>
          <div className="absolute inset-0 pointer-events-none rounded-[inherit] shadow-[inset_16px_3px_44.8px_0px_rgba(114,133,255,0.36)]" />
        </div>
        <ExecutionSidebar task={task} backDecoration={backDecoration} />

      </div>
    </div>
  );
}

export function ExecutionView({ task, panelDecoration, backDecoration, record, setRecord, readOnly = false, canRevise = false, canCancelRevision = false, revisionBusy = false, submitting = false, submitDisabled = false, submitLabel = "提交任务证据" }: ExecutionProps & { record: string; setRecord: (value: string) => void; readOnly?: boolean; canRevise?: boolean; canCancelRevision?: boolean; revisionBusy?: boolean; submitting?: boolean; submitDisabled?: boolean; submitLabel?: string }) {
  return (
    <div className="content-stretch flex flex-col items-start relative size-full" data-node-id="2038:3524" data-name="day1 查看任务以及任务提交界面">
      <div className="grid-cols-[max-content] grid-rows-[max-content] inline-grid leading-[0] place-items-start relative shrink-0" data-node-id="2038:3525">
        <div className="col-1 h-[1080px] ml-0 mt-0 relative row-1 w-[1920px]" data-node-id="2038:3526" data-name="image 74">
          <img alt="" className="absolute inset-0 max-w-none object-cover pointer-events-none size-full" src={imgImage74} />
        </div>
        <div className="border-[#e8f6ff] border-[1.6px] border-solid col-1 content-stretch flex flex-col h-[859.8px] items-start ml-[654px] mt-[105px] p-[24px] relative rounded-[16px] row-1 shadow-[0px_0px_39.9px_0px_rgba(0,112,191,0.66)] w-[1180px] figma-stroke figma-stroke-panel holo-panel" data-node-id="2038:3527" data-name="Section">{panelDecoration}
          <div aria-hidden className="absolute inset-0 pointer-events-none rounded-[16px]" style={{ backgroundImage: "linear-gradient(264.5472023483291deg, rgba(0, 50, 91, 0.41) 2.4688%, rgba(36, 77, 132, 0.169) 14.255%, rgba(0, 7, 55, 0.34) 44.37%, rgba(7, 1, 94, 0.41) 90.024%)" }} />
          <div className="border-[rgba(65,164,214,0.25)] border-b border-solid h-[207px] mb-[-18px] relative shrink-0 w-[1128px]" data-node-id="2038:3528" data-name="Header">
            <div className="absolute content-stretch flex flex-col items-start left-0 top-0 w-[150px]" data-node-id="2038:3529" data-name="Container">
              <div className="h-[26.391px] relative shrink-0 w-full" data-node-id="2038:3530" data-name="Container" />
              <div className="content-stretch flex flex-col h-[36px] items-start pl-[22px] pt-[4px] relative shrink-0 w-[202px]" data-node-id="2038:3531" data-name="Heading 2">
                <div className="grid-cols-[max-content] grid-rows-[max-content] inline-grid leading-[0] place-items-start relative shrink-0" data-node-id="2038:3532">
                  <p className="[word-break:break-word] col-1 font-['Source_Han_Sans_SC'] font-black leading-[26.4px] ml-0 mt-0 not-italic relative row-1 text-[#bfeaf4] text-[16px] whitespace-nowrap" data-node-id="2038:3533">
                    第一步：点击查看任务链接
                  </p>
                  <button type="button" className="col-1 grid-cols-[max-content] grid-rows-[max-content] inline-grid ml-[254.4px] mt-[47px] place-items-start relative row-1" data-action="task-link" data-node-id="2038:3534">
                    <div className="col-1 h-[87px] ml-0 mt-0 relative row-1 w-[548px]" data-node-id="2038:3535" data-name="CyanGlow">
                      <div className="absolute inset-[-20.69%_-3.28%]">
                        <img alt="" className="block max-w-none" src={imgCyanGlow} />
                      </div>
                    </div>
                    <div className="col-1 h-[87px] ml-0 mt-0 relative row-1 w-[548px]" data-node-id="2038:3536" data-name="PurpleGlow">
                      <div className="absolute inset-[-30.46%_-4.84%]">
                        <img alt="" className="block max-w-none" src={imgPurpleGlow} />
                      </div>
                    </div>
                    <div className="col-1 grid-cols-[max-content] grid-rows-[max-content] inline-grid ml-0 mt-0 place-items-start relative row-1" data-node-id="2038:3537">
                      <div className="col-1 h-[87px] ml-0 mt-0 relative row-1 w-[548px]" data-node-id="2038:3538" data-name="Button">
                        <div className="absolute inset-[-1.15%_-0.18%]">
                          <img alt="" className="block max-w-none" src={imgButton} />
                        </div>
                      </div>
                      <div className="col-1 grid-cols-[max-content] grid-rows-[max-content] inline-grid ml-[117px] mt-[21px] place-items-start relative row-1" data-node-id="2038:3539">
                        <div className="col-1 content-stretch flex items-center justify-between ml-0 mt-0 relative row-1 w-[229px]" data-node-id="2038:3540">
                          <div className="content-stretch flex gap-[16px] items-center relative shrink-0" data-node-id="2038:3541">
                            <div className="h-[27.012px] relative shrink-0 w-[23.636px]" data-node-id="2038:3542" data-name="Vector (Stroke)">
                              <img alt="" className="absolute block inset-0 max-w-none" src={imgVectorStroke} />
                            </div>
                            <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] font-bold leading-[normal] not-italic relative shrink-0 text-[32px] text-center text-white whitespace-nowrap" data-node-id="2038:3543">
                              点这里查看任务详情
                            </p>
                          </div>
                        </div>
                      </div>
                    </div>
                  </button>
                </div>
              </div>
            </div>
            <div className="absolute h-[22px] left-[1055.8px] top-[40.39px] w-[73px]" data-node-id="2038:3544" data-name="Small" />
          </div>
          <div className="h-[639.6px] relative shrink-0 w-[1095.57px]" data-node-id="2038:3545" data-name="Container:margin">
            <div className="absolute h-[681.334px] left-0 right-0 top-[21.35px]" data-node-id="2038:3546" data-name="Container">
              <div className="absolute contents left-[19.4px] top-[15.05px]" data-node-id="2038:3547">
                <p className="[word-break:break-word] absolute font-['Source_Han_Sans_SC'] font-black leading-[26.4px] left-[19.4px] not-italic text-[#bfeaf4] text-[16px] top-[15.05px] whitespace-nowrap" data-node-id="2038:3548">
                  第二步：填写您的学习记录的云文档连接、可结合AI自查进行修改
                </p>
                <div className="absolute bg-[rgba(3,21,42,0.45)] border-[#3a9fc6] border-[1.25px] border-solid content-stretch flex flex-col h-[382px] items-start left-[19.4px] min-h-[150px] overflow-clip p-[14px] rounded-[8px] top-[51.05px] w-[1076px]" data-node-id="2038:3549" data-name="Text Area">
                  <div className="grid-cols-[max-content] grid-rows-[max-content] inline-grid leading-[0] place-items-start relative shrink-0" data-node-id="2038:3550">
                    <textarea className="bg-[rgba(39,151,181,0.18)] border-[1.888px] border-[rgba(117,245,255,0.24)] border-solid col-1 h-[349px] ml-0 mt-0 relative rounded-[11.328px] row-1 w-[688px]" data-node-id="2038:3551"  aria-label="当前任务学习记录或云文档链接" value={record} readOnly={submitting || readOnly || revisionBusy} onChange={event => setRecord(event.target.value)} placeholder="填写你的学习记录或云文档链接" />
                  </div>
                </div>
                <div className="absolute contents left-[56.4px] top-[377.05px]" data-node-id="2038:3552">
                  <p className="[word-break:break-word] absolute font-['Source_Han_Sans_SC'] font-black leading-[21.45px] left-[56.4px] not-italic text-[#b42318] text-[13px] top-[377.05px] whitespace-nowrap" data-node-id="2038:3553">{`已输入 ${effectiveCharacterCount(record)} 个有效字符｜要求 40-8000｜还差 ${Math.max(0, 40 - effectiveCharacterCount(record))} 个`}</p>
                </div>
                <div className="absolute contents left-[830.4px] top-[366.05px]" data-node-id="2038:3554">
                  <button type="button" className="absolute bg-[#2854d7] border-[1.287px] border-[rgba(0,0,0,0)] border-solid content-stretch flex h-[49.428px] items-center justify-center left-[830.4px] min-h-[49.42789077758789px] px-[18.535px] py-[10.297px] rounded-[10.297px] top-[366.05px] w-[240px]" data-action="execution-check" data-node-id="2038:3555" data-name="Button">
                    <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] font-black leading-[27.185px] not-italic relative shrink-0 text-[16.476px] text-center text-white whitespace-nowrap" data-node-id="2038:3556">
                      ✦ 开始 AI 自查 →
                    </p>
                  </button>
                </div>
                <p className="[word-break:break-word] absolute font-['Source_Han_Sans_SC'] font-black leading-[26.4px] left-[942.4px] not-italic text-[#ededed] text-[16px] top-[72.05px] whitespace-nowrap" data-action="execution-history" role="button" tabIndex={0} onKeyDown={event => { if (event.key === "Enter" || event.key === " ") { event.preventDefault(); event.currentTarget.click(); } }} data-node-id="2038:3557">
                  历史AI自查记录↗
                </p>
              </div>
              {(canRevise || canCancelRevision) && <button type="button" className="execution-revision-action" disabled={revisionBusy || submitting} data-action={canRevise ? "revise-proof" : "cancel-revision"}>{revisionBusy ? "处理中…" : canRevise ? "重新修改" : "取消本次修改"}</button>}
              <button type="button" className="-translate-x-1/2 absolute bg-gradient-to-r border-[#75f5ff] border-[2.149px] border-solid from-[#42dced] h-[104px] left-[calc(50%+0.12px)] rounded-[15.042px] shadow-[0px_0px_30.084px_0px_#2edfff,0px_0px_55.871px_0px_rgba(18,195,255,0.55)] to-[#5ceeff] top-[462.05px] via-[#31c9f5] via-[45%] w-[585px]" disabled={submitDisabled} aria-busy={submitting} data-action="review-proof" data-node-id="2038:3558" data-name="Link">
                <div className="-translate-x-1/2 -translate-y-1/2 absolute content-stretch flex gap-[14px] items-center justify-center left-[calc(50%+0.5px)] top-[calc(50%+0.5px)]" data-node-id="2038:3559">
                  <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] font-black leading-[56.73px] not-italic relative shrink-0 text-[#03245f] text-[34.382px] tracking-[2.7505px] whitespace-nowrap" data-node-id="2038:3560">
                    {submitLabel}
                  </p>
                  <div className="content-stretch flex flex-col items-start relative shrink-0" data-node-id="2038:3561" data-name="Text">
                    <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] font-black leading-[56.73px] not-italic relative shrink-0 text-[#03245f] text-[34.382px] tracking-[2.7505px] whitespace-nowrap" data-node-id="2038:3562">
                      →
                    </p>
                  </div>
                </div>
              </button>
            </div>
          </div>
          <div className="absolute inset-0 pointer-events-none rounded-[inherit] shadow-[inset_16px_3px_44.8px_0px_rgba(114,133,255,0.36)]" />
        </div>
        <ExecutionSidebar task={task} backDecoration={backDecoration} />

      </div>
    </div>
  );
}
