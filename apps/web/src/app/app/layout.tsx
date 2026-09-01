import Link from "next/link";

export default function LearnerLayout({
  children,
}: Readonly<{ children: React.ReactNode }>) {
  return (
    <>
      <nav className="learner-route-nav" aria-label="旅程导航">
        <Link href="/app">我的旅程</Link>
      </nav>
      {children}
    </>
  );
}
