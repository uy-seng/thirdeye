import type { FormEvent } from "react";
import { useState } from "react";

import { login } from "../../lib/api";
import type { SessionResponse } from "../../lib/types";
import { Button, Card, TextInput } from "../ui";

export function LoginPanel({ onLogin }: { onLogin: (session: SessionResponse) => void }) {
  const [username, setUsername] = useState("admin");
  const [password, setPassword] = useState("");
  const [message, setMessage] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(event: FormEvent) {
    event.preventDefault();
    setBusy(true);
    setMessage("");
    try {
      onLogin(await login(username, password));
    } catch (error) {
      setMessage(error instanceof Error ? error.message : "Unable to sign in.");
    } finally {
      setBusy(false);
    }
  }

  return (
    <main className="login-screen">
      <Card className="login-card">
        <p className="eyebrow">Local controller</p>
        <h2>Sign in to thirdeye</h2>
        <form className="stack" onSubmit={submit}>
          <label>
            Username
            <TextInput autoComplete="username" onChange={(event) => setUsername(event.target.value)} required value={username} />
          </label>
          <label>
            Password
            <TextInput autoComplete="current-password" onChange={(event) => setPassword(event.target.value)} required type="password" value={password} />
          </label>
          <Button disabled={busy} type="submit">
            {busy ? "Signing in..." : "Sign in"}
          </Button>
          {message ? <p className="form-message">{message}</p> : null}
        </form>
      </Card>
    </main>
  );
}
