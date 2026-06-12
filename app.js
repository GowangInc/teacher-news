(function () {
  'use strict';

  const storiesTable = document.getElementById('stories');

  function escapeHtml(str) {
    return String(str)
      .replace(/&/g, '&amp;')
      .replace(/</g, '&lt;')
      .replace(/>/g, '&gt;')
      .replace(/"/g, '&quot;');
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

  function textToHtml(text) {
    if (!text) return '';
    // Escape HTML, then split paragraphs on blank lines and wrap in <p>.
    const escaped = escapeHtml(text);
    const paragraphs = escaped.split(/\n\s*\n/).filter(p => p.trim());
    if (paragraphs.length === 0) return '';
    return paragraphs
      .map(p => '<p>' + p.replace(/\n/g, '<br>') + '</p>')
      .join('');
  }

  function renderComment(comment, depth) {
    const container = document.createElement('div');
    container.className = 'nested-comment';
    container.style.marginLeft = depth > 0 ? '40px' : '0';

    const by = escapeHtml(comment.by || 'teacher');
    const time = formatTime(comment.time);
    const body = textToHtml(comment.text);

    container.innerHTML = `
      <div class="comment">
        <div class="comment-meta">
          <span class="votebtn">▲</span>
          <a href="#"><strong>${by}</strong></a> ${time}
          <span class="toggle" style="margin-left:6px;">[–]</span>
        </div>
        <div class="comment-body">${body}</div>
      </div>
    `;

    const toggle = container.querySelector('.toggle');
    toggle.addEventListener('click', (e) => {
      e.preventDefault();
      const body = container.querySelector('.comment-body');
      const visible = body.style.display !== 'none';
      body.style.display = visible ? 'none' : 'block';
      toggle.textContent = visible ? '[+]' : '[–]';
    });

    const replies = comment.replies || [];
    replies.forEach(reply => {
      container.appendChild(renderComment(reply, depth + 1));
    });

    return container;
  }

  function renderStory(story, index) {
    const rank = index + 1;
    const domain = hostname(story.url);
    const domainHtml = domain ? ` (<span class="sitestr"><a href="${escapeHtml(story.url)}">${escapeHtml(domain)}</a></span>)` : '';
    const commentsCount = story.comment_count || (story.comments || []).length;
    const time = formatTime(story.time);

    const storyRow = document.createElement('tr');
    storyRow.className = 'story-row';
    storyRow.innerHTML = `
      <td align="right" valign="top" class="rank">${rank}.</td>
      <td valign="top" class="votelinks">
        <div class="votebtn" data-id="${story.id}" title="upvote">▲</div>
      </td>
      <td class="titleline">
        <a href="${escapeHtml(story.url || '#')}">${escapeHtml(story.title)}</a>${domainHtml}
      </td>
    `;

    const voteBtn = storyRow.querySelector('.votebtn');
    voteBtn.addEventListener('click', () => {
      voteBtn.classList.toggle('upvoted');
      const upvoted = voteBtn.classList.contains('upvoted');
      voteBtn.title = upvoted ? 'upvoted' : 'upvote';
      const scoreSpan = document.getElementById(`score-${story.id}`);
      if (scoreSpan) {
        const baseScore = parseInt(scoreSpan.dataset.score, 10);
        scoreSpan.textContent = (baseScore + (upvoted ? 1 : 0)) + ' points';
      }
    });

    const subRow = document.createElement('tr');
    subRow.innerHTML = `
      <td colspan="2"></td>
      <td class="subline">
        <span id="score-${story.id}" data-score="${story.score || 0}">${story.score || 0} points</span>
        by <a href="#">${escapeHtml(story.by || 'teacher')}</a>
        ${time}
        | <a href="#" class="comments-toggle" data-id="${story.id}">${commentsCount} comments</a>
        | <a href="${escapeHtml(story.original_url || story.url || '#')}" title="Original: ${escapeHtml(story.original_title || story.title)}">original</a>
      </td>
    `;

    const commentRow = document.createElement('tr');
    commentRow.className = 'comment-row';
    commentRow.id = `comments-${story.id}`;
    commentRow.innerHTML = '<td colspan="2"></td><td class="comment-cell"></td>';
    const commentCell = commentRow.querySelector('.comment-cell');

    const comments = story.comments || [];
    comments.forEach(comment => {
      commentCell.appendChild(renderComment(comment, 0));
    });

    subRow.querySelector('.comments-toggle').addEventListener('click', (e) => {
      e.preventDefault();
      commentRow.classList.toggle('expanded');
    });

    storiesTable.appendChild(storyRow);
    storiesTable.appendChild(subRow);
    storiesTable.appendChild(commentRow);

    const spacer = document.createElement('tr');
    spacer.style.height = '5px';
    storiesTable.appendChild(spacer);
  }

  function showError(msg) {
    const row = document.createElement('tr');
    row.innerHTML = `<td colspan="3" class="error">${escapeHtml(msg)}</td>`;
    storiesTable.appendChild(row);
  }

  async function init() {
    try {
      const resp = await fetch('data.json');
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      (data.stories || []).forEach(renderStory);
    } catch (err) {
      showError('Could not load stories: ' + err.message);
      console.error(err);
    }
  }

  init();
})();
