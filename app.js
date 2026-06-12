(function () {
  'use strict';

  const { escapeHtml, formatTime, hostname, hnItemUrl } = window.TN;
  const storiesTable = document.getElementById('stories');

  function renderStory(story, index) {
    const rank = index + 1;
    const domain = hostname(story.url);
    const domainHtml = domain
      ? ` <span class="sitestr">(${escapeHtml(domain)})</span>`
      : '';
    const commentsCount = story.comment_count || (story.comments || []).length;
    const time = formatTime(story.time);
    const storyUrl = hnItemUrl(story.id);
    const itemPage = `item.html?id=${story.id}`;

    const storyRow = document.createElement('tr');
    storyRow.className = 'story-row';
    storyRow.innerHTML = `
      <td align="right" valign="top" class="rank">${rank}.</td>
      <td valign="top" class="votelinks">
        <div class="votebtn" data-id="${story.id}" title="upvote">▲</div>
      </td>
      <td class="titleline">
        <a href="${storyUrl}">${escapeHtml(story.title)}</a>${domainHtml}
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
        by <a href="${storyUrl}">${escapeHtml(story.by || 'teacher')}</a>
        <a href="${storyUrl}">${time}</a>
        | <a href="${itemPage}">${commentsCount} comments</a>
        | <a href="${escapeHtml(story.original_url || story.url || '#')}" title="Original article: ${escapeHtml(story.original_title || story.title)}">source article</a>
      </td>
    `;

    storiesTable.appendChild(storyRow);
    storiesTable.appendChild(subRow);

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
