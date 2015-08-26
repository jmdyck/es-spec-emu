# Notes on my initial conversion of the ES2015 spec to ecmarkup, 2015-07-13.

Here's my rough pipeline:
 1. I start with the official HTML version of the spec.
 2. I convert it into XHTML, because it turns out that XML is easier
    for me to work with.
 3. I pretty-print it, with block-level elements consistently indented,
    and other linebreaks (except in `<pre>` elements) normalized to
    single spaces (so each paragraph is usually a single line). 
 4. Then I apply a (rather hairy) script that fixes a lot of the
    mistakes and inconsistencies in the HTML spec. (This will be
    useful, if only as documentation, if I ever need to maintain
    es-spec-html.)
 5. Finally, I apply a (relatively straightforward) script to convert
    the cleaned-up XHTML into ecmarkup/ecmarkdown/grammarkdown.

What follows are my notes on the result. (Generally, the subtext is:
"It wasn't obvious how I should handle X. Here's how I handled it.
What do you think?")

## Additional 'emu' elements I created:

### `<emu-see-also-para>`

The content of all the "See also" paragraphs can be generated based on
the other content of the base document, so I invented the
`<emu-see-also-para>` element as a placeholder. For example, 11.6.1.2 has
```
    <emu-see-also-para op="StringValue"></emu-see-also-para>
```
The 'op' attribute could probably be inferred from the containing
subclause, but having it in the attribute is a little easier.  Of
course, you might choose to not generate the "See also" paragraphs
as such.

### `<emu-formula>`

When a prose paragraph includes text that would normally appear only in
algorithm blocks, the spec sometimes (I'm not sure how consistently)
sets it off in a different font.  In the PDF this is more noticeable,
since prose is in sans-serif, and the included text is in serif. (E.g.,
in 5.2 Algorithm Conventions, see para 2's "operationName(arg1, arg2)".
Also see later in the same section, where the various mathementical
functions are introduced. Interestingly, for the phrase "x module y",
it seems that the change of font wasn't enough, so quotes were added.)

In the HTML version, both fonts are serif, though slightly different
(in my browser, anyhow), so the distinction is harder to see.

In case you want to retain this distinction in markup, I created
`<emu-formula>`.

### `<emu-placeholder>`

I invented `<emu-placeholder>` to stand in for large chunks of content
that can be generated based on other content.
It has one attribute, named `for`,
whose value indicates the content for which the element is a placeholder.
So far, the values are:
`"title-page"` (for the title page, including disclaimer),
`"toc"` (for the Table of Contents),
`"inner-title"` (for the inner title div), and
8 forms of `"grammar-summary/..."` (for the guts of Annex A).


## Grammar stuff:

There are a few constructs used in the spec's productions that aren't
listed as valid in https://github.com/rbuckton/grammarkdown:
 - "one of"
 - "but not X"
 - "but not one of ... or ..."
 - "U+0000 through U+001F" (in rhs for DoubleStringCharacter)
 - "but only if ..." (in rhs for AtomEscape and ClassAtomNoDashInRange in B.1.4)

In each case, I just passed the text through as emu-grammar content.
(It looks like the first 3 are actually valid, they just aren't listed as such.)

For the two cases of "one of `<table>`" (in 11.6.2.1 Keyword and
11.7 Punctuator), I didn't want a `<table>` in an `<emu-grammar>`,
so I just unravelled the table.

It's unclear from the ecmarkup readme whether `<emu-grammar>` is block or
inline, or can be either depending on context or content. Should it
have an attribute to distinguish? Or should there be two different
element names?

I didn't use any of ecmarkup's 'structured' grammar elements:
 -  emu-production
 -  emu-rhs
 -  emu-nt
 -  emu-t
 -  emu-gmod
 -  emu-gann
 -  emu-gprose
 -  emu-prodref

Maybe ecmarkup doesn't need to support them.

One anomaly is clause 12.3.2, which has 8 right-hand-sides with no
left-hand-sides. I converted them to ecmarkdown, but presumably can't
put the results into `<emu-grammar>` elements because they're not full
productions. So they still have the `<div class="rhs">` markup from the
HTML spec. However, it seems like there's no reason they couldn't be
made into full productions (with MemberExpression and CallExpression
as the LHS), allowing them to be put into `<emu-grammar>` elements, for a
more uniform treatment. (Mind you, that `<identifier-name-string>` would
still be odd. It should maybe be changed to the actual nonterminal
`|StringLiteral|`.)

I mostly gutted Annex A, leaving behind just an
```
    <emu-placeholder for="grammar-summary/...">
```
for each section,
allowing it to be generarated based on productions in the document body.
One interesting thing about Annex A is that it isn't *just* productions,
there are also some prose paragraphs.
But not every paragraph from a 'Syntax' section gets copied to Annex A,
and it's not obvious what the selection criterion is,
so I've marked certain `<p>` elements with the attribute
```
    copy_to_summary="yes"
```


## Algorithms:

The HTML spec has a couple of `<ol class="proc">` that don't look like
algorithms to me:
 - 11.9.1 three basic rules of ASI and
 - B.3.3 uses cases in intersection semantics

I converted them to plain `<ol>` rather than `<emu-alg>`. 

The ecmarkdown readme, under "Numeric lists", says "Lines can be
indented by multiples of exactly two spaces to indicate nesting."
However, I found that a two-space indent wasn't enough to make the
structure clear. (Try it with, say, the algorithm in 9.1.6.3.) You need
at least three spaces to get a substep to "tuck under" the body of the
parent step, which looks a lot 'cleaner' to me.  In the end, I used a
four-space indent, because I was re-using the two-space indents from
the XML file, and there are two XML-element-levels between a step and
its substep (`<ol>` and `<li>`).

I assume that the content of an `<emu-alg>` can include child elements:
 - `<emu-grammar>`      (e.g., for 13.2.5 / group 3 / step 1)
 - `<emu-xref>`         (e.g., for 6.2.3.1 / step 6.a)
 - `<a>`                (e.g., for 21.1.3.12 / step 8)

Also, there are two places where an `<emu-alg>` contains a `<table>` (or a
`<figure>` containing a `<table>`):
 - 21.2.2.6.1 IsWordChar / step 3
 - 24.3.2.2 QuoteJSONString / step 2.b.ii

Those could perhaps be marked up differently.

There are also two places in the HTML where an algorithm contains an
`<ul>`:
 - 22.1.3.24 / alg 3 / step 1
 - B.2.3.2.1 / step 5.d

Originally, ecmarkdown didn't have a way to denote unordered-list-items,
so I invented one, but I'm now using the label '*'.

In the PDF, "NOTE" steps in algorithms are rendered in sans-serif, but
in the HTML, they're generally in serif, the same as other steps. I
assumed that they didn't need any special markup in the emu doc.

Within an algorithm, the HTML spec almost always encloses a list of
substeps in `<ol class="block">`. But it uses `<ol class="nested proc">`
in 14 cases, mostly when the 'parent' step is creating an internal
closure and the substeps belong to the closure, not the algorithm per
se. In the HTML spec, this results in the scheme for substep-labels
'resetting' to decimal (where it would otherwise be lowercase-latin,
say). In the PDF spec, there's moreover a bigger-than-usual increase
in indentation. But as far as I can see, ecmarkdown has no way to make
this distinction, so I've converted those two kinds of `<ol>` the same.


## code containing metavariables:

There are several places in the spec where a run of code refers to an
expositional metavariable. The HTML spec isn't consistent in how it
marks these up, but I decided that each should be a single `<code>`
element with embedded `<i>` or `<var>` elements. The problem comes when
converting this to ecmarkdown. The ecmarkdown readme doesn't say, but
I gather that when a backtick-delimited span of text is converted to
a `<code>` element, no further processing of that span is done. For
example, if I were to down-convert:
```
    <code><i>constructor</i>.prototype</code>
```
to
```
    `_constructor_.prototype`
```
then I believe ecmarkdown would up-convert that to
```
    <code>_constructor_.prototype</code>
```
not recognizing the embedded variable.

Consequently, I didn't do any down-conversion in the following cases:

    4.3.5 / note
    <code><i>constructor</i>.prototype</code>

    18.2.6.1.1 / step 4.d.vi.2
    <code>"%<var>XY</var>"</code>

    18.2.6.1.2 / Table 43
    <code>00000000 0<i>zzzzzzz</i></code>
    (among others)

    19.5.6.1 / para 1
    <code><i>NativeError</i>(&hellip;)</code>
    <code>new <i>NativeError</i>(&hellip;)</code>

    19.5.6.1.1 / 
    <code>"%<i>NativeError</i>Prototype%"</code>

    19.5.6.2.1 /
    <code><i>NativeError</i>.prototype</code>

    20.3.4.41 / note 1
    <code><i>d</i>.valueOf()</code>

    21.1.3.1 / note 1
    <code>x.charAt(<var>pos</var>)</code>
    <code>x.substring(<var>pos</var>, <var>pos</var>+1)</code>

    22.2.6.1 / para 1
    <code><i>TypedArray</i>.prototype.BYTES_PER_ELEMENT</code>

    22.2.6.2 / para 1
    <code><i>TypedArray</i>.prototype.constructor</code>

    B.2.1.1 / para 2
    <code>%<i>xx</i></code>
    <code>%u<i>xxxx</i></code>

    B.2.1.1 / step 6.c.i
    <code>"%u<var>wxyz</var>"</code>

    B.2.1.1 / step 6.d.i
    <code>"%<var>xy</var>"</code>

(There would be more examples involving `<i>NativeError<i>` and
`<i>TypedArray</i>`, but the spec isn't consistent in its application of
`<code>`.)

## Miscellaneous:

Frontmatter: I retained the Copyright Notice, replaced the Table of Contents
with `<emu-placeholder for="toc">`, and deleted the rest.

Sections: I figured it would be useful to know the section-number
that each section had in ES6, so I put it into an HTML comment preceding
each `<emu-clause>`.

Section ids: I just re-used the ids from the HTML spec. However,
they seem somewhat inconsistent, so this might be an occasion to
devise a better system of ids.

Table ids: Currently, the HTML assigns serial ids to tables ('table-1',
'table-2', etc.), but since these can change from draft to draft,
they presumably should be replaced with robust ids. E.g., 'table-1'
could become 'table-well-known-symbols'. I haven't done this.

Defining occurrences: The spec sometimes uses italics to emphasize
a word/phrase at its first or defining occurrence. (In clauses 4 and
4.2, it uses bold-italic.) I've converted a bunch of these to `<dfn>`,
but I've probably missed a bunch too, so those would have ended up
converted to `_foo_`.

For section 6.1.7.3 "Invariants of the Essential Internal Methods",
the markup in the HTML spec is very presentational. I converted it
to something more structural, but you might want to go farther.

Each of 20.2.2.{13,31,34} has a note containing a formula in
italic. Should be in code?

