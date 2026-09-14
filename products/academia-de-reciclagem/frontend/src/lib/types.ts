/** Shared response envelope — contract §0. Every list response is this shape. */
export interface Envelope<T> {
  items: T[];
  total: number;
}
