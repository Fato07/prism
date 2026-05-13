"use client";

/**
 * WaitlistSignupForm — Client component for email signup.
 *
 * Handles form state, client-side validation, submission to /api/waitlist,
 * and displays success/duplicate/error feedback inline using design tokens.
 */

import { useState, type FormEvent } from "react";
import { ArrowRight, Check, AlertCircle } from "lucide-react";
import { cn } from "@/lib/utils";

type SignupState = "idle" | "submitting" | "success" | "duplicate" | "error";

export function WaitlistSignupForm() {
  const [email, setEmail] = useState("");
  const [state, setState] = useState<SignupState>("idle");
  const [errorMessage, setErrorMessage] = useState("");

  async function handleSubmit(e: FormEvent<HTMLFormElement>): Promise<void> {
    e.preventDefault();
    setState("submitting");
    setErrorMessage("");

    try {
      const res = await fetch("/api/waitlist", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ email }),
      });

      const data = (await res.json()) as { success: boolean; message: string };

      if (res.ok && data.success) {
        if (data.message.includes("Already")) {
          setState("duplicate");
        } else {
          setState("success");
        }
        setEmail("");
      } else if (res.status === 400) {
        setState("error");
        setErrorMessage(data.message || "Invalid email address");
      } else {
        setState("error");
        setErrorMessage(data.message || "Something went wrong");
      }
    } catch {
      setState("error");
      setErrorMessage("Network error. Please try again.");
    }
  }

  const showFeedback = state === "success" || state === "duplicate" || state === "error";

  return (
    <form
      onSubmit={handleSubmit}
      className="flex w-full flex-col gap-3"
      noValidate
    >
      <div
        className={cn(
          "group relative flex items-stretch overflow-hidden rounded-xl",
          "border border-[var(--color-border-strong)] bg-[var(--color-canvas-raised)]/80 backdrop-blur",
          "transition-all duration-[var(--duration-base)]",
          "focus-within:border-[var(--color-trader)]",
          "focus-within:shadow-[0_0_0_3px_color-mix(in_oklch,var(--color-trader)_25%,transparent)]",
          state === "error" &&
            "border-[var(--color-danger)] focus-within:border-[var(--color-danger)] focus-within:shadow-[0_0_0_3px_color-mix(in_oklch,var(--color-danger)_25%,transparent)]",
        )}
      >
        <label htmlFor="waitlist-email" className="sr-only">
          Email address
        </label>
        <input
          id="waitlist-email"
          type="email"
          required
          placeholder="you@example.com"
          value={email}
          onChange={(e) => {
            setEmail(e.target.value);
            if (state === "error") setState("idle");
          }}
          disabled={state === "submitting"}
          className={cn(
            "min-w-0 flex-1 bg-transparent px-4 py-3.5 text-base text-fg outline-none",
            "placeholder:text-fg-faint disabled:opacity-50",
            "text-mono tracking-tight",
          )}
          aria-describedby="waitlist-feedback"
          aria-invalid={state === "error"}
        />
        <button
          type="submit"
          disabled={state === "submitting" || !email}
          className={cn(
            "inline-flex items-center gap-1.5 px-5 py-3.5 text-sm font-medium",
            "text-canvas",
            "transition-all duration-[var(--duration-base)]",
            "disabled:cursor-not-allowed disabled:opacity-50",
            "focus-visible:outline-none",
          )}
          style={{
            backgroundImage:
              "linear-gradient(120deg, var(--color-trader) 0%, oklch(0.78 0.20 280) 60%, var(--color-sentinel) 100%)",
          }}
        >
          {state === "submitting" ? (
            <span className="inline-flex items-center gap-1.5">
              <span className="h-3 w-3 animate-spin rounded-full border-2 border-canvas/30 border-t-canvas" />
              Joining
            </span>
          ) : (
            <>
              Join
              <ArrowRight className="h-3.5 w-3.5" strokeWidth={2.4} />
            </>
          )}
        </button>
      </div>

      {/* Feedback line */}
      <div
        id="waitlist-feedback"
        aria-live="polite"
        className="h-5 text-xs"
      >
        {showFeedback && state === "success" && (
          <p className="inline-flex items-center gap-1.5 text-[var(--color-success)]">
            <Check className="h-3.5 w-3.5" strokeWidth={2.4} />
            <span>You&apos;re on the list. We&apos;ll email you when the doors open.</span>
          </p>
        )}
        {showFeedback && state === "duplicate" && (
          <p className="inline-flex items-center gap-1.5 text-[var(--color-warning)]">
            <Check className="h-3.5 w-3.5" strokeWidth={2.4} />
            <span>Already on the list — see you at launch.</span>
          </p>
        )}
        {showFeedback && state === "error" && (
          <p className="inline-flex items-center gap-1.5 text-[var(--color-danger)]">
            <AlertCircle className="h-3.5 w-3.5" strokeWidth={2.4} />
            <span>{errorMessage}</span>
          </p>
        )}
      </div>
    </form>
  );
}
