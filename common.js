(function (global) {
  'use strict';

  function escapeHtml(str) {
    return String(str)
      .replace(/\u0026/g, '\u0026amp;')
      .replace(/</g, '\u0026lt;')
      .replace(/>/g, '\u0026gt;')
      .replace(/"/g, '\u0026quot;');
  }

  function formatTime(unixTimestamp) {
    if (!unixTimestamp) return '';
    const now = Math.floor(Date.now() / 1000);
    const diff = now - unixTimestamp;
    if (diff < 60) return diff + ' seconds ago';
    if (diff < 3600) return Math.floor(diff / 60) + ' minutes ago';
    if (diff < 86400) return Math.floor(diff / 3600) + ' hours ago';
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
    const paragraphs = escaped.split(/\n\s*\n/).filter(p => p.trim());
    if (paragraphs.length === 0) return '';
    return paragraphs
      .map(p => '<p>' + p.replace(/\n/g, '<br>') + '</p>')
      .join('');
  }

  function renderComment(storyId, comment, depth) {
    const container = document.createElement('div');
    container.className = 'nested-comment';
    const isMobile = window.innerWidth <= 600;
    const indent = isMobile ? Math.min(depth * 12, 36) : (depth * 40);
    container.style.marginLeft = indent + 'px';

    const by = escapeHtml(comment.by || 'teacher');
    const time = formatTime(comment.time);
    const body = textToHtml(comment.text);
    const commentUrl = hnItemUrl(comment.id || storyId);

    container.innerHTML = `
      <div class="comment">
        <div class="comment-meta">
          <span class="votebtn">▲</span>
          <a href="${commentUrl}"><strong>${by}</strong></a>
          <a href="${commentUrl}">${time}</a>
          <span class="toggle" style="margin-left:6px;">[–]</span>
        </div>
        <div class="comment-body">${body}</div>
      </div>
    `;

    const toggle = container.querySelector('.toggle');
    toggle.addEventListener('click', (e) => {
      e.preventDefault();
      const bodyEl = container.querySelector('.comment-body');
      const visible = bodyEl.style.display !== 'none';
      bodyEl.style.display = visible ? 'none' : 'block';
      toggle.textContent = visible ? '[+]' : '[–]';
    });

    const replies = comment.replies || [];
    replies.forEach(reply => {
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
