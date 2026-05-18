#!/usr/bin/env node
import { spawnSync } from "node:child_process";
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";

const root = resolve(new URL("..", import.meta.url).pathname);
const promptPath = join(root, "higgsfield", "broll-prompts.json");
const outDir = join(root, "public", "broll");
const propsPath = join(root, "public", "broll", "showcase-broll-props.json");
const dryRun = process.argv.includes("--dry-run");
const yes = process.argv.includes("--yes") || process.env.HIGGSFIELD_YES === "1";
const maxCredits = Number(process.env.HIGGSFIELD_MAX_CREDITS ?? "60");
const cli = ["-y", "-p", "@higgsfield/cli", "higgsfield"];

function run(args, { json = false, quiet = false } = {}) {
  const result = spawnSync("npx", [...cli, ...args], {
    cwd: root,
    encoding: "utf-8",
    stdio: quiet ? ["ignore", "pipe", "pipe"] : ["ignore", "pipe", "inherit"],
  });
  if (result.status !== 0) {
    throw new Error(`higgsfield ${args.join(" ")} failed`);
  }
  const stdout = result.stdout.trim();
  if (!json) return stdout;
  try {
    return JSON.parse(stdout);
  } catch (error) {
    throw new Error(`Expected JSON from higgsfield ${args.join(" ")}: ${stdout.slice(0, 500)}`);
  }
}

function paramsToArgs(params) {
  const args = [];
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null || value === "") continue;
    args.push(`--${key}`, String(value));
  }
  return args;
}

function collectUrls(value, urls = []) {
  if (!value) return urls;
  if (typeof value === "string") {
    if (/^https?:\/\//.test(value) && /\.(mp4|mov|webm)(\?|$)/i.test(value)) {
      urls.push(value);
    }
    return urls;
  }
  if (Array.isArray(value)) {
    for (const item of value) collectUrls(item, urls);
    return urls;
  }
  if (typeof value === "object") {
    for (const item of Object.values(value)) collectUrls(item, urls);
  }
  return urls;
}

async function download(url, destination) {
  const response = await fetch(url);
  if (!response.ok) {
    throw new Error(`Failed to download ${url}: HTTP ${response.status}`);
  }
  const bytes = Buffer.from(await response.arrayBuffer());
  mkdirSync(dirname(destination), { recursive: true });
  writeFileSync(destination, bytes);
}

const prompts = JSON.parse(readFileSync(promptPath, "utf-8"));
if (!Array.isArray(prompts) || prompts.length === 0) {
  throw new Error(`No prompts found in ${promptPath}`);
}

console.log(`Loaded ${prompts.length} Higgsfield b-roll prompts.`);

const status = run(["account", "status", "--json"], { json: true, quiet: true });
const availableCredits = Number(status.credits ?? 0);
console.log(`Available credits: ${availableCredits}`);

const estimates = [];
for (const prompt of prompts) {
  const estimate = run(
    ["generate", "cost", prompt.model, ...paramsToArgs(prompt.params), "--json"],
    { json: true, quiet: true },
  );
  const credits = Number(estimate.credits_exact ?? estimate.credits ?? 0);
  estimates.push({ ...prompt, credits });
  console.log(`${prompt.output}: ${credits} credits (${prompt.model})`);
}

const total = estimates.reduce((sum, item) => sum + item.credits, 0);
console.log(`Estimated total: ${total} credits`);

if (dryRun) {
  if (total > maxCredits) {
    console.log(
      `Dry-run warning: estimated total ${total} exceeds HIGGSFIELD_MAX_CREDITS=${maxCredits}.`,
    );
  }
  if (availableCredits < total) {
    console.log(
      `Dry-run warning: insufficient Higgsfield credits: have ${availableCredits}, need ~${total}.`,
    );
  }
  console.log("Dry run complete. No jobs created.");
  process.exit(0);
}

if (total > maxCredits) {
  throw new Error(
    `Estimated total ${total} exceeds HIGGSFIELD_MAX_CREDITS=${maxCredits}. Increase the env var to proceed.`,
  );
}

if (availableCredits < total) {
  throw new Error(
    `Insufficient Higgsfield credits: have ${availableCredits}, need ~${total}. Top up/upgrade, then rerun.`,
  );
}

if (!yes) {
  throw new Error(
    "Generation is credit-spending. Rerun with --yes or HIGGSFIELD_YES=1 after reviewing the cost estimate.",
  );
}

mkdirSync(outDir, { recursive: true });
const brollProps = {};

for (const prompt of estimates) {
  console.log(`Creating ${prompt.output} with ${prompt.model}...`);
  const result = run(
    [
      "generate",
      "create",
      prompt.model,
      ...paramsToArgs(prompt.params),
      "--wait",
      "--wait-timeout",
      "25m",
      "--wait-interval",
      "10s",
      "--json",
    ],
    { json: true, quiet: true },
  );

  const urls = collectUrls(result);
  if (urls.length === 0) {
    const artifact = join(outDir, `${prompt.output}.json`);
    writeFileSync(artifact, JSON.stringify(result, null, 2));
    throw new Error(`No video URL found for ${prompt.output}. Raw response saved to ${artifact}`);
  }

  const destination = join(outDir, prompt.output);
  await download(urls[0], destination);
  brollProps[prompt.key] = `broll/${prompt.output}`;
  writeFileSync(join(outDir, `${prompt.output}.json`), JSON.stringify(result, null, 2));
  console.log(`Saved ${destination}`);
}

writeFileSync(propsPath, JSON.stringify({ broll: brollProps }, null, 2));
console.log(`Wrote Remotion props: ${propsPath}`);
console.log("Render with:");
console.log(`pnpm --dir apps/pitch-video render:showcase -- --props=public/broll/showcase-broll-props.json`);
