import { useId, useLayoutEffect, useRef, useState, type ReactNode } from "react";
import "./journeyDialog.css";

// Every dialog uses the welcome dialog's single, transparent-center gradient stroke.
export function JourneyDialogSurface({ children }: { children: ReactNode }) {
  const id = useId();
  const svg = useRef<SVGSVGElement>(null);
  const [size, setSize] = useState({ width: 540, height: 560 });
  useLayoutEffect(() => {
    const element = svg.current;
    if (!element) return;
    const update = () => setSize({ width: element.clientWidth, height: element.clientHeight });
    const observer = new ResizeObserver(update);
    observer.observe(element);
    update();
    return () => observer.disconnect();
  }, []);
  const angle = 57.83 * Math.PI / 180;
  const dx = Math.sin(angle);
  const dy = -Math.cos(angle);
  const half = (Math.abs(size.width * dx) + Math.abs(size.height * dy)) / 2;
  const stops: [number, string, number][] = [
    [0, "#1e3961", .85], [26, "#529cc8", .91], [42, "#0f1f3e", .94],
    [53, "#87b1ff", 1], [76, "#1e4380", .91], [93, "#3e94db", .88], [100, "#67b6f2", 1],
  ];
  return <>
    <svg ref={svg} className="journey-dialog-stroke" aria-hidden="true" focusable="false">
      <defs><linearGradient id={id} gradientUnits="userSpaceOnUse"
        x1={size.width / 2 - dx * half} y1={size.height / 2 - dy * half}
        x2={size.width / 2 + dx * half} y2={size.height / 2 + dy * half}>
        {stops.map(([offset, color, opacity]) => <stop key={offset} offset={`${offset}%`} stopColor={color} stopOpacity={opacity} />)}
      </linearGradient></defs>
      <rect x=".5" y=".5" rx="9.5" fill="none" stroke={`url(#${id})`} strokeWidth="1" />
      <rect className="journey-dialog-tracer" x=".5" y=".5" rx="9.5" fill="none" stroke="#b8f5ff" strokeWidth="1" pathLength="1000" strokeDasharray="35 965" strokeLinecap="round" />
    </svg>
    <div className="journey-dialog-body">{children}</div>
  </>;
}
