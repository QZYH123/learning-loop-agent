export const COMMANDS = [
  {
    name: '/组卷',
    aliases: ['/exam', '/quiz'],
    hint: '按要求出蓝图',
    argHint: '写出题要求',
    argsOptional: true,
    needs: null,
    run: 'parseBlueprint',
  },
  {
    name: '/改卷',
    aliases: ['/editexam'],
    hint: '说明怎么改',
    argHint: '请写修改要求',
    needs: 'examOrDraft',
    run: 'proposeExamEdit',
  },
  {
    name: '/文档',
    aliases: ['/doc', '/笔记'],
    hint: '整理成文档',
    argHint: '请写文档主题',
    needs: null,
    run: 'createAiDocument',
  },
  {
    name: '/改文档',
    aliases: ['/editdoc'],
    hint: '说明怎么改',
    argHint: '请写修改要求',
    needs: 'aiDocument',
    run: 'proposeDocEdit',
  },
];

export function matchCommand(text) {
  const match = String(text || '').trim().match(/^(\/\S+)(?:\s+([\s\S]*))?$/);
  if (!match) return null;
  const token = match[1];
  const args = (match[2] || '').trim();
  for (const def of COMMANDS) {
    if (def.name === token || def.aliases.includes(token)) {
      if (!args && !def.argsOptional) return { def, args: '', missingArgs: true };
      return { def, args };
    }
  }
  return null;
}

export function prefixMatchCommands(prefix) {
  const items = [];
  const seen = new Set();
  for (const def of COMMANDS) {
    for (const name of [def.name, ...def.aliases]) {
      if (!name.startsWith(prefix) || seen.has(def.name)) continue;
      seen.add(def.name);
      items.push({ name, def });
    }
  }
  return items;
}
