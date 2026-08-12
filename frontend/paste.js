/* 富文本粘贴 → Markdown（面向从语雀/Notion/网页复制的笔记）。
 *
 * 题目、参考答案、关键要点、项目描述这些 textarea 默认粘贴只保留纯文本，
 * 会丢掉颜色、高亮、代码块、表格等结构。这里拦截 paste，读取剪贴板里的
 * text/html，用 Turndown 转成 Markdown 后再插入，保证结构不丢。
 */
(function () {
  "use strict";

  if (typeof window.TurndownService !== "function") return;

  const SAFE_COLOR = /^(#[\da-f]{3,8}|rgba?\([^)]*\)|hsla?\([^)]*\)|[a-z]+)$/i;

  const service = new window.TurndownService({
    headingStyle: "atx",
    codeBlockStyle: "fenced",
    bulletListMarker: "-",
    emDelimiter: "*",
    strongDelimiter: "**",
    hr: "---",
  });

  // GitHub Flavored Markdown 规则：表格 / 任务列表（turndown 核心不含）
  if (window.turndownPluginGfm) {
    service.use(window.turndownPluginGfm.tables);
    service.use(window.turndownPluginGfm.taskListItems);
  }

  // 删除线：gfm 用单 ~，但 markdown-it 需要双 ~~，这里自定义。
  service.addRule("strikethrough", {
    filter: ["del", "s", "strike"],
    replacement(content) {
      return `~~${content}~~`;
    },
  });

  // 语雀/网页的彩色文字：<span style="color:#..."> -> 内联 HTML，渲染器支持着色
  service.addRule("coloredText", {
    filter(node) {
      return node.nodeName === "SPAN" && /color\s*:/i.test(node.getAttribute("style") || "");
    },
    replacement(content, node) {
      const match = (node.getAttribute("style") || "").match(/color\s*:\s*([^;]+)/i);
      if (!match || !SAFE_COLOR.test(match[1].trim())) return content;
      return `<span style="color:${match[1].trim()}">${content}</span>`;
    },
  });

  // 高亮/荧光笔：<mark> 或 background-color -> ==text==（渲染成 <mark>）
  service.addRule("markHighlight", {
    filter(node) {
      return node.nodeName === "MARK" ||
        (node.nodeName === "SPAN" && /background-color\s*:/i.test(node.getAttribute("style") || ""));
    },
    replacement(content) {
      return `==${content}==`;
    },
  });

  // 上标 / 下标 -> 内联 HTML（渲染器白名单允许 sub/sup）
  service.addRule("subscript", {
    filter: "sub",
    replacement(content) { return `<sub>${content}</sub>`; },
  });
  service.addRule("superscript", {
    filter: "sup",
    replacement(content) { return `<sup>${content}</sup>`; },
  });

  function convert(html) {
    return service.turndown(html);
  }

  function insertAtCursor(textarea, text) {
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    textarea.value = textarea.value.slice(0, start) + text + textarea.value.slice(end);
    textarea.selectionStart = textarea.selectionEnd = start + text.length;
    textarea.dispatchEvent(new Event("input", { bubbles: true }));
  }

  function attach(el) {
    if (!el) return;
    el.addEventListener("paste", (event) => {
      const html = event.clipboardData && event.clipboardData.getData("text/html");
      if (!html || !html.trim()) return; // 无富文本时走浏览器默认纯文本粘贴
      event.preventDefault();
      insertAtCursor(el, convert(html));
    });
  }

  window.RichPaste = { convert: convert, attach: attach };
})();
