import type { ReactNode } from "react";
import { executionTasks } from "./ExecutionPages";
import { useTaskStatus } from "./journey-context";
import type { PreviewIdentity } from "./previewStorage";
import { readTaskActivity } from "./taskActivity";

const assetPathPrefix = "/assets/project29/dashboard-2047";
const imgEllipse2 = `${assetPathPrefix}/40565.svg`;
const imgEllipse3 = "/assets/project29/54dd9.svg";
const imgEllipse4 = `${assetPathPrefix}/cfbf2.svg`;
const imgFrame5 = `${assetPathPrefix}/11489.svg`;
const imgFrame6 = `${assetPathPrefix}/7545d.svg`;
const imgImage87 = `${assetPathPrefix}/07842.webp`;
const imgImage88 = `${assetPathPrefix}/c8f76.webp`;
const imgLine3 = `${assetPathPrefix}/29038.svg`;
const imgLine4 = `${assetPathPrefix}/5555c.svg`;
const imgRectangle64 = `${assetPathPrefix}/0b881.svg`;
const imgVector = `${assetPathPrefix}/0b3ec.svg`;
const imgVector1 = `${assetPathPrefix}/608f9.svg`;
const imgVector2 = "/assets/project29/63e0c.svg";
const imgVector3 = "/assets/project29/cec96.svg";
const imgVectorStroke = `${assetPathPrefix}/d01e9.svg`;

export function DashboardMain({ decoration, stageDecoration, identity }: { decoration: ReactNode; stageDecoration: ReactNode; identity: PreviewIdentity | null }) {
  const taskStatus = useTaskStatus();
  const active = executionTasks.findIndex((_, index) => ["active", "revision"].includes(taskStatus(index)));
  const currentTaskIndex = active === -1 ? executionTasks.length - 1 : active;
  const task = executionTasks[currentTaskIndex];
  const activity = readTaskActivity(executionTasks, identity);
  return <>
        <div className="absolute contents left-[357px] top-[359px]" data-node-id="2047:4422">
          <div className="absolute contents left-[357px] top-[359px]" data-node-id="2047:4423">
            <div className="figma-stroke figma-stroke-task absolute border-2 border-[rgba(30,57,97,0.85)] border-solid h-[456px] left-[357px] rounded-[18px] top-[359px] w-[1016px]" data-node-id="2047:4424" style={{ backgroundImage: "linear-gradient(266.8739361050559deg, rgba(14, 25, 43, 0.86) 1.1026%, rgba(22, 39, 71, 0.76) 16.424%, rgba(12, 26, 44, 0.86) 62.839%, rgba(10, 35, 76, 0.84) 98.83%)" }} >{decoration}</div>
            <p className="[word-break:break-word] absolute font-['Source_Han_Sans_SC'] font-black leading-[normal] left-[403px] not-italic text-[#eff6ff] text-[34.55px] top-[392px] whitespace-nowrap" data-node-id="2047:4425">
              当前任务
            </p>
            <div className="absolute contents left-[568px] top-[404px]" data-node-id="2047:4426">
              <div className="absolute bg-gradient-to-r from-[#bff359] h-[31.71px] left-[568px] rounded-[5.115px] to-[#60ed8e] top-[404px] w-[109.452px]" data-node-id="2047:4427" />
              <div className="-translate-y-1/2 [word-break:break-word] absolute flex flex-col font-['Source_Han_Sans_SC'] font-medium h-[1.023px] justify-center leading-[0] left-[575.16px] not-italic text-[#031308] text-[15.344px] top-[419.86px] w-[95.131px]" data-node-id="2047:4428">
                <p className="leading-[normal]">{`探索任务·${String(currentTaskIndex + 1).padStart(2, "0")}`}</p>
              </div>
            </div>
            <div className="absolute border-[2.137px] border-[rgba(30,57,97,0.85)] border-solid h-[201.913px] left-[403px] rounded-[19.23px] top-[473.54px] w-[172px]" data-node-id="2047:4429" data-name="image 87">
              <div className="absolute inset-0 overflow-hidden pointer-events-none rounded-[19.23px]">
                <img alt="" className="absolute h-[108.09%] left-[-7.39%] max-w-none top-[-4.62%] w-[113.72%]" src={imgImage87} />
              </div>
            </div>
            <p className="[word-break:break-word] absolute font-['Source_Han_Sans_SC'] font-bold leading-[normal] left-[603px] not-italic text-[#eff6ff] text-[30px] top-[468px] tracking-[1.3607px] whitespace-nowrap" data-node-id="2047:4430">
              {currentTaskIndex === 0 ? "公司基础介绍材料" : task.name}
            </p>
            <p className="[word-break:break-word] absolute bottom-[421px] font-['Source_Han_Sans_SC'] font-normal leading-[normal] not-italic right-[996px] text-[#9ab0c6] text-[18px] text-justify top-[522px] tracking-[1px] w-[321px]" data-node-id="2047:4431">
              {task.description.trim()}
            </p>
            <div className="[word-break:break-word] absolute contents left-[970px] not-italic top-[473.42px]" data-node-id="2047:4432">
              <p className="absolute font-['Source_Han_Sans_SC'] font-normal leading-[normal] left-[970px] text-[#9ab0c6] text-[12.777px] top-[473.42px] whitespace-nowrap" data-node-id="2047:4433">
                ◷ 预计用时
              </p>
              <p className="absolute font-['Source_Han_Sans_SC'] font-black leading-[normal] left-[970px] text-[#ebf5ff] text-[14.907px] top-[502.39px] whitespace-nowrap" data-node-id="2047:4434">
                30 分钟
              </p>
              <p className="absolute font-['Source_Han_Sans_SC'] font-normal leading-[normal] left-[970px] text-[#9ab0c6] text-[12.777px] top-[533.58px] whitespace-nowrap" data-node-id="2047:4435">
                ▣ 截止时间
              </p>
              <p className="absolute font-['Source_Han_Sans_SC'] font-black leading-[normal] left-[970px] text-[#ebf5ff] text-[14.907px] top-[562.54px] whitespace-nowrap" data-node-id="2047:4436">
                12月31日
              </p>
              <p className="absolute font-['Source_Han_Sans_SC'] font-normal leading-[normal] left-[970px] text-[#9ab0c6] text-[12.777px] top-[593.73px] whitespace-nowrap" data-node-id="2047:4437">
                任务星级
              </p>
              <p className="absolute font-['Source_Han_Sans_SC'] font-black leading-[0] left-[970px] text-[#ebf5ff] text-[14.907px] top-[622.7px] tracking-[2.1295px] whitespace-nowrap" data-node-id="2047:4438">
                <span className="leading-[14.907px]">★★★★</span>
                <span className="leading-[14.907px] text-[#40526b]">★</span>
              </p>
              <p className="absolute font-['Source_Han_Sans_SC'] font-normal h-[35.213px] leading-[normal] left-[1068.03px] text-[#9ab0c6] text-[12.777px] top-[473.42px] w-[62.6px]" data-node-id="2047:4439">
                任务奖励
              </p>
              <div className="absolute contents font-['Source_Han_Sans_SC'] font-normal left-[1068.03px] top-[503.5px] whitespace-nowrap" data-node-id="2047:4440">
                <div className="-translate-x-1/2 -translate-y-1/2 absolute flex flex-col justify-center leading-[0] left-[1077.53px] text-[#ffc34d] text-[18.232px] text-center top-[514.5px]" data-node-id="2047:4441">
                  <p className="leading-[21.166px]">◈</p>
                </div>
                <p className="absolute leading-[normal] left-[1089.2px] text-[#b9cce1] text-[13.842px] top-[504.62px]" data-node-id="2047:4442">
                  +100
                </p>
              </div>
              <div className="absolute contents font-['Source_Han_Sans_SC'] font-normal left-[1068.03px] top-[562.54px] whitespace-nowrap" data-node-id="2047:4443">
                <p className="absolute leading-[21.166px] left-[1068.03px] text-[#82a1ff] text-[18.232px] top-[562.54px]" data-node-id="2047:4444">
                  ⬢
                </p>
                <p className="absolute leading-[normal] left-[1090.31px] text-[#b9cce1] text-[13.842px] top-[565.88px]" data-node-id="2047:4445">
                  +1
                </p>
              </div>
              <div className="absolute contents font-['Source_Han_Sans_SC'] font-normal left-[1068.03px] top-[619.36px] whitespace-nowrap" data-node-id="2047:4446">
                <p className="absolute leading-[21.166px] left-[1068.03px] text-[#ffc34d] text-[18.232px] top-[619.36px]" data-node-id="2047:4447">
                  ★
                </p>
                <p className="absolute leading-[normal] left-[1092.54px] text-[#b9cce1] text-[13.842px] top-[622.7px]" data-node-id="2047:4448">
                  +1
                </p>
              </div>
            </div>
            <button type="button" data-action="open-task" data-task-index={currentTaskIndex} className="absolute bg-gradient-to-r border-[#75f5ff] border-[0.876px] border-solid content-stretch flex from-[#42dced] h-[55.464px] items-center justify-center left-[403px] px-[5.258px] py-[0.876px] rounded-[9.639px] shadow-[0px_0px_14.021px_0px_#2edfff,0px_0px_28.042px_0px_rgba(18,195,255,0.55)] to-[#5ceeff] top-[714.77px] via-[#31c9f5] via-[45%] w-[717px]" data-node-id="2047:4449" data-name="Button">
              <div className="content-stretch flex gap-[9.076px] items-center relative shrink-0" data-node-id="2047:4450">
                <div className="h-[21.031px] relative shrink-0 w-[18.402px]" data-node-id="2047:4451" data-name="Vector (Stroke)">
                  <img alt="" className="absolute block inset-0 max-w-none size-full" src={imgVectorStroke} />
                </div>
                <p className="font-['Source_Han_Sans_SC'] font-black leading-[normal] not-italic relative shrink-0 text-[#03245f] text-[18.402px] text-center tracking-[3.5052px] w-max whitespace-nowrap" data-node-id="2047:4452">
                  点击查看当前任务详情
                </p>
              </div>
            </button>
            <p className="[word-break:break-word] absolute font-['Source_Han_Sans_SC'] font-medium leading-[normal] left-[1224.01px] not-italic text-[#eff6ff] text-[28.373px] top-[426px] tracking-[1.4849px] whitespace-nowrap" data-node-id="2047:4453">
              审核人
            </p>
            <div className="[word-break:break-word] absolute font-['Source_Han_Sans_SC'] font-normal leading-[0] left-[1188px] not-italic text-[#9ab0c6] text-[17.819px] top-[635.53px] whitespace-nowrap" data-node-id="2047:4454">
              <p className="leading-[normal] mb-0">“期待看到你的思考</p>
              <p className="leading-[normal]">和独特视角!”</p>
            </div>
            <p className="[word-break:break-word] absolute font-['Source_Han_Sans_SC'] font-normal leading-[normal] left-[1224.01px] not-italic text-[#b1cae3] text-[17.819px] top-[551.5px] whitespace-nowrap" data-node-id="2047:4455">
              李魔王老师
            </p>
            <p className="[word-break:break-word] absolute font-['Source_Han_Sans_SC'] font-normal leading-[normal] left-[1215.28px] not-italic text-[#69c9d6] text-[17.819px] top-[588.6px] whitespace-nowrap" data-node-id="2047:4456">
              产品设计导师
            </p>
            <div className="absolute border-[#86bbdf] border-[1.294px] border-solid grid grid-cols-[_47.86px] grid-rows-[_47.86px] left-[1242.56px] rounded-[25.224px] size-[50.449px] top-[488.2px]" data-node-id="2047:4457" style={{ backgroundImage: "linear-gradient(145.0000003379585deg, rgb(240, 217, 192) 6.1733%, rgb(85, 115, 143) 93.827%)" }} data-name="Container">
              <p className="[word-break:break-word] col-1 font-['Source_Han_Sans_SC'] font-black justify-self-center leading-[normal] not-italic relative row-1 self-center shrink-0 text-[#09223c] text-[20.697px] whitespace-nowrap" data-node-id="2047:4458">
                李
              </p>
            </div>
            <div className="absolute flex h-[378px] items-center justify-center left-[1162px] top-[392px] w-0" data-node-id="2047:4459">
              <div className="flex-none rotate-90">
                <div className="h-0 relative w-[378px]">
                  <div className="absolute inset-[-0.98px_0_0_0]">
                    <img alt="" className="block max-w-none size-full" src={imgLine4} />
                  </div>
                </div>
              </div>
            </div>
            <button type="button" data-action="mentor-profile" className="absolute border-2 border-[rgba(30,57,97,0.85)] border-solid h-[46px] left-[1193px] rounded-[18px] top-[724px] w-[150px]" data-node-id="2047:4460" style={{ backgroundImage: "linear-gradient(265.4300513511579deg, rgba(14, 25, 43, 0.86) 1.1026%, rgba(22, 39, 71, 0.76) 16.424%, rgba(12, 26, 44, 0.86) 62.839%, rgba(10, 35, 76, 0.84) 98.83%)" }}>
              <p className="font-['Source_Han_Sans_SC'] font-normal leading-[normal] text-[#b1cae3] text-[17.819px] text-center whitespace-nowrap" data-node-id="2047:4462">查看导师资料</p>
            </button>
          </div>
        </div>
        <div className="absolute contents left-[543px] top-[179px]" data-node-id="2047:4463">
          <div className="absolute contents left-[543px] top-[179px]" data-node-id="2047:4464">
            <div className="figma-stroke dashboard-stage-active absolute border-[1.006px] border-[rgba(30,57,97,0.85)] border-solid h-[58px] left-[572px] rounded-[9.058px] top-[179px] w-[141px]" data-node-id="2047:4465" style={{ backgroundImage: "linear-gradient(268.09742029731274deg, rgba(0, 22, 58, 0.9) 4.2063%, rgba(0, 12, 34, 0.8) 27.99%, rgba(2, 18, 38, 0.86) 64.305%, rgba(4, 19, 44, 0.84) 99.341%)" }}>{stageDecoration}</div>
            <p className="[word-break:break-word] absolute font-['Source_Han_Sans_SC'] font-normal leading-[normal] left-[603px] not-italic text-[#44e7f1] text-[16.615px] top-[184px] tracking-[-1.4954px] whitespace-nowrap" data-node-id="2047:4466">
              01
            </p>
            <p className="[word-break:break-word] absolute font-['Source_Han_Sans_SC'] font-medium leading-[normal] left-[626.26px] not-italic text-[#fefefe] text-[16.615px] top-[184px] whitespace-nowrap" data-node-id="2047:4467">
              探索启航
            </p>
            <p className="[word-break:break-word] absolute font-['Source_Han_Sans_SC'] font-normal leading-[normal] left-[626.26px] not-italic text-[#51d0c5] text-[12.763px] top-[210.17px] whitespace-nowrap" data-node-id="2047:4468">
              进行中
            </p>
            <div className="absolute h-[13.569px] left-[603px] top-[213.08px] w-[15.508px]" data-node-id="2047:4469" data-name="Frame">
              <img alt="" className="absolute block inset-0 max-w-none size-full" src={imgFrame5} />
            </div>
            <div className="absolute left-[543px] mix-blend-screen size-[45.554px] top-[184.51px]" data-node-id="2047:4473">
              <div className="absolute inset-[-35.56%]">
                <img alt="" className="block max-w-none size-full" src={imgEllipse2} />
              </div>
            </div>
            <div className="absolute left-[555.6px] size-[18.415px] top-[198.08px]" data-node-id="2047:4474">
              <img alt="" className="absolute block inset-0 max-w-none size-full" src={imgEllipse3} />
            </div>
            <div className="absolute inset-[18.32%_70.13%_80.71%_29.14%]" data-node-id="2047:4475" data-name="Vector">
              <div className="absolute inset-[-9.22%_-6.9%_0.53%_-6.9%]">
                <img alt="" className="block max-w-none size-full" src={imgVector} />
              </div>
            </div>
            <div className="absolute flex items-center justify-center left-[572.56px] size-[1.938px] top-[200.02px]" data-node-id="2047:4476">
              <div className="flex-none rotate-135">
                <div className="h-0 relative w-[2.741px]">
                  <div className="absolute inset-[-0.97px_-35.36%]">
                    <img alt="" className="block max-w-none size-full" src={imgLine3} />
                  </div>
                </div>
              </div>
            </div>
          </div>
          <div className="absolute flex items-center justify-center left-[545px] mix-blend-screen size-[39.745px] top-[217px]" data-node-id="2047:4477">
            <div className="flex-none rotate-[45.85deg]">
              <div className="h-[28.113px] relative w-[28.101px]">
                <div className="absolute inset-[-32.01%_-32.59%_-32.67%_-32.03%]">
                  <img alt="" className="block max-w-none size-full" src={imgRectangle64} />
                </div>
              </div>
            </div>
          </div>
        </div>
        <div className="absolute contents left-[674px] top-[103px]" data-node-id="2047:4478">
          <div className="absolute border-[1.006px] border-[rgba(30,57,97,0.85)] border-solid h-[58px] left-[703px] rounded-[9.058px] top-[103px] w-[141px]" data-node-id="2047:4479" style={{ backgroundImage: "linear-gradient(268.09742029731274deg, rgba(0, 22, 58, 0.9) 4.2063%, rgba(0, 12, 34, 0.8) 27.99%, rgba(2, 18, 38, 0.86) 64.305%, rgba(4, 19, 44, 0.84) 99.341%)" }} />
          <p className="[word-break:break-word] absolute font-['Source_Han_Sans_SC'] font-normal leading-[normal] left-[734px] not-italic text-[#5a7c9a] text-[16.615px] top-[108px] tracking-[-1.4954px] whitespace-nowrap" data-node-id="2047:4480">
            02
          </p>
          <p className="[word-break:break-word] absolute font-['Source_Han_Sans_SC'] font-medium leading-[normal] left-[757.26px] not-italic text-[#809bc3] text-[16.615px] top-[108px] whitespace-nowrap" data-node-id="2047:4481">
            能力进阶
          </p>
          <p className="[word-break:break-word] absolute font-['Source_Han_Sans_SC'] font-normal leading-[normal] left-[757.26px] not-italic text-[#5a7c9a] text-[12.763px] top-[134.17px] whitespace-nowrap" data-node-id="2047:4482">
            待解锁
          </p>
          <div className="absolute h-[13.569px] left-[734px] top-[137.08px] w-[15.508px]" data-node-id="2047:4483" data-name="Frame">
            <img alt="" className="absolute block inset-0 max-w-none size-full" src={imgFrame6} />
          </div>
          <div className="absolute contents left-[674px] top-[108.51px]" data-node-id="2047:4487">
            <div className="absolute contents left-[674px] top-[108.51px]" data-node-id="2047:4488">
              <div className="absolute contents left-[674px] top-[108.51px]" data-node-id="2047:4489">
                <div className="absolute left-[674px] size-[45.554px] top-[108.51px]" data-node-id="2047:4490">
                  <img alt="" className="absolute block inset-0 max-w-none size-full" src={imgEllipse4} />
                </div>
              </div>
            </div>
            <div className="absolute contents inset-[11%_63.22%_87.23%_35.87%]" data-node-id="2047:4491">
              <div className="absolute contents inset-[11%_63.22%_87.23%_35.87%]" data-node-id="2047:4492">
                <div className="absolute inset-[11.8%_63.22%_87.23%_35.87%]" data-node-id="2047:4493" data-name="Vector">
                  <div className="absolute inset-[-9.22%_-5.56%]">
                    <img alt="" className="block max-w-none size-full" src={imgVector1} />
                  </div>
                </div>
                <div className="absolute inset-[11%_63.42%_88.2%_36.08%]" data-node-id="2047:4494" data-name="Vector">
                  <div className="absolute inset-[-11.26%_-10%]">
                    <img alt="" className="block max-w-none size-full" src={imgVector2} />
                  </div>
                </div>
                <div className="absolute inset-[12.15%_63.67%_87.58%_36.33%]" data-node-id="2047:4495" data-name="Vector">
                  <div className="absolute inset-[-33.79%_-0.97px]">
                    <img alt="" className="block max-w-none size-full" src={imgVector3} />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div className="absolute contents left-[1007px] top-[167px]" data-node-id="2047:4496">
          <div className="absolute border-[1.006px] border-[rgba(30,57,97,0.85)] border-solid h-[58px] left-[1036px] rounded-[9.058px] top-[167px] w-[141px]" data-node-id="2047:4497" style={{ backgroundImage: "linear-gradient(268.09742029731274deg, rgba(0, 22, 58, 0.9) 4.2063%, rgba(0, 12, 34, 0.8) 27.99%, rgba(2, 18, 38, 0.86) 64.305%, rgba(4, 19, 44, 0.84) 99.341%)" }} />
          <p className="[word-break:break-word] absolute font-['Source_Han_Sans_SC'] font-normal leading-[normal] left-[1067px] not-italic text-[#5a7c9a] text-[16.615px] top-[172px] tracking-[-1.4954px] whitespace-nowrap" data-node-id="2047:4498">
            03
          </p>
          <p className="[word-break:break-word] absolute font-['Source_Han_Sans_SC'] font-medium leading-[normal] left-[1090.26px] not-italic text-[#809bc3] text-[16.615px] top-[172px] whitespace-nowrap" data-node-id="2047:4499">
            专业深耕
          </p>
          <p className="[word-break:break-word] absolute font-['Source_Han_Sans_SC'] font-normal leading-[normal] left-[1090.26px] not-italic text-[#5a7c9a] text-[12.763px] top-[198.17px] whitespace-nowrap" data-node-id="2047:4500">
            待解锁
          </p>
          <div className="absolute h-[13.569px] left-[1067px] top-[201.08px] w-[15.508px]" data-node-id="2047:4501" data-name="Frame">
            <img alt="" className="absolute block inset-0 max-w-none size-full" src={imgFrame6} />
          </div>
          <div className="absolute contents left-[1007px] top-[172.51px]" data-node-id="2047:4505">
            <div className="absolute contents left-[1007px] top-[172.51px]" data-node-id="2047:4506">
              <div className="absolute contents left-[1007px] top-[172.51px]" data-node-id="2047:4507">
                <div className="absolute left-[1007px] size-[45.554px] top-[172.51px]" data-node-id="2047:4508">
                  <img alt="" className="absolute block inset-0 max-w-none size-full" src={imgEllipse4} />
                </div>
              </div>
            </div>
            <div className="absolute contents inset-[16.91%_45.87%_81.32%_53.22%]" data-node-id="2047:4509">
              <div className="absolute contents inset-[16.91%_45.87%_81.32%_53.22%]" data-node-id="2047:4510">
                <div className="absolute inset-[17.71%_45.87%_81.32%_53.22%]" data-node-id="2047:4511" data-name="Vector">
                  <div className="absolute inset-[-9.22%_-5.56%]">
                    <img alt="" className="block max-w-none size-full" src={imgVector1} />
                  </div>
                </div>
                <div className="absolute inset-[16.91%_46.08%_82.29%_53.42%]" data-node-id="2047:4512" data-name="Vector">
                  <div className="absolute inset-[-11.26%_-10%]">
                    <img alt="" className="block max-w-none size-full" src={imgVector2} />
                  </div>
                </div>
                <div className="absolute inset-[18.06%_46.33%_81.67%_53.67%]" data-node-id="2047:4513" data-name="Vector">
                  <div className="absolute inset-[-33.79%_-0.97px]">
                    <img alt="" className="block max-w-none size-full" src={imgVector3} />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div className="absolute contents left-[1143px] top-[227px]" data-node-id="2047:4514">
          <div className="absolute border-[1.006px] border-[rgba(30,57,97,0.85)] border-solid h-[58px] left-[1172px] rounded-[9.058px] top-[227px] w-[141px]" data-node-id="2047:4515" style={{ backgroundImage: "linear-gradient(268.09742029731274deg, rgba(0, 22, 58, 0.9) 4.2063%, rgba(0, 12, 34, 0.8) 27.99%, rgba(2, 18, 38, 0.86) 64.305%, rgba(4, 19, 44, 0.84) 99.341%)" }} />
          <p className="[word-break:break-word] absolute font-['Source_Han_Sans_SC'] font-normal leading-[normal] left-[1203px] not-italic text-[#5a7c9a] text-[16.615px] top-[232px] tracking-[-1.4954px] whitespace-nowrap" data-node-id="2047:4516">
            04
          </p>
          <p className="[word-break:break-word] absolute font-['Source_Han_Sans_SC'] font-medium leading-[normal] left-[1226.26px] not-italic text-[#809bc3] text-[16.615px] top-[232px] whitespace-nowrap" data-node-id="2047:4517">
            蜕变沉淀
          </p>
          <p className="[word-break:break-word] absolute font-['Source_Han_Sans_SC'] font-normal leading-[normal] left-[1226.26px] not-italic text-[#5a7c9a] text-[12.763px] top-[258.17px] whitespace-nowrap" data-node-id="2047:4518">
            待解锁
          </p>
          <div className="absolute h-[13.569px] left-[1203px] top-[261.08px] w-[15.508px]" data-node-id="2047:4519" data-name="Frame">
            <img alt="" className="absolute block inset-0 max-w-none size-full" src={imgFrame6} />
          </div>
          <div className="absolute contents left-[1143px] top-[232.51px]" data-node-id="2047:4523">
            <div className="absolute contents left-[1143px] top-[232.51px]" data-node-id="2047:4524">
              <div className="absolute contents left-[1143px] top-[232.51px]" data-node-id="2047:4525">
                <div className="absolute left-[1143px] size-[45.554px] top-[232.51px]" data-node-id="2047:4526">
                  <img alt="" className="absolute block inset-0 max-w-none size-full" src={imgEllipse4} />
                </div>
              </div>
            </div>
            <div className="absolute contents inset-[22.34%_38.79%_75.89%_60.3%]" data-node-id="2047:4527">
              <div className="absolute contents inset-[22.34%_38.79%_75.89%_60.3%]" data-node-id="2047:4528">
                <div className="absolute inset-[23.14%_38.79%_75.89%_60.3%]" data-node-id="2047:4529" data-name="Vector">
                  <div className="absolute inset-[-9.22%_-5.56%]">
                    <img alt="" className="block max-w-none size-full" src={imgVector1} />
                  </div>
                </div>
                <div className="absolute inset-[22.34%_38.99%_76.86%_60.5%]" data-node-id="2047:4530" data-name="Vector">
                  <div className="absolute inset-[-11.26%_-10%]">
                    <img alt="" className="block max-w-none size-full" src={imgVector2} />
                  </div>
                </div>
                <div className="absolute inset-[23.49%_39.24%_76.24%_60.76%]" data-node-id="2047:4531" data-name="Vector">
                  <div className="absolute inset-[-33.79%_-0.97px]">
                    <img alt="" className="block max-w-none size-full" src={imgVector3} />
                  </div>
                </div>
              </div>
            </div>
          </div>
        </div>
        <div className="absolute contents left-[359px] top-[37px]" data-node-id="2047:4532">
          <div className="-translate-x-1/2 -translate-y-1/2 [word-break:break-word] absolute flex flex-col font-['Source_Han_Sans_SC'] font-normal h-[28.91px] justify-center leading-[0] left-[477.9px] not-italic text-[#709ed1] text-[18.986px] text-center top-[51.46px] tracking-[1.8986px] w-[237.809px]" data-node-id="2047:4533">
            <p className="leading-[normal]">学习·实践·沉淀·成长</p>
          </div>
        </div>
        <div className="absolute h-[132px] left-[1175px] top-[16px] w-[211px]" data-node-id="2047:4534" data-name="image 88">
          <img alt="" className="absolute inset-0 max-w-none object-cover pointer-events-none size-full" src={imgImage88} />
        </div>
        <div className="figma-stroke figma-stroke-task absolute border-2 border-[rgba(30,57,97,0.85)] border-solid content-stretch flex flex-col h-[204px] items-start left-[357px] overflow-clip p-[16px] rounded-[18px] top-[838px] w-[1016px]" data-node-id="2047:4535" style={{ backgroundImage: "linear-gradient(263.03982600534584deg, rgba(14, 25, 43, 0.86) 1.1026%, rgba(22, 39, 71, 0.76) 16.424%, rgba(12, 26, 44, 0.86) 62.839%, rgba(10, 35, 76, 0.84) 98.83%)" }} data-name="Section">{decoration}
          <div className="content-stretch flex items-center relative shrink-0 w-full" data-node-id="2047:4536" data-name="Heading 3">
            <p className="[word-break:break-word] font-['Source_Han_Sans_SC'] font-black leading-[normal] not-italic relative shrink-0 text-[#eff6ff] text-[20.571px] whitespace-nowrap" data-node-id="2047:4537">
              任务日志
            </p>
          </div>
          <div className="dashboard-task-activity" data-node-id="2047:4538" tabIndex={0} role="region" aria-label="任务操作日志">
            {activity.length === 0 ? <p className="dashboard-task-activity-empty">暂无任务日志，完成或修改任务后将在这里显示。</p> : activity.map(entry => <div className="dashboard-task-activity-row" key={entry.id}>
              <div className="dashboard-task-activity-avatar" aria-hidden="true">{entry.actorId}</div>
              <div className="dashboard-task-activity-content">
                <p><strong>{entry.actorName}</strong> {entry.action === "completed" ? "完成了任务" : entry.action === "modified" ? "修改了任务答案" : "重新提交了任务"} <span>{entry.taskTitle}</span></p>
                <time dateTime={entry.createdAt}>{new Date(entry.createdAt).toLocaleString("zh-CN", { year: "numeric", month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit", hour12: false })}</time>
              </div>
            </div>)}
          </div>
        </div>
        <div className="-translate-x-1/2 [word-break:break-word] absolute bg-clip-text bg-gradient-to-r font-['Source_Han_Sans_SC'] font-medium from-[rgba(66,220,237,0.55)] leading-[0] left-[895px] not-italic text-[0px] text-[transparent] text-center text-shadow-[0px_0px_28.042px_rgba(18,195,255,0.55),0px_0px_14.021px_#2edfff] to-[rgba(92,238,255,0.55)] top-[266px] via-[45%] via-[rgba(49,201,245,0.55)] whitespace-nowrap" data-node-id="2047:4550">
          <p className="bg-clip-text bg-gradient-to-r from-[rgba(66,220,237,0.55)] leading-[100.1500015258789%] mb-0 text-[22px] to-[rgba(92,238,255,0.55)] via-[45%] via-[rgba(49,201,245,0.55)]">成长之路</p>
          <p className="bg-clip-text bg-gradient-to-r from-[rgba(66,220,237,0.55)] leading-[100.1500015258789%] text-[10px] to-[rgba(92,238,255,0.55)] via-[45%] via-[rgba(49,201,245,0.55)]">A BRIGHTER YOU</p>
        </div>
  </>;
}
