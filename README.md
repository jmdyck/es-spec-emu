# es-spec-emu
The current ECMAScript language specification,
formatted in [ecmarkup](https://github.com/bterlson/ecmarkup/)
(with [ecmarkdown](https://github.com/domenic/ecmarkdown)
and [grammarkdown](https://github.com/rbuckton/grammarkdown)).
Note that it doesn't necessarily conform to the latest (or perhaps any) version of these formats.
Things are in flux.

(See also [markdown-es6-spec](https://github.com/DanielRosenwasser/markdown-es6-spec)
for a similar effort using a different flavour of markdown.)

| file           | brief description
|---------------:|:----
|    es-spec.emu | an ecmarkup version of the ES6 spec (derived from the published HTML version)
|        emu.css | a CSS file that makes the above look not terrible in a browser
| notes_on_conversion_to_ecmarkup.md | notes on converting the HTML version into the ecmarkup version
| emu_to_html.py | a script to convert an ecmarkup doc into HTML
|   es-spec.html | the result of applying the above script to es-spec.emu (mostly reconstructs the original HTML version) 
|        es6.css | a CSS file for use by the above (just copied from the HTML version)
-----------------------
