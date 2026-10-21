import type { ReviewItem } from "@/lib/server/api";
export const DOMAINS = ["产品开发", "数据交付", "技术开发", "PMO", "AI评测", "质量检测", "项目管理", "AI 能力"];
export const BADGES = [
 {id:'data',name:'数据交付',color:'#648b83'}, {id:'tech',name:'技术开发',color:'#6b83a0'},
 {id:'product',name:'产品开发',color:'#b68c58'}, {id:'pmo',name:'PMO勋',color:'#9988ad'},
 {id:'ai-eval',name:'AI评测',color:'#748b9a'}, {id:'quality',name:'质量检测',color:'#a58b74'},
 {id:'project',name:'项目管理',color:'#7d9172'}, {id:'ai',name:'AI 能力',color:'#8d85a9'},
];
export const PRESETS: Record<string, [number, number, number]> = { "入门": [30, 50, 5], "进阶": [60, 100, 10], "挑战": [90, 200, 20] };
export type Material = { id: string; name: string; type: "link" | "file" | "image" | "text"; url: string; text?: string; mime?: string; size?: number };
export type AdminTask = {
 id: string; title: string; summary: string; camp: "exploration" | "novice"; domain: string; difficulty: string;
 badges: { id: string; weight: number }[]; materials: Material[]; reviewMode: "manual" | "ai"; passScore: number;
 rubric: { id: string; name: string; points: number; description: string }[]; rubricAttachments: Material[];
 revision: number; status: string; author?: string; authorId?: string; stableKey?: string;
 participants?: number; completions?: number; version?: number;
};
export type AdminReview = ReviewItem & { learner_id: string; task_id: string; camp: string; domain: string; review_mode: string;
 decision: string | null; feedback: string; score: number | null; reasons: string[]; ai_statuses: string[] };
export type Member = { id: string; name: string; roles: string[]; revision: number; certification: { domain: string; level: string } | null };
export type AdminState = { tasks: AdminTask[]; reviews: AdminReview[]; members: Member[]; actor: { id: string; name: string }; operatorId: string | null };
export type Result<T> = { ok: true; data: T } | { ok: false; error: string; status?: number; code?: string };
export function blankTask(): AdminTask { return { id: crypto.randomUUID(), title: "", summary: "", camp: "novice", domain: DOMAINS[0], difficulty: "入门", badges: [{ id: "product", weight: 100 }], materials: [], reviewMode: "manual", passScore: 60, rubric: [], rubricAttachments: [], revision: 0, status: "draft" }; }
