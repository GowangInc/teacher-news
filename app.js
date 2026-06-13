(function () {
  'use strict';

  const { escapeHtml, formatTime, hostname, hnItemUrl } = window.TN;
  const storiesTable = document.getElementById('stories');

  function getPageFromUrl() {
    const params = new URLSearchParams(window.location.search);
    return parseInt(params.get('p'), 10) || 1;
  }

  function dataUrlForPage(page) {
    return page === 1 ? 'data.json?_=' + Date.now() : 'data-p' + page + '.json?_=' + Date.now();
  }

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

  function addMoreLink(currentPage, totalPages) {
    if (currentPage >= totalPages) return;
    // Don't add if there's already a More link
    if (storiesTable.querySelector('.more-link')) return;
    const nextPage = currentPage + 1;
    const spacer = document.createElement('tr');
    spacer.style.height = '10px';
    storiesTable.appendChild(spacer);

    const row = document.createElement('tr');
    row.innerHTML = `
      <td colspan="3" class="more-link">
        <a href="?p=${nextPage}">More</a>
      </td>
    `;
    storiesTable.appendChild(row);
  }

  function addPrevLink(currentPage) {
    if (currentPage <= 1) return;
    const spacer = document.createElement('tr');
    spacer.style.height = '10px';
    storiesTable.appendChild(spacer);

    const row = document.createElement('tr');
    row.innerHTML = `
      <td colspan="3" class="more-link">
        <a href="?p=${currentPage - 1}">&lt; Previous</a>
        &nbsp;|&nbsp;
        <a href="?p=1">Front Page</a>
      </td>
    `;
    storiesTable.appendChild(row);
  }

  function showError(msg) {
    const row = document.createElement('tr');
    row.innerHTML = `<td colspan="3" class="error">${escapeHtml(msg)}</td>`;
    storiesTable.appendChild(row);
  }

  const STORIES_PER_PAGE = 30;

  async function init() {
    const page = getPageFromUrl();
    const dataUrl = dataUrlForPage(page);

    // Clear pre-rendered content if we're not on page 1
    if (page !== 1 && storiesTable.querySelector('.story-row')) {
      storiesTable.innerHTML = '';
    }

    // For page 1 with pre-rendered content, load full 30 stories from JSON
    if (page === 1 && storiesTable.querySelector('.story-row')) {
      // Clear pre-rendered content and load fresh
      storiesTable.innerHTML = '';
    }

    try {
      const resp = await fetch(dataUrl);
      if (!resp.ok) {
        if (page > 1) {
          showError('Page ' + page + ' not found. <a href="?p=1">Back to front page</a>');
        } else {
          throw new Error('HTTP ' + resp.status);
        }
        return;
      }
      const data = await resp.json();
      const stories = data.stories || [];

      // Calculate starting rank for this page
      const startRank = (page - 1) * STORIES_PER_PAGE + 1;

      stories.forEach((story, idx) => renderStory(story, startRank + idx - 1));

      const totalPages = data.total_pages || page + 1;
      
      addPrevLink(page);
      addMoreLink(page, totalPages);
    } catch (err) {
      showError('Could not load stories: ' + err.message);
      console.error(err);
    }
  }

  init();
})();
