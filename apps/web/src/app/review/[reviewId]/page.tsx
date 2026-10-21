import { redirect } from "next/navigation";
export const dynamic = "force-dynamic";
export default async function ReviewDetailPage({params}:{params:Promise<{reviewId:string}>}) {
 const {reviewId}=await params;
 redirect(`/review?review=${encodeURIComponent(reviewId)}`);
}
