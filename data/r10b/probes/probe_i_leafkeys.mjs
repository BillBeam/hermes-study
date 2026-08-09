// R10B slice I probe — count authored leaf keys in the desktop i18n language
// packs and in the `Translations` type contract, using the real TypeScript
// parser (no execution, no imports resolved).
//
// Usage:
//   node --experimental-strip-types \
//     /home/user/hermes-study/data/r10b/probes/probe_i_leafkeys.mjs <hermes-agent-root> [--paths <name>]
//
// It needs the `typescript` package. Point NODE_PATH at any checkout that has
// it installed, e.g. the R10B TS copy:
//   NODE_PATH=/home/user/r10b-ts/hermes-agent/node_modules node probe_i_leafkeys.mjs /home/user/hermes-agent
//
// Definitions used:
//   leaf   = a property whose value is NOT an object literal: string,
//            template literal, arrow/function (interpolator), array, number.
//   opaque = a property whose value is a bare identifier imported from
//            elsewhere (e.g. `fieldLabels: FIELD_LABELS`). The parser cannot
//            see inside it; reported separately, never silently counted as 1.
//   call   = `defineFieldCopy({...})` — we recurse into the first object
//            literal argument, so its contents ARE counted as leaves.

import { createRequire } from 'node:module'
import path from 'node:path'
import fs from 'node:fs'

const require = createRequire(import.meta.url)
const ts = require('typescript')

const ROOT = process.argv[2]
if (!ROOT) {
  console.error('usage: probe_i_leafkeys.mjs <hermes-agent-root> [--paths <locale>]')
  process.exit(2)
}
const PATHS_FOR = process.argv.includes('--paths') ? process.argv[process.argv.indexOf('--paths') + 1] : null

const I18N = path.join(ROOT, 'apps/desktop/src/i18n')

// locale file -> exported const name
const PACKS = [
  ['en.ts', 'en'],
  ['zh.ts', 'zh'],
  ['ja.ts', 'ja'],
  ['zh-hant.ts', 'zhHant'],
  ['ar.ts', 'ar']
]

function parse(file) {
  const src = fs.readFileSync(file, 'utf8')
  return ts.createSourceFile(file, src, ts.ScriptTarget.Latest, true, ts.ScriptKind.TS)
}

function propName(node) {
  const n = node.name
  if (!n) return null
  if (ts.isIdentifier(n) || ts.isStringLiteral(n) || ts.isNumericLiteral(n)) return n.text
  return `[computed]`
}

// ---------- language packs (value side) ----------

function walkObject(obj, prefix, out) {
  for (const prop of obj.properties) {
    if (ts.isSpreadAssignment(prop)) {
      out.spreads.push(prefix || '(root)')
      continue
    }
    if (!ts.isPropertyAssignment(prop) && !ts.isShorthandPropertyAssignment(prop)) continue
    const name = propName(prop)
    if (name == null) continue
    const dotted = prefix ? `${prefix}.${name}` : name

    if (ts.isShorthandPropertyAssignment(prop)) {
      out.opaque.push(dotted)
      continue
    }

    let v = prop.initializer
    // unwrap `as const`, satisfies, parens
    while (ts.isAsExpression(v) || ts.isSatisfiesExpression?.(v) || ts.isParenthesizedExpression(v)) {
      v = v.expression
    }

    if (ts.isObjectLiteralExpression(v)) {
      walkObject(v, dotted, out)
    } else if (ts.isCallExpression(v)) {
      const arg = v.arguments.find(a => ts.isObjectLiteralExpression(a))
      if (arg) {
        out.calls.push(`${dotted} <- ${v.expression.getText()}()`)
        walkObject(arg, dotted, out)
      } else {
        out.opaque.push(`${dotted} <- ${v.expression.getText()}()`)
      }
    } else if (ts.isIdentifier(v) || ts.isPropertyAccessExpression(v)) {
      out.opaque.push(`${dotted} <- ${v.getText()}`)
    } else {
      out.leaves.push(dotted)
    }
  }
}

function packRoot(sf, constName) {
  let found = null
  sf.forEachChild(node => {
    if (found) return
    if (!ts.isVariableStatement(node)) return
    for (const decl of node.declarationList.declarations) {
      if (!ts.isIdentifier(decl.name) || decl.name.text !== constName) continue
      let init = decl.initializer
      while (init && (ts.isAsExpression(init) || ts.isParenthesizedExpression(init))) init = init.expression
      if (init && ts.isObjectLiteralExpression(init)) {
        found = { kind: 'literal', obj: init }
      } else if (init && ts.isCallExpression(init)) {
        const arg = init.arguments.find(a => ts.isObjectLiteralExpression(a))
        if (arg) found = { kind: `${init.expression.getText()}()`, obj: arg }
      }
    }
  })
  return found
}

// ---------- types.ts (contract side) ----------

function walkTypeMembers(members, prefix, out) {
  for (const m of members) {
    if (!ts.isPropertySignature(m)) continue
    const name = propName(m)
    if (name == null) continue
    const dotted = prefix ? `${prefix}.${name}` : name
    const t = m.type
    if (t && ts.isTypeLiteralNode(t)) {
      walkTypeMembers(t.members, dotted, out)
    } else {
      out.leaves.push(dotted)
    }
  }
}

function contractLeaves(sf) {
  const out = { leaves: [], opaque: [], calls: [], spreads: [] }
  sf.forEachChild(node => {
    if (ts.isInterfaceDeclaration(node) && node.name.text === 'Translations') {
      walkTypeMembers(node.members, '', out)
    }
    if (ts.isTypeAliasDeclaration(node) && node.name.text === 'Translations' && ts.isTypeLiteralNode(node.type)) {
      walkTypeMembers(node.type.members, '', out)
    }
  })
  return out
}

// ---------- run ----------

// `en.ts` writes `fieldLabels: FIELD_LABELS` / `fieldDescriptions:
// FIELD_DESCRIPTIONS`, importing both from src/app/settings/constants.ts,
// while every translated pack inlines `defineFieldCopy({...})`. Without
// resolving the two imports, en's leaf count is not comparable with the
// others. Parse that file too and graft the two subtrees onto en.
const CONSTANTS = path.join(ROOT, 'apps/desktop/src/app/settings/constants.ts')
function fieldCopyLeaves(constName) {
  const sf = parse(CONSTANTS)
  const root = packRoot(sf, constName)
  const out = { leaves: [], opaque: [], calls: [], spreads: [] }
  if (root) walkObject(root.obj, '', out)
  return out
}

const results = {}
for (const [file, constName] of PACKS) {
  const full = path.join(I18N, file)
  const sf = parse(full)
  const root = packRoot(sf, constName)
  const out = { leaves: [], opaque: [], calls: [], spreads: [] }
  if (!root) {
    console.error(`!! could not locate exported const ${constName} in ${file}`)
  } else {
    walkObject(root.obj, '', out)
  }
  // graft resolved field copy onto en so all five packs are counted alike
  if (file === 'en.ts') {
    const grafted = []
    for (const o of out.opaque) {
      const m = /^settings\.(fieldLabels|fieldDescriptions) <- (FIELD_LABELS|FIELD_DESCRIPTIONS)$/.exec(o)
      if (!m) {
        grafted.push(o)
        continue
      }
      const sub = fieldCopyLeaves(m[2])
      out.leaves.push(...sub.leaves.map(p => `settings.${m[1]}.${p}`))
      out.calls.push(`settings.${m[1]} <- ${m[2]} (resolved from src/app/settings/constants.ts)`)
    }
    out.opaque = grafted
  }
  results[file] = { authoring: root ? root.kind : '??', ...out }
}

const typesSf = parse(path.join(I18N, 'types.ts'))
results['types.ts'] = { authoring: 'interface Translations', ...contractLeaves(typesSf) }

if (PATHS_FOR) {
  const r = results[PATHS_FOR]
  if (!r) {
    console.error(`no such entry: ${PATHS_FOR}`)
    process.exit(2)
  }
  for (const l of r.leaves) console.log(l)
  process.exit(0)
}

console.log('file            authoring        leaves  opaque  call-subtrees  spreads')
for (const [file, r] of Object.entries(results)) {
  console.log(
    `${file.padEnd(15)} ${String(r.authoring).padEnd(16)} ${String(r.leaves.length).padStart(6)}  ${String(r.opaque.length).padStart(6)}  ${String(r.calls.length).padStart(13)}  ${String(r.spreads.length).padStart(7)}`
  )
}

console.log('\n-- opaque (parser cannot see inside; NOT counted as leaves) --')
for (const [file, r] of Object.entries(results)) {
  for (const o of r.opaque) console.log(`${file}: ${o}`)
}
console.log('\n-- call subtrees (recursed into; contents ARE counted) --')
for (const [file, r] of Object.entries(results)) {
  for (const c of r.calls) console.log(`${file}: ${c}`)
}
