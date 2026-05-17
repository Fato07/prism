"use client";

/**
 * AnimatedNumber — count-up wrapper for react-countup.
 *
 * Used in server-rendered stats tiles to animate integer values
 * when they scroll into view. Wraps CountUp with sensible defaults
 * so individual tiles don't repeat configuration.
 *
 * Respects `prefers-reduced-motion` — react-countup will render
 * the final value instantly when reduced motion is preferred.
 */

import CountUp from "react-countup";

interface AnimatedNumberProps {
  /** Target value to count up to. */
  end: number;
  /** Animation duration in seconds. Default: 1.5 (snappy). */
  duration?: number;
  /** Delay before animation starts (seconds). Default: 0.2. */
  delay?: number;
  /** Thousands separator. Default: ",". */
  separator?: string;
  /** Additional CSS class names for the span. */
  className?: string;
}

export function AnimatedNumber({
  end,
  duration = 1.5,
  delay = 0.2,
  separator = ",",
  className,
}: AnimatedNumberProps) {
  return (
    <CountUp
      end={end}
      duration={duration}
      delay={delay}
      separator={separator}
      enableScrollSpy
      scrollSpyOnce
      className={className}
    />
  );
}
