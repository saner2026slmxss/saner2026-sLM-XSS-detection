#!/usr/bin/env node
// tools/pdg/build_pdg.js — improved
// Usage: node build_pdg.js <input.js> > <output.pdg.json>
// deps: npm i esprima estraverse

const fs = require('fs');
const esprima = require('esprima-next');
const estraverse = require('estraverse');
const MAX_NODES = 20000;
const MAX_EDGES = 50000;
const RE_BLOCK = /\/\*[\s\S]*?\*\//g;
const RE_LINE  = /(^|[^:])\/\/(?!\/).*$/gm;

if (process.argv.length < 3) {
  console.error('Usage: node build_pdg.js <input.js>');
  process.exit(1);
}

function stripCommentsText(s){
  return s.replace(RE_BLOCK, '').replace(RE_LINE, '$1');
}

let ORIG = fs.readFileSync(process.argv[2], 'utf8');

if (ORIG.startsWith('#!')) {
  const newlineIndex = ORIG.indexOf('\n');
  if (newlineIndex !== -1) {
    ORIG = ORIG.substring(newlineIndex + 1);
  } else {
    ORIG = '';
  }
}

function makeParseable(code){
  const SEP = new Set([';','}']);
  const out=[], map=[];
  for (let i=0;i<code.length;i++){
    const ch=code[i];
    out.push(ch); map.push(i);
    if (SEP.has(ch) && code[i+1] !== '\n'){ out.push('\n'); map.push(i); }
  }
  return {parseCode: out.join(''), map};
}
const {parseCode: CODE, map: MAP} = makeParseable(ORIG);

let AST;
try {
  AST = esprima.parseScript(CODE, {range:true, tolerant:true, comment:true, loc:true});
} catch(e) {
  AST = esprima.parseScript(ORIG, {range:true, tolerant:true, comment:true, loc:true});
  for (let i=0;i<ORIG.length;i++) MAP[i]=i;
}

function mapRangeParsedToOrig([sP,eP]){
  const s = Math.max(0, Math.min(sP, MAP.length-1));
  const e = Math.max(0, Math.min(eP-1, MAP.length-1));
  const s0 = MAP[s];
  const e0 = MAP[e] + 1;
  return [s0, e0];
}

let NEXT_ID = 0;
const nodes = []; // {id,type,start,end,snippet,ast_size}
const edges = []; // {src,dst,type,name?}

// AST node -> PDG node id (for statement-level nodes)
const stmtId = new Map();

function snip(start, end) {
  const MAX = 160;
  const raw = ORIG.slice(start, Math.min(end, start + MAX));
  const noCom = stripCommentsText(raw);
  return noCom.replace(/\s+/g, ' ').trim();
}

function addNodeFromAst(astNode, label){
  if (!astNode || !astNode.range) return null;
  if (nodes.length >= MAX_NODES) return null;
  const [start, end] = mapRangeParsedToOrig(astNode.range);
  const id = NEXT_ID++;
  nodes.push({ id, type: label || astNode.type, start, end, snippet: snip(start, end), ast_size: Math.max(0, end - start) });
  return id;
}

function addEdge(src, dst, type, name){
  if (src == null || dst == null) return;
  if (edges.length >= MAX_EDGES) return;
  edges.push(name ? { src, dst, type, name } : { src, dst, type });
}

const scopeStack = [];
function pushScope() { scopeStack.push({ defs: new Map() }); }
function popScope() { scopeStack.pop(); }
function defineVar(name, nodeId) {
  if (!scopeStack.length) pushScope();
  scopeStack[scopeStack.length - 1].defs.set(name, nodeId);
}
function findDef(name) {
  for (let i = scopeStack.length - 1; i >= 0; i--) {
    const hit = scopeStack[i].defs.get(name);
    if (hit != null) return hit;
  }
  return null;
}

function collectDefTargets(node, out) {
  if (!node) return;
  switch (node.type) {
    case 'Identifier':
      out.push(node.name);
      break;
    case 'ArrayPattern':
      for (const el of node.elements) if (el) collectDefTargets(el, out);
      break;
    case 'ObjectPattern':
      for (const p of node.properties) {
        if (p.type === 'Property') collectDefTargets(p.value, out);
        else if (p.type === 'RestElement') collectDefTargets(p.argument, out);
      }
      break;
    case 'AssignmentPattern':
      collectDefTargets(node.left, out);
      break;
  }
}

const _useCache = new WeakMap();
function collectUsesFast(root, cap = 2000) {
  if (!root) return [];
  if (_useCache.has(root)) return _useCache.get(root);
  const skip = new Set(['ArrayExpression','ObjectExpression','Literal','TemplateLiteral','RegExpLiteral']);
  const out = [];
  const st = [root];
  while (st.length) {
    const n = st.pop();
    if (!n || typeof n !== 'object') continue;
    if (n.type === 'Identifier') {
      out.push(n.name);
      if (out.length >= cap) break;
    }
    if (skip.has(n.type)) continue;
    for (const k in n) {
      if (k === 'range' || k === 'loc') continue;
      const v = n[k];
      if (Array.isArray(v)) for (let i=v.length-1;i>=0;i--) st.push(v[i]);
      else if (v && typeof v === 'object') st.push(v);
    }
  }
  _useCache.set(root, out);
  return out;
}

function isStatement(n) {
  return /Statement$/.test(n.type) ||
         n.type === 'FunctionDeclaration' ||
         n.type === 'VariableDeclaration';
}

function listStatements(body) {
  if (!body) return [];
  if (Array.isArray(body)) return body.filter(isStatement);
  if (body.type === 'BlockStatement') return body.body.filter(isStatement);
  return isStatement(body) ? [body] : [];
}

function firstStmtIdIn(node) {
  const stmts = listStatements(node);
  if (!stmts.length) return null;
  return stmtId.get(stmts[0]);
}

const { VisitorOption } = estraverse;
const VO = VisitorOption || estraverse.VisitorOption;

estraverse.traverse(AST, {
  enter(node, parent) {
    if (node.type === 'ArrayExpression' ||
        node.type === 'ObjectExpression' ||
        node.type === 'Literal' ||
        node.type === 'TemplateLiteral' ||
        node.type === 'RegExpLiteral') {
      return VisitorOption.Skip;
    }
    if (isStatement(node)) {
      const id = addNodeFromAst(node, node.type);
      stmtId.set(node, id);
    }
  }
});

estraverse.traverse(AST, {
  enter(node, parent) {
    if (node.type === 'ArrayExpression' ||
        node.type === 'ObjectExpression' ||
        node.type === 'Literal' ||
        node.type === 'TemplateLiteral' ||
        node.type === 'RegExpLiteral') {
      return VisitorOption.Skip;
    }
    if (node.type === 'Program' || node.type === 'FunctionDeclaration' || node.type === 'FunctionExpression' || node.type === 'ArrowFunctionExpression') {
      pushScope();
    }

    if (node.type === 'BlockStatement') {
      const stmts = node.body.filter(isStatement);
      for (let i = 1; i < stmts.length; i++) {
        const prevId = stmtId.get(stmts[i - 1]);
        const curId = stmtId.get(stmts[i]);
        addEdge(prevId, curId, 'control');
      }
    }

    if (node.type === 'IfStatement') {
      const ifId = stmtId.get(node) ?? addNodeFromAst(node, 'IfStatement');
      const cId = firstStmtIdIn(node.consequent);
      const aId = firstStmtIdIn(node.alternate);
      addEdge(ifId, cId, 'control');
      addEdge(ifId, aId, 'control');
    }

    if (/^For(Statement|InStatement|OfStatement)$/.test(node.type) || node.type === 'WhileStatement' || node.type === 'DoWhileStatement') {
      const loopId = stmtId.get(node) ?? addNodeFromAst(node, node.type);
      const bId = firstStmtIdIn(node.body);
      addEdge(loopId, bId, 'control');
    }

    if (node.type === 'VariableDeclaration') {
      const ownerId = stmtId.get(node);
      for (const decl of node.declarations) {
        const targets = [];
        collectDefTargets(decl.id, targets);
        for (const name of targets) defineVar(name, ownerId);
        if (decl.init) {
          const uses = collectUsesFast(decl.init);
          for (const u of uses) {
            const d = findDef(u);
            addEdge(d ?? ownerId, ownerId, 'data', u);
          }
        }
      }
    }

    if (node.type === 'AssignmentExpression') {
      const ownerId = stmtId.get(parent) ?? stmtId.get(node) ?? addNodeFromAst(parent || node, 'AssignOwner');
      const targets = [];
      collectDefTargets(node.left, targets);
      for (const name of targets) defineVar(name, ownerId);
      const uses = collectUsesFast(node.right);
      for (const u of uses) {
        const d = findDef(u);
        addEdge(d ?? ownerId, ownerId, 'data', u);
      }
    }

    if (node.type === 'ExpressionStatement') {
      const ownerId = stmtId.get(node);
      const uses = collectUsesFast(node.expression);
      for (const u of uses) {
        const d = findDef(u);
        addEdge(d ?? ownerId, ownerId, 'data', u);
      }
    }

    if (node.type === 'FunctionDeclaration' ||
        node.type === 'FunctionExpression' ||
        node.type === 'ArrowFunctionExpression') {
      const ownerId = stmtId.get(node) ?? addNodeFromAst(node, node.type);
      for (const p of node.params || []) {
        const targets = [];
        collectDefTargets(p, targets);
        for (const name of targets) defineVar(name, ownerId);
      }
    }
  },
  leave(node, parent) {
    if (node.type === 'Program' || node.type === 'FunctionDeclaration' || node.type === 'FunctionExpression' || node.type === 'ArrowFunctionExpression') {
      popScope();
    }
  }
});

console.log(JSON.stringify({ nodes, edges }, null, 2));
