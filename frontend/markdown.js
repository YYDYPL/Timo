/* 参考答案 Markdown 渲染 + 安全净化（无构建、离线可用）。
 *
 * - 用 vendor/markdown-it（MIT）解析标准 Markdown：标题、加粗、斜体、
 *   删除线、行内代码、代码块、列表、表格、引用、链接、分割线、换行。
 * - 开启 html:true 让内联 HTML 生效（如 <span style="color:red"> 着色），
 *   输出再经过白名单净化器，剥离 script / 事件属性 / javascript: 链接等。
 */
(function () {
  "use strict";

  let _markdownit = null;
  try {
    if (typeof window.markdownit === "function") {
      _markdownit = window.markdownit({
        html: true, // 允许内联 HTML（着色用），输出会再过白名单净化
        linkify: false,
        breaks: true, // 单个换行渲染为 <br>
        typographer: false,
      });
    }
  } catch (error) {
    _markdownit = null;
  }

  const ALLOWED_TAGS = new Set([
    "p", "br", "hr", "strong", "em", "b", "i", "s", "del", "u", "mark",
    "sub", "sup", "small", "kbd", "code", "pre",
    "blockquote", "ul", "ol", "li", "dl", "dt", "dd",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "table", "thead", "tbody", "tfoot", "tr", "th", "td", "caption",
    "a", "span", "font", "div",
  ]);
  const ALLOWED_ATTRS = new Set([
    "href", "title", "color", "lang", "class", "style", "align", "start", "value",
  ]);

  function sanitizeStyle(value) {
    // 剥离能向 CSS 夹带脚本的写法，保留 color/背景等普通声明。
    return String(value || "")
      .replace(/url\s*\(/gi, "")
      .replace(/expression\s*\(/gi, "")
      .replace(/@import/gi, "")
      .replace(/(-moz-binding|behavior)\s*:/gi, "");
  }

  function sanitizeHtml(html) {
    const doc = new DOMParser().parseFromString(`<div id="__md_root">${html}</div>`, "text/html");
    const root = doc.getElementById("__md_root");
    if (!root) return "";

    root.querySelectorAll("*").forEach((el) => {
      [...el.attributes].forEach((attr) => {
        const name = attr.name.toLowerCase();
        const value = attr.value || "";
        if (name.startsWith("on") || name === "srcset" || name === "srcdoc" || name === "formaction") {
          el.removeAttribute(attr.name);
          return;
        }
        if (name === "style") {
          el.setAttribute("style", sanitizeStyle(value));
          return;
        }
        if ((name === "href" || name === "src" || name === "xlink:href" || name === "background") &&
            /^\s*(javascript|data|vbscript):/i.test(value)) {
          el.removeAttribute(attr.name);
          return;
        }
        if (!ALLOWED_ATTRS.has(name)) {
          el.removeAttribute(attr.name);
        }
      });
      if (!ALLOWED_TAGS.has(el.tagName.toLowerCase())) {
        // 白名单外的标签：剥掉标签本身，保留其内容。
        const parent = el.parentNode;
        if (parent) {
          while (el.firstChild) parent.insertBefore(el.firstChild, el);
          parent.removeChild(el);
        }
      }
    });

    const walker = root.ownerDocument.createTreeWalker(root, NodeFilter.SHOW_COMMENT, null);
    const comments = [];
    while (walker.nextNode()) comments.push(walker.currentNode);
    comments.forEach((node) => node.remove());

    return root.innerHTML;
  }

  function renderMarkdown(text) {
    const source = String(text ?? "");
    if (!source.trim()) return "";
    if (!_markdownit) return escapeHtmlText(source);
    return sanitizeHtml(_markdownit.render(source));
  }

  function renderInline(text) {
    const source = String(text ?? "").trim();
    if (!source) return "";
    if (!_markdownit) return escapeHtmlText(source);
    // 单行上下文（如题目标题）用行内渲染，避免块级 <p> 嵌套进 <h2> 等元素。
    return sanitizeHtml(_markdownit.renderInline(source));
  }

  function escapeHtmlText(value) {
    return String(value ?? "").replace(/[&<>'"]/g, (char) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
    })[char]);
  }

  window.MarkdownRenderer = { render: renderMarkdown, renderInline: renderInline, sanitize: sanitizeHtml };
})();
