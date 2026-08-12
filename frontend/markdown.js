/* 参考答案 Markdown 渲染 + 安全净化 + 增强渲染（公式/代码高亮/图表）。
 *
 * - vendor/markdown-it（MIT）解析标准 Markdown；markdown-it-mark 支持 ==高亮==。
 * - 开启 html:true 让内联 HTML 生效（如 <span style="color:red"> 着色），输出再过白名单净化。
 * - render() 后再调用 enhance(el) 做：KaTeX 公式、highlight.js 代码高亮、mermaid 图表。
 */
(function () {
  "use strict";

  const _md = (function () {
    if (typeof window.markdownit !== "function") return null;
    const md = window.markdownit({
      html: true, // 允许内联 HTML（着色用），输出会再过白名单净化
      linkify: false,
      breaks: true, // 单个换行渲染为 <br>
      typographer: false,
    });
    if (typeof window.markdownitMark === "function") {
      md.use(window.markdownitMark);
    }
    return md;
  })();

  const ALLOWED_TAGS = new Set([
    "p", "br", "hr", "strong", "em", "b", "i", "s", "del", "u", "mark",
    "sub", "sup", "small", "kbd", "code", "pre",
    "blockquote", "ul", "ol", "li", "dl", "dt", "dd",
    "h1", "h2", "h3", "h4", "h5", "h6",
    "table", "thead", "tbody", "tfoot", "tr", "th", "td", "caption",
    "a", "span", "font", "div", "img", "input",
  ]);
  const ALLOWED_ATTRS = new Set([
    "href", "title", "color", "lang", "class", "style", "align", "start", "value",
    "src", "alt", "width", "height", "type", "checked", "disabled",
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
      const tag = el.tagName.toLowerCase();

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
        if (name === "src" || name === "background" || name === "xlink:href" || name === "href") {
          if (/^\s*(javascript|vbscript):/i.test(value)) {
            el.removeAttribute(attr.name);
            return;
          }
          if (name === "href" && /^\s*data:/i.test(value)) {
            el.removeAttribute(attr.name);
            return;
          }
          if ((name === "src" || name === "background") && /^\s*data:/i.test(value) && !/^\s*data:image\//i.test(value)) {
            el.removeAttribute(attr.name);
            return;
          }
        }
        if (!ALLOWED_ATTRS.has(name)) {
          el.removeAttribute(attr.name);
        }
      });

      // 图片：只允许 http(s) 或 data:image 源，避免远程加载追踪类注入。
      if (tag === "img") {
        const src = el.getAttribute("src") || "";
        if (!/^(https?:|data:image\/)/i.test(src)) {
          el.removeAttribute("src");
        }
      }
      // 复选框：只允许任务列表的 <input type=checkbox disabled>。
      if (tag === "input") {
        const type = (el.getAttribute("type") || "").toLowerCase();
        if (type !== "checkbox" || !el.hasAttribute("disabled")) {
          el.remove();
          return;
        }
        // 保留 type/disabled/checked，其余属性全部剥掉。
        [...el.attributes].forEach((attr) => {
          if (attr.name !== "checked" && attr.name !== "disabled" && attr.name !== "type") {
            el.removeAttribute(attr.name);
          }
        });
      }

      if (!ALLOWED_TAGS.has(tag)) {
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

  // 把以 "[ ] " / "[x] " 开头的列表项转成任务列表复选框。
  function convertTaskLists(html) {
    return html.replace(/<li(\s[^>]*)?>([\s\S]*?)<\/li>/g, (match, attrs, inner) => {
      const boxMatch = inner.match(/^\s*(\[[ xX]\])\s+/);
      if (!boxMatch) return match;
      const checked = /^\[[xX]\]$/.test(boxMatch[1]);
      const rest = inner.replace(boxMatch[0], "");
      const cls = attrs && attrs.match(/class="([^"]*)"/) ? attrs.match(/class="([^"]*)"/)[1] : "";
      return `<li${attrs || ""} class="${(cls ? cls + " " : "")}task-list-item"><input type="checkbox" disabled${checked ? " checked" : ""}> ${rest}</li>`;
    });
  }

  function escapeHtmlText(value) {
    return String(value ?? "").replace(/[&<>'"]/g, (char) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
    })[char]);
  }

  function renderMarkdown(text) {
    const source = String(text ?? "");
    if (!source.trim()) return "";
    if (!_md) return escapeHtmlText(source);
    let html = _md.render(source);
    html = convertTaskLists(html);
    return sanitizeHtml(html);
  }

  function renderInline(text) {
    const source = String(text ?? "").trim();
    if (!source) return "";
    if (!_md) return escapeHtmlText(source);
    // 单行上下文（如题目标题）用行内渲染，避免块级 <p> 嵌套进 <h2> 等元素。
    return sanitizeHtml(_md.renderInline(source));
  }

  // -------------------------------------------------------------------------
  // 增强渲染：数学公式 / 代码高亮 / mermaid 图表。对同一容器可重复调用（幂等）。

  let _mermaidReady = false;

  function renderMermaid(pre, code) {
    const id = "timo-mermaid-" + Math.random().toString(36).slice(2, 10);
    try {
      window.mermaid.render(id, code).then(({ svg }) => {
        pre.innerHTML = svg;
      }).catch(() => {
        pre.innerHTML = `<div class="mermaid-fallback">图表渲染失败，原文：</div><pre><code>${escapeHtmlText(code)}</code></pre>`;
      });
    } catch (_) {
      pre.innerHTML = `<div class="mermaid-fallback">图表渲染失败，原文：</div><pre><code>${escapeHtmlText(code)}</code></pre>`;
    }
  }

  function enhance(root) {
    if (!root || root.nodeType !== 1 || typeof root.querySelectorAll !== "function") return;

    // 数学公式（KaTeX auto-render；跳过 pre/code 里的内容）
    if (window.katex && typeof window.renderMathInElement === "function") {
      try {
        window.renderMathInElement(root, {
          delimiters: [
            { left: "$$", right: "$$", display: true },
            { left: "$", right: "$", display: false },
            { left: "\\(", right: "\\)", display: false },
            { left: "\\[", right: "\\]", display: true },
          ],
          ignoredTags: ["script", "noscript", "style", "textarea", "pre", "code", "option"],
          throwOnError: false,
        });
      } catch (_) { /* 保持原文 */ }
    }

    // 代码高亮
    if (window.hljs) {
      root.querySelectorAll("pre code").forEach((block) => {
        if (block.dataset.hljsDone || block.classList.contains("language-mermaid")) return;
        block.dataset.hljsDone = "1";
        try { window.hljs.highlightElement(block); } catch (_) { /* 忽略 */ }
      });
    }

    // mermaid 图表
    const blocks = root.querySelectorAll("pre code.language-mermaid");
    if (blocks.length && window.mermaid) {
      if (!_mermaidReady) {
        _mermaidReady = true;
        try {
          window.mermaid.initialize({ startOnLoad: false, securityLevel: "strict", theme: "default" });
        } catch (_) { /* 忽略 */ }
      }
      blocks.forEach((block) => {
        const pre = block.closest("pre");
        if (!pre || pre.dataset.mermaidDone) return;
        pre.dataset.mermaidDone = "1";
        renderMermaid(pre, block.textContent || "");
      });
    }
  }

  function enhanceAll(root) {
    if (!root) return;
    if (root.classList && root.classList.contains("markdown")) enhance(root);
    root.querySelectorAll(".markdown").forEach((el) => enhance(el));
  }

  window.MarkdownRenderer = {
    render: renderMarkdown,
    renderInline: renderInline,
    sanitize: sanitizeHtml,
    enhance: enhance,
    enhanceAll: enhanceAll,
  };
})();
