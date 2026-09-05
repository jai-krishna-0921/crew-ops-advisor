"use client";

/**
 * The assistant's prose, rendered as markdown.
 *
 * Three constraints shape this component and none of them is decoration.
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
 *
 * **The rhythm is set here, per element, not by a uniform gap.** The previous
 * version put a flat `space-y-3` between top level blocks, which is the
 * shortcut that makes generated prose look generated: a heading sat as far
 * from the paragraph it introduces as from the one it follows, list items had
 * no room to breathe, and a table butted straight into the sentence that set
 * it up. Vertical space is what tells a reader which things belong together,
 * so every block declares its own.
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
    /* THE COLUMN WIDENED; THE PROSE DID NOT. A paragraph is easiest to read
       at roughly 60 to 75 characters a line, and past that the eye loses the
       start of the next line on the way back. The container is wide for the
       things that need it, the option cards, the cost comparison, the rule
       rows and the tables, and running text keeps its own measure inside it.
       `grounded-prose.tsx` already did this for a verified answer; markdown
       never did, so a wider column would have made every paragraph worse. */
    p: ({ children }) => (
      <p className="my-4 max-w-[68ch] text-md leading-[1.72] text-ink">
        {linked(children)}
      </p>
    ),
    strong: ({ children }) => (
      <strong className="font-semibold text-ink">{linked(children)}</strong>
    ),
    em: ({ children }) => <em className="italic">{linked(children)}</em>,

    /* Markers sit OUTSIDE the text block, so a wrapped second line aligns
       under the first word rather than under the bullet. On a list of legal
       findings that hang is the difference between four items and one
       paragraph with dots in it. */
    ul: ({ children }) => (
      <ul className="my-4 ml-5 list-outside list-disc space-y-2 text-md leading-[1.68] text-ink marker:text-ink-3">
        {children}
      </ul>
    ),
    ol: ({ children }) => (
      <ol className="my-4 ml-5 list-outside list-decimal space-y-2 text-md leading-[1.68] text-ink marker:text-ink-3 marker:tabular-nums">
        {children}
      </ol>
    ),
    li: ({ children }) => (
      <li className="max-w-[68ch] pl-1.5">{linked(children)}</li>
    ),

    /* A heading belongs to what comes after it, so it carries a large space
       above and a small one below. */
    h1: ({ children }) => (
      <h3 className="macro mt-7 mb-2 text-lg text-ink">{linked(children)}</h3>
    ),
    h2: ({ children }) => (
      <h3 className="macro mt-7 mb-2 text-lg text-ink">{linked(children)}</h3>
    ),
    h3: ({ children }) => (
      <h4 className="mt-6 mb-1.5 text-md font-semibold text-ink">
        {linked(children)}
      </h4>
    ),
    h4: ({ children }) => (
      <h5 className="mt-5 mb-1 text-base font-semibold text-ink">
        {linked(children)}
      </h5>
    ),

    code: ({ children }) => (
      <code className="mono rounded-xs bg-inset px-1.5 py-0.5 text-[0.92em] text-ink">
        {children}
      </code>
    ),
    pre: ({ children }) => (
      <pre className="mono my-4 overflow-x-auto rounded-md bg-inset p-3.5 text-xs leading-[1.7] text-ink">
        {children}
      </pre>
    ),
    blockquote: ({ children }) => (
      <blockquote className="my-4 rounded-r-sm border-l-2 border-line-strong bg-inset/60 py-1 pr-3 pl-3.5 text-md text-ink-2">
        {children}
      </blockquote>
    ),

    /* Tables in prose are rare here: a result set arrives as a typed Table and
       renders through its own component. This covers the occasional inline
       one, and it is set the same way, so the two do not look like they came
       from different products. */
    table: ({ children }) => (
      <div className="my-5 overflow-x-auto">
        <table className="w-full border-collapse text-base">{children}</table>
      </div>
    ),
    th: ({ children }) => (
      <th className="label-micro border-b border-line-soft px-3 py-2 text-left">
        {children}
      </th>
    ),
    td: ({ children }) => (
      <td className="border-b border-line-soft px-3 py-2 align-top text-ink">
        {linked(children)}
      </td>
    ),

    hr: () => <hr className="my-7 border-line-soft" />,

    /* Links are rendered as plain text. Nothing in a grounded answer should
       navigate anywhere, and a model-authored href is an obvious hazard. */
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
    // Each block owns its own margin, so the first and last are collapsed
    // here rather than every element having to know whether it is an edge.
    <div className="[&>*:first-child]:mt-0 [&>*:last-child]:mb-0">
      <ReactMarkdown remarkPlugins={[remarkGfm]} components={components}>
        {text}
      </ReactMarkdown>
    </div>
  );
});
