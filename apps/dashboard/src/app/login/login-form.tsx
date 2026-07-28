"use client";

import React, { useState, FormEvent, Suspense } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { createClient } from "@/lib/supabase/browser";

type Mode = "password" | "magic" | "admin";

function LoginFormInner({ supabaseReady }: { supabaseReady: boolean }) {
  const router = useRouter();
  const searchParams = useSearchParams();
  const next = searchParams.get("next") || "/";
  const urlError = searchParams.get("error");

  const [mode, setMode] = useState<Mode>(supabaseReady ? "password" : "admin");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [adminToken, setAdminToken] = useState("");
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState(urlError ? decodeURIComponent(urlError) : "");
  const [messageType, setMessageType] = useState<"error" | "success">(
    urlError ? "error" : "success"
  );

  const flash = (text: string, type: "error" | "success") => {
    setMessage(text);
    setMessageType(type);
  };

  const onPassword = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    flash("", "success");
    try {
      const supabase = createClient();
      const { error } = await supabase.auth.signInWithPassword({ email, password });
      if (error) throw error;
      router.replace(next);
      router.refresh();
    } catch (err: unknown) {
      flash(err instanceof Error ? err.message : String(err), "error");
    } finally {
      setBusy(false);
    }
  };

  const onMagic = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    flash("", "success");
    try {
      const supabase = createClient();
      const redirectTo = `${window.location.origin}/auth/callback?next=${encodeURIComponent(next)}`;
      const { error } = await supabase.auth.signInWithOtp({
        email,
        options: { emailRedirectTo: redirectTo },
      });
      if (error) throw error;
      flash("Check your email for the magic link.", "success");
    } catch (err: unknown) {
      flash(err instanceof Error ? err.message : String(err), "error");
    } finally {
      setBusy(false);
    }
  };

  const onAdmin = async (e: FormEvent) => {
    e.preventDefault();
    setBusy(true);
    flash("", "success");
    try {
      const res = await fetch("/api/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ token: adminToken }),
      });
      const json = await res.json();
      if (!res.ok) throw new Error(json.error || "Login failed");
      router.replace(next);
      router.refresh();
    } catch (err: unknown) {
      flash(err instanceof Error ? err.message : String(err), "error");
    } finally {
      setBusy(false);
    }
  };

  return (
    <main className="login-shell">
      <div className="login-atmosphere" aria-hidden />
      <section className="login-panel">
        <p className="login-brand">
          MINTRY<span>.FABRIC</span>
        </p>
        <h1 className="login-title">Sign in</h1>
        <p className="login-sub">
          Control-plane access only. Enforcement stays local on your agents.
        </p>

        <div className="login-tabs" role="tablist">
          {supabaseReady && (
            <>
              <button
                type="button"
                role="tab"
                aria-selected={mode === "password"}
                className={mode === "password" ? "active" : ""}
                onClick={() => setMode("password")}
              >
                Email
              </button>
              <button
                type="button"
                role="tab"
                aria-selected={mode === "magic"}
                className={mode === "magic" ? "active" : ""}
                onClick={() => setMode("magic")}
              >
                Magic link
              </button>
            </>
          )}
          <button
            type="button"
            role="tab"
            aria-selected={mode === "admin"}
            className={mode === "admin" ? "active" : ""}
            onClick={() => setMode("admin")}
          >
            Admin token
          </button>
        </div>

        {!supabaseReady && (
          <p className="login-hint">
            Supabase Auth is not configured for the browser. Set{" "}
            <code>NEXT_PUBLIC_SUPABASE_URL</code> and{" "}
            <code>NEXT_PUBLIC_SUPABASE_ANON_KEY</code>, or use the admin token.
          </p>
        )}

        {mode === "password" && (
          <form onSubmit={onPassword} className="login-form">
            <label htmlFor="email">Email</label>
            <input
              id="email"
              type="email"
              autoComplete="username"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="form-input"
            />
            <label htmlFor="password">Password</label>
            <input
              id="password"
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="form-input"
            />
            <button type="submit" className="btn-submit" disabled={busy}>
              {busy ? "Signing in…" : "Sign in"}
            </button>
          </form>
        )}

        {mode === "magic" && (
          <form onSubmit={onMagic} className="login-form">
            <label htmlFor="magic-email">Email</label>
            <input
              id="magic-email"
              type="email"
              autoComplete="username"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="form-input"
            />
            <button type="submit" className="btn-submit" disabled={busy}>
              {busy ? "Sending…" : "Send magic link"}
            </button>
          </form>
        )}

        {mode === "admin" && (
          <form onSubmit={onAdmin} className="login-form">
            <label htmlFor="admin-token">Admin token</label>
            <input
              id="admin-token"
              type="password"
              autoComplete="off"
              required
              value={adminToken}
              onChange={(e) => setAdminToken(e.target.value)}
              className="form-input"
              placeholder="MINTRY_DASHBOARD_ADMIN_TOKEN"
            />
            <button type="submit" className="btn-submit" disabled={busy}>
              {busy ? "Signing in…" : "Sign in with token"}
            </button>
            <p className="login-hint">
              Break-glass / local ops. Prefer Supabase Auth in shared environments.
            </p>
          </form>
        )}

        {message && (
          <p
            className={`feedback-message ${messageType}`}
            style={{ marginTop: "1rem" }}
          >
            {message}
          </p>
        )}
      </section>
    </main>
  );
}

export function LoginForm({ supabaseReady }: { supabaseReady: boolean }) {
  return (
    <Suspense
      fallback={
        <main className="login-shell">
          <p className="login-sub">Loading…</p>
        </main>
      }
    >
      <LoginFormInner supabaseReady={supabaseReady} />
    </Suspense>
  );
}
