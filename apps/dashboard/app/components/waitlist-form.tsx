"use client";

/**
 * WaitlistSignupForm — Client component for email signup.
 *
 * Handles form state, client-side validation, submission to /api/waitlist,
 * and displays success/duplicate/error feedback inline.
 */

import { useState, type FormEvent } from "react";

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

  return (
    <form onSubmit={handleSubmit} className="flex flex-col gap-3 sm:flex-row sm:items-start">
      <div className="flex-1 w-full">
        <label htmlFor="waitlist-email" className="sr-only">
          Email address
        </label>
        <input
          id="waitlist-email"
          type="email"
          required
          placeholder="you@example.com"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          disabled={state === "submitting"}
          className="w-full rounded-lg border border-gray-700 bg-gray-900 px-4 py-3 text-gray-100 placeholder-gray-500 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500 disabled:opacity-50 text-base"
          aria-describedby="waitlist-feedback"
        />
      </div>
      <button
        type="submit"
        disabled={state === "submitting" || !email}
        className="w-full sm:w-auto rounded-lg bg-blue-600 px-6 py-3 font-semibold text-white transition-colors hover:bg-blue-500 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 focus:ring-offset-gray-950 disabled:opacity-50 disabled:cursor-not-allowed text-base"
      >
        {state === "submitting" ? "Joining..." : "Join Waitlist"}
      </button>
      {/* Feedback message */}
      <div id="waitlist-feedback" className="sm:absolute sm:mt-1" aria-live="polite">
        {state === "success" && (
          <p className="text-green-400 text-sm">You&apos;re on the list!</p>
        )}
        {state === "duplicate" && (
          <p className="text-yellow-400 text-sm">Already on the list!</p>
        )}
        {state === "error" && (
          <p className="text-red-400 text-sm">{errorMessage}</p>
        )}
      </div>
    </form>
  );
}
