/**
 * POST /api/waitlist — Email signup for the Prism waitlist.
 *
 * Validates email, inserts into Neon DB (upsert/ignore for duplicates).
 * Returns { success: true, message: "You're on the list!" } or
 *         { success: true, message: "Already on the list!" } for duplicates.
 */

import { NextRequest, NextResponse } from "next/server";
import { z } from "zod/v4";
import { addWaitlistEmail, ensureWaitlistTable } from "@/lib/db";

const WaitlistSignupSchema = z.object({
  email: z.string().email("Please enter a valid email address"),
});

export async function POST(request: NextRequest): Promise<NextResponse> {
  try {
    const body: unknown = await request.json();
    const parseResult = WaitlistSignupSchema.safeParse(body);

    if (!parseResult.success) {
      return NextResponse.json(
        { success: false, message: parseResult.error.issues[0].message },
        { status: 400 }
      );
    }

    const { email } = parseResult.data;

    // Ensure table exists (idempotent)
    await ensureWaitlistTable();

    // Insert with ON CONFLICT DO NOTHING
    const result = await addWaitlistEmail(email);

    if (result.inserted) {
      return NextResponse.json(
        { success: true, message: "You're on the list!" },
        { status: 200 }
      );
    }

    return NextResponse.json(
      { success: true, message: "Already on the list!" },
      { status: 200 }
    );
  } catch (error: unknown) {
    // Log the error but don't expose details to the client
    console.error("Waitlist signup error:", error);
    return NextResponse.json(
      { success: false, message: "Something went wrong. Please try again." },
      { status: 500 }
    );
  }
}
