export const COMMANDS = [
  {
    name: '/组卷',
    aliases: ['/exam', '/quiz'],
    hint: '按要求生成一份试卷蓝图',
    needs: null,
    run: 'parseBlueprint',
  },
  {
    name: '/改卷',
    aliases: ['/editexam'],
    hint: '修改当前试卷',
    needs: 'exam',
    run: 'proposeExamEdit',
  },
  {
    name: '/文档',
    aliases: ['/doc', '/笔记'],
    hint: '把要求整理成 AI 文档',
    needs: null,
    run: 'createAiDocument',
  },
  {
    name: '/改文档',
    aliases: ['/editdoc'],
    hint: '修改当前 AI 文档',
    needs: 'aiDocument',
    run: 'proposeDocEdit',
  },
];

export function matchCommand(text) {
  const match = String(text || '').match(/^(\/\S+)\s+(.+)$/s);
  if (!match) return null;
  const token = match[1];
  const args = match[2].trim();
  if (!args) return null;
  for (const def of COMMANDS) {
    if (def.name === token || def.aliases.includes(token)) {
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
