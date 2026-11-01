export default function keepPanelFocus(event) {
  if (event.key !== 'Tab' || !event.currentTarget.contains(document.activeElement)) return;
  const elements = [
    ...event.currentTarget.querySelectorAll(
      'button:not([disabled]), a[href], input:not([disabled]):not([hidden]), select:not([disabled]), textarea:not([disabled]), [tabindex="0"]',
    ),
  ].filter((element) => element.tabIndex >= 0 && element.getClientRects().length);
  if (!elements.length) return;
  const first = elements[0],
    last = elements.at(-1);
  if (event.shiftKey && document.activeElement === first) {
    event.preventDefault();
    last.focus();
  } else if (!event.shiftKey && document.activeElement === last) {
    event.preventDefault();
    first.focus();
  }
}
