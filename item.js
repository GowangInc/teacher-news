(function () {
  'use strict';

  const { escapeHtml, formatTime, hostname, hnItemUrl, renderComment } = window.TN;
  const params = new URLSearchParams(window.location.search);
  const storyId = parseInt(params.get('id'), 10);

  function showError(msg) {
    const header = document.getElementById('story-header');
    header.innerHTML = `<tr><td colspan="3" class="error">${escapeHtml(msg)}</td></tr>`;
  }

  function renderHeader(story) {
    const header = document.getElementById('story-header');
    const domain = hostname(story.url);
    const domainHtml = domain
      ? ` <span class="sitestr">(${escapeHtml(domain)})</span>`
      : '';
    const time = formatTime(story.time);
    const storyUrl = hnItemUrl(story.id);

    header.innerHTML = `
      <tr class="story-row">
        <td valign="top" class="votelinks">
          <div class="votebtn" data-id="${story.id}" title="upvote">▲</div>
        </td>
        <td class="titleline">
          <a href="${storyUrl}">${escapeHtml(story.title)}</a>${domainHtml}
        </td>
      </tr>
      <tr>
        <td colspan="2"></td>
        <td class="subline">
          <span id="score-${story.id}" data-score="${story.score || 0}">${story.score || 0} points</span>
          by <a href="${storyUrl}">${escapeHtml(story.by || 'teacher')}</a>
          <a href="${storyUrl}">${time}</a>
          | <a href="${escapeHtml(story.original_url || story.url || '#')}" title="Original article: ${escapeHtml(story.original_title || story.title)}">source article</a>
        </td>
      </tr>
    `;

    const voteBtn = header.querySelector('.votebtn');
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
  }

  function renderComments(story) {
    const container = document.getElementById('comments');
    const comments = story.comments || [];
    if (comments.length === 0) {
      container.innerHTML = '<div class="comment">No comments yet.</div>';
      return;
    }
    comments.forEach(comment => {
      container.appendChild(renderComment(story.id, comment, 0));
    });
  }

  async function init() {
    if (!storyId) {
      showError('Missing story id.');
      return;
    }
    try {
      const resp = await fetch('data.json?_=' + Date.now());
      if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
      const data = await resp.json();
      const story = (data.stories || []).find(s => s.id === storyId);
      if (!story) {
        showError('Story not found.');
        return;
      }
      renderHeader(story);
      renderComments(story);
    } catch (err) {
      showError('Could not load story: ' + err.message);
      console.error(err);
    }
  }

  init();
})();
