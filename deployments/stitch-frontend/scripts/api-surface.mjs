import fs from "node:fs";
import path from "node:path";

import { parse } from "@babel/parser";

const SRC = path.resolve(import.meta.dirname, "../src");
const OUT = path.resolve(import.meta.dirname, "../../../docs/stitch-frontend-package.md");
const MAX_VALUE = 80;

const walk = (dir) =>
  fs.readdirSync(dir, { withFileTypes: true }).flatMap((entry) => {
    const full = path.join(dir, entry.name);
    if (entry.isDirectory()) return entry.name === "test" || entry.name === "tests" ? [] : walk(full);
    if (!/\.jsx?$/.test(entry.name) || /\.test\.jsx?$/.test(entry.name)) return [];
    return [full];
  });

const text = (src, node) => src.slice(node.start, node.end).replace(/\s+/g, " ");
const params = (src, fn) => fn.params.map((p) => text(src, p)).join(", ");
const sig = (src, fn, name) => `${fn.async ? "async " : ""}${name}(${params(src, fn)})`;
const clip = (s) => (s.length > MAX_VALUE ? `${s.slice(0, MAX_VALUE)}…` : s);

const value = (src, init) => {
  if (init.type === "ObjectExpression") return "{…}";
  if (init.type === "ArrayExpression") {
    const full = text(src, init);
    return full.length > MAX_VALUE ? "[…]" : full;
  }
  if (init.type === "CallExpression") return `${text(src, init.callee)}(…)`;
  return clip(text(src, init));
};

const fromDeclarator = (src, node) => {
  const { init } = node;
  const name = node.id.name;
  if (init.type === "FunctionExpression" || init.type === "ArrowFunctionExpression") {
    return { line: node.loc.start.line, sig: sig(src, init, name) };
  }
  return { line: node.loc.start.line, sig: `${name} = ${value(src, init)}` };
};

const fromDeclaration = (src, node) => {
  if (node.type === "FunctionDeclaration") {
    return [{ line: node.loc.start.line, sig: sig(src, node, node.id.name) }];
  }
  if (node.type === "VariableDeclaration") return node.declarations.map((d) => fromDeclarator(src, d));
  throw new Error(`unexpected declaration: ${node.type}`);
};

const fromBinding = (src, body, name) => {
  for (const node of body) {
    const decl = node.type === "ExportNamedDeclaration" ? node.declaration : node;
    if (!decl) continue;
    if (decl.type === "FunctionDeclaration" && decl.id.name === name) {
      return { line: decl.loc.start.line, sig: sig(src, decl, name) };
    }
    if (decl.type === "VariableDeclaration") {
      const match = decl.declarations.find((d) => d.id.name === name);
      if (match) return fromDeclarator(src, match);
    }
  }
  throw new Error(`no top-level binding for default export: ${name}`);
};

const members = (src, body) =>
  body.flatMap((node) => {
    if (node.type === "ExportNamedDeclaration") return fromDeclaration(src, node.declaration);
    if (node.type !== "ExportDefaultDeclaration") return [];
    const decl = node.declaration;
    if (decl.type === "Identifier") return [fromBinding(src, body, decl.name)];
    return fromDeclaration(src, decl);
  });

const files = walk(SRC)
  .map((file) => path.relative(SRC, file).split(path.sep).join("/"))
  .sort();

const out = ["# `stitch-frontend`", ""];

for (const rel of files) {
  const src = fs.readFileSync(path.join(SRC, rel), "utf8");
  const ast = parse(src, { sourceType: "module", plugins: ["jsx"] });
  const items = members(src, ast.program.body).sort((a, b) => a.line - b.line);
  if (items.length === 0) continue;
  out.push(`## \`${rel}\``, "");
  for (const item of items) out.push(`- **${item.line}: \`${item.sig}\`**`);
  out.push("");
}

fs.mkdirSync(path.dirname(OUT), { recursive: true });
fs.writeFileSync(OUT, out.join("\n"));
console.log(OUT);
