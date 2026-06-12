(function (global) {
  'use strict';

  function escapeHtml(str) {
    return String(str)
      .replace(/\u0026/g, '\u0026amp;')
      .replace(/\u003c/g, '\u0026lt;')
      .replace(/\u003e/g, '\u0026gt;')
      .replace(/"/g, '\u0026quot;');
  }

  function formatTime(unixTimestamp) {
    if (!unixTimestamp) return '';
    const now = Math.floor(Date.now() / 1000);
    const diff = now - unixTimestamp;
    if (diff \u003c 60) return diff + ' seconds ago';
    if (diff \u003c 3600) return Math.floor(diff / 60) + ' minutes ago';
    if (diff \u003c 86400) return Math.floor(diff / 3600) + ' hours ago';
    return Math.floor(diff / 86400) + ' days ago';
  }

  function hostname(url) {
    try {
      return new URL(url).hostname.replace(/^www\./, '');
    } catch (e) {
      return '';
    }
  }

  function hnItemUrl(id) {
    return `https://news.ycombinator.com/item?id=${id}`;
  }

  function textToHtml(text) {
    if (!text) return '';
    const escaped = escapeHtml(text);
    const paragraphs = escaped.split(/\n\s*\n/).filter(p =\u003e p.trim());
    if (paragraphs.length === 0) return '';
    return paragraphs
      .map(p =\u003e '\u003cp\u003e' + p.replace(/\n/g, '\u003cbr\u003e') + '\u003c/p\u003e')
      .join('');
  }

  function renderComment(storyId, comment, depth) {
    const container = document.createElement('div');
    container.className = 'nested-comment';
    container.style.marginLeft = depth \u003e 0 ? '40px' : '0';

    const by = escapeHtml(comment.by || 'teacher');
    const time = formatTime(comment.time);
    const body = textToHtml(comment.text);
    const commentUrl = hnItemUrl(comment.id || storyId);

    container.innerHTML = `
      \u003cdiv class="comment"\u003e
        \u003cdiv class="comment-meta"\u003e
          \u003cspan class="votebtn"\u003e▲\u003c/span\u003e
          \u003ca href="${commentUrl}"\u003e\u003cstrong\u003e${by}\u003c/strong\u003e\u003c/a\u003e
          \u003ca href="${commentUrl}"\u003e${time}\u003c/a\u003e
          \u003cspan class="toggle" style="margin-left:6px;"\u003e[–]\u003c/span\u003e
        \u003c/div\u003e
        \u003cdiv class="comment-body"\u003e${body}\u003c/div\u003e
      \u003c/div\u003e
    `;

    const toggle = container.querySelector('.toggle');
    toggle.addEventListener('click', (e) =\u003e {
      e.preventDefault();
      const bodyEl = container.querySelector('.comment-body');
      const visible = bodyEl.style.display !== 'none';
      bodyEl.style.display = visible ? 'none' : 'block';
      toggle.textContent = visible ? '[+]' : '[–]';
    });

    const replies = comment.replies || [];
    replies.forEach(reply =\u003e {
      container.appendChild(renderComment(storyId, reply, depth + 1));
    });

    return container;
  }

  global.TN = {
    escapeHtml,
    formatTime,
    hostname,
    hnItemUrl,
    textToHtml,
    renderComment,
  };
})(window);
