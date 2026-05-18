#!/usr/bin/env node
import { mkdirSync, writeFileSync } from "node:fs";
import { dirname, join, resolve } from "node:path";

const root = resolve(new URL("..", import.meta.url).pathname);
const outPath = join(root, "public", "audio", "prism-showcase-bed.wav");
const sampleRate = 48_000;
const durationSeconds = 70;
const channels = 2;
const totalSamples = sampleRate * durationSeconds;
const left = new Float32Array(totalSamples);
const right = new Float32Array(totalSamples);
const transitions = [0, 6, 15, 28, 42, 52, 62];
const chords = [
  [65.41, 98.0, 130.81, 196.0],
  [73.42, 110.0, 146.83, 220.0],
  [61.74, 92.5, 123.47, 185.0],
  [87.31, 130.81, 174.61, 261.63],
];

function clamp(value, min = -1, max = 1) {
  return Math.max(min, Math.min(max, value));
}

function smoothstep(edge0, edge1, x) {
  const t = clamp((x - edge0) / (edge1 - edge0), 0, 1);
  return t * t * (3 - 2 * t);
}

function envelope(t) {
  const fadeIn = smoothstep(0, 4, t);
  const fadeOut = 1 - smoothstep(durationSeconds - 8, durationSeconds, t);
  return fadeIn * fadeOut;
}

function sceneEnergy(t) {
  if (t < 6) return 0.52;
  if (t < 15) return 0.42;
  if (t < 28) return 0.58;
  if (t < 42) return 0.7;
  if (t < 52) return 0.78;
  if (t < 62) return 0.74;
  return 0.5;
}

function pulse(t, at, length, attack = 0.03, release = 1.0) {
  const x = t - at;
  if (x < 0 || x > length) return 0;
  return smoothstep(0, attack, x) * (1 - smoothstep(length - release, length, x));
}

function deterministicNoise(i) {
  const x = Math.sin(i * 12.9898 + 78.233) * 43758.5453;
  return (x - Math.floor(x)) * 2 - 1;
}

for (let i = 0; i < totalSamples; i += 1) {
  const t = i / sampleRate;
  const env = envelope(t);
  const energy = sceneEnergy(t);
  const chord = chords[Math.min(chords.length - 1, Math.floor(t / 18))];

  let pad = 0;
  for (let n = 0; n < chord.length; n += 1) {
    const freq = chord[n];
    const drift = Math.sin(t * 0.037 + n) * 0.18;
    pad += Math.sin(2 * Math.PI * (freq + drift) * t + n * 0.7) * (0.14 / (n + 1));
    pad += Math.sin(2 * Math.PI * (freq * 2.005 + drift) * t + n) * (0.035 / (n + 1));
  }

  const subFreq = chord[0] / 2;
  const subGate = 0.58 + 0.42 * Math.max(0, Math.sin(2 * Math.PI * 0.25 * t));
  const sub = Math.sin(2 * Math.PI * subFreq * t) * 0.2 * subGate;

  let hits = 0;
  for (const at of transitions) {
    const impact = pulse(t, at, 1.4, 0.004, 1.15);
    const shimmer = pulse(t, at + 0.08, 2.2, 0.04, 1.8);
    hits += Math.sin(2 * Math.PI * 92 * t) * 0.36 * impact;
    hits += Math.sin(2 * Math.PI * 740 * t) * 0.08 * shimmer;
    hits += deterministicNoise(i) * 0.06 * shimmer;
  }

  let tick = 0;
  const beat = t % 2;
  const tickEnv = pulse(beat, 0, 0.08, 0.003, 0.05);
  tick += Math.sin(2 * Math.PI * 1230 * t) * tickEnv * 0.035;

  const air = deterministicNoise(i) * 0.012 * (0.6 + 0.4 * Math.sin(t * 0.2));
  const stereo = Math.sin(t * 0.31) * 0.08;
  const sample = (pad + sub + hits + tick + air) * env * energy;

  left[i] = clamp(sample * (1 - stereo));
  right[i] = clamp(sample * (1 + stereo));
}

const bytesPerSample = 2;
const dataSize = totalSamples * channels * bytesPerSample;
const buffer = Buffer.alloc(44 + dataSize);

buffer.write("RIFF", 0);
buffer.writeUInt32LE(36 + dataSize, 4);
buffer.write("WAVE", 8);
buffer.write("fmt ", 12);
buffer.writeUInt32LE(16, 16);
buffer.writeUInt16LE(1, 20);
buffer.writeUInt16LE(channels, 22);
buffer.writeUInt32LE(sampleRate, 24);
buffer.writeUInt32LE(sampleRate * channels * bytesPerSample, 28);
buffer.writeUInt16LE(channels * bytesPerSample, 32);
buffer.writeUInt16LE(16, 34);
buffer.write("data", 36);
buffer.writeUInt32LE(dataSize, 40);

let offset = 44;
for (let i = 0; i < totalSamples; i += 1) {
  buffer.writeInt16LE(Math.round(clamp(left[i]) * 32767), offset);
  offset += 2;
  buffer.writeInt16LE(Math.round(clamp(right[i]) * 32767), offset);
  offset += 2;
}

mkdirSync(dirname(outPath), { recursive: true });
writeFileSync(outPath, buffer);
console.log(`Wrote ${outPath}`);
