export const COMMANDS = [
  {
    name: '/组卷',
    aliases: ['/exam', '/quiz'],
    hint: '不写题型也行，例如：出一套简单计网小测',
    argHint: '也可以直接发送 /组卷，右侧会给出默认可改的题型题量',
    argsOptional: true,
    needs: null,
    run: 'parseBlueprint',
  },
  {
    name: '/改卷',
    aliases: ['/editexam'],
    hint: '例如：把第一题改简单一点',
    argHint: '请写修改要求，例如：把判断题改短一点',
    needs: 'examOrDraft',
    run: 'proposeExamEdit',
  },
  {
    name: '/文档',
    aliases: ['/doc', '/笔记'],
    hint: '例如：整理这一章的要点',
    argHint: '请写文档主题，例如：整理这一章的要点',
    needs: null,
    run: 'createAiDocument',
  },
  {
    name: '/改文档',
    aliases: ['/editdoc'],
    hint: '例如：把第二节写短一点',
    argHint: '请写修改要求，例如：把第二节写短一点',
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
