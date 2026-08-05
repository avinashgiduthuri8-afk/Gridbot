import "@testing-library/jest-dom/vitest";

// Radix UI primitives (Select, Dropdown) call these DOM APIs, which jsdom
// doesn't implement — standard test-environment polyfills for Radix.
if (!Element.prototype.hasPointerCapture) {
  Element.prototype.hasPointerCapture = () => false;
}
if (!Element.prototype.scrollIntoView) {
  Element.prototype.scrollIntoView = () => {};
}
if (!Element.prototype.releasePointerCapture) {
  Element.prototype.releasePointerCapture = () => {};
}
