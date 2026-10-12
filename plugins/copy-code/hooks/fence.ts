// The fence languages Claude Code highlights in a reply, as its resolver in the 2.1.289 binary lists them:
// highlight.js's language ids and aliases (the tables at offsets ~202281323 and ~202284635) and its own cedar
// grammar. A language missing here is fenced as plain text, so a newer Claude Code's extra language loses its
// colours, never shows wrong ones or a second name.
const HIGHLIGHTED = new Set(
  `
  abnf accesslog actionscript ada angelscript apache applescript arcade arduino armasm asciidoc aspectj autohotkey
  autoit avrasm awk axapta bash basic bnf brainfuck c cal capnproto ceylon clean clojure clojure-repl cmake
  coffeescript coq cos cpp crmsh crystal csharp csp css d dart delphi diff django dns dockerfile dos dsconfig dts
  dust ebnf elixir elm erb erlang erlang-repl excel fix flix fortran fsharp gams gauss gcode gherkin glsl go golo
  gradle graphql groovy haml handlebars haskell haxe hsp http hy inform7 ini irpf90 java javascript jboss-cli json
  julia julia-repl kotlin lasso latex ldif leaf less lisp livecodeserver livescript llvm lsl lua makefile markdown
  matlab mel mercury mipsasm mizar mojolicious monkey moonscript n1ql nestedtext nginx nim nix node-repl nsis
  objectivec ocaml openscad oxygene parser3 perl pf pgsql php php-template plaintext pony powershell processing
  profile prolog properties protobuf puppet purebasic python python-repl q qml r reasonml rib roboconf routeros
  rsl ruby ruleslanguage rust sas scala scheme scilab scss shell smali smalltalk sml sql stan stata step21 stylus
  subunit swift taggerscript tap tcl thrift tp twig typescript vala vbnet vbscript vbscript-html verilog vhdl vim
  wasm wren x86asm xl xml xquery yaml zephir as asc apacheconf osascript ino arm adoc ahk x++ sh zsh bf h capnp
  icl dcl clj edn cmake.in coffee cson iced cls cc c++ h++ hpp hh hxx cxx crm pcmk cr cs c# dpr dfm pas pascal
  patch jinja bind zone docker bat cmd dst ex exs erl xlsx xls f90 f95 fs f# gms gss nc feature golang gql hbs
  html.hbs html.handlebars htmlbars hs hx https hylang i7 toml jsp js jsx mjs cjs wildfly-cli jsonc jldoctest kt
  kts ls lassoscript tex pluto mk mak make md mkdown mkd m moo mips moon nt nginxconf nixos mm objc obj-c obj-c++
  objective-c++ ml scad pl pm pf.conf postgres postgresql text txt pwsh ps ps1 pde proto pp pb pbi py gyp ipython
  pycon k kdb qt re graph instances mikrotik rb gemspec podspec thor irb rs scm sci console shellsession st
  stanfuncs do ado p21 step stp styl tk craftcms ts tsx mts cts vb vbs v sv svh tao html xhtml rss atom xjb xsd
  xsl plist wsf svg xpath xq xqm yml zep mysql oracle freepascal lazarus lpr lfm php3 php4 php5 php6 php7 php8
  cedar cedarpolicy
  `
    .trim()
    .split(/\s+/),
)

// The fence that draws `code` as Claude Code draws a reply's code block: the same renderer, so the same colours.
// It is longer than any backtick run in the code, so the code can't close it. Claude Code highlights by the info
// string's leading word (`u=i.match(/^[\w.+#-]+/)`, binary offset ~213293337), so only that word goes. A language
// it can't highlight goes as plaintext, since its fence would print the name dim above the code, repeating the box's.
export function fence(code: string, language?: string): string {
  const ticks = '`'.repeat(Math.max(3, ...(code.match(/`+/g) ?? []).map(run => run.length + 1)))
  const word = language?.match(/^[\w.+#-]+/)?.[0]
  const info =
    language === undefined ? '' : word !== undefined && HIGHLIGHTED.has(word.toLowerCase()) ? word : 'plaintext'
  return `${ticks}${info}\n${code}\n${ticks}`
}
