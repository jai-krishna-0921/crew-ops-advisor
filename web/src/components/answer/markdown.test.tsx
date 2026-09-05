import { cleanup, render } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";

import { Markdown } from "./markdown";

/**
 * A wider column must not become a wider line of prose.
 *
 * The conversation was capped at 48rem, which left a band of empty page down
 * both sides on any real monitor and squeezed the things that actually want
 * room: the ranked option cards, the cost comparison, the rule rows and the
 * tables. That squeeze is why the table carried a negative-margin bleed.
 *
 * Widening the column fixes those and breaks the prose, because the two want
 * opposite things. A paragraph is easiest to read at roughly 60 to 75
 * characters a line; past that the eye loses the start of the next line on the
 * way back. So the container widens and the running text keeps its measure,
 * which is what `grounded-prose.tsx` already does for a verified answer and
 * what markdown never did.
 */

afterEach(cleanup);

it("holds a paragraph to a readable measure", () => {
  const { container } = render(<Markdown facts={[]} text="A plain paragraph." />);
  const paragraph = container.querySelector("p");

  expect(paragraph).not.toBeNull();
  expect(paragraph!.className).toMatch(/max-w-\[68ch\]/);
});

it("holds list items to the same measure", () => {
  const { container } = render(<Markdown facts={[]} text={"- one\n- two"} />);
  const item = container.querySelector("li");

  expect(item).not.toBeNull();
  expect(item!.className).toMatch(/max-w-\[68ch\]/);
});

it("lets a table use the whole column", () => {
  const source = "| Crew | Cost |\n| --- | --- |\n| C-3310 | 18,500 |";
  const { container } = render(<Markdown facts={[]} text={source} />);
  const wrapper = container.querySelector("table")?.parentElement;

  expect(wrapper).not.toBeNull();
  expect(wrapper!.className).not.toMatch(/max-w-\[68ch\]/);
  expect(wrapper!.className).toMatch(/overflow-x-auto/);
});

it("lets a code block use the whole column", () => {
  const { container } = render(<Markdown facts={[]} text={"```\nDX412\n```"} />);
  const pre = container.querySelector("pre");

  expect(pre).not.toBeNull();
  expect(pre!.className).not.toMatch(/max-w-\[68ch\]/);
});
