import Link from "next/link";
import { explorationOnlyMessage } from "@/lib/learner-module-access";
import styles from "./company-login-notice.module.css";

export default function CompanyLoginNotice() {
  return (
    <main className={styles.page}>
      <section className={styles.card}>
        <h1>{explorationOnlyMessage}</h1>
        <Link href="/join" prefetch={false}>前往登录</Link>
      </section>
    </main>
  );
}
