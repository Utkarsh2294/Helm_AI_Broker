import { useSyncExternalStore } from 'react';

// One observer shared by the dock, task rail, toast host and citation popovers.
const listeners = new Set();
let observer = null,
  host = null;
function update() {
  const next = document.querySelector('dialog[open] .panel-body') || document.body;
  if (next !== host) {
    host = next;
    listeners.forEach((listener) => listener());
  }
}
function subscribe(listener) {
  listeners.add(listener);
  if (!observer) {
    observer = new MutationObserver(update);
    observer.observe(document.body, {
      childList: true,
      subtree: true,
      attributes: true,
      attributeFilter: ['open'],
    });
    update();
  }
  return () => {
    listeners.delete(listener);
    if (!listeners.size) {
      observer.disconnect();
      observer = null;
      host = null;
    }
  };
}
const inactive = () => () => {},
  empty = () => null,
  getSnapshot = () => host || document.body;
export default function usePanelHost(active) {
  return useSyncExternalStore(active ? subscribe : inactive, active ? getSnapshot : empty, empty);
}
