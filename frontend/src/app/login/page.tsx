import { Activity } from "lucide-react";

export default function LoginPage() {
  return (
    <main className="login-wrap">
      <section className="panel login-panel">
        <div className="brand">
          <Activity size={22} />
          AI Forex Signals
        </div>
        <form>
          <input className="input" type="email" placeholder="Email" autoComplete="email" />
          <input className="input" type="password" placeholder="Password" autoComplete="current-password" />
          <button className="button" type="button">
            Sign in
          </button>
        </form>
      </section>
    </main>
  );
}
