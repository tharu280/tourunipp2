import { useEffect, useRef, useState } from "react";

export default function useRepeatingDemoTask({
  enabled,
  onTick,
  intervalMs = 30_000,
  runImmediately = true,
}) {
  const callbackRef = useRef(onTick);
  const [secondsRemaining, setSecondsRemaining] = useState(
    Math.ceil(intervalMs / 1000)
  );

  useEffect(() => {
    callbackRef.current = onTick;
  }, [onTick]);

  useEffect(() => {
    const fullIntervalSeconds = Math.ceil(intervalMs / 1000);
    setSecondsRemaining(fullIntervalSeconds);

    if (!enabled) return undefined;

    let nextRunAt = Date.now() + intervalMs;

    if (runImmediately) {
      void Promise.resolve(callbackRef.current?.()).catch(() => {});
    }

    const timer = window.setInterval(() => {
      const now = Date.now();

      if (now >= nextRunAt) {
        nextRunAt = now + intervalMs;
        setSecondsRemaining(fullIntervalSeconds);
        void Promise.resolve(callbackRef.current?.()).catch(() => {});
        return;
      }

      setSecondsRemaining(Math.max(1, Math.ceil((nextRunAt - now) / 1000)));
    }, 250);

    return () => window.clearInterval(timer);
  }, [enabled, intervalMs, runImmediately]);

  return secondsRemaining;
}
