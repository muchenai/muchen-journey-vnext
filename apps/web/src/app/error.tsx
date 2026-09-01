"use client";

import Link from "next/link";
import { useEffect, useRef } from "react";

export default function GlobalError({
  error,
  reset,
}: {
  error: Error & { digest?: string };
  reset: () => void;
}) {
  const errorHeadingRef = useRef<HTMLHeadingElement>(null);

  useEffect(() => {
    errorHeadingRef.current?.focus();
  }, []);

  return (
    <section className="content-narrow" role="alert">
      <p className="eyebrow">暂时无法继续</p>
      <h1 ref={errorHeadingRef} tabIndex={-1}>操作没有完成</h1>
      <p>已提交的业务事实不会因此回滚。请重试；若仍失败，请联系试点运营。</p>
      {error.digest ? <p className="status-meta">页面参考编号：<code>{error.digest}</code></p> : null}
      <div className="action-row">
        <button className="button primary" type="button" onClick={reset}>重试</button>
        <Link className="button secondary" href="/app">返回我的旅程</Link>
      </div>
    </section>
  );
}
