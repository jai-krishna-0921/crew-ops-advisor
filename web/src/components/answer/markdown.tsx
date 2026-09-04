"use client";

/**
 * The assistant's prose, rendered as markdown.
 *
 * Two constraints shape this component and neither is cosmetic.
 *
 * **Every element is mapped explicitly.** No raw HTML is allowed through, and
 * there is no `rehype-raw`. The text being rendered is model output, and the
 * one thing a grounded system must never do is hand model output a path to
 * inject markup into the page it is being trusted on.
 *
 * **Figures stay linkable.** Every number, crew id and rule id in the prose is
 * bound to the Fact that attests it, so the text nodes are walked and those
 * atoms wrapped before they are painted. Rendering markdown naively would
 * flatten that, and the link between a figure and its arithmetic is the whole
 * point of the interface.
 */

import { memo, useMemo, type ReactNode } from "react";
import ReactMarkdown, { type Components } from "react-markdown";
import remarkGfm from "remark-gfm";

import type { Fact } from "@/lib/contracts";
import { GroundedText } from "@/components/answer/grounded-prose";

/** Wrap the atoms in every leaf string so figures stay traceable. */
function link(children: ReactNode, facts: Fact[]): ReactNode {
  if (typeof children === "string") {
    return <GroundedText text={children} facts={facts} />;
  }
  if (Array.isArray(children)) {
    return children.map((child, index) =>
      typeof child === "string" ? (
        <GroundedText key={index} text={child} facts={facts} />
      ) : (
        child
      ),
    );
  }
  return children;
}

function componentsFor(facts: Fact[]): Components {
  const linked = (children: ReactNode) => link(children, facts);
  return {
    p: ({ children }) => (
      <p className="text-md leading-relaxed text-ink">{linked(children)}</p>
    ),
    strong: ({ children }) => (
      <strong className="font-semibold text-ink">{linked(children)}</strong>
    ),
    em: ({ children }) => <em className="italic">{linked(children)}</em>,
    ul: ({ children }) => (
      <ul className="ml-4 list-disc space-y-1 text-md leading-relaxed text-ink marker:text-ink-3">
        {children}
      </ul>
    ),
    ol: ({ children }) => (
      <ol className="ml-4 list-decimal space-y-1 text-md leading-relaxed text-ink marker:text-ink-3">
        {children}
      </ol>
    ),
    li: ({ children }) => <li>{linked(children)}</li>,
    h1: ({ children }) => (
      <h3 className="text-lg font-semibold text-ink">{linked(children)}</h3>
    ),
    h2: ({ children }) => (
      <h3 className="text-md font-semibold text-ink">{linked(children)}</h3>
    ),
    h3: ({ children }) => (
      <h4 className="text-base font-semibold text-ink">{linked(children)}</h4>
    ),
    code: ({ children }) => (
      <code className="num rounded-sm bg-surface px-1 py-0.5 text-[0.95em] text-ink">
        {children}
      </code>
    ),
    pre: ({ children }) => (
      <pre className="num overflow-x-auto rounded-md bg-surface p-3 text-xs leading-relaxed text-ink hairline">
        {children}
      </pre>
    ),
    blockquote: ({ children }) => (
      <blockquote className="border-l-2 border-line-strong pl-3 text-md text-ink-2">
        {children}
      </blockquote>
    ),
    // Tables in prose are rare here: a result set arrives as a typed Table and
    // renders through its own component. This covers the occasional inline one.
    table: ({ children }) => (
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-base">{children}</table>
      </div>
    ),
    th: ({ children }) => (
      <th className="label-micro border-b border-line px-2 py-1.5 text-left">
        {children}
      </th>
    ),
    td: ({ children }) => (
      <td className="border-b border-line-soft px-2 py-1.5 align-top text-ink">
        {linked(children)}
      </td>
    ),
    hr: () => <hr className="border-line" />,
    // Links are rendered as plain text. Nothing in a grounded answer should
    // navigate anywhere, and a model-authored href is an obvious hazard.
    a: ({ children }) => <span className="text-ink">{linked(children)}</span>,
    img: () => null,
  };
}

export const Markdown = memo(function Markdown({
  text,
  facts,
}: {
  text: string;
  facts: Fact[];
}) {
  const components = useMemo(() => componentsFor(facts), [facts]);
  return (
    <div className="space-y-3">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {text}
      </ReactMarkdown>
    </div>
  );
});
