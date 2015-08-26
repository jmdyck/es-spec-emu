#!/usr/bin/python

# The initial purpose of this script is to regenerate the HTML source
# from which es-spec.emu was derived, thus demonstrating that es-spec.emu
# contains all the information necessary to do so.
# Once that's done, we can start to evolve this script and the generated HTML.
#
# (Code marked "RECONSTRUCTING" is particularly foxused on reconstructing the
# particular form of the HTML source, and will probably not be wanted going forward.)

import sys, re, cStringIO, collections, pdb, atexit
import xml.dom.minidom
import html5lib

input_filename = 'es-spec.emu'
output_filename = 'es-spec.html.new'

def main():
    print >> sys.stderr, "Attempting to parse %s as HTML5..." % input_filename
    input_f = open(input_filename,'r')
    parser = html5lib.HTMLParser(tree=html5lib.treebuilders.getTreeBuilder('dom'))
        # The default treebuilder is etree, which I don't like.
    document = parser.parse(input_f)
    if parser.errors:
        print >> sys.stderr, "Parsing raised the following errors:"
        for error in parser.errors:
            print >> sys.stderr, error
        sys.exit(-1)

    do_prep(document)

    print >> sys.stderr, "Converting the document..."
    global output_buffer
    output_buffer = cStringIO.StringIO()
    serialize(document, True)
    print >> sys.stderr

    print >> sys.stderr, "Writing the document..."
    output_f = open(output_filename,'w')
    output_f.write(output_buffer.getvalue())

    if len(annex_a):
        print >> sys.stderr, 'Annex A did not recap:', annex_a.keys()

# XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX

def do_prep(doc):
    # For some reason, htmllib.HTMLParser (or maybe the 'dom' treebuilder)
    # eats the linebreak at the start of every <pre> element.
    # Put them back.
    for pre in doc.getElementsByTagName('pre'):
        pre.insertBefore(doc.createTextNode('\n'), pre.firstChild)
        # If, as is usual, the firstChild is a text node,
        # the call to dom.normalize() will merge them.

    doc.normalize()
    # In addition to the merges referred to above,
    # this call merges text-nodes created for character-entity-refs.
    # For example, before normalize(), the element
    #     <h1>The Unsigned Right Shift Operator ( `&gt;&gt;&gt;` )</h1>
    # has 5 children, including a text-node for each '&gt;'

    print >> sys.stderr, "Gathering section info..."
    for bica in getElementsByTagNames(doc, ['body', 'emu-intro', 'emu-clause', 'emu-annex']):
        # "bica" = "body / intro / clause / annex"
        bica._section_info = SectionInfo(bica)

    print >> sys.stderr, "Inferring section kinds..."
    global n_defns_for_rec_method
    n_defns_for_rec_method = collections.defaultdict(int)
    infer_section_kind(section_info_root)
    # We could do this in SectionInfo(),
    # but it's somewhat easier after the section-tree has been built.
    # dump_section_kinds(section_info_root); sys.exit()

    print >> sys.stderr, "Prepping for see-also..."
    prep_for_see_also(doc)

    print >> sys.stderr, "Prepping for add_xlinks..."
    prep_for_add_xlinks(section_info_root)

    print >> sys.stderr, "Assigning note-numbers..."
    assign_note_numbers(doc)

    print >> sys.stderr, "Marking productions for copy to Annex A..."
    mark_annexable_syntax(doc)

def get_enclosing_section(node):
    a = node
    while a.nodeName not in ['emu-intro', 'emu-clause', 'emu-annex']:
        a = a.parentNode
    return a

# ------------------------------------------------------------------------------

info_for_id_ = {}
section_info_root = None

class SectionInfo:
    def __init__(self, bica):
        assert bica.nodeType == bica.ELEMENT_NODE

        self.node = bica
        self.nodeName = bica.nodeName

        self.children = []

        if bica.nodeName == 'body':
            # This won't become a section,
            # but it's useful to build a SectionInfo for it.
            self.level = 0
            self.numbered_child_counter = 0
            self.lettered_child_counter = 0

            global section_info_root
            section_info_root = self
            return

        parent_si = bica.parentNode._section_info

        self.level = parent_si.level + 1
        parent_si.children.append(self)

        h1 = bica.firstChild.nextSibling
        assert h1.nodeName == 'h1'
        self.title_xml = toxml_content(h1)

        if bica.nodeName == 'emu-intro':
            self.toc_thing = self.title_xml
            self.h1_prefix = ''
            self.dotnum = '0'

        elif bica.nodeName in ['emu-clause', 'emu-annex']:

            self.id = bica.getAttribute('id')
            info_for_id_[self.id] = self

            if parent_si.level == 0:
                inherited_dotnum = ''
            else:
                inherited_dotnum = parent_si.dotnum + '.'

            if bica.nodeName == 'emu-annex' and self.level == 1:
                assert inherited_dotnum == ''
                parent_si.lettered_child_counter += 1
                num_within_parent = 'ABCDEFGHIJK'[parent_si.lettered_child_counter-1]
                self.dotnum = inherited_dotnum + num_within_parent
                dotnum_phrase = 'Annex ' + self.dotnum
                status = 'normative' if bica.hasAttribute('normative') else 'informative'
                status_piece = '<span class="section-status">(%s)</span> ' % status
            else:
                parent_si.numbered_child_counter += 1
                num_within_parent = str(parent_si.numbered_child_counter)
                self.dotnum = inherited_dotnum + num_within_parent
                dotnum_phrase = self.dotnum
                status_piece = ''

            self.toc_thing = '<span class="secnum"><a href="#%s">%s</a></span> %s%s' % (
                self.id,
                dotnum_phrase,
                status_piece,
                expand_ecmarkdown(self.title_xml)
            )

            self.h1_prefix = (
                '<span class="secnum" id="sec-%s"><a href="#%s" title="link to this section">%s</a></span> %s' % (
                    self.dotnum,
                    self.id,
                    dotnum_phrase,
                    status_piece
                )
            )

            if self.title_xml == 'Bibliography':
                # RECONSTRUCTING
                self.toc_thing = self.title_xml
                self.h1_prefix = ''

            if self.dotnum[0].isdigit():
                if self.level == 1:
                    self.type_for_internal_refs = 'clause'
                else:
                    self.type_for_internal_refs = 'subclause'
            else:
                self.type_for_internal_refs = 'Annex'

            self.numbered_child_counter = 0

# ------------------------------------------------------------------------------

def infer_section_kind(si, expectation='general'):
    def recurse(rsi, exp):
        for si_child in rsi.children:
            infer_section_kind(si_child, exp)

    if si.nodeName == 'body':
        si.kind = ''
        recurse(si, 'general')
        return

    if expectation == 'general':
        patterns = [

            (r'^(?P<op_name>NormalCompletion|Throw an Exception|ReturnIfAbrupt|IfAbruptRejectPromise)\b', 'shorthand'),

            (r'^((Runtime|Static) Semantics: )?(?P<op_name>[\w/]+) *\((?P<params>[^()]*)\)$', 'abstract_operation'),
            (r'^((Runtime|Static) Semantics: )?(?P<op_name>\w+) Abstract Operation$',         'abstract_operation'),
            (r'^(?P<op_name>ToString Applied to the Number Type)$',                           'abstract_operation'),
            (r'^(?P<op_name>(Abstract|Strict) (Relational|Equality) Comparison)$',            'abstract_operation'),
            (r'^(?P<op_name>NextJob) result$',                                                'abstract_operation'),
            (r'^ECMAScript (?P<op_name>Initialization)\(\)$',                                 'abstract_operation'),

            (r'^(Runtime|Static) Semantics: (?P<op_name>[\w]+)$', 'production_based_operation'),

            (r'^(?P<method_name>\w+) *\((?P<params>[^()]*)\) Concrete Method$', 'module_rec_method'),

            (r'^\[\[(?P<im_name>\w+)\]\] *\((?P<params>[^()]*)\)$', 'internal_method'),

            (r'^Static Semantics: Early Errors$', 'early_errors'),

            (r'^_NativeError_ Object Structure', 'loop'),

            (r'^(The )?\w+ Constructors?$',        'Call_and_Construct_ims_of_an_intrinsic_object'),
            (r'The %TypedArray% Intrinsic Object', 'Call_and_Construct_ims_of_an_intrinsic_object'),

            (r'^The (?P<what>\S+) Object$',                                            'properties_of_an_intrinsic_object'),
            (r'^(Additional )?Properties of the (?P<what>.+ (Constructors?|Object))$', 'properties_of_an_intrinsic_object'),
            (r'^Properties of (?P<what>Generator Prototype)$',                         'properties_of_an_intrinsic_object'),

            (r'^Properties of (?P<what>.+) Instances$', 'properties_of_instances'),
            (r'^\w+ Instances$',                        'properties_of_instances'),

            (r'(?<!Non-ECMAScript) Functions$', 'function_factory'),

            (r'^Notation$', 'catchall'),

        ]
    elif expectation == 'properties':
        patterns = [
            (r'^\w+ Properties of the \w+ Object$', 'group_of_properties1'),
            (r'^URI Handling Functions$',           'group_of_properties2'),

            (r'^(get|set)', 'accessor_property'),
            (r'^(?P<property_fullname>\S+) *\(', 'function_property'),
            (r'^(?P<property_fullname>[\w%]+(\.\w+)*)$', 'other_property'),
            (r'^[\w%]+(\.\w+)* *\[ @@\w+ \]$', 'other_property'),
        ]
    else:
        assert 0, expectation

    # --------------------------

    for (pattern, kind) in patterns:
        mo = re.search(pattern, si.title_xml)
        if mo:
            si.kind = kind
            si.kind_stuff = mo.groupdict()
            break
    else:
        if re.match(r'^\w+$', si.title_xml) and si.dotnum.startswith('21.2.2'):
            si.kind = 'production_based_operation'
            si.kind_stuff = {'op_name': 'RegExEvaluate'}
        elif re.match(r'^%TypedArray%.prototype.set *\(', si.title_xml):
            si.kind = 'one_piece_of_overloaded_alg'
        else:
            si.kind = 'catchall'

    # --------------------------

    if re.match(r'^\w+ Environment Records$', si.title_xml):
        assert si.kind == 'catchall'
        for si_child in si.children:
            mo = re.match(r'^(?P<method_name>\w+) *\((?P<params>.*)\)$', si_child.title_xml)
            assert mo, si_child.title_xml
            si_child.kind = 'env_rec_method'
            si_child.kind_stuff = mo.groupdict()

            n_defns_for_rec_method[si_child.kind_stuff['method_name']] += 1

            if 0:
                if si_child.kind_stuff['method_name'] in [
                    'HasBinding',
                    'CreateMutableBinding',
                    'CreateImmutableBinding',
                    'InitializeBinding',
                    'SetMutableBinding',
                    'GetBindingValue',
                    'DeleteBinding',
                    'HasThisBinding',
                    'HasSuperBinding',
                    'WithBaseObject',
                ]:
                    si_child.kind += '_IOAM' # implementation of abstract method
                else:
                    si_child.kind += '_IBTC' # introduced by this 'class'

            recurse(si_child, 'general')
        return

    elif kind == 'Call_and_Construct_ims_of_an_intrinsic_object':
        pieces = [si_child for si_child in si.children if '(' in si_child.title_xml]
        if len(pieces) == 1:
            x = 'non_overloaded_CallConstruct_alg'
        else:
            x = 'one_piece_of_overloaded_alg'
        for si_child in si.children:
            if si_child in pieces:
                si_child.kind = x
            else:
                si_child.kind = 'catchall'
            recurse(si_child, 'general')
        return

    elif kind in ['properties_of_an_intrinsic_object', 'group_of_properties1', 'group_of_properties2']:
        expectation = 'properties'

    elif kind == 'module_rec_method':
        n_defns_for_rec_method[si.kind_stuff['method_name']] += 1
        expectation = 'general'

    else:
        expectation = 'general'

    recurse(si, expectation)

def dump_section_kinds(si):
    if not hasattr(si, 'kind'):
        kind = 'UNSET'
    else:
        kind = si.kind

    if si.nodeName == 'body':
        pass
    else:
        print '%s%-47s%s %s' % (
            '  '*(si.level-1), kind, si.dotnum, si.title_xml
        )

    for si_child in si.children:
        dump_section_kinds(si_child)

# ------------------------------------------------------------------------------

see_also_info = collections.defaultdict(list)

def prep_for_see_also(doc):
    for ica in getElementsByTagNames(doc, ['emu-intro', 'emu-clause', 'emu-annex']):
        si = ica._section_info
        if si.kind == 'production_based_operation':
            op_name = si.kind_stuff['op_name']
            if op_name == 'RegExEvaluate': continue
            see_also_info[op_name].append(si)
        elif si.title_xml == 'Static Semantic Rules':
            see_also_info['Contains'].append(si)
        elif si.title_xml == '__proto__ Property Names in Object Initializers':
            see_also_info['PropertyDefinitionEvaluation'].append(si)

# ------------------------------------------------------------------------------

def assign_note_numbers(doc):
    for ica in getElementsByTagNames(doc, ['emu-intro', 'emu-clause', 'emu-annex']):
        emu_notes = [
            child
            for child in ica.childNodes
            if child.nodeName == 'emu-note'
        ]
        n_notes = len(emu_notes)
        if n_notes == 0:
            pass
        elif n_notes == 1:
            assign_note_number(emu_notes[0], '')
        else:
            for (i, emu_note) in enumerate(emu_notes):
                assign_note_number(emu_note, ' %d' % (i+1))

def assign_note_number(emu_note, num):
    assert emu_note.nodeName == 'emu-note'
    t = emu_note.firstChild
    assert t.nodeType == t.TEXT_NODE
    p = t.nextSibling
    assert p.nodeName == 'p'
    p._note_number = num

# ------------------------------------------------------------------------------

def mark_annexable_syntax(document):
    for emu_clause in document.getElementsByTagName('emu-clause'):
        dotnum = emu_clause._section_info.dotnum
        if dotnum.startswith('B.'): continue
        if dotnum == '12.14.5': continue # XXX RECONSTRUCTING omission from annex

        grammar_summary_part = None
        for child in emu_clause.childNodes:
            if child.nodeName == 'h2':
                x = child.toxml()
                if x in ['<h2>Syntax</h2>', '<h2>Supplemental Syntax</h2>']:
                    # XXX shouldn't use dotnums
                    if dotnum.startswith('10') or dotnum.startswith('11'):
                        grammar_summary_part = 'lexical-grammar'
                    elif dotnum.startswith('12'):
                        grammar_summary_part = 'expressions'
                    elif dotnum.startswith('13'):
                        grammar_summary_part = 'statements'
                    elif dotnum.startswith('14'):
                        grammar_summary_part = 'functions-and-classes'
                    elif dotnum.startswith('15'):
                        grammar_summary_part = 'scripts-and-modules'
                    elif dotnum.startswith('7'):
                        grammar_summary_part = 'number-conversions'
                    elif dotnum.startswith('18.2.6.1'):
                        grammar_summary_part = 'universal-resource-identifier-character-classes'
                    elif dotnum.startswith('21.2.1'):
                        grammar_summary_part = 'regular-expressions'
                    else:
                        assert 0
                    copy_all_contents = (x == '<h2>Supplemental Syntax</h2>')
                else:
                    grammar_summary_part = None
            elif child.nodeName == 'emu-clause':
                grammar_summary_part = None
            elif grammar_summary_part and child.nodeType == child.ELEMENT_NODE:
                if child.nodeName == 'emu-grammar' or copy_all_contents:
                    child.setUserData('grammar_summary_part', grammar_summary_part, None)
                elif child.getAttribute('copy_to_summary') == 'yes':
                    child.removeAttribute('copy_to_summary')
                    child.setUserData('grammar_summary_part', grammar_summary_part, None)
                else:
                    pass
                    # print
                    # print my_toxml(child)
                    # (25 <emu-note>s and 10 <p>s)

# XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX

def serialize(node, apply_emd_expansions):
    if node.nodeType == node.DOCUMENT_NODE:
        serializeChildren(node, apply_emd_expansions)
    elif node.nodeType == node.DOCUMENT_TYPE_NODE:
        put(node.toxml())
        put('\n')

    elif node.nodeType == node.ELEMENT_NODE:
        name = node.nodeName
        if name == 'emu-placeholder':
            f = node.getAttribute('for')
            if f in ['title-page', 'inner-title']:
                put_title_thing(f)
            elif f == 'toc':
                put_toc()
            elif f.startswith('grammar-summary/'):
                grammar_summary_part = f.replace('grammar-summary/', '')
                s = annex_a[grammar_summary_part].getvalue()
                put(s.lstrip())
                del annex_a[grammar_summary_part]
            else:
                assert 0, f

        elif name == 'emu-external-ref':
            href = node.getAttribute('href')
            linktext_template = node.getAttribute('linktext')
            if linktext_template == 'URL':
                linktext = href
            else:
                assert 0, linktext_template
            put('<a href="%s">%s</a>' % (href, linktext))

        elif name == 'emu-internal-ref':
            refid = node.getAttribute('refid')
            linktext_template = node.firstChild.nodeValue
            put(convert_emu_internal_ref(refid, linktext_template))

        elif name == 'emu-see-also-para':
            handle_emu_see_also_para(node)

        elif name == 'emu-grammar':
            handle_emu_grammar_node(node)

        elif name == 'emu-alg':
            handle_emu_alg(node)

        elif name == 'emu-eqn':
            handle_emu_eqn(node)

        elif name == 'emu-table':
            handle_emu_table(node)

        elif name == 'emu-figure':
            handle_emu_figure(node)

        else:
            if node.hasAttributes():
                attrs = dict(node.attributes.items())
            else:
                attrs = {}

            if name in ['emu-intro', 'emu-clause', 'emu-annex']:
                global current_section_id
                try:
                    current_section_id = node.getAttribute('id')
                except:
                    current_section_id = None
                output_name = 'section'
                if 'normative' in attrs: del attrs['normative'] # RECONSTRUCTING
                if 'aoid' in attrs: del attrs['aoid'] # RECONSTRUCTING
            elif name == 'emu-formula':
                output_name = 'span'
                attrs['style'] = 'font-family: Times New Roman'
            elif name == 'emu-note':    
                output_name = 'div'
                attrs['class'] = 'note'
            elif name == 'link':
                if attrs['href'] == 'emu.css':
                    attrs['href'] = 'es6.css'
                output_name = name
            else:
                output_name = name

            grammar_summary_part = node.getUserData('grammar_summary_part')
            if grammar_summary_part:
                # This is kludgey, but for now I just want something tha
                global output_buffer
                start_posn = len(output_buffer.getvalue())

            put('<' + output_name)
            for (attr_name, attr_value) in sorted(attrs.items()):
                put(' %s="%s"' % (attr_name, attr_value))

            if name in ['br', 'img', 'meta', 'link']:
                put('/>') # The slash is there for RECONSTRUCTING
            else:
                put('>')
                if name == 'head':
                    put('\n    ')
                    put_title_thing('title-in-head')
                    # because you can't put an <emu-placeholder> in the <head>
                elif name == 'h1':
                    ica = node.parentNode
                    assert ica.nodeName in ['emu-intro', 'emu-clause', 'emu-annex']
                    put(ica._section_info.h1_prefix)
                elif name == 'p' and hasattr(node, '_note_number'):
                    put('<span class="nh">NOTE%s</span> ' % node._note_number)

                if name in ['pre', 'code']:
                    apply_emd_expansions = False

                serializeChildren(node, apply_emd_expansions)
                put('</' + output_name + '>')

            if grammar_summary_part:
                line = output_buffer.getvalue()[start_posn:]
                annex_a[grammar_summary_part].write('\n        ' + line)

    elif node.nodeType == node.TEXT_NODE:
        global text_node_counter
        text_node_counter += 1
        if text_node_counter % 500 == 0: sys.stderr.write('.')
        if re.match(r'^\n\n +$', node.nodeValue): return # XXX RECONSTRUCTING: no blank lines between sections
        s = my_toxml(node)
        if apply_emd_expansions: s = expand_ecmarkdown(s)
        if node.parentNode.nodeName not in ['h1', 'dfn']: s = add_xlinks(s)
        put(s)

    elif node.nodeType == node.COMMENT_NODE:
        if node.nodeValue.startswith(' es6num='): return # XXX RECONSTRUCTING: no comment before section
        put('<!--%s-->' % node.nodeValue)

    else:
        print >> sys.stderr, node.nodeType
        assert 0, node.toxml()

text_node_counter = 0

def serializeChildren(node, apply_emd_expansions):
    for child in node.childNodes:
        serialize(child, apply_emd_expansions)

# XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX

def put_title_thing(f):
    if f == 'title-in-head':
        template = '''
            <title>
              {spec_name_noreg} &ndash; {spec_designation} {spec_edition}th Edition
            </title>
        '''
    elif f == 'title-page':
        template = '''
            <img alt="Ecma International Logo." height="146" src="Ecma_RVB-003.jpg" width="373"/>
            <hgroup>
              <h1 style="color: #ff6600">Standard {spec_designation}</h1>
              <h1 style="color: #ff6600">{spec_edition}<sup>th</sup> Edition / {spec_approval_date}</h1>
              <h1 style="color: #ff6600; font-size: 225%; margin-top: 20px">{spec_name_reg}</h1>
            </hgroup>
            <div id="unofficial">
              <p>This is the HTML rendering of <i>{spec_designation} {spec_edition}<sup>th</sup> Edition, The {spec_name_noreg}</i>.</p>
              <p>The PDF rendering of this document is located at <a href="{spec_pdf_url}">{spec_pdf_url}</a>.</p>
              <p>The PDF version is the definitive specification. Any discrepancies between this HTML version and the PDF version are unintentional.</p>
            </div>
            <hr/>
        '''
    elif f == 'inner-title':
        template = '''
            <div class="inner-title">
              {spec_name_noreg}
            </div>
        '''
    else:
        assert 0, f

    text = ( template
        .replace('\n        ', '\n') # for RECONSTRUCTING indentation
        .strip()
        .format(
            # Eventually, these settings will come from some kind of metadata section.
            spec_designation = 'ECMA-262',
            spec_edition = '6',
            spec_name_reg = 'ECMAScript<sup>&reg;</sup> 2015 Language Specification',
            spec_name_noreg = 'ECMAScript 2015 Language Specification',
            spec_approval_date = 'June 2015',
            spec_pdf_url = 'http://www.ecma-international.org/ecma-262/6.0/ECMA-262.pdf',
        )
    )

    put(text)

# ----------------------------------

def put_toc():
    put('<section id="contents">')
    put('\n      <h1>Contents</h1>')
    put_toc_r(section_info_root, '\n      ')
    put('\n    </section>')
    put('\n    ')

def put_toc_r(section_info_parent, indent):
    if section_info_parent.level == 3: return
    if section_info_parent.children == []: return

    put(indent + '<ol class="toc">')

    for si in section_info_parent.children:
        put(indent + '  <li>')
        put(indent + '    ' + si.toc_thing)
        put_toc_r(si, indent + '    ')
        put(indent + '  </li>')

    put(indent + '</ol>')

# XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX

class MultiSub:
    def __init__(self, pattern_repls):
        self.pattern_things = [
            PatternThing(pattern, repl)
            for (pattern, repl) in pattern_repls
        ]

    def apply(self, subject):
        s = subject
        for pattern_thing in self.pattern_things:
            (s,n) = pattern_thing.reo.subn(pattern_thing.repl, s)
            pattern_thing.counter += n
        return s

    def report_all(self):
        print >> sys.stderr
        for pattern_thing in self.pattern_things:
            print >> sys.stderr, '    %5d %s' % (pattern_thing.counter, maybe_elide(pattern_thing.pattern))

    def report_unused(self):
        print >> sys.stderr
        for pattern_thing in self.pattern_things:
            if pattern_thing.counter == 0:
                print >> sys.stderr, '    ' + maybe_elide(pattern_thing.pattern)

def maybe_elide(s):
    if len(s) > 220:
        return s[:100] + '[...]' + s[-100:]
    else:
        return s

# ------------------------------------------------------------------------------

class LexerConverter:

    def __init__(self, pattern_repls, nomatch_repl):
        self.pattern_things = [
            PatternThing(pattern, repl)
            for (pattern, repl) in pattern_repls
        ]
        self.nomatch_repl = nomatch_repl

    def process(self, subject):
        # Perform a lexical analysis of `subject`,
        # based on the token-definitions passed to the constructor.
        # That is, do a single left-to-right pass over `subject`,
        # recognizing tokens.

        # There are two reasonable approaches for dealing with
        # the potential of multiple matches:
        # (a) first match wins.
        # (b) longest match wins.
        # I'm going to try (a) for now, since it's simpler to code + understand.

        replacements = []
        posn = 0
        while posn < len(subject):
            for pattern_thing in self.pattern_things:
                mo = pattern_thing.reo.match(subject, posn)
                if mo:
                    if callable(pattern_thing.repl):
                        replacement = pattern_thing.repl(mo)
                    else:
                        replacement = mo.expand(pattern_thing.repl)
                    replacements.append(replacement)
                    posn = mo.end()
                    break
            else:
                print >> sys.stderr, "no match:", subject[0:posn] + '!!!' + subject[posn:]
                replacements.append( self.nomatch_repl.replace(r'\1', subject[posn:]) )
                break

        return ''.join(replacements)

# ------------------------------------------------------------------------------

class PatternThing:
    def __init__(self, pattern, repl):
        self.pattern = pattern
        self.repl = repl
        self.reo = re.compile(pattern)
        self.counter = 0

# XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX

def handle_emu_see_also_para(node):
    op = node.getAttribute('op')
    si = node.parentNode._section_info
    assert si.kind == 'production_based_operation'
    assert op == si.kind_stuff['op_name']

    put('<p>See also: ')
    put(', '.join([
        '<a href="#%s">%s</a>' % (also_si.id, also_si.dotnum)
        for also_si in see_also_info[op]
        if also_si.id != si.id
    ]))
    put('.</p>')

# XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX

grammar_converter = LexerConverter(
    [
        # units that start with a letter:
        (r'(but only if the integer value of) (DecimalEscape) (is &lt;=) _(NCapturingParens)_',
            r'\1 <span class="nt">\2</span> \3 <var>\4</var>'),
        (r'(but only if) (ClassEscape) (evaluates to a CharSet with exactly one character)',
            r'\1 <span class="nt">\2</span> \3'),
        (r'(U\+0000 through U\+001F)', r'<span class="gprose">\1</span>'),
        (r'(but not one of)',          r'<span class="grhsmod">\1</span>'),
        (r'(but not)',                 r'<span class="grhsmod">\1</span>'),
        (r'(one of)',                  r'<span class="grhsmod">\1</span>'),
        (r'(or)',                      r'<span class="grhsmod">\1</span>'),
        (r'(\w+|@)',                   r'<span class="nt">\1</span>'),

        # units that start with a left-square-bracket:
        (r'\[lookahead != (&lt;[A-Z]+&gt;) \]',
            r'<span class="grhsannot">[lookahead &ne; \1 ]</span>'),
        (r'\[lookahead != `([^ `]+)` \]',
            r'<span class="grhsannot">[lookahead &ne; <code class="t">\1</code> ]</span>'),
        (r'\[lookahead &lt;! (\w+)\]',
            r'<span class="grhsannot">[lookahead &notin; <span class="nt">\1</span>]</span>'),
        (r'\[lookahead &lt;! {(.+?)}\]',
            lambda mo: (
                    r'<span class="grhsannot">[lookahead &notin; {'
                    + re.sub('`([^`]+)`', r'<code class="t">\1</code>', mo.group(1))
                    + '}]</span>'
                )
        ),
        (r'(\[match only if the SV of) (Hex4Digits) (is .*?\])',
            r'<span class="grhsannot">\1 <span class="nt">\2</span> \3</span>'),
        (r'\[no (LineTerminator) here\]',
            r'<span class="grhsannot">[no <span class="nt">\1</span> here]</span>'),
        #
        (r'(\[empty\])',               r'<span class="grhsannot">\1</span>'),
        (r'(\[[+~]\w+\])',             r'<span class="grhsannot">\1</span>'),
        (r'(\[[\w, ?]+\])',            r'<sub class="g-params">\1</sub>'),

        # other units:
        (r'(:+)',                      r'<span class="geq">\1</span>'),
        (r'`([^` ]+|`)`',              r'<code class="t">\1</code>'),
        (r'(\?)',                      r'<sub class="g-opt">opt</sub>'),
        (r'&gt; +(.+)',                r'<span class="gprose">\1</span>'),
        (r'(&lt;[A-Z]+&gt;)',          r'\1'),

        # whitespace:
        (r'( +)',                      r'\1'),
    ],
    r'<GRAMMAR-LEX-ERROR>\1</GRAMMAR-LEX-ERROR>'
)

annex_a = {}
for grammar_summary_part in [
    'lexical-grammar',
    'expressions',
    'statements',
    'functions-and-classes',
    'scripts-and-modules',
    'number-conversions',
    'universal-resource-identifier-character-classes',
    'regular-expressions',
]:
    annex_a[grammar_summary_part] = cStringIO.StringIO()

def handle_emu_grammar_node(emu_grammar):
    assert emu_grammar.nodeName == 'emu-grammar'
    body_xml = toxml_content(emu_grammar)

    grammar_summary_part = emu_grammar.getUserData('grammar_summary_part')

    if '\n' not in body_xml:
        # one single-line production

        assert not grammar_summary_part

        s = grammar_converter.process(body_xml)

        pn = emu_grammar.parentNode.nodeName
        if pn in ['emu-clause', 'emu-annex']:
            indent = emu_grammar.previousSibling.nodeValue
            put('<div class="gp prod">')
            put(indent + '  ' + s)
            put(indent + '</div>')
        elif pn in ['p', 'li']:
            put('<span_prod>') # XXX RECONSTRUCTING
            put(s)
            put('</span_prod>')
        else:
            assert 0, pn

    else:
        # A set of one or more productions

        outer_indent = re.search(r'\n *$', body_xml).group(0)

        body_xml = re.sub(r'^\n+', '', body_xml)
        body_xml = re.sub(r'\s+$', '', body_xml)

        production_texts = re.split(r'\n{2,}', body_xml)

        for (i,prodn_text) in enumerate(production_texts):

            lines = prodn_text.split('\n')

            line_tuples = [
                re.match(r'^( *)(.+)$', line).groups()
                for line in lines
            ]

            if len(lines) == 1:
                # single-line production
                div_class = "gp prod"
                [(_, body)] = line_tuples
                olines = ['  ' + grammar_converter.process(body)]

            else:
                # multi-line production

                # Second and subsequent lines must be indented
                div_class = "gp"
                lhs_indent = line_tuples[0][0]
                rhs_indent = line_tuples[1][0]
                assert rhs_indent.startswith(lhs_indent)
                assert len(rhs_indent) > len(lhs_indent)
                for (r_indent, _) in line_tuples[1:]:
                    assert r_indent == rhs_indent
                # now forget those indents.

                olines = []
                for (j, (_, body)) in enumerate(line_tuples):
                    cls = "lhs" if j == 0 else "rhs"
                    olines.append('  <div class="%s">' % cls)

                    if len(body) < 150:
                        olines.append('    ' + grammar_converter.process(body))

                    elif len(body) > 265:
                        # RECONSTRUCTING
                        assert re.match(r'^`[^` ]+`( `[^` ]+`)+$', body)
                        terminals = body.split(' ')
                        if len(terminals) == 33:
                            # 11.6.2.1 Keyword
                            n_per_row = 4
                            blanks = [27,31,35,39]
                        elif len(terminals) == 47:
                            # 11.7 Punctuator
                            n_per_row = 6
                            blanks = [17]
                        else:
                            assert 0, len(terminals)

                        for t in blanks:
                            terminals.insert(t, '')

                        t = 0
                        olines.append('    <table class="lightweight-table">')
                        olines.append('     <tbody>')
                        while True:
                            olines.append('      <tr>')
                            for c in range(n_per_row):
                                olines.append('        <td>')
                                olines.append('          ' + re.sub(r'^`(.+)`$', r'<code>\1</code>', terminals[t]))
                                olines.append('        </td>')
                                t += 1
                                if t == len(terminals):
                                    break
                            olines.append('      </tr>')
                            if t >= len(terminals) - 1 :
                                break
                        olines.append('     </tbody>')
                        olines.append('    </table>')

                    else:
                        assert 0, body

                    olines.append('  </div>')

            if i > 0: put(outer_indent)
            put('<div class="%s">' % div_class)
            for oline in olines:
                put(outer_indent + oline)
            put(outer_indent + '</div>')

            if grammar_summary_part:
                si = emu_grammar.parentNode._section_info
                extra = 'clause ' if si.level == 1 else ''
                def annex_put(line):
                    annex_a[grammar_summary_part].write('\n        ' + line)
                annex_put('<div class="%s">' % div_class)
                annex_put('  <div class="gsumxref">')
                annex_put('    <a href="#%s">See %s%s</a>' % (si.id, extra, si.dotnum))
                annex_put('  </div>')
                for oline in olines:
                    annex_put(oline)
                annex_put('</div>')

# XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX

def handle_emu_alg(emu_alg):
    assert emu_alg.nodeName == 'emu-alg'
    body_xml = toxml_content(emu_alg)

    assert '\n\n' not in body_xml

    body_xml = re.sub(r'^\n+', '', body_xml)
    body_xml = re.sub(r'\s+$', '', body_xml)

    assert body_xml != ''

    lines = body_xml.split('\n')
    line_tuples = [
        # split each line into indentation, optional label, and body.
        re.match(r'([ \t]*)(?:(\d+\.|\*) )?(.*)$', line).groups()
        for line in lines
    ]

    def do_list(start_i, end_i):
        # The list that spans lines[start_i:end_i]
        # (i.e., not including lines[end_i])

        assert start_i < end_i

        (start_item_indent, start_item_label, start_item_body) = line_tuples[start_i]

        assert start_item_label is not None
        if start_item_label == '*':
            list_type = 'ul'
            list_attrs = ''
        else:
            assert start_item_label.endswith('.')
            start_item_label = start_item_label[:-1]
            assert start_item_label.isdigit()

            list_type = 'ol'

            if start_i == 0:
                list_attrs = ' class="proc"'
                if emu_alg.hasAttribute('type'):
                    list_attrs += ' type="%s"' % emu_alg.getAttribute('type')
            else:
                prev_body = line_tuples[start_i-1][2]
                if appears_to_introduce_a_nested_proc(prev_body):
                    list_attrs = ' class="nested proc"'
                else:
                    list_attrs = ' class="block"'
                
            if start_item_label != '1':
                if start_i == 0:
                    list_attrs += ' start="%s"' % start_item_label
                else:
                    assert 0 # or just ignore it

        if start_item_indent.endswith('  '):
            # XXX RECONSTRUCTING: Just to reconstruct original indenting
            list_indent = start_item_indent[:-2]
        else:
            list_indent = start_item_indent

        list_starter = '%s<%s%s>' % (
            ('' if start_i == 0 else '\n' + list_indent), # because the <emu-alg> tag was indented
            list_type,
            list_attrs
        )
        list_ender = '%s</%s>' % ( '\n' + list_indent, list_type )

        # We're interested in the items of this list.
        # i.e., the items that *directly* belong to this list.
        # i.e., the items that are siblings of the list's first item.
        # Find the index of the first line of each of those items.
        item_first_line_indexes = []

        for i in range(start_i, end_i):
            (indent, label, body) = line_tuples[i]
            if indent == start_item_indent:
                # This line is indented the same as the starter.
                # So it should be an item at the same level.
                if label is None:
                    assert 0
                elif label == '*':
                    assert list_type == 'ul'
                else:
                    assert list_type == 'ol'

                item_first_line_indexes.append(i)

            elif indent.startswith(start_item_indent):
                # This line is indented farther than the starter.
                # So it's an item in a sub-list
                # OR it might be a continuation line.
                pass

            else:
                print >> sys.stderr, 'inconsistent indentation:'
                print >> sys.stderr, '  ' + repr(lines[start_i])
                print >> sys.stderr, '  ' + repr(lines[i])
                assert 0 

        assert item_first_line_indexes[0] == start_i

        put(list_starter)
        for (item_start_i, item_end_i) in zip(item_first_line_indexes, item_first_line_indexes[1:] + [end_i]):
            # An item of the list spans lines[item_start_i:item_end_i]

            put('\n' + start_item_indent + '<li>')

            for i in range(item_start_i, item_end_i):
                (indent, label, body) = line_tuples[i]

                rest_expanded = add_xlinks(expand_ecmarkdown(expand_emu_grammar_text(body)))
                # XXX But what if 'body' contains a <code> or <pre> element?
                # We shouldn't apply emd-expansion within that element.
                # (There are currently 6 such cases, but they don't contain
                # any text that expand_ecmarkdown() could mistakenly expand.)

                if i == item_start_i:
                    assert indent == start_item_indent
                    assert label is not None
                    put('\n' + indent + '  ' + rest_expanded)
                else:
                    assert indent != start_item_indent
                    assert indent.startswith(start_item_indent)
                    if label is None:
                        # This is a continuation line.
                        put('\n' + indent + '  ' + rest_expanded)
                    else:
                        # This is the start of a sublist
                        do_list(i, item_end_i)
                        break

            put('\n' + start_item_indent + '</li>')
        put(list_ender)

    do_list(0, len(lines))

def appears_to_introduce_a_nested_proc(body):
    return (
        re.search(r'^(Return|Create) an internal( \w+)? closure .+ and performs the following steps', body)
        or
        re.search(r'such that when evaluation is resumed .+ the following steps will be performed:$', body)
        or
        re.search(r'perform the following steps in place of', body)
    )

# ----------------------

def expand_emu_grammar_text(s):
    return re.sub(
        r'<emu-grammar>(.+?)</emu-grammar>',
        lambda mo: (
            '<span_prod>'
            + grammar_converter.process(mo.group(1))
            + '</span_prod>'
        ),
        s
    )

# XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX

def handle_emu_eqn(emu_eqn):
    assert emu_eqn.nodeName == 'emu-eqn'

    ps = emu_eqn.previousSibling
    assert ps.nodeType == ps.TEXT_NODE
    outer_indent = ps.nodeValue

    body_xml = toxml_content(emu_eqn)
    s = body_xml.rstrip()
    s = re.sub(r'(\n +)', outer_indent + r'  <br/>\1', s)
    s = add_xlinks(expand_ecmarkdown(s))

    put('<p class="normalBullet">')
    put(s)
    put('</p>')

# XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX

def handle_emu_table(emu_table):
    assert emu_table.nodeName == 'emu-table'

    ps = emu_table.previousSibling
    assert ps.nodeType == ps.TEXT_NODE
    outer_indent = ps.nodeValue

    id = emu_table.getAttribute('id')
    table_number = id.replace('table-', '')
    caption = emu_table.getAttribute('caption')
    maybe_informative = ' (Informative)' if emu_table.hasAttribute('informative') else ''

    put('<figure>')
    put(outer_indent + '  <figcaption>')
    put(outer_indent + '    <span id="%s">Table %s</span>%s &mdash; %s' % (
        id, table_number, maybe_informative, expand_ecmarkdown(caption)))
    put(outer_indent + '  </figcaption>')
    put(outer_indent + '  ')

    assert len(emu_table.childNodes) == 3
    [ws1, table, ws2] = emu_table.childNodes
    assert is_whitespace_text_node(ws1)
    assert is_whitespace_text_node(ws2)

    table.setAttribute('class', 'real-table')
    serialize(table, True)

    put(outer_indent + '</figure>')

# XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX

def handle_emu_figure(emu_figure):
    assert emu_figure.nodeName == 'emu-figure'

    ps = emu_figure.previousSibling
    assert ps.nodeType == ps.TEXT_NODE
    outer_indent = ps.nodeValue

    id = emu_figure.getAttribute('id')
    figure_number = id.replace('figure-', '')
    caption = emu_figure.getAttribute('caption')
    maybe_informative = ' (informative)' if emu_figure.hasAttribute('informative') else ''

    put('<figure>')
    put(outer_indent + '  ')

    assert len(emu_figure.childNodes) == 3
    [ws1, img_or_object, ws2] = emu_figure.childNodes
    assert is_whitespace_text_node(ws1)
    assert is_whitespace_text_node(ws2)
    serialize(img_or_object, True)

    put(outer_indent + '  <figcaption>')
    put(outer_indent + '    Figure %s%s &mdash; %s' % (
        figure_number, maybe_informative, expand_ecmarkdown(caption)))
    put(outer_indent + '  </figcaption>')
    put(outer_indent + '</figure>')

def is_whitespace_text_node(node):
    return (
        node.nodeType == node.TEXT_NODE
        and
        re.match(r'^\s+$', node.nodeValue)
    )

# XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX

def expand_ecmarkdown(s):
    # if '<code>' in s or '<pre>' in s: print s
    return emd_converter.process(s)

emd_converter = LexerConverter([
        (r'\*(\w+|[+-](0|&infin;)|(positive|negative) (zero|Infinity))\*',   r'<span class="value">\1</span>'),
        (r'\b_([A-Za-z0-9]+)_',        r'<var>\1</var>'),
        (r'~(\w+|\[empty\])~',  r'<span class="specvalue">\1</span>'),

        (r'\|(\w+)(\[[^][]+\])\|', r'<span class="nt">\1</span><sub>\2</sub>'),
        (r'\|(\w+)_opt\|',         r'<span class="nt">\1</span><sub>opt</sub>'),
        (r'\|(\w+)\|',             r'<span class="nt">\1</span>'),

        (r'(<[^<>]+>)',         r'\1'),
        (r'`([^`]+)`',          r'<code>\1</code>'),
        (r'\\([\\*_~`|])',      r'\1'),
        (r'''(?x)
            (
                (
                    (?<![\w;]) \* (?![\w&+-])
                |
                    (?<!\w)    \| (?!\w)
                |
                    \B _ | \b __
                |
                    \\ [^\\*_~`|]
                |
                    [^_~|*<>`\\]
                |
                    \n
                )
                +
            )''', r'\1'),
    ],
    r'<EMD-LEX-ERROR>\1</EMD-LEX-ERROR>'
)

# XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX
# xlinks = cross-links = cross-references for which we generate hyperlinks
#
# Think of this as a separate module that exports:
#     prep_for_add_xlinks()
#     current_section_id (as a settable variable)
#     add_xlinks()
#     convert_emu_internal_ref()

def prep_for_add_xlinks(si):

    if si.node.hasAttribute('aoid'):
        section_is_target_for(si.id, si.node.getAttribute('aoid'))

    elif si.kind == 'function_property':
        if 'property_fullname' in si.kind_stuff:
            fullname = si.kind_stuff['property_fullname']
            if '.' in fullname and '%.' not in fullname:
                section_is_target_for(si.id, fullname)

    elif si.kind.endswith('_rec_method'):
        method_name = si.kind_stuff['method_name']
        if n_defns_for_rec_method[method_name] == 1:
            section_is_target_for(si.id, method_name)

    for si_child in si.children: 
        prep_for_add_xlinks(si_child)

    # ----------------------------------

    if si.nodeName == 'body':
        for emu_eqn in si.node.getElementsByTagName('emu-eqn'):
            aoid = emu_eqn.getAttribute('aoid')
            section = get_enclosing_section(emu_eqn)
            id = section.getAttribute('id')
            section_is_target_for(id, aoid)

        for dfn in si.node.getElementsByTagName('dfn'):
            assert dfn.nodeType == dfn.ELEMENT_NODE
            assert len(dfn.childNodes) == 1
            [text] = dfn.childNodes
            assert text.nodeType == text.TEXT_NODE
            term = text.nodeValue
            section = get_enclosing_section(dfn)
            id = section.getAttribute('id')
            section_is_target_for(id, term)

        for (id, term) in ad_hoc_xlink_info:
            section_is_target_for(id, term)

        bake_xlinks_stuff()

ad_hoc_xlink_info = [

    # 5.1.1 Context-Free Grammars
    ('sec-context-free-grammars', 'chain productions'),

    # 5.2 Algorithm Conventions
    ('sec-algorithm-conventions', 'abs'),
    ('sec-algorithm-conventions', 'floor'),
    ('sec-algorithm-conventions', 'modulo'),
    ('sec-algorithm-conventions', 'Assert'),

    # 6.1 ECMAScript Language Types
    ('sec-ecmascript-language-types', 'ECMAScript language values'),

    # 6.1.7 The Object Type
    ('sec-object-type', 'property key value'),
    ('sec-object-type', 'property key'),

    # 6.1.7.2 Object Internal Methods and Internal Slots
    ('sec-object-internal-methods-and-internal-slots', 'internal slot'),

    # 6.2.2 The Completion Record Specification Type
    ('sec-completion-record-specification-type', 'Completion Record'),

    # 6.2.3 The Reference Specification Type
    ('sec-reference-specification-type', 'GetBase'),
    ('sec-reference-specification-type', 'GetReferencedName'),
    ('sec-reference-specification-type', 'HasPrimitiveBase'),
    ('sec-reference-specification-type', 'IsPropertyReference'),
    ('sec-reference-specification-type', 'IsStrictReference'),
    ('sec-reference-specification-type', 'IsSuperReference'),
    ('sec-reference-specification-type', 'IsUnresolvableReference'),
    ('sec-reference-specification-type', 'unresolvable Reference'),

    # 7.2.9 SameValue(x, y)
    ('sec-samevalue', 'the SameValue Algorithm'),
    ('sec-samevalue', 'the SameValue algorithm'),

    # 8.1 Lexical Environments
    ('sec-lexical-environments', 'lexical environment'),
    ('sec-lexical-environments', 'outer environment reference'),
    ('sec-lexical-environments', 'outer lexical environment reference'),

    # 8.1.1.1 Declarative Environment Records
    ('sec-declarative-environment-records', 'Declarative Environment Record'),

    # 8.1.1.2 Object Environment Records
    ('sec-object-environment-records', 'Object Environment Record'),

    # 8.1.1.3 Function Environment Records
    ('sec-function-environment-records', 'Function Environment Records'),

    # 8.1.1.4 Global Environment Records
    ('sec-global-environment-records', 'Global Environment Records'),
    ('sec-global-environment-records', 'the global environment'),

    # 8.2 Code Realms
    ('sec-code-realms', 'Code Realm'),

    # 8.3 Execution Contexts
    ('sec-execution-contexts', 'ECMAScript code execution context'),
    ('sec-execution-contexts', 'LexicalEnvironment'),
    ('sec-execution-contexts', 'Suspend'),
    ('sec-execution-contexts', 'VariableEnvironment'),
    ('sec-execution-contexts', 'execution context stack'),
    ('sec-execution-contexts', 'suspended'),
    ('sec-execution-contexts', 'the currently running execution context'),
    ('sec-execution-contexts', 'the execution context stack'),
    ('sec-execution-contexts', 'the running execution context'),

    # 9.2 ECMAScript Function Objects
    ('sec-ecmascript-function-objects', 'ECMAScript Function object'),
    ('sec-ecmascript-function-objects', 'ECMAScript function object'),

    # 9.4.1 Bound Function Exotic Objects
    ('sec-bound-function-exotic-objects', 'Bound Function'),
    ('sec-bound-function-exotic-objects', '[[BoundTargetFunction]]'),
    ('sec-bound-function-exotic-objects', '[[BoundArguments]]'),
    ('sec-bound-function-exotic-objects', '[[BoundThis]]'),

    # 9.4.2 Array Exotic Objects
    ('sec-array-exotic-objects', 'Array exotic object'),

    # 9.4.3 String Exotic Objects
    ('sec-string-exotic-objects', 'String exotic object'),

    # 10.2.1 Strict Mode Code
    ('sec-strict-mode-code', 'strict code'),

    # 11.9 Automatic Semicolon Insertion
    ('sec-automatic-semicolon-insertion', 'automatic semicolon insertion'),

    # 18.3.8 Float32Array ( . . . )
    ('sec-float32array', 'Float32Array'),

    # 18.3.9 Float64Array ( . . . )
    ('sec-float64array', 'Float64Array'),

    # 18.3.11 Int8Array ( . . . )
    ('sec-int8array', 'Int8Array'),

    # 18.3.12 Int16Array ( . . . )
    ('sec-int16array', 'Int16Array'),

    # 18.3.13 Int32Array ( . . . )
    ('sec-int32array', 'Int32Array'),

    # 18.3.27 Uint8Array ( . . . )
    ('sec-uint8array', 'Uint8Array'),

    # 18.3.28 Uint8ClampedArray ( . . . )
    ('sec-uint8clampedarray', 'Uint8ClampedArray'),

    # 18.3.29 Uint16Array ( . . . )
    ('sec-uint16array', 'Uint16Array'),

    # 18.3.30 Uint32Array ( . . . )
    ('sec-uint32array', 'Uint32Array'),

    # 18.3.31 URIError ( . . . )
    ('sec-constructor-properties-of-the-global-object-urierror', 'URIError'),

    # 20.3.1.8 Daylight Saving Time Adjustment
    ('sec-daylight-saving-time-adjustment', 'DaylightSavingTA'),

    # 21.2.4.1 RegExp.prototype
    ('sec-regexp.prototype', 'RegExp.prototype'),

    # 23.3.2.1 WeakMap.prototype
    ('sec-weakmap.prototype', 'WeakMap.prototype'),

    # 23.4.2.1 WeakSet.prototype
    ('sec-weakset.prototype', 'WeakSet.prototype'),

    # 24.1.3.2 ArrayBuffer.prototype
    ('sec-arraybuffer.prototype', 'ArrayBuffer.prototype'),

    # 24.2.3.1 DataView.prototype
    ('sec-dataview.prototype', 'DataView.prototype'),

    # 25.2.2.2 GeneratorFunction.prototype
    ('sec-generatorfunction.prototype', 'GeneratorFunction.prototype'),

    # 25.4.1.5.1 GetCapabilitiesExecutor Functions
    ('sec-getcapabilitiesexecutor-functions', 'GetCapabilitiesExecutor Functions'),

]

target_id_for_term_ = {}
terms_before_left_paren = []
phrase_terms = []
other_terms = []

def section_is_target_for(id, term):

    if term in ['Call', 'Set', 'Type', 'UTC']:
        # These are the names of abstract operations, but they're also
        # words that the spec uses with their normal English meaning.
        # E.g.:
        #    Set the value of the property ...
        #    The Type of the return value ...
        #    Call <i>envRec</i>.InitializeBinding(...)
        #    ... milliseconds since 01 January, 1970 UTC.
        # So we want to recognize them (and create a link)
        # when they occur immediately before a left-paren,
        # but not otherwise.
        terms_before_left_paren.append(term)
        # regex = r'\b%s(?= *\(' % term 

    elif term in [
        'Abstract Equality Comparison',
        'Strict Equality Comparison',
        'Abstract Relational Comparison',
        'NextJob',
    ]:
        # These terms wouldn't cause false matches per se,
        # but they are terms that, for whatever reason, the ES6 spec didn't link.
        # So, when RECONSTRUCTING, we don't link them either.
        return

    elif re.match(r'^\w+([. /]\w+)*$', term):
        # (a series of one or more words, separated by dots or spaces or slashes)
        # The assumption is that we should only recognize+linkify this phrase
        # when it starts and ends at word-boundaries.
        phrase_terms.append(re.escape(term))

    elif re.match(r'^(%\w+%|\[\[\w+\]\])$', term):
        # Such terms don't start and end at word-boundaries.
        other_terms.append(re.escape(term))

    else:
        print "  warning, skipping term '%s'" % term
        return

    if term in target_id_for_term_:
        print >> sys.stderr, "warning: target_id_for_term_ already has entry for '%s' (%s)" % (term, target_id_for_term_[term])
        assert id == target_id_for_term_[term]
    target_id_for_term_[term] = id


current_section_id = None

def term_repl(mo):
    term = mo.group(0)
    linkid = target_id_for_term_.get(term, None)

    if term == 'Set' and 'Coded Character Set (UCS)' in mo.string:
        return term
        # Kludgey, but not sure how else to do it.

    if linkid and linkid != current_section_id:
        return '<a href="#%s">%s</a>' % (linkid, term)
    else:
        return term

def bake_xlinks_stuff():

    phrase_terms_re = r'\b(%s)\b(?!\]\]|%%|\.\w)' % '|'.join(sorted(phrase_terms, key=lambda t: -len(t)))

    term_before_paren_re = r'\b(%s)(?= *\()' % '|'.join(terms_before_left_paren)

    other_terms_re = '|'.join(other_terms)

    term_re = '|'.join([phrase_terms_re, term_before_paren_re, other_terms_re])

    global xlinks_multisub
    xlinks_multisub = MultiSub([
        (r'<emu-internal-ref refid="([^"]+)">([^<>]+)</emu-internal-ref>',
            lambda mo: convert_emu_internal_ref(mo.group(1), mo.group(2))),

        # 21.1.3.12:
        (r'<emu-external-ref href="([^"]+)" linktext="URL"/>',
            r'<a href="\1">\1</a>'),

        (term_re, term_repl),

    ])
    atexit.register(xlinks_multisub.report_all)

def add_xlinks(s):
    s = xlinks_multisub.apply(s)
    return s

def convert_emu_internal_ref(refid, linktext_template):
    try:
        si = info_for_id_[refid]
        num = si.dotnum
        typ = si.type_for_internal_refs

    except KeyError:
        # XXX
        mo = re.match(r'^(table)-(\d+)$', refid)
        assert mo, refid
        typ = mo.group(1).capitalize()
        num = mo.group(2)

    if linktext_template == 'NUM':
        linktext = num
    elif linktext_template == 'TYPE NUM':
        linktext = typ + ' ' + num
    else:
        assert 0, linktext_template

    return '<a href="#%s">%s</a>' % (refid, linktext)

# XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX

def toxml_content(node):
    assert node.nodeType == node.ELEMENT_NODE
    s = my_toxml(node)
    # strip the outermost tags:
    s = re.sub('(?s)^<[^<>]+>(.*)</[\w-]+>$', r'\1', s)
    return s

def my_toxml(node):
    s = node.toxml()

    # Tweak s so that it's easier to work with,
    # but still denotes the same thing.

    # (1) Change '&quot;' to '"'
    s = s.replace('&quot;', '"')
    # (This would be invalid if '&quot;' appeared in an attribute value
    # that was delimited by double-quotes.)
    # (Alternative would be to hack minidom.py so that
    # _write_data only generates '&quot;' in attribute values.)

    # (2) Change non-ASCII characters to character-references.
    s = encode_nonascii(s)
    # (This would be invalid if any element/attribute names
    # contained non-ASCII chars?)

    return s

def encode_nonascii(s):
    return re.sub(r'[^\n -~]', lambda mo: entitize_char(mo.group(0)), s)

def entitize_char(c):
    return {
        u'\u00a9': '&copy;',
        u'\u00ab': '&laquo;',
        u'\u00bb': '&raquo;',
        u'\u00bd': '&frac12;',
        u'\u00d7': '&times;',
        u'\u00df': '&szlig;',
        u'\u00f7': '&divide;',
        u'\u03c0': '&pi;',
        u'\u200d': '&zwj;',
        u'\u2013': '&ndash;',
        u'\u2014': '&mdash;',
        u'\u2019': '&rsquo;',
        u'\u201c': '&ldquo;',
        u'\u201d': '&rdquo;',
        u'\u2026': '&hellip;',
        u'\u2122': '&trade;',
        u'\u2192': '&rarr;',
        u'\u2209': '&notin;',
        u'\u221e': '&infin;',
        u'\u2260': '&ne;',
        u'\u2264': '&le;',
        u'\u2265': '&ge;',
    }.get(c, '&#x%04x;' % ord(c))

# XXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXXX

def put(s):
    global output_buffer
    output_buffer.write(s)

# ---------------------------------

def getElementsByTagNames(node, names):
    return _get_elements_by_tagNames_helper(node, names, xml.dom.minidom.NodeList())

def _get_elements_by_tagNames_helper(parent, names, rc):
    for node in parent.childNodes:
        if node.nodeType == node.ELEMENT_NODE and node.tagName in names:
            rc.append(node)
        _get_elements_by_tagNames_helper(node, names, rc)
    return rc

# ---------------------------------

main()

# vim: sw=4 ts=4 expandtab
