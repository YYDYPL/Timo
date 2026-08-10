(() => {
  "use strict";

  const page = document.body.dataset.page;

  class ApiError extends Error {
    constructor(message, status, payload) {
      super(message);
      this.name = "ApiError";
      this.status = status;
      this.payload = payload;
    }
  }

  async function api(path, options = {}) {
    const init = { method: options.method || "GET", headers: { ...(options.headers || {}) } };
    if (options.body !== undefined) {
      init.headers["Content-Type"] = "application/json";
      init.body = JSON.stringify(options.body);
    }

    let response;
    try {
      response = await fetch(path, init);
    } catch (error) {
      throw new ApiError("无法连接本地服务，请确认 Uvicorn 已启动。", 0, null);
    }

    const text = await response.text();
    let payload = null;
    if (text) {
      try { payload = JSON.parse(text); } catch { payload = text; }
    }
    if (!response.ok) {
      let message = "请求失败，请稍后重试。";
      if (typeof payload === "string" && payload.trim()) message = payload;
      if (payload && typeof payload.detail === "string") message = payload.detail;
      if (payload && Array.isArray(payload.detail)) {
        message = payload.detail.map((item) => item.msg || String(item)).join("；");
      }
      throw new ApiError(message, response.status, payload);
    }
    return payload;
  }

  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];

  function escapeHtml(value) {
    return String(value ?? "").replace(/[&<>'"]/g, (char) => ({
      "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;",
    })[char]);
  }

  function asList(payload, keys = ["items"]) {
    if (Array.isArray(payload)) return payload;
    for (const key of keys) {
      if (Array.isArray(payload?.[key])) return payload[key];
    }
    return [];
  }

  function numberValue(value, fallback = 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : fallback;
  }

  function clampPercent(value) {
    return Math.max(0, Math.min(100, numberValue(value)));
  }

  function formatDateTime(value) {
    if (!value) return "--";
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return String(value);
    return new Intl.DateTimeFormat("zh-CN", {
      month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
    }).format(date);
  }

  function categoryLabel(value) {
    const normalized = String(value || "").toLowerCase();
    if (normalized === "agent") return "Agent";
    return value || "未分类";
  }

  function categoryClass(value) {
    const normalized = String(value || "").toLowerCase();
    if (normalized === "agent") return "agent";
    if (value === "项目") return "project";
    return "";
  }

  function normalizeQuestion(item) {
    if (item && typeof item.question === "object") {
      return { ...item.question, review: item.review || item.question.review || {} };
    }
    return { ...(item || {}), keypoints: asList(item?.keypoints, []), review: item?.review || {} };
  }

  function normalizeStringList(value) {
    if (Array.isArray(value)) return value.map((item) => String(item).trim()).filter(Boolean);
    if (typeof value === "string") {
      try {
        const parsed = JSON.parse(value);
        if (Array.isArray(parsed)) return normalizeStringList(parsed);
      } catch { /* Plain text is handled below. */ }
      return value.split(/\r?\n|,|，/).map((item) => item.trim()).filter(Boolean);
    }
    return [];
  }

  function setButtonBusy(button, busy, label) {
    if (!button) return;
    if (busy) {
      button.dataset.originalLabel = button.textContent;
      button.disabled = true;
      button.textContent = label;
    } else {
      button.disabled = false;
      button.textContent = button.dataset.originalLabel || button.textContent;
      delete button.dataset.originalLabel;
    }
  }

  function toast(title, message = "", type = "success") {
    const region = $("#toast-region");
    if (!region) return;
    const element = document.createElement("div");
    element.className = `toast ${type === "error" ? "error" : ""}`;
    element.innerHTML = `<div><strong>${escapeHtml(title)}</strong>${message ? `<span>${escapeHtml(message)}</span>` : ""}</div>`;
    region.appendChild(element);
    window.setTimeout(() => element.remove(), 3600);
  }

  function openDialog(dialog) {
    if (!dialog) return;
    if (typeof dialog.showModal === "function") dialog.showModal();
    else dialog.setAttribute("open", "");
  }

  function closeDialog(dialog) {
    if (!dialog) return;
    if (typeof dialog.close === "function") dialog.close();
    else dialog.removeAttribute("open");
  }

  function setDueBadge(count) {
    $$('[data-due-count]').forEach((badge) => {
      const value = Math.max(0, numberValue(count));
      badge.textContent = value > 99 ? "99+" : String(value);
      badge.hidden = value === 0;
    });
  }

  async function loadNavSnapshot() {
    if (page === "stats") return;
    try {
      const data = await api("/api/stats?recent_limit=1");
      setDueBadge(data.today_due);
    } catch { /* Navigation remains usable if the optional snapshot fails. */ }
  }

  async function updateAiStatus() {
    try {
      const status = await api("/api/ai/status");
      const label = $(".sidebar-status span:last-child");
      if (label) label.textContent = status.configured ? "本地数据 · AI 可用" : "本地数据 · AI 未配置";
      return status.configured !== false;
    } catch {
      return true;
    }
  }

  function initCommon() {
    $(`[data-nav="${page}"]`)?.classList.add("active");
    loadNavSnapshot();
  }

  // -----------------------------------------------------------------------
  // Question bank

  function initQuestionsPage() {
    const state = { questions: [] };
    const list = $("#question-list");
    const searchInput = $("#question-search");
    const categoryFilter = $("#category-filter");
    const topicFilter = $("#topic-filter");
    const clearFilters = $("#clear-filters");
    const dialog = $("#question-dialog");
    const form = $("#question-form");

    function setSelectValue(select, value, label = value) {
      const normalized = String(value ?? "");
      if (normalized && ![...select.options].some((option) => option.value === normalized)) {
        select.add(new Option(label, normalized));
      }
      select.value = normalized;
    }

    function refreshTopicOptions() {
      const selected = topicFilter.value;
      const category = categoryFilter.value;
      const topics = [...new Set(state.questions
        .filter((item) => !category || item.category === category)
        .map((item) => item.topic)
        .filter(Boolean))].sort((a, b) => a.localeCompare(b, "zh-CN"));
      topicFilter.innerHTML = `<option value="">全部主题</option>${topics.map((topic) => `<option value="${escapeHtml(topic)}">${escapeHtml(topic)}</option>`).join("")}`;
      if (topics.includes(selected)) topicFilter.value = selected;
    }

    function difficultyMarkup(value) {
      const difficulty = Math.max(1, Math.min(5, numberValue(value, 3)));
      return `<span class="difficulty-badge" title="难度 ${difficulty}/5" aria-label="难度 ${difficulty}/5">${[1, 2, 3, 4, 5].map((level) => `<i class="${level <= difficulty ? "on" : ""}"></i>`).join("")}</span>`;
    }

    function visibleQuestions() {
      const query = searchInput.value.trim().toLowerCase();
      const category = categoryFilter.value;
      const topic = topicFilter.value;
      return state.questions.filter((item) => {
        if (category && item.category !== category) return false;
        if (topic && item.topic !== topic) return false;
        if (!query) return true;
        const haystack = [item.question, item.answer, item.topic, item.source, ...normalizeStringList(item.keypoints)].join(" ").toLowerCase();
        return haystack.includes(query);
      });
    }

    function renderQuestions() {
      const items = visibleQuestions();
      const filtering = Boolean(searchInput.value.trim() || categoryFilter.value || topicFilter.value);
      $("#question-count").textContent = filtering ? `${items.length} / ${state.questions.length}` : String(state.questions.length);
      clearFilters.hidden = !filtering;

      if (!items.length) {
        list.innerHTML = `<div class="empty-state"><div class="empty-mark">?</div><h2>${filtering ? "没有匹配的题目" : "题库还是空的"}</h2><p>${filtering ? "换个关键词或清除筛选条件。" : "添加第一道题，复习队列会自动创建。"}</p>${filtering ? "" : '<button class="button primary" type="button" data-action="new-question">新建题目</button>'}</div>`;
        return;
      }

      list.innerHTML = items.map((item) => {
        const keypoints = normalizeStringList(item.keypoints);
        const repetitions = numberValue(item.review?.repetitions);
        const suspended = Boolean(item.review?.suspended);
        const detailId = `question-detail-${item.id}`;
        return `
          <article class="question-item" data-question-id="${item.id}">
            <div class="question-main-row">
              <div class="question-title">
                <strong>${escapeHtml(item.question)}</strong>
                <div class="question-title-meta">
                  <span class="category-badge ${categoryClass(item.category)}">${escapeHtml(categoryLabel(item.category))}</span>
                  ${suspended ? '<span class="muted-label">待安排</span>' : ""}
                  ${repetitions ? `<span class="muted-label">复习 ${repetitions} 次</span>` : ""}
                </div>
              </div>
              <span class="topic-label" title="${escapeHtml(item.topic || "未分类")}">${escapeHtml(item.topic || "未分类")}</span>
              ${difficultyMarkup(item.difficulty)}
              <div class="row-actions">
                <button class="button ghost small review-question" type="button" title="立即复习这道题">背</button>
                <button class="button ghost small view-question" type="button" aria-expanded="false" aria-controls="${detailId}">查看</button>
                <button class="button ghost small edit-question" type="button">编辑</button>
                <button class="icon-button delete-question" type="button" aria-label="删除题目" title="删除">×</button>
              </div>
            </div>
            <div class="question-detail" id="${detailId}" hidden>
              <div class="question-detail-inner">
                <div><h3>参考答案</h3><p class="answer-preview">${escapeHtml(item.answer || "暂无参考答案")}</p>${item.source ? `<p class="source-line">来源：${escapeHtml(item.source)}</p>` : ""}</div>
                <div><h3>关键要点</h3>${keypoints.length ? `<ul class="keypoint-preview">${keypoints.map((point) => `<li>${escapeHtml(point)}</li>`).join("")}</ul>` : '<p class="answer-preview">暂无要点</p>'}</div>
              </div>
            </div>
          </article>`;
      }).join("");
    }

    function openQuestionForm(question = null) {
      form.reset();
      $("#question-id").value = question?.id || "";
      $("#question-dialog-title").textContent = question ? "编辑题目" : "新建题目";
      setSelectValue($("#question-category"), question?.category || "八股", categoryLabel(question?.category || "八股"));
      $("#question-topic").value = question?.topic || "";
      $("#question-text").value = question?.question || "";
      $("#question-answer").value = question?.answer || "";
      $("#question-keypoints").value = normalizeStringList(question?.keypoints).join("\n");
      $("#question-difficulty").value = String(question?.difficulty || 3);
      $("#question-source").value = question?.source || "";
      $("#question-suspended").checked = Boolean(question?.review?.suspended);
      openDialog(dialog);
      window.setTimeout(() => $("#question-text").focus(), 30);
    }

    async function loadQuestions() {
      try {
        const [payload, aiConfigured] = await Promise.all([api("/api/questions"), updateAiStatus()]);
        state.questions = asList(payload).map(normalizeQuestion);
        $("#generate-answer").disabled = !aiConfigured;
        $("#generate-answer").title = aiConfigured ? "" : "请先在 .env 中配置 LLM";
        refreshTopicOptions();
        renderQuestions();
      } catch (error) {
        list.innerHTML = `<div class="empty-state"><div class="empty-mark error">!</div><h2>题库加载失败</h2><p>${escapeHtml(error.message)}</p><button class="button primary" type="button" data-action="retry">重新加载</button></div>`;
        $("#question-count").textContent = "--";
      }
    }

    $("#new-question").addEventListener("click", () => openQuestionForm());
    $$(".close-dialog").forEach((button) => button.addEventListener("click", () => closeDialog(dialog)));

    $("#generate-answer").addEventListener("click", async () => {
      const questionText = $("#question-text").value.trim();
      if (!questionText) {
        toast("先写题目", "AI 需要题目内容才能生成参考答案。", "error");
        return;
      }
      const keypoints = $("#question-keypoints").value.split(/\r?\n/)
        .map((point) => point.replace(/^[-*•]\s*/, "").trim()).filter(Boolean);
      const button = $("#generate-answer");
      setButtonBusy(button, true, "生成中…");
      try {
        const result = await api("/api/ai/generate-answer", {
          method: "POST",
          body: { question: questionText, keypoints },
        });
        $("#question-answer").value = result.answer || "";
        toast("参考答案已生成", "已填入参考答案文本框，可继续编辑。");
      } catch (error) {
        toast(error.status === 503 ? "AI 尚未配置" : "生成失败", error.message, "error");
      } finally {
        setButtonBusy(button, false);
      }
    });
    [searchInput, categoryFilter, topicFilter].forEach((control) => control.addEventListener(control === searchInput ? "input" : "change", () => {
      if (control === categoryFilter) refreshTopicOptions();
      renderQuestions();
    }));
    clearFilters.addEventListener("click", () => {
      searchInput.value = "";
      categoryFilter.value = "";
      refreshTopicOptions();
      topicFilter.value = "";
      renderQuestions();
      searchInput.focus();
    });

    list.addEventListener("click", async (event) => {
      const action = event.target.closest("button");
      if (!action) return;
      if (action.dataset.action === "new-question") return openQuestionForm();
      if (action.dataset.action === "retry") return loadQuestions();
      const itemElement = action.closest("[data-question-id]");
      const id = Number(itemElement?.dataset.questionId);
      const question = state.questions.find((item) => Number(item.id) === id);
      if (!question) return;
      if (action.classList.contains("review-question")) {
        window.location.href = `/review.html?id=${id}`;
        return;
      }
      if (action.classList.contains("view-question")) {
        const detail = $(`#question-detail-${id}`);
        detail.hidden = !detail.hidden;
        action.textContent = detail.hidden ? "查看" : "收起";
        action.setAttribute("aria-expanded", String(!detail.hidden));
      }
      if (action.classList.contains("edit-question")) openQuestionForm(question);
      if (action.classList.contains("delete-question")) {
        if (!window.confirm(`确定删除“${question.question}”吗？复习记录也会一并删除。`)) return;
        action.disabled = true;
        try {
          await api(`/api/questions/${id}`, { method: "DELETE" });
          state.questions = state.questions.filter((item) => Number(item.id) !== id);
          refreshTopicOptions();
          renderQuestions();
          toast("题目已删除");
          loadNavSnapshot();
        } catch (error) {
          action.disabled = false;
          toast("删除失败", error.message, "error");
        }
      }
    });

    form.addEventListener("submit", async (event) => {
      event.preventDefault();
      const id = $("#question-id").value;
      const saveButton = $("#save-question");
      const payload = {
        category: $("#question-category").value,
        topic: $("#question-topic").value.trim(),
        question: $("#question-text").value.trim(),
        answer: $("#question-answer").value.trim(),
        keypoints: $("#question-keypoints").value.split(/\r?\n/).map((point) => point.replace(/^[-*•]\s*/, "").trim()).filter(Boolean),
        difficulty: Number($("#question-difficulty").value),
        source: $("#question-source").value.trim(),
        suspended: $("#question-suspended").checked,
      };
      setButtonBusy(saveButton, true, "保存中…");
      try {
        await api(id ? `/api/questions/${id}` : "/api/questions", { method: id ? "PUT" : "POST", body: payload });
        closeDialog(dialog);
        toast(id ? "题目已更新" : "题目已加入题库");
        await loadQuestions();
        loadNavSnapshot();
      } catch (error) {
        toast("保存失败", error.message, "error");
      } finally {
        setButtonBusy(saveButton, false);
      }
    });

    loadQuestions();
  }

  // -----------------------------------------------------------------------
  // Active recall review

  function initReviewPage() {
    const state = { queue: [], current: null, attempts: 0, evaluation: null, aiConfigured: true, sourceTotal: 0, forcedId: null };
    const rawId = new URLSearchParams(window.location.search).get("id");
    state.forcedId = rawId && Number.isInteger(Number(rawId)) && Number(rawId) > 0 ? Number(rawId) : null;
    const loading = $("#review-loading");
    const card = $("#review-card");
    const empty = $("#review-empty");
    const errorState = $("#review-error");

    function updateProgress(done = false) {
      const remaining = state.queue.length + (state.current ? 1 : 0);
      const total = state.attempts + remaining;
      const percent = total ? (state.attempts / total) * 100 : (done && state.sourceTotal ? 100 : 0);
      $("#review-progress-label").textContent = `${state.attempts} / ${total}`;
      $("#review-progress-bar").style.width = `${percent}%`;
    }

    function showNextQuestion() {
      state.evaluation = null;
      $("#evaluation-panel").hidden = true;
      $("#evaluation-panel").innerHTML = "";
      $("#recall-answer").value = "";
      $("#recall-panel").hidden = false;
      $("#answer-panel").hidden = true;
      if (!state.queue.length) {
        state.current = null;
        card.hidden = true;
        empty.hidden = false;
        updateProgress(true);
        $("#empty-today-link").hidden = !state.forcedId;
        if (state.forcedId) {
          $("#review-empty-title").textContent = "这道题复习完了";
          $("#review-empty-copy").textContent = "记住的题会按记忆间隔自动安排。";
          loadNavSnapshot();
        } else {
          $("#review-empty-title").textContent = "今天的复习完成了";
          $("#review-empty-copy").textContent = "新的复习会按记忆间隔自动出现。";
          setDueBadge(0);
        }
        return;
      }

      state.current = state.queue.shift();
      const question = state.current;
      const category = $("#review-category");
      category.textContent = categoryLabel(question.category);
      category.className = `category-badge ${categoryClass(question.category)}`;
      $("#review-topic").textContent = question.topic || "未分类";
      $("#review-position").textContent = `${state.queue.length + 1} 张待处理`;
      $("#review-question").textContent = question.question;
      $("#review-answer").textContent = question.answer || "暂无参考答案，请以关键要点为准。";
      const keypoints = normalizeStringList(question.keypoints);
      $("#review-keypoints").innerHTML = keypoints.length
        ? keypoints.map((point) => `<li>${escapeHtml(point)}</li>`).join("")
        : "<li>暂无关键要点</li>";
      $("#evaluate-answer").disabled = !state.aiConfigured;
      $("#evaluate-answer").title = state.aiConfigured ? "" : "请先在 .env 中配置 LLM";
      card.hidden = false;
      empty.hidden = true;
      errorState.hidden = true;
      updateProgress();
      window.scrollTo({ top: 0, behavior: "smooth" });
    }

    async function loadQueue() {
      loading.hidden = false;
      card.hidden = true;
      empty.hidden = true;
      errorState.hidden = true;
      state.queue = [];
      state.current = null;
      state.attempts = 0;
      try {
        if (state.forcedId) {
          // Single-question review: drill one card regardless of its due date.
          const [question, aiConfigured] = await Promise.all([
            api(`/api/questions/${state.forcedId}`),
            updateAiStatus(),
          ]);
          state.aiConfigured = aiConfigured;
          state.queue = [normalizeQuestion(question)];
          state.sourceTotal = 1;
          loading.hidden = true;
          loadNavSnapshot();
          showNextQuestion();
          return;
        }
        const [payload, aiConfigured] = await Promise.all([
          api("/api/review/today"),
          updateAiStatus(),
        ]);
        state.aiConfigured = aiConfigured;
        state.queue = asList(payload).map(normalizeQuestion);
        state.sourceTotal = numberValue(payload.total, state.queue.length);
        setDueBadge(payload.total);
        loading.hidden = true;
        showNextQuestion();
      } catch (error) {
        loading.hidden = true;
        errorState.hidden = false;
        $("#review-error-message").textContent = error.message;
      }
    }

    $("#reveal-answer").addEventListener("click", () => {
      $("#recall-panel").hidden = true;
      $("#answer-panel").hidden = false;
      window.setTimeout(() => $("#answer-panel").scrollIntoView({ behavior: "smooth", block: "nearest" }), 20);
    });

    $("#skip-question").addEventListener("click", () => {
      if (!state.current) return;
      if (!state.queue.length) {
        toast("当前只有这一题", "先试着回忆，再查看答案。", "error");
        return;
      }
      state.queue.push(state.current);
      state.current = null;
      showNextQuestion();
    });

    $("#evaluate-answer").addEventListener("click", async (event) => {
      const answer = $("#recall-answer").value.trim();
      if (!answer) {
        toast("先写下你的回答", "写几个关键词也可以。", "error");
        return;
      }
      const button = event.currentTarget;
      setButtonBusy(button, true, "AI 评估中…");
      try {
        const result = await api("/api/ai/evaluate", {
          method: "POST",
          body: { question_id: state.current.id, answer },
        });
        state.evaluation = result;
        const coverage = clampPercent(result.coverage ?? result.coverage_percent);
        const covered = normalizeStringList(result.covered);
        const missed = normalizeStringList(result.missed ?? result.missed_keypoints);
        const suggestion = result.suggestion || "继续围绕关键要点组织更完整的回答。";
        const panel = $("#evaluation-panel");
        panel.innerHTML = `
          <div class="evaluation-summary">
            <div class="coverage-score">${Math.round(coverage)}%</div>
            <div><h3>${coverage >= 80 ? "覆盖得很扎实" : coverage >= 55 ? "主干已经答到了" : "还可以补几个关键点"}</h3><p>已覆盖 ${covered.length} 项，遗漏 ${missed.length} 项</p></div>
          </div>
          ${missed.length ? `<div class="missed-points">${missed.map((point) => `<span>${escapeHtml(point)}</span>`).join("")}</div>` : ""}
          <p class="evaluation-suggestion">${escapeHtml(suggestion)}</p>`;
        panel.hidden = false;
        panel.scrollIntoView({ behavior: "smooth", block: "nearest" });
      } catch (error) {
        toast(error.status === 503 ? "AI 尚未配置" : "评估失败", error.message, "error");
      } finally {
        setButtonBusy(button, false);
      }
    });

    $$(".rating-button").forEach((button) => button.addEventListener("click", async () => {
      if (!state.current) return;
      const quality = Number(button.dataset.quality);
      const buttons = $$(".rating-button");
      buttons.forEach((item) => { item.disabled = true; });
      const reviewedCard = state.current;
      try {
        const result = await api(`/api/review/${reviewedCard.id}`, {
          method: "POST",
          body: { quality, covered_keypoints: normalizeStringList(state.evaluation?.covered) },
        });
        if (quality === 1 || result.repeat_today) state.queue.push(reviewedCard);
        state.current = null;
        state.attempts += 1;
        const interval = numberValue(result.review?.interval);
        const message = quality === 1 ? "已放到本轮队列末尾" : interval ? `${interval} 天后再见` : "复习进度已记录";
        toast(result.quality_label || "复习已记录", message);
        showNextQuestion();
        setDueBadge(state.queue.length + (state.current ? 1 : 0));
      } catch (error) {
        toast("记录失败", error.message, "error");
      } finally {
        buttons.forEach((item) => { item.disabled = false; });
      }
    }));

    $("#retry-review").addEventListener("click", loadQueue);
    loadQueue();
  }

  // -----------------------------------------------------------------------
  // Project stories and AI follow-ups

  function initProjectsPage() {
    const state = { projects: [], currentProject: null, followups: [], aiConfigured: true };
    const list = $("#project-list");
    const projectDialog = $("#project-dialog");
    const projectForm = $("#project-form");
    const followupDialog = $("#followup-dialog");

    function renderProjects() {
      if (!state.projects.length) {
        list.innerHTML = '<div class="empty-state large"><div class="empty-mark">＋</div><h2>添加你的第一个项目</h2><p>项目名称、技术细节和结果越具体，生成的追问越贴近真实面试。</p><button class="button primary" type="button" data-action="new-project">添加项目</button></div>';
        return;
      }
      list.innerHTML = state.projects.map((project) => {
        const tags = normalizeStringList(project.tags);
        return `
          <article class="project-card" data-project-id="${project.id}">
            <div class="project-card-head">
              <h2>${escapeHtml(project.name)}</h2>
              <div class="project-menu"><button class="button ghost small edit-project" type="button">编辑</button><button class="icon-button delete-project" type="button" aria-label="删除项目" title="删除">×</button></div>
            </div>
            <p class="project-description">${escapeHtml(project.description || "暂无项目描述")}</p>
            <div class="tag-list">${tags.length ? tags.map((tag) => `<span class="tag">${escapeHtml(tag)}</span>`).join("") : '<span class="tag">未添加标签</span>'}</div>
            <div class="project-actions">
              <button class="button secondary generate-followups" type="button" ${state.aiConfigured ? "" : "disabled"} title="${state.aiConfigured ? "" : "请先在 .env 中配置 LLM"}">${state.aiConfigured ? "生成面试追问" : "AI 未配置"}</button>
            </div>
          </article>`;
      }).join("");
    }

    function openProjectForm(project = null) {
      projectForm.reset();
      $("#project-id").value = project?.id || "";
      $("#project-dialog-title").textContent = project ? "编辑项目" : "添加项目";
      $("#project-name").value = project?.name || "";
      $("#project-description").value = project?.description || "";
      $("#project-tags").value = normalizeStringList(project?.tags).join(", ");
      openDialog(projectDialog);
      window.setTimeout(() => $("#project-name").focus(), 30);
    }

    async function loadProjects() {
      try {
        const [payload, aiConfigured] = await Promise.all([api("/api/projects"), updateAiStatus()]);
        state.projects = asList(payload);
        state.aiConfigured = aiConfigured;
        renderProjects();
      } catch (error) {
        list.innerHTML = `<div class="empty-state large"><div class="empty-mark error">!</div><h2>项目加载失败</h2><p>${escapeHtml(error.message)}</p><button class="button primary" type="button" data-action="retry-projects">重新加载</button></div>`;
      }
    }

    function selectedFollowups() {
      return $$(".followup-select:checked", $("#followup-list")).map((input) => state.followups[Number(input.value)]).filter(Boolean);
    }

    function refreshFollowupSelection() {
      const selected = selectedFollowups().length;
      $("#followup-count").textContent = `已选 ${selected} / ${state.followups.length}`;
      $("#select-all-followups").checked = selected === state.followups.length && state.followups.length > 0;
      $("#select-all-followups").indeterminate = selected > 0 && selected < state.followups.length;
      $("#import-followups").disabled = selected === 0;
    }

    function renderFollowups() {
      $("#followup-list").innerHTML = state.followups.map((item, index) => {
        const points = normalizeStringList(item.keypoints);
        return `
          <label class="followup-item">
            <span class="followup-check"><input class="followup-select" type="checkbox" value="${index}" checked></span>
            <span>
              <h3>${escapeHtml(item.question)}</h3>
              ${item.answer ? `<p class="followup-answer">${escapeHtml(item.answer)}</p>` : ""}
              <span class="followup-keypoints">${points.map((point) => `<span>${escapeHtml(point)}</span>`).join("")}</span>
            </span>
          </label>`;
      }).join("");
      refreshFollowupSelection();
    }

    async function generateFollowups(project) {
      state.currentProject = project;
      state.followups = [];
      $("#followup-title").textContent = `${project.name} · 项目追问`;
      $("#followup-loading").hidden = false;
      $("#followup-content").hidden = true;
      $("#followup-error").hidden = true;
      openDialog(followupDialog);
      try {
        const payload = await api(`/api/projects/${project.id}/generate-followups`, {
          method: "POST", body: { count: 6, save: false },
        });
        state.followups = asList(payload).map((item) => ({
          question: String(item.question || "").trim(),
          answer: String(item.answer || "").trim(),
          keypoints: normalizeStringList(item.keypoints),
        })).filter((item) => item.question);
        if (!state.followups.length) throw new Error("模型没有返回可用的追问，请再试一次。");
        renderFollowups();
        $("#followup-loading").hidden = true;
        $("#followup-content").hidden = false;
      } catch (error) {
        $("#followup-loading").hidden = true;
        $("#followup-error").hidden = false;
        $("#followup-error-message").textContent = error.message;
      }
    }

    $("#new-project").addEventListener("click", () => openProjectForm());
    $$(".close-project-dialog").forEach((button) => button.addEventListener("click", () => closeDialog(projectDialog)));
    $$(".close-followup-dialog").forEach((button) => button.addEventListener("click", () => closeDialog(followupDialog)));
    $("#retry-followups").addEventListener("click", () => state.currentProject && generateFollowups(state.currentProject));

    list.addEventListener("click", async (event) => {
      const action = event.target.closest("button");
      if (!action) return;
      if (action.dataset.action === "new-project") return openProjectForm();
      if (action.dataset.action === "retry-projects") return loadProjects();
      const id = Number(action.closest("[data-project-id]")?.dataset.projectId);
      const project = state.projects.find((item) => Number(item.id) === id);
      if (!project) return;
      if (action.classList.contains("edit-project")) openProjectForm(project);
      if (action.classList.contains("generate-followups")) generateFollowups(project);
      if (action.classList.contains("delete-project")) {
        if (!window.confirm(`确定删除项目“${project.name}”吗？已入库的题目不会被删除。`)) return;
        action.disabled = true;
        try {
          await api(`/api/projects/${id}`, { method: "DELETE" });
          state.projects = state.projects.filter((item) => Number(item.id) !== id);
          renderProjects();
          toast("项目已删除");
        } catch (error) {
          action.disabled = false;
          toast("删除失败", error.message, "error");
        }
      }
    });

    projectForm.addEventListener("submit", async (event) => {
      event.preventDefault();
      const id = $("#project-id").value;
      const saveButton = $("#save-project");
      const payload = {
        name: $("#project-name").value.trim(),
        description: $("#project-description").value.trim(),
        tags: $("#project-tags").value.split(/[,，\n]/).map((tag) => tag.trim()).filter(Boolean),
      };
      setButtonBusy(saveButton, true, "保存中…");
      try {
        await api(id ? `/api/projects/${id}` : "/api/projects", { method: id ? "PUT" : "POST", body: payload });
        closeDialog(projectDialog);
        toast(id ? "项目已更新" : "项目已添加");
        await loadProjects();
      } catch (error) {
        toast("保存失败", error.message, "error");
      } finally {
        setButtonBusy(saveButton, false);
      }
    });

    $("#followup-list").addEventListener("change", refreshFollowupSelection);
    $("#select-all-followups").addEventListener("change", (event) => {
      $$(".followup-select", $("#followup-list")).forEach((input) => { input.checked = event.target.checked; });
      refreshFollowupSelection();
    });
    $("#import-followups").addEventListener("click", async (event) => {
      const selected = selectedFollowups();
      if (!selected.length || !state.currentProject) return;
      const button = event.currentTarget;
      setButtonBusy(button, true, "正在入库…");
      try {
        const result = await api(`/api/projects/${state.currentProject.id}/followups`, {
          method: "POST",
          body: {
            questions: selected.map((item) => ({ question: item.question, answer: item.answer, keypoints: item.keypoints })),
            suspended: $("#import-suspended").checked,
          },
        });
        closeDialog(followupDialog);
        toast("追问已加入题库", `共 ${numberValue(result.count, selected.length)} 道题`);
        loadNavSnapshot();
      } catch (error) {
        toast("入库失败", error.message, "error");
      } finally {
        setButtonBusy(button, false);
      }
    });

    loadProjects();
  }

  // -----------------------------------------------------------------------
  // Statistics

  function initStatsPage() {
    const loading = $("#stats-loading");
    const content = $("#stats-content");
    const errorState = $("#stats-error");

    function masteryValue(item) {
      return clampPercent(item.mastery_percent ?? item.mastery ?? item.score);
    }

    function renderStats(data) {
      const mastery = clampPercent(data.mastery_percent);
      $("#stat-due").textContent = numberValue(data.today_due);
      $("#stat-total").textContent = numberValue(data.total_questions);
      $("#stat-mastered").textContent = numberValue(data.mastered_count);
      $("#stat-mastery").textContent = `${Math.round(mastery)}%`;
      $("#stat-mastery-bar").style.width = `${mastery}%`;
      setDueBadge(data.today_due);

      const categories = asList(data.by_category, []);
      $("#category-stats").innerHTML = categories.length ? categories.map((item) => {
        const value = masteryValue(item);
        return `<div class="distribution-row"><div class="distribution-row-head"><strong>${escapeHtml(categoryLabel(item.name ?? item.category))}</strong><span>${Math.round(value)}% · ${numberValue(item.mastered)}/${numberValue(item.total)} 已掌握</span></div><div class="distribution-track"><span style="width:${value}%"></span></div></div>`;
      }).join("") : '<div class="empty-state"><p>还没有分类数据。</p></div>';

      const topics = asList(data.by_topic, []).slice().sort((a, b) => masteryValue(a) - masteryValue(b));
      $("#topic-stats").innerHTML = topics.length ? topics.map((item) => {
        const value = masteryValue(item);
        const weak = item.weak === true || value < 50;
        return `<div class="topic-stat-row ${weak ? "weak" : ""}"><div class="topic-stat-head"><strong>${escapeHtml(item.name ?? item.topic ?? "未分类")}</strong><span>${Math.round(value)}%</span></div><div class="topic-stat-meta"><span>${numberValue(item.total)} 道题</span><span>${numberValue(item.due)} 待复习</span><span>${numberValue(item.mastered)} 已掌握</span></div></div>`;
      }).join("") : '<div class="empty-state"><p>还没有主题数据。</p></div>';

      const recent = asList(data.recent_reviews, []);
      const qualityLabels = { 1: "重来", 2: "重来", 3: "困难", 4: "良好", 5: "简单" };
      $("#recent-reviews").innerHTML = recent.length ? recent.map((item) => {
        const quality = numberValue(item.quality);
        return `<div class="history-row"><span class="quality-label q${quality}">${escapeHtml(item.quality_label || qualityLabels[quality] || "已复习")}</span><span class="history-question" title="${escapeHtml(item.question)}">${escapeHtml(item.question)}</span><span class="topic-label">${escapeHtml(item.topic || categoryLabel(item.category))}</span><time class="history-time">${escapeHtml(formatDateTime(item.reviewed_at))}</time></div>`;
      }).join("") : '<div class="empty-state"><p>完成一次复习后，记录会出现在这里。</p></div>';
    }

    async function loadStats() {
      loading.hidden = false;
      content.hidden = true;
      errorState.hidden = true;
      try {
        const data = await api("/api/stats");
        renderStats(data);
        loading.hidden = true;
        content.hidden = false;
      } catch (error) {
        loading.hidden = true;
        errorState.hidden = false;
        $("#stats-error-message").textContent = error.message;
      }
    }

    $("#retry-stats").addEventListener("click", loadStats);
    loadStats();
  }

  initCommon();
  if (page === "questions") initQuestionsPage();
  if (page === "review") initReviewPage();
  if (page === "projects") initProjectsPage();
  if (page === "stats") initStatsPage();
})();
