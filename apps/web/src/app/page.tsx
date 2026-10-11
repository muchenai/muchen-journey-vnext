import { redirect } from "next/navigation";

export const dynamic = "force-dynamic";

export default async function Home({ searchParams }: { searchParams: Promise<{ auth_error?: string }> }) {
  const query = await searchParams;
  redirect(query.auth_error ? `/join?auth_error=${encodeURIComponent(query.auth_error)}` : "/join");
}
