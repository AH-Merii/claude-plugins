export const NAMES: Record<string, string> = {
  py: 'python', python3: 'python', py3: 'python',
  js: 'javascript', mjs: 'javascript', cjs: 'javascript',
  ts: 'typescript', mts: 'typescript', cts: 'typescript',
  md: 'markdown', mdx: 'markdown',
  sh: 'shell', shellscript: 'shell', console: 'shell session', 'shell-session': 'shell session',
  ps1: 'powershell', psm1: 'powershell',
  yml: 'yaml',
  rb: 'ruby', rs: 'rust', kt: 'kotlin', kts: 'kotlin', cs: 'c#', fs: 'f#',
  cpp: 'c++', cc: 'c++', cxx: 'c++', hpp: 'c++', h: 'c',
  objc: 'objective-c', hs: 'haskell', ex: 'elixir', exs: 'elixir', erl: 'erlang',
  pl: 'perl', jl: 'julia', clj: 'clojure', ml: 'ocaml', tf: 'terraform', hcl: 'terraform',
  txt: 'text', plaintext: 'text', patch: 'diff', dockerfile: 'docker', containerfile: 'docker',
}

// The full name of a fence's language, as written when it is not an alias.
export function languageName(language: string): string {
  return NAMES[language.toLowerCase()] ?? language
}
