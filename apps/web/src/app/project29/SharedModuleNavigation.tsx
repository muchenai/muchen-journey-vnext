import type { ReactNode } from "react"
import type { ModuleDestination } from "./ModuleShell"
const assetPathPrefix = "/assets/project29/home-4062"
const imgImage44 = "/assets/project29/6f233.webp"
const imgImage67 = "/assets/project29/96be2.webp"
const imgImage62 = "/assets/project29/82501.webp"
const imgIcon = `${assetPathPrefix}/bfb49.svg`
const imgLine1 = `${assetPathPrefix}/c5fda.svg`
const imgRectangle50 = `${assetPathPrefix}/27eec.svg`
const imgRectangle60 = "/assets/project29/home-4062/603f5.svg"
const imgRectangle61 = `${assetPathPrefix}/603f5.svg`
const imgFrame = `${assetPathPrefix}/8c48a.svg`
const imgVector = `${assetPathPrefix}/7fe67.svg`

export function SharedModuleNavigation({
  module,
  onNavigate,
  activeDecoration,
  idleDecoration,
  children,
}: {
  module: ModuleDestination
  onNavigate: (destination: ModuleDestination) => void
  activeDecoration: ReactNode
  idleDecoration: ReactNode
  children: ReactNode
}) {
  return (
    <aside className="module-shared-sidebar">
      <div className="module-shared-sidebar-stack">
        <div
          className="h-[80px] relative shrink-0 w-[208px]"
          data-node-id="4062:465"
          data-name="Container"
        >
          <div
            className="absolute content-stretch flex h-[46px] items-center justify-center left-[-0.29px] pb-[5.125px] pl-[13px] right-[0.29px] top-[6.43px]"
            data-node-id="4062:466"
            data-name="Heading 1:margin"
          >
            <div
              className="relative shrink-0 size-[61.521px]"
              data-node-id="4062:467"
              data-name="image 44"
            >
              <img
                alt=""
                className="absolute inset-0 max-w-none object-cover pointer-events-none size-full"
                src={imgImage44}
              />
            </div>
            <div
              className="content-stretch flex flex-[1_0_0] flex-col items-start min-w-px relative"
              data-node-id="4062:468"
              data-name="Heading 1"
            >
              <div
                className="[word-break:break-word] bg-clip-text font-['Source_Han_Sans_SC'] font-bold leading-[0] not-italic relative shrink-0 text-[23.053px] text-[transparent] tracking-[0.8233px] whitespace-nowrap"
                data-node-id="4062:469"
                style={{
                  backgroundImage:
                    "linear-gradient(109.83453136673711deg, rgb(146, 244, 255) 6.5249%, rgb(49, 201, 245) 43.5%, rgb(200, 249, 255) 88.692%)",
                }}
              >
                <p className="font-['Source_Han_Sans_SC'] font-black mb-0 whitespace-pre">
                  <span
                    className="bg-clip-text leading-[23.053px] tracking-[1.7438px]"
                    style={{
                      backgroundImage:
                        "linear-gradient(109.83453136673711deg, rgb(146, 244, 255) 6.5249%, rgb(49, 201, 245) 43.5%, rgb(200, 249, 255) 88.692%)",
                    }}
                  >{` MUCHEN`}</span>
                  <span
                    className="bg-clip-text leading-[23.053px]"
                    style={{
                      backgroundImage:
                        "linear-gradient(109.83453136673711deg, rgb(146, 244, 255) 6.5249%, rgb(49, 201, 245) 43.5%, rgb(200, 249, 255) 88.692%)",
                    }}
                  >{` `}</span>
                </p>
                <p
                  className="bg-clip-text font-['Source_Han_Sans_SC'] font-black leading-[23.053px] whitespace-pre"
                  style={{
                    backgroundImage:
                      "linear-gradient(109.83453136673711deg, rgb(146, 244, 255) 6.5249%, rgb(49, 201, 245) 43.5%, rgb(200, 249, 255) 88.692%)",
                  }}
                >
                  JOURNEY
                </p>
              </div>
            </div>
          </div>
          <div
            className="absolute h-[11.229px] left-0 right-[0.27px] top-[68.43px]"
            data-node-id="4062:470"
            data-name="Small:margin"
          >
            <div
              className="absolute content-stretch flex flex-col items-start left-[-0.33px] top-[-0.47px] w-[216.717px]"
              data-node-id="4062:471"
              data-name="Small"
            >
              <p
                className="[word-break:break-word] font-['Source_Han_Sans_SC'] font-normal h-[21px] leading-[12.789px] not-italic relative shrink-0 text-[#6388b0] text-[12.789px] text-center tracking-[4px] w-[217px]"
                data-node-id="4062:472"
              >
                从这里，走向更大的自己
              </p>
            </div>
          </div>
        </div>
        <div
          className="h-0 relative shrink-0 w-[208px]"
          data-node-id="4062:473"
        >
          <div className="absolute inset-[-1px_0.15%_0_0.15%]">
            <img alt="" className="block max-w-none size-full" src={imgLine1} />
          </div>
        </div>
        <div
          className="content-stretch flex flex-col gap-[20px] items-start leading-[0] relative shrink-0 w-[207.829px]"
          data-node-id="4062:474"
        >
          <button
            type="button"
            className="grid-cols-[max-content] grid-rows-[max-content] inline-grid place-items-start relative shrink-0"
            data-action="dashboard"
            data-node-id="4062:475"
            onClick={() => onNavigate("dashboard")}
            aria-current={module === "dashboard" ? "page" : undefined}
          >
            <div
              className="col-1 grid-cols-[max-content] grid-rows-[max-content] inline-grid ml-0 mt-0 place-items-start relative row-1"
              data-node-id="4062:476"
            >
              <div
                className="col-1 h-[74.323px] ml-0 mt-0 relative row-1 w-[207.829px]"
                data-node-id="4062:477"
              >
                <img
                  alt=""
                  className="absolute block inset-0 max-w-none size-full"
                  src={imgRectangle50}
                />
              </div>
              {module === "dashboard" && (
                <div
                  className="col-1 h-[74.167px] ml-[44.39px] mt-0 relative rounded-[11.011px] row-1 w-[163.441px]"
                  data-node-id="4062:478"
                  data-name="image 67"
                >
                  <div className="absolute inset-0 opacity-66 overflow-hidden pointer-events-none rounded-[11.011px]">
                    <img
                      alt=""
                      className="absolute h-[329.8%] left-[-7.87%] max-w-none top-[-46.98%] w-[265.91%]"
                      src={imgImage67}
                    />
                  </div>
                </div>
              )}
              <div
                className="bg-gradient-to-r col-1 from-[#07101f] h-[74.323px] ml-0 mt-0 relative rounded-[11.011px] row-1 to-[rgba(0,0,0,0)] w-[103.226px]"
                data-node-id="4062:479"
              />
              {module === "dashboard" ? (
                <div
                  className="dashboard-nav-frame figma-stroke border-[#e8f6ff] border-[1.101px] border-solid col-1 h-[74.323px] ml-0 mt-0 pointer-events-none relative rounded-[11.011px] row-1 shadow-[0px_2.753px_19.544px_0px_rgba(91,63,255,0.6)] w-[207.829px]"
                  data-node-id="shared-nav-frame-480"
                >
                  {activeDecoration}
                  <div
                    aria-hidden
                    className="absolute inset-0 rounded-[11.011px]"
                    style={{
                      backgroundImage:
                        "linear-gradient(258.9936469792472deg, rgba(201, 231, 255, 0.49) 2.4688%, rgba(52, 113, 195, 0.202) 14.255%, rgba(1, 14, 105, 0.49) 34.784%, rgba(7, 5, 134, 0.377) 68.342%, rgba(10, 0, 153, 0.49) 90.024%)",
                    }}
                  />
                  <div className="absolute inset-0 rounded-[inherit] shadow-[inset_11.011px_2.065px_30.83px_1.376px_rgba(114,133,255,0.64)]" />
                </div>
              ) : (
                <div
                  className="dashboard-nav-frame figma-stroke border-[#3a3e91] border-[1.101px] border-solid col-1 h-[74.323px] ml-0 mt-0 pointer-events-none relative rounded-[11.011px] row-1 w-[207.829px]"
                  data-node-id="shared-nav-frame-480"
                >
                  {idleDecoration}
                  <div
                    aria-hidden
                    className="absolute inset-0 rounded-[11.011px]"
                    style={{
                      backgroundImage:
                        "linear-gradient(90.50703003926601deg, rgb(15, 26, 49) 5.1177%, rgb(13, 22, 41) 32.915%, rgba(16, 29, 49, 0.88) 76.853%, rgba(22, 56, 100, 0.73) 98.373%)",
                    }}
                  />
                  <div className="absolute inset-0 rounded-[inherit] shadow-[inset_-48.86px_-8.946px_35.372px_1.376px_rgba(22,89,130,0.32)]" />
                </div>
              )}
            </div>
            <div
              className="col-1 content-stretch flex gap-[31.656px] items-center ml-[13.08px] mt-[17.89px] relative row-1"
              data-node-id="4062:481"
            >
              <div
                className="content-stretch flex gap-[15.828px] items-center relative shrink-0"
                data-node-id="4062:482"
              >
                <div
                  className="h-[38.64px] relative shrink-0 w-[39.123px]"
                  data-node-id="4062:483"
                  data-name="image 62"
                >
                  <div className="absolute inset-0 overflow-hidden pointer-events-none">
                    <img
                      alt=""
                      className="absolute h-[200%] left-[-31.29%] max-w-none top-[-1.24%] w-[296.3%]"
                      src={imgImage62}
                    />
                  </div>
                </div>
                <div
                  className="[word-break:break-word] content-stretch flex flex-col gap-[4.817px] items-start leading-[normal] not-italic relative shrink-0 w-[85.334px]"
                  data-node-id="4062:484"
                >
                  <p
                    className="font-['Source_Han_Sans_SC'] font-medium relative shrink-0 text-[14.452px] text-white w-full"
                    data-node-id="4062:485"
                  >
                    探索营
                  </p>
                  <p
                    className="font-['Source_Han_Sans_SC'] font-normal relative shrink-0 text-[#8ea1e2] text-[10.667px] w-full"
                    data-node-id="4062:486"
                  >
                    欢迎尽情探索
                  </p>
                </div>
              </div>
              <div
                className="flex h-[10.238px] items-center justify-center relative shrink-0 w-[10.24px]"
                data-node-id="4062:487"
              >
                <div className="flex-none rotate-[45.97deg]">
                  <div className="h-[7.29px] relative w-[7.192px]">
                    <div className="absolute inset-[-9.44%_-9.57%]">
                      <img
                        alt=""
                        className="block max-w-none size-full"
                        src={imgRectangle60}
                      />
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </button>
          <button
            type="button"
            className="grid-cols-[max-content] grid-rows-[max-content] inline-grid place-items-start relative shrink-0"
            data-action="novice-village"
            data-node-id="4062:488"
            onClick={() => onNavigate("village")}
            aria-current={module === "village" ? "page" : undefined}
          >
            <div
              className="col-1 grid-cols-[max-content] grid-rows-[max-content] inline-grid ml-0 mt-0 place-items-start relative row-1"
              data-node-id="4062:489"
            >
              <div
                className="col-1 grid-cols-[max-content] grid-rows-[max-content] inline-grid ml-0 mt-0 place-items-start relative row-1"
                data-node-id="4062:490"
              >
                {module === "village" ? (
                  <div
                    className="dashboard-nav-frame figma-stroke border-[#e8f6ff] border-[1.101px] border-solid col-1 h-[74.323px] ml-0 mt-0 pointer-events-none relative rounded-[11.011px] row-1 shadow-[0px_2.753px_19.544px_0px_rgba(91,63,255,0.6)] w-[207.829px]"
                    data-node-id="shared-nav-frame-491"
                  >
                    {activeDecoration}
                    <div
                      aria-hidden
                      className="absolute inset-0 rounded-[11.011px]"
                      style={{
                        backgroundImage:
                          "linear-gradient(258.9936469792472deg, rgba(201, 231, 255, 0.49) 2.4688%, rgba(52, 113, 195, 0.202) 14.255%, rgba(1, 14, 105, 0.49) 34.784%, rgba(7, 5, 134, 0.377) 68.342%, rgba(10, 0, 153, 0.49) 90.024%)",
                      }}
                    />
                    <div className="absolute inset-0 rounded-[inherit] shadow-[inset_11.011px_2.065px_30.83px_1.376px_rgba(114,133,255,0.64)]" />
                  </div>
                ) : (
                  <div
                    className="dashboard-nav-frame figma-stroke border-[#3a3e91] border-[1.101px] border-solid col-1 h-[74.323px] ml-0 mt-0 pointer-events-none relative rounded-[11.011px] row-1 w-[207.829px]"
                    data-node-id="shared-nav-frame-491"
                  >
                    {idleDecoration}
                    <div
                      aria-hidden
                      className="absolute inset-0 rounded-[11.011px]"
                      style={{
                        backgroundImage:
                          "linear-gradient(90.50703003926601deg, rgb(15, 26, 49) 5.1177%, rgb(13, 22, 41) 32.915%, rgba(16, 29, 49, 0.88) 76.853%, rgba(22, 56, 100, 0.73) 98.373%)",
                      }}
                    />
                    <div className="absolute inset-0 rounded-[inherit] shadow-[inset_-48.86px_-8.946px_35.372px_1.376px_rgba(22,89,130,0.32)]" />
                  </div>
                )}
              </div>
              <div
                className="col-1 content-stretch flex items-center ml-[12.39px] mt-[17.2px] relative row-1"
                data-node-id="4062:492"
              >
                <div
                  className="grid-cols-[max-content] grid-rows-[max-content] inline-grid leading-[0] place-items-start relative shrink-0"
                  data-node-id="4062:493"
                >
                  <div
                    className="col-1 content-stretch flex gap-[15.828px] items-center ml-0 mt-0 relative row-1"
                    data-node-id="4062:494"
                  >
                    <div
                      className="h-[39.668px] relative shrink-0 w-[40.164px]"
                      data-node-id="4062:495"
                      data-name="image 63"
                    >
                      <div className="absolute inset-0 overflow-hidden pointer-events-none">
                        <img
                          alt=""
                          className="absolute h-[200%] left-[-163.61%] max-w-none top-[-3.74%] w-[296.3%]"
                          src={imgImage62}
                        />
                      </div>
                    </div>
                    <div
                      className="[word-break:break-word] content-stretch flex flex-col gap-[4.817px] items-start leading-[normal] not-italic relative shrink-0 w-[85.334px]"
                      data-node-id="4062:496"
                    >
                      <p
                        className="font-['Source_Han_Sans_SC'] font-medium relative shrink-0 text-[14.452px] text-white w-full"
                        data-node-id="4062:497"
                      >
                        新手村
                      </p>
                      <p
                        className="font-['Source_Han_Sans_SC'] font-normal relative shrink-0 text-[#8ea1e2] text-[10.667px] w-full"
                        data-node-id="4062:498"
                      >
                        开启你的成长地图
                      </p>
                    </div>
                  </div>
                  <div
                    className="col-1 flex h-[10.238px] items-center justify-center ml-[172.73px] mt-[14.84px] relative row-1 w-[10.24px]"
                    data-node-id="4062:499"
                  >
                    <div className="flex-none rotate-[45.97deg]">
                      <div className="h-[7.29px] relative w-[7.192px]">
                        <div className="absolute inset-[-9.44%_-9.57%]">
                          <img
                            alt=""
                            className="block max-w-none size-full"
                            src={imgRectangle61}
                          />
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </button>
          <button
            type="button"
            className="grid-cols-[max-content] grid-rows-[max-content] inline-grid place-items-start relative shrink-0"
            data-action="unavailable"
            data-node-id="4062:500"
            onClick={() => onNavigate("academy")}
            aria-current={module === "academy" ? "page" : undefined}
          >
            {module === "academy" ? (
              <div
                className="dashboard-nav-frame figma-stroke border-[#e8f6ff] border-[1.101px] border-solid col-1 h-[74.323px] ml-0 mt-0 pointer-events-none relative rounded-[11.011px] row-1 shadow-[0px_2.753px_19.544px_0px_rgba(91,63,255,0.6)] w-[207.829px]"
                data-node-id="shared-nav-frame-501"
              >
                {activeDecoration}
                <div
                  aria-hidden
                  className="absolute inset-0 rounded-[11.011px]"
                  style={{
                    backgroundImage:
                      "linear-gradient(258.9936469792472deg, rgba(201, 231, 255, 0.49) 2.4688%, rgba(52, 113, 195, 0.202) 14.255%, rgba(1, 14, 105, 0.49) 34.784%, rgba(7, 5, 134, 0.377) 68.342%, rgba(10, 0, 153, 0.49) 90.024%)",
                  }}
                />
                <div className="absolute inset-0 rounded-[inherit] shadow-[inset_11.011px_2.065px_30.83px_1.376px_rgba(114,133,255,0.64)]" />
              </div>
            ) : (
              <div
                className="dashboard-nav-frame figma-stroke border-[#3a3e91] border-[1.101px] border-solid col-1 h-[74.323px] ml-0 mt-0 pointer-events-none relative rounded-[11.011px] row-1 w-[207.829px]"
                data-node-id="shared-nav-frame-501"
              >
                {idleDecoration}
                <div
                  aria-hidden
                  className="absolute inset-0 rounded-[11.011px]"
                  style={{
                    backgroundImage:
                      "linear-gradient(90.50703003926601deg, rgb(15, 26, 49) 5.1177%, rgb(13, 22, 41) 32.915%, rgba(16, 29, 49, 0.88) 76.853%, rgba(22, 56, 100, 0.73) 98.373%)",
                  }}
                />
                <div className="absolute inset-0 rounded-[inherit] shadow-[inset_-48.86px_-8.946px_35.372px_1.376px_rgba(22,89,130,0.32)]" />
              </div>
            )}
            <div
              className="col-1 content-stretch flex gap-[31.656px] items-center ml-[12.39px] mt-[17.2px] relative row-1"
              data-node-id="4062:502"
            >
              <div
                className="content-stretch flex gap-[15.828px] items-center relative shrink-0"
                data-node-id="4062:503"
              >
                <div
                  className="h-[39.324px] relative shrink-0 w-[39.815px]"
                  data-node-id="4062:504"
                  data-name="image 64"
                >
                  <div className="absolute inset-0 overflow-hidden pointer-events-none">
                    <img
                      alt=""
                      className="absolute h-[200%] left-[-31.29%] max-w-none top-[-95.3%] w-[296.3%]"
                      src={imgImage62}
                    />
                  </div>
                </div>
                <div
                  className="[word-break:break-word] content-stretch flex flex-col gap-[4.817px] items-start leading-[normal] not-italic relative shrink-0 w-[85.334px]"
                  data-node-id="4062:505"
                >
                  <p
                    className="font-['Source_Han_Sans_SC'] font-medium relative shrink-0 text-[14.452px] text-white w-full"
                    data-node-id="4062:506"
                  >
                    AI学院
                  </p>
                  <p
                    className="font-['Source_Han_Sans_SC'] font-normal relative shrink-0 text-[#8ea1e2] text-[10.667px] w-full"
                    data-node-id="4062:507"
                  >
                    与AI共创可能
                  </p>
                </div>
              </div>
              <div
                className="flex h-[10.238px] items-center justify-center relative shrink-0 w-[10.24px]"
                data-node-id="4062:508"
              >
                <div className="flex-none rotate-[45.97deg]">
                  <div className="h-[7.29px] relative w-[7.192px]">
                    <div className="absolute inset-[-9.44%_-9.57%]">
                      <img
                        alt=""
                        className="block max-w-none size-full"
                        src={imgRectangle60}
                      />
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </button>
          <button
            type="button"
            className="grid-cols-[max-content] grid-rows-[max-content] inline-grid place-items-start relative shrink-0"
            data-action="unavailable"
            data-node-id="4062:509"
            onClick={() => onNavigate("guild")}
            aria-current={module === "guild" ? "page" : undefined}
          >
            {module === "guild" ? (
              <div
                className="dashboard-nav-frame figma-stroke border-[#e8f6ff] border-[1.101px] border-solid col-1 h-[74.323px] ml-0 mt-0 pointer-events-none relative rounded-[11.011px] row-1 shadow-[0px_2.753px_19.544px_0px_rgba(91,63,255,0.6)] w-[207.829px]"
                data-node-id="shared-nav-frame-510"
              >
                {activeDecoration}
                <div
                  aria-hidden
                  className="absolute inset-0 rounded-[11.011px]"
                  style={{
                    backgroundImage:
                      "linear-gradient(258.9936469792472deg, rgba(201, 231, 255, 0.49) 2.4688%, rgba(52, 113, 195, 0.202) 14.255%, rgba(1, 14, 105, 0.49) 34.784%, rgba(7, 5, 134, 0.377) 68.342%, rgba(10, 0, 153, 0.49) 90.024%)",
                  }}
                />
                <div className="absolute inset-0 rounded-[inherit] shadow-[inset_11.011px_2.065px_30.83px_1.376px_rgba(114,133,255,0.64)]" />
              </div>
            ) : (
              <div
                className="dashboard-nav-frame figma-stroke border-[#3a3e91] border-[1.101px] border-solid col-1 h-[74.323px] ml-0 mt-0 pointer-events-none relative rounded-[11.011px] row-1 w-[207.829px]"
                data-node-id="shared-nav-frame-510"
              >
                {idleDecoration}
                <div
                  aria-hidden
                  className="absolute inset-0 rounded-[11.011px]"
                  style={{
                    backgroundImage:
                      "linear-gradient(90.50703003926601deg, rgb(15, 26, 49) 5.1177%, rgb(13, 22, 41) 32.915%, rgba(16, 29, 49, 0.88) 76.853%, rgba(22, 56, 100, 0.73) 98.373%)",
                  }}
                />
                <div className="absolute inset-0 rounded-[inherit] shadow-[inset_-48.86px_-8.946px_35.372px_1.376px_rgba(22,89,130,0.32)]" />
              </div>
            )}
            <div
              className="col-1 content-stretch flex gap-[31.656px] items-center ml-[12.39px] mt-[17.2px] relative row-1"
              data-node-id="4062:511"
            >
              <div
                className="content-stretch flex gap-[15.828px] items-center relative shrink-0"
                data-node-id="4062:512"
              >
                <div
                  className="h-[39.324px] relative shrink-0 w-[39.815px]"
                  data-node-id="4062:513"
                  data-name="image 65"
                >
                  <div className="absolute inset-0 overflow-hidden pointer-events-none">
                    <img
                      alt=""
                      className="absolute h-[200%] left-[-163.61%] max-w-none top-[-99.51%] w-[296.3%]"
                      src={imgImage62}
                    />
                  </div>
                </div>
                <div
                  className="[word-break:break-word] content-stretch flex flex-col gap-[4.817px] items-start leading-[normal] not-italic relative shrink-0 w-[85.334px]"
                  data-node-id="4062:514"
                >
                  <p
                    className="font-['Source_Han_Sans_SC'] font-medium relative shrink-0 text-[14.452px] text-white w-full"
                    data-node-id="4062:515"
                  >
                    交付线公会
                  </p>
                  <p
                    className="font-['Source_Han_Sans_SC'] font-normal relative shrink-0 text-[#8ea1e2] text-[10.667px] w-full"
                    data-node-id="4062:516"
                  >
                    在实践中创造价值
                  </p>
                </div>
              </div>
              <div
                className="flex h-[10.238px] items-center justify-center relative shrink-0 w-[10.24px]"
                data-node-id="4062:517"
              >
                <div className="flex-none rotate-[45.97deg]">
                  <div className="h-[7.29px] relative w-[7.192px]">
                    <div className="absolute inset-[-9.44%_-9.57%]">
                      <img
                        alt=""
                        className="block max-w-none size-full"
                        src={imgRectangle60}
                      />
                    </div>
                  </div>
                </div>
              </div>
            </div>
          </button>
        </div>
        <div
          className="h-0 relative shrink-0 w-[208px]"
          data-node-id="4062:518"
        >
          <div className="absolute inset-[-1px_0.15%_0_0.15%]">
            <img alt="" className="block max-w-none size-full" src={imgLine1} />
          </div>
        </div>
        {children}
      </div>
    </aside>
  )
}
