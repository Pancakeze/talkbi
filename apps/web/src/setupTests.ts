import "@testing-library/jest-dom/vitest";

// Node 22+ can inject a non-functional `localStorage` when `NODE_OPTIONS` / CLI flags
// are involved; provide an in-memory store for unit tests.
if (typeof globalThis.localStorage === "undefined" || typeof globalThis.localStorage.getItem !== "function") {
  const storage: Record<string, string> = {};
  const mock = {
    getItem: (key: string) => (Object.prototype.hasOwnProperty.call(storage, key) ? storage[key]! : null),
    setItem: (key: string, value: string) => {
      storage[key] = value;
    },
    removeItem: (key: string) => {
      delete storage[key];
    },
    clear: () => {
      for (const k of Object.keys(storage)) delete storage[k];
    }
  };
  Object.defineProperty(globalThis, "localStorage", { value: mock, configurable: true, writable: true });
}
